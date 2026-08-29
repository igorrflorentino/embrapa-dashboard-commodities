"""Two-phase Bronze pipeline for the PEVS SILVICULTURE half (SIDRA 291).

Sibling of test_pam_pipeline: the module reuses the same generic SIDRA client and Bronze
primitives, so what needs pinning is not the plumbing but the things that make THIS half
different — the table/classification it queries, the raw-zone segment that keeps it from
colliding with the extraction half's archives, and the product-code column its delta guard
joins on.
"""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from embrapa_dashboard.config import Settings
from embrapa_dashboard.ibge import silvicultura_pipeline


@pytest.fixture(autouse=True)
def _all_products_present():
    """Default: every configured product already has Bronze rows, so ``_delta_start_year``
    takes the normal delta path (the missing-product branch has its own test)."""
    with patch(
        "embrapa_dashboard.ibge.silvicultura_pipeline.bronze_products_present",
        side_effect=lambda *a, **k: set(a[3]),
    ):
        yield


@pytest.fixture
def settings() -> Settings:
    return Settings(
        gcp_project_id="test-project",
        gcs_bucket="test-bucket",
        silvicultura_start_year=2020,
        silvicultura_end_year=2020,
        silvicultura_product_codes="3457",
        _env_file=None,
    )  # type: ignore[call-arg]


@pytest.fixture
def sidra_df() -> pd.DataFrame:
    """t291-shaped frame mimicking `fetch_sidra_dataframe` output."""
    return pd.DataFrame(
        {
            "municipio_codigo": ["3550308", "3509502"],
            "municipio": ["São Paulo - SP", "Campinas - SP"],
            "ano": ["2020", "2020"],
            "variavel_codigo": ["143", "143"],
            "variavel": ["Valor da produção", "Valor da produção"],
            "tipo_de_produto_da_silvicultura_codigo": ["3457", "3457"],
            "tipo_de_produto_da_silvicultura": ["1.3 - Madeira em tora", "1.3 - Madeira em tora"],
            "unidade_de_medida": ["Mil Reais", "Mil Reais"],
            "valor": ["100", "200"],
        }
    )


def _run(settings, sidra_df, **kw):
    """Drive run() with every I/O boundary patched; returns (destination, mocks)."""
    with (
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.fetch_sidra_dataframe") as fetch,
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.storage.Client"),
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.bigquery.Client"),
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.ensure_dataset"),
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.land_raw") as land_raw,
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.read_raw") as read_raw,
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.load_dataframe") as load,
        patch(
            "embrapa_dashboard.ibge.silvicultura_pipeline.latest_reference_year",
            return_value=kw.pop("latest_year", None),
        ),
    ):
        fetch.return_value = sidra_df
        read_raw.return_value = sidra_df.astype(str)
        destination = silvicultura_pipeline.run(settings, **kw)
    return destination, {"fetch": fetch, "land_raw": land_raw, "load": load}


def test_run_queries_t291_and_loads_to_its_own_bronze_table(settings, sidra_df) -> None:
    destination, m = _run(settings, sidra_df)

    assert destination == (
        f"{settings.gcp_project_id}.{settings.bq_bronze_ibge_dataset}"
        f".{settings.bq_bronze_silvicultura_table}"
    )
    kw = m["fetch"].call_args.kwargs
    assert kw["table_id"] == "291"
    assert kw["classification"] == "194"
    assert kw["products"] == ["3457"]
    assert kw["geo_level"] == "n6"
    # Quantity AND value. Dropping 143 would ingest cleanly and null out the value column
    # for origem='silvicultura' — half a Gold column empty, with no error anywhere.
    assert set(kw["variables"].split(",")) == {"142", "143"}

    load_kw = m["load"].call_args.kwargs
    assert load_kw["clustering_fields"] == ["municipio_codigo", "ano", "variavel_codigo"]


def test_the_raw_segment_is_isolated_from_the_extraction_half(settings, sidra_df) -> None:
    """Both halves are source='ibge'; only the DATASET segment separates their archives.

    Share it and a `--from-raw` replay of one half would rebuild its Bronze from the
    other's payload — different product codes, different variables, silently wrong.
    """
    _, m = _run(settings, sidra_df)
    kw = m["land_raw"].call_args.kwargs
    assert kw["source"] == "ibge"
    assert kw["dataset"] == "silvicultura"
    assert kw["basename"] == "products_3457_2020_2020"
    assert kw["provenance"]["table_id"] == "291"


def test_the_delta_guard_joins_on_the_silviculture_product_column(settings, sidra_df) -> None:
    """The Bronze column name is derived by the client from SIDRA's header, and the
    missing-product backfill guard joins on it. A wrong name would not error — it would
    silently report every product as present and disable the guard."""
    with (
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.fetch_sidra_dataframe") as fetch,
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.storage.Client"),
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.bigquery.Client"),
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.ensure_dataset"),
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.land_raw"),
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.read_raw") as read_raw,
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.load_dataframe"),
        patch(
            "embrapa_dashboard.ibge.silvicultura_pipeline.latest_reference_year", return_value=2019
        ),
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.bronze_products_present") as present,
    ):
        fetch.return_value = sidra_df
        read_raw.return_value = sidra_df.astype(str)
        present.return_value = {"3457"}
        silvicultura_pipeline.run(settings)

    assert present.call_args.args[2] == "tipo_de_produto_da_silvicultura_codigo"
    assert present.call_args.args[2] in sidra_df.columns


