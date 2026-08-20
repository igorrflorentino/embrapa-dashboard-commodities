"""Evidence for the monthly "do we need a `reconcile`?" question.

`reconcile` exists because IBGE and BCB ingestion is DELTA: the nightly run only
re-queries a small recent window, so a correction the source publishes to an OLD year is
never picked up. The monthly reminder issue asks an operator to decide whether that has
happened — and, until now, offered no way to find out, on the reasoning that checking an
old year costs about as much as re-fetching it.

That is true of the whole history. It is NOT true of a well-chosen sample, and for BCB it
is not true at all: the SGS API returns an entire series in one request, so that half of
the check is exhaustive rather than sampled.

What this module does NOT do: fix anything. It only answers "did anything old change?"
with a number. A non-zero answer is the operator's cue to run `embrapa ingest reconcile`.

COMEX is deliberately out of scope: its per-file ETag check already re-detects a revision
to any year on every nightly run, so `reconcile` adds nothing for it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from google.cloud import bigquery

from .config import Settings

# Pará — the largest PEVS producer, so the sample carries the most non-null cells per
# request. A state with few producing municipalities would compare mostly absences.
DEFAULT_SAMPLE_UF = "15"
# Years comfortably outside the delta window (overlap defaults to 1), spread across the
# series rather than clustered, so a revision campaign touching one era is still visible.
DEFAULT_SAMPLE_YEARS = (2015, 2019, 2022)


@dataclass
class SourceCheck:
    """One source's answer to "did anything old change?"."""

    source: str
    detail: str
    compared: int = 0
    diverged: int = 0
    only_source: int = 0
    only_bronze: int = 0
    samples: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return self.diverged == 0 and self.only_source == 0 and self.only_bronze == 0


def _bronze_pevs_cells(
    client: bigquery.Client, settings: Settings, year: int, uf: str
) -> dict[tuple[str, str, str], str]:
    """Latest-ingestion Bronze cells for one year × UF, keyed by natural key."""
    query = f"""
      SELECT municipio_codigo, variavel_codigo, tipo_de_produto_extrativo_codigo, valor
      FROM `{settings.gcp_project_id}.{settings.bq_bronze_ibge_dataset}.sidra_t289_raw`
      WHERE ano = @year AND SUBSTR(municipio_codigo, 1, 2) = @uf
      QUALIFY ROW_NUMBER() OVER (
        PARTITION BY municipio_codigo, variavel_codigo, tipo_de_produto_extrativo_codigo
        ORDER BY ingestion_timestamp DESC) = 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("year", "STRING", str(year)),
            bigquery.ScalarQueryParameter("uf", "STRING", uf),
        ]
    )
    rows = client.query(query, job_config=job_config).result()
    return {
        (
            str(r["municipio_codigo"]),
            str(r["variavel_codigo"]),
            str(r["tipo_de_produto_extrativo_codigo"]),
        ): str(r["valor"])
        for r in rows
    }


def _live_pevs_cells(settings: Settings, year: int, uf: str) -> dict[tuple[str, str, str], str]:
    """The same slice, fetched live from SIDRA at the grain we store (n6)."""
    from .ibge.client import fetch_sidra_dataframe

    frame = fetch_sidra_dataframe(
        table_id=settings.ibge_table_id,
        start_year=year,
        end_year=year,
        classification=settings.ibge_classification_id,
        products=settings.ibge_product_codes.split(","),
        geo_level="n6",
        variables="all",
    )
    columns = {c.lower(): c for c in frame.columns}
    geo = next(c for k, c in columns.items() if "municipio" in k and k.endswith("_codigo"))
    var = next(c for k, c in columns.items() if k.startswith("variavel") and k.endswith("_codigo"))
    # SIDRA has renamed this classification header before, so match it structurally
    # (the one *_codigo that is none of the fixed dimensions) instead of hardcoding.
    fixed = ("municipio", "variavel", "ano", "nivel_territorial", "unidade")
    prod = next(
        c
        for k, c in columns.items()
        if k.endswith("_codigo") and not any(k.startswith(f) for f in fixed)
    )
    value = columns["valor"]
    cells = {}
    for _, row in frame.iterrows():
        code = str(row[geo])
        if not code.startswith(uf):
            continue
        cells[(code, str(row[var]), str(row[prod]))] = str(row[value])
    return cells


def check_ibge_pevs(
    client: bigquery.Client,
    settings: Settings,
    years: tuple[int, ...] = DEFAULT_SAMPLE_YEARS,
    uf: str = DEFAULT_SAMPLE_UF,
) -> SourceCheck:
    """Compare live SIDRA against Bronze CELL BY CELL, at the grain we store.

    Deliberately not a national-total comparison: IBGE suppresses small municipal cells
    for confidentiality, so an aggregate would differ for reasons that are not revisions.
    """
    result = SourceCheck("IBGE PEVS", f"n6 · UF {uf} · anos {', '.join(map(str, years))}")
    for year in years:
        live = _live_pevs_cells(settings, year, uf)
        bronze = _bronze_pevs_cells(client, settings, year, uf)
        for key, live_value in live.items():
            if key not in bronze:
                result.only_source += 1
                continue
            result.compared += 1
            if live_value != bronze[key]:
                result.diverged += 1
                if len(result.samples) < 5:
                    result.samples.append(f"{year} {key}: fonte={live_value} bronze={bronze[key]}")
        result.only_bronze += sum(1 for key in bronze if key not in live)
    return result


def _is_before(date_str: str, cutoff: str) -> bool:
    """True when a dd/mm/yyyy BCB date falls before an ISO cutoff."""
    parts = date_str.split("/")
    if len(parts) != 3:
        return False
    return f"{parts[2]}-{parts[1]}-{parts[0]}" < cutoff


def check_bcb_series(
    client: bigquery.Client,
    settings: Settings,
    code: str,
    label: str,
    table: str,
    cutoff: str,
) -> SourceCheck:
    """Compare EVERY stored point older than `cutoff` against the live series.

    One SGS request returns the whole series, so unlike IBGE this is exhaustive.
    """
    from .bcb.client import fetch_series

    result = SourceCheck(label, f"série {code} · pontos anteriores a {cutoff}")
    frame = fetch_series(code, start_year=settings.bcb_start_year, end_year=settings.bcb_end_year)
    live = {str(r["data"]): str(r["valor"]) for _, r in frame.iterrows()}

    query = f"""
      SELECT reference_date_str, value_str
      FROM `{settings.gcp_project_id}.{settings.bq_bronze_bcb_dataset}.{table}`
      WHERE series_code = @code
      QUALIFY ROW_NUMBER() OVER (
        PARTITION BY reference_date_str ORDER BY ingestion_timestamp DESC) = 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("code", "STRING", str(code))]
    )
    for row in client.query(query, job_config=job_config).result():
        date_str = str(row["reference_date_str"])
        if not _is_before(date_str, cutoff):
            continue
        if date_str not in live:
            result.only_bronze += 1
            continue
        result.compared += 1
        if live[date_str] != str(row["value_str"]):
            result.diverged += 1
            if len(result.samples) < 5:
                result.samples.append(
                    f"{date_str}: fonte={live[date_str]} bronze={row['value_str']}"
                )
    return result
