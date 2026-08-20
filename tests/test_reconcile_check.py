"""Tests for the reconcile evidence check.

The point of the module is to answer "did anything OLD change?" honestly, so these tests
care most about the ways it could answer WRONGLY: missing a real divergence, inventing
one, or quietly comparing the wrong things.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from typer.testing import CliRunner

from embrapa_dashboard import reconcile_check
from embrapa_dashboard.cli import app

runner = CliRunner()


def _settings() -> MagicMock:
    s = MagicMock()
    s.gcp_project_id = "proj"
    s.bq_bronze_ibge_dataset = "bronze_ibge"
    s.bq_bronze_bcb_dataset = "bronze_bcb"
    s.ibge_table_id = "289"
    s.ibge_classification_id = "194"
    s.ibge_product_codes = "3405,3435"
    s.bcb_start_year = 1995
    s.bcb_end_year = 2026
    s.bcb_inflation_series_ipca_code = "433"
    return s


def _client(rows: list[dict]) -> MagicMock:
    client = MagicMock()
    client.query.return_value.result.return_value = rows
    return client


# ── SourceCheck.clean ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("diverged", "only_source", "only_bronze", "clean"),
    [(0, 0, 0, True), (1, 0, 0, False), (0, 1, 0, False), (0, 0, 1, False)],
)
def test_clean_requires_all_three_counters_at_zero(diverged, only_source, only_bronze, clean):
    # A row appearing or disappearing is as much a revision as a value changing, so
    # `clean` must not key off `diverged` alone.
    check = reconcile_check.SourceCheck("x", "y", 10, diverged, only_source, only_bronze)
    assert check.clean is clean


# ── the BCB date filter ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "cutoff", "expected"),
    [
        ("31/12/2024", "2025-01-01", True),
        ("01/01/2025", "2025-01-01", False),  # boundary is exclusive
        ("02/01/2025", "2025-01-01", False),
        ("01/02/2024", "2025-01-01", True),  # dd/mm, not mm/dd
        ("2024-12-31", "2025-01-01", False),  # already ISO ⇒ not the expected shape
        ("lixo", "2025-01-01", False),
    ],
)
def test_is_before_parses_bcb_dates(value, cutoff, expected):
    assert reconcile_check._is_before(value, cutoff) is expected


# ── IBGE PEVS ────────────────────────────────────────────────────────────────


def test_ibge_reports_no_divergence_when_source_matches_bronze():
    cells = {("1500107", "144", "3405"): "100"}
    with (
        patch.object(reconcile_check, "_live_pevs_cells", return_value=cells),
        patch.object(reconcile_check, "_bronze_pevs_cells", return_value=dict(cells)),
    ):
        out = reconcile_check.check_ibge_pevs(MagicMock(), _settings(), (2015,), "15")
    assert (out.compared, out.diverged, out.only_source, out.only_bronze) == (1, 0, 0, 0)
    assert out.clean


def test_ibge_flags_a_changed_value_and_records_it():
    live = {("1500107", "144", "3405"): "999"}
    bronze = {("1500107", "144", "3405"): "100"}
    with (
        patch.object(reconcile_check, "_live_pevs_cells", return_value=live),
        patch.object(reconcile_check, "_bronze_pevs_cells", return_value=bronze),
    ):
        out = reconcile_check.check_ibge_pevs(MagicMock(), _settings(), (2015,), "15")
    assert (out.compared, out.diverged) == (1, 1)
    assert not out.clean
    assert "fonte=999" in out.samples[0] and "bronze=100" in out.samples[0]


def test_ibge_counts_added_and_removed_cells_separately():
    # A municipality that only the source has is a NEW row; one only Bronze has was
    # withdrawn. Neither is a value change, and both matter.
    live = {("1500107", "144", "3405"): "1", ("1500200", "144", "3405"): "2"}
    bronze = {("1500107", "144", "3405"): "1", ("1500300", "144", "3405"): "3"}
    with (
        patch.object(reconcile_check, "_live_pevs_cells", return_value=live),
        patch.object(reconcile_check, "_bronze_pevs_cells", return_value=bronze),
    ):
        out = reconcile_check.check_ibge_pevs(MagicMock(), _settings(), (2015,), "15")
    assert (out.compared, out.diverged, out.only_source, out.only_bronze) == (1, 0, 1, 1)


def test_ibge_caps_the_recorded_samples():
    live = {(f"15001{i:02d}", "144", "3405"): "9" for i in range(12)}
    bronze = {k: "1" for k in live}
    with (
        patch.object(reconcile_check, "_live_pevs_cells", return_value=live),
        patch.object(reconcile_check, "_bronze_pevs_cells", return_value=bronze),
    ):
        out = reconcile_check.check_ibge_pevs(MagicMock(), _settings(), (2015,), "15")
    assert out.diverged == 12
    assert len(out.samples) == 5  # the count is complete; the printout stays readable


def test_bronze_pevs_query_is_scoped_and_parameterised():
    client = _client(
        [
            {
                "municipio_codigo": "1500107",
                "variavel_codigo": "144",
                "tipo_de_produto_extrativo_codigo": "3405",
                "valor": "100",
            }
        ]
    )
    out = reconcile_check._bronze_pevs_cells(client, _settings(), 2015, "15")
    assert out == {("1500107", "144", "3405"): "100"}
    sql = client.query.call_args[0][0]
    # Latest-ingestion-wins, or the check would compare against a superseded row.
    assert "ingestion_timestamp DESC" in sql
    params = {p.name: p.value for p in client.query.call_args[1]["job_config"].query_parameters}
    assert params == {"year": "2015", "uf": "15"}


def test_live_pevs_matches_the_product_column_structurally_and_filters_by_uf():
    # SIDRA has renamed this header before; the module must find it by shape. The frame
    # also carries a município from another state, which must not enter the comparison.
    frame = pd.DataFrame(
        [
            {
                "municipio_codigo": "1500107",
                "variavel_codigo": "144",
                "algum_nome_novo_codigo": "3405",
                "valor": "100",
                "unidade_de_medida_codigo": "1",
            },
            {
                "municipio_codigo": "3500107",
                "variavel_codigo": "144",
                "algum_nome_novo_codigo": "3405",
                "valor": "7",
                "unidade_de_medida_codigo": "1",
            },
        ]
    )
    with patch("embrapa_dashboard.ibge.client.fetch_sidra_dataframe", return_value=frame):
        out = reconcile_check._live_pevs_cells(_settings(), 2015, "15")
    assert out == {("1500107", "144", "3405"): "100"}


# ── BCB ──────────────────────────────────────────────────────────────────────


def _bcb_frame(pairs):
    return pd.DataFrame([{"data": d, "valor": v} for d, v in pairs])


def test_bcb_compares_only_points_older_than_the_cutoff():
    live = _bcb_frame([("31/12/2024", "1.0"), ("15/06/2025", "2.0")])
    client = _client(
        [
            {"reference_date_str": "31/12/2024", "value_str": "1.0"},
            {"reference_date_str": "15/06/2025", "value_str": "SOMETHING ELSE"},
        ]
    )
    with patch("embrapa_dashboard.bcb.client.fetch_series", return_value=live):
        out = reconcile_check.check_bcb_series(
            client, _settings(), "433", "IPCA", "inflation_series_raw", "2025-01-01"
        )
    # The 2025 point differs, but it is INSIDE the nightly's rewind window — the nightly
    # already re-fetches it, so counting it here would raise a false reconcile alarm.
    assert (out.compared, out.diverged) == (1, 0)
    assert out.clean


def test_bcb_flags_a_revised_old_point():
    live = _bcb_frame([("31/12/2024", "9.99")])
    client = _client([{"reference_date_str": "31/12/2024", "value_str": "1.0"}])
    with patch("embrapa_dashboard.bcb.client.fetch_series", return_value=live):
        out = reconcile_check.check_bcb_series(
            client, _settings(), "433", "IPCA", "inflation_series_raw", "2025-01-01"
        )
    assert (out.compared, out.diverged) == (1, 1)
    assert not out.clean and "fonte=9.99" in out.samples[0]


def test_bcb_counts_a_point_the_source_no_longer_serves():
    live = _bcb_frame([("30/12/2024", "1.0")])
    client = _client([{"reference_date_str": "31/12/2024", "value_str": "1.0"}])
    with patch("embrapa_dashboard.bcb.client.fetch_series", return_value=live):
        out = reconcile_check.check_bcb_series(
            client, _settings(), "433", "IPCA", "inflation_series_raw", "2025-01-01"
        )
    assert (out.compared, out.only_bronze) == (0, 1)
    assert not out.clean


def test_bcb_caps_the_recorded_samples():
    dates = [f"{d:02d}/01/2024" for d in range(1, 9)]
    live = _bcb_frame([(d, "9") for d in dates])
    client = _client([{"reference_date_str": d, "value_str": "1"} for d in dates])
    with patch("embrapa_dashboard.bcb.client.fetch_series", return_value=live):
        out = reconcile_check.check_bcb_series(
            client, _settings(), "433", "IPCA", "inflation_series_raw", "2025-01-01"
        )
    assert out.diverged == 8
    assert len(out.samples) == 5


# ── the CLI command ──────────────────────────────────────────────────────────


def _clean(*_a, **_k):
    return reconcile_check.SourceCheck("fonte", "escopo", compared=10)


def _dirty(*_a, **_k):
    return reconcile_check.SourceCheck(
        "fonte", "escopo", compared=10, diverged=2, samples=["2015 x: fonte=9 bronze=1"]
    )


def test_cli_exits_zero_and_says_no_reconcile_needed_when_clean():
    with (
        patch("embrapa_dashboard.cli.get_settings", return_value=_settings()),
        patch("embrapa_dashboard.cli.bigquery.Client"),
        patch.object(reconcile_check, "check_ibge_pevs", _clean),
        patch.object(reconcile_check, "check_bcb_series", _clean),
    ):
        result = runner.invoke(app, ["reconcile-check"])
    assert result.exit_code == 0
    assert "não é necessário" in result.stdout


def test_cli_exits_one_and_surfaces_samples_when_a_revision_is_found():
    # The non-zero exit is the contract a scheduled workflow would gate on.
    with (
        patch("embrapa_dashboard.cli.get_settings", return_value=_settings()),
        patch("embrapa_dashboard.cli.bigquery.Client"),
        patch.object(reconcile_check, "check_ibge_pevs", _dirty),
        patch.object(reconcile_check, "check_bcb_series", _dirty),
    ):
        result = runner.invoke(app, ["reconcile-check"])
    assert result.exit_code == 1
    assert "Revisão detectada" in result.stdout


def test_cli_forwards_the_sampling_options():
    seen = {}

    def spy(_client, _settings, years, uf):
        seen["years"], seen["uf"] = years, uf
        return _clean()

    with (
        patch("embrapa_dashboard.cli.get_settings", return_value=_settings()),
        patch("embrapa_dashboard.cli.bigquery.Client"),
        patch.object(reconcile_check, "check_ibge_pevs", spy),
        patch.object(reconcile_check, "check_bcb_series", _clean),
    ):
        result = runner.invoke(app, ["reconcile-check", "--years", "2001,2002", "--uf", "35"])
    assert result.exit_code == 0
    assert seen == {"years": (2001, 2002), "uf": "35"}