def test_delta_rewinds_to_the_recent_window(settings, sidra_df) -> None:
    settings.silvicultura_end_year = 2024
    settings.silvicultura_delta_overlap_years = 1
    _, m = _run(settings, sidra_df, latest_year=2023)
    assert m["fetch"].call_args.kwargs["start_year"] == 2022


def test_delta_is_a_clean_noop_when_bronze_is_already_current(settings, sidra_df) -> None:
    """Bronze at/past the end year: nothing to fetch. Returning '' rather than fetching an
    INVERTED (start > end) window, which SIDRA answers with an empty payload."""
    destination, m = _run(settings, sidra_df, latest_year=2024)
    assert destination == ""
    m["fetch"].assert_not_called()


def test_full_bypasses_the_delta_window(settings, sidra_df) -> None:
    settings.silvicultura_end_year = 2024
    _, m = _run(settings, sidra_df, full=True, latest_year=2023)
    assert m["fetch"].call_args.kwargs["start_year"] == 2020  # the configured floor


def test_a_product_absent_from_bronze_forces_a_full_window_backfill(settings, sidra_df) -> None:
    """A newly added product has no Bronze rows, so the table-global delta window would
    start it at last_year - overlap and silently truncate its history."""
    settings.silvicultura_end_year = 2024
    with (
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.fetch_sidra_dataframe") as fetch,
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.storage.Client"),
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.bigquery.Client"),
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.ensure_dataset"),
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.land_raw"),
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.read_raw") as read_raw,
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.load_dataframe"),
        patch(
            "embrapa_dashboard.ibge.silvicultura_pipeline.latest_reference_year", return_value=2023
        ),
        patch(
            "embrapa_dashboard.ibge.silvicultura_pipeline.bronze_products_present",
            return_value=set(),  # nothing present → the new-product branch
        ),
    ):
        fetch.return_value = sidra_df
        read_raw.return_value = sidra_df.astype(str)
        silvicultura_pipeline.run(settings)

    assert fetch.call_args.kwargs["start_year"] == 2020  # full window, not 2022


def test_an_empty_sidra_response_is_skipped_rather_than_archived(settings) -> None:
    """SIDRA with nothing to give (end year ahead of the latest published) must not land an
    empty archive or an empty Bronze append."""
    with (
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.fetch_sidra_dataframe") as fetch,
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.storage.Client"),
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.bigquery.Client"),
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.ensure_dataset"),
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.land_raw") as land_raw,
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.load_dataframe") as load,
        patch(
            "embrapa_dashboard.ibge.silvicultura_pipeline.latest_reference_year", return_value=None
        ),
    ):
        fetch.return_value = pd.DataFrame()
        destination = silvicultura_pipeline.run(settings)

    assert destination == ""
    land_raw.assert_not_called()
    load.assert_not_called()


def test_from_raw_replays_the_archive_without_querying_sidra(settings, sidra_df) -> None:
    with (
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.fetch_sidra_dataframe") as fetch,
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.storage.Client"),
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.bigquery.Client"),
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.ensure_dataset"),
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.list_raw", return_value=["a", "b"]),
        patch(
            "embrapa_dashboard.ibge.silvicultura_pipeline._order_by_fetched_at",
            return_value=["b", "a"],
        ) as order,
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.read_raw") as read_raw,
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.load_dataframe") as load,
    ):
        read_raw.return_value = sidra_df.astype(str)
        silvicultura_pipeline.run(settings, from_raw=True)

    fetch.assert_not_called()
    order.assert_called_once()  # oldest-fetch-first, so the newest extract wins dedup
    assert load.call_count == 2


def test_from_raw_with_no_archive_is_a_clean_noop(settings) -> None:
    with (
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.storage.Client"),
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.bigquery.Client"),
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.ensure_dataset"),
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.list_raw", return_value=[]),
        patch("embrapa_dashboard.ibge.silvicultura_pipeline.load_dataframe") as load,
    ):
        assert silvicultura_pipeline.run(settings, from_raw=True) == ""
    load.assert_not_called()


def test_product_codes_resolve_the_catalog_scoped_to_t291(settings, monkeypatch) -> None:
    """This ingest MUST scope its catalog read to its own SIDRA table.

    The 'pevs' token holds BOTH halves, so resolving it bare would query the SILVICULTURE
    table with EXTRACTION codes — SIDRA answers empty and the run reports a clean no-op,
    the worst kind of wrong. Until 2026-08-29 the guard was to skip the catalog entirely
    (the entries carried no table tag); now they do, so the guard is the SCOPE."""
    visto = {}

    def _fake(cfg, banco, *, env_fallback, sidra_tabela=None, bq_client=None):
        visto.update(banco=banco, sidra_tabela=sidra_tabela, env_fallback=env_fallback)
        return ["3455", "3456", "3457"]

    monkeypatch.setattr(silvicultura_pipeline.catalog_resolver, "resolve_product_codes", _fake)

    assert silvicultura_pipeline._product_codes(settings) == ["3455", "3456", "3457"]
    assert visto["banco"] == "pevs"
    # The scope is the whole guard: a None here would hand t291 the extraction codes.
    assert visto["sidra_tabela"] == settings.silvicultura_table_id
    assert visto["env_fallback"] == settings.silvicultura_product_codes_list


def test_bronze_shares_the_ibge_dataset_with_the_extraction_half(settings) -> None:
    """One survey, one dataset — separate TABLES. Doctor's BRONZE_TARGETS pairs them."""
    fqn = silvicultura_pipeline._bronze_fqn(settings)
    assert fqn.endswith(".bronze_ibge.sidra_t291_raw")
