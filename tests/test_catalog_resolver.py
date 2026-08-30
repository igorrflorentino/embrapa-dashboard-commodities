"""Tests for the catalog-driven product-code resolver (``ibge.catalog_resolver``).

The resolver is the seam that lets the Curadoria catalog drive which SIDRA product
codes get ingested. Its contract is safety-first: it must NEVER raise and must fall
back to the caller's env codes whenever the catalog can't be trusted (flag off,
table absent, empty, a BQ error, or the safety cap tripping).
"""

from __future__ import annotations

from google.api_core.exceptions import BadRequest, NotFound

from embrapa_dashboard.ibge import catalog_resolver

ENV = ["3405", "3435", "3450"]


class _FakeJob:
    def __init__(self, rows, exc=None):
        self._rows = rows
        self._exc = exc

    def result(self):
        if self._exc is not None:
            raise self._exc
        return self._rows


class _FakeBQ:
    """Minimal stand-in for a bigquery.Client — records the query + job_config."""

    def __init__(self, rows=None, exc=None):
        self._rows = rows or []
        self._exc = exc
        self.calls: list = []

    def query(self, sql, job_config=None):
        self.calls.append((sql, job_config))
        return _FakeJob(self._rows, self._exc)


def _rows(*codes):
    return [{"codigo_produto": c} for c in codes]


def test_flag_off_returns_env_without_touching_bq(settings_factory):
    """Feature off (default) → env codes, and the BQ client is never queried."""
    settings = settings_factory(catalog_authoritative_ingestion=False)
    fake = _FakeBQ(rows=_rows("999"))
    out = catalog_resolver.resolve_product_codes(settings, "pevs", env_fallback=ENV, bq_client=fake)
    assert out == ENV
    assert fake.calls == []


def test_catalog_codes_returned_when_flag_on(settings_factory):
    """Feature on + active rows → the catalog codes (not the env codes)."""
    settings = settings_factory(catalog_authoritative_ingestion=True)
    fake = _FakeBQ(rows=_rows("3405", "3450"))
    out = catalog_resolver.resolve_product_codes(settings, "pevs", env_fallback=ENV, bq_client=fake)
    assert out == ["3405", "3450"]
    sql, _job_config = fake.calls[0]
    # A coluna FAZ parte da chave desde que a identidade virou (banco, tabela, código), e
    # o esquema do log a declara — então referenciá-la é correto e seguro. A asserção
    # anterior ("not in sql") protegia contra uma instalação onde a coluna não existisse;
    # essa garantia migrou para o ESQUEMA, e foi este teste que expôs o furo quando a
    # coluna foi adicionada às tabelas vivas mas não às constantes de criação.
    assert "ifnull(tabela" in sql


class _FakeBQNoIngestaoColumn:
    """A log table that predates the `ingestao` column: the first query (which selects
    and filters on it) 400s, a retry without it succeeds."""

    def __init__(self, rows):
        self._rows = rows
        self.calls: list = []

    def query(self, sql, job_config=None):
        self.calls.append((sql, job_config))
        if "ingestao" in sql:
            return _FakeJob([], exc=BadRequest("Unrecognized name: ingestao"))
        return _FakeJob(self._rows)


def test_missing_ingestao_column_still_uses_the_catalog(settings_factory):
    """A pre-two-axis log table must NOT silently abandon the catalog.

    The resolver's SELECT references `ingestao`; on a table without it BigQuery raises
    BadRequest. Left to the caller's broad except, that would fall back to the ENV codes —
    skipping codes the researcher registered and re-fetching ones they paused. Instead the
    resolver retries without the pause filter, which is exactly equivalent: no row can be
    paused if the column does not exist."""
    settings = settings_factory(catalog_authoritative_ingestion=True)
    fake = _FakeBQNoIngestaoColumn(rows=_rows("3405", "3450"))
    out = catalog_resolver.resolve_product_codes(settings, "pevs", env_fallback=ENV, bq_client=fake)
    assert out == ["3405", "3450"], "fell back to env instead of retrying without the filter"
    assert len(fake.calls) == 2, "expected one failed attempt + one retry"
    assert "ingestao" in fake.calls[0][0]
    assert "ingestao" not in fake.calls[1][0]


def test_paused_products_are_excluded_from_ingestion(settings_factory):
    """The pause filter is actually in the query the resolver sends."""
    settings = settings_factory(catalog_authoritative_ingestion=True)
    fake = _FakeBQ(rows=_rows("3405"))
    catalog_resolver.resolve_product_codes(settings, "pevs", env_fallback=ENV, bq_client=fake)
    sql = fake.calls[0][0]
    assert "coalesce(ingestao, 'ativa') != 'pausada'" in sql


def test_empty_catalog_falls_back_to_env(settings_factory):
    """Feature on but no active rows for the banco → env fallback (cold start)."""
    settings = settings_factory(catalog_authoritative_ingestion=True)
    fake = _FakeBQ(rows=[])
    out = catalog_resolver.resolve_product_codes(settings, "pam", env_fallback=ENV, bq_client=fake)
    assert out == ENV


def test_notfound_falls_back_to_env(settings_factory):
    """Missing log table (NotFound) → env fallback, never raises."""
    settings = settings_factory(catalog_authoritative_ingestion=True)
    fake = _FakeBQ(exc=NotFound("no such table"))
    out = catalog_resolver.resolve_product_codes(settings, "pevs", env_fallback=ENV, bq_client=fake)
    assert out == ENV


def test_arbitrary_error_falls_back_to_env(settings_factory):
    """Any BQ/permission error → env fallback, never raises."""
    settings = settings_factory(catalog_authoritative_ingestion=True)
    fake = _FakeBQ(exc=RuntimeError("boom"))
    out = catalog_resolver.resolve_product_codes(settings, "pevs", env_fallback=ENV, bq_client=fake)
    assert out == ENV


def test_safety_cap_falls_back_to_env(settings_factory):
    """Resolved set larger than the cap → refuse and fall back to env codes."""
    settings = settings_factory(catalog_authoritative_ingestion=True, catalog_resolver_max_codes=2)
    fake = _FakeBQ(rows=_rows("1", "2", "3"))  # 3 > cap of 2
    out = catalog_resolver.resolve_product_codes(settings, "pevs", env_fallback=ENV, bq_client=fake)
    assert out == ENV


def test_ppm_routes_by_tabela(settings_factory):
    """PPM passes tabela → the query filters + binds the discriminator."""
    settings = settings_factory(catalog_authoritative_ingestion=True)
    fake = _FakeBQ(rows=_rows("2670", "2675"))
    out = catalog_resolver.resolve_product_codes(
        settings, "ppm", env_fallback=ENV, tabela="3939", bq_client=fake
    )
    assert out == ["2670", "2675"]
    sql, job_config = fake.calls[0]
    assert "tabela = @tabela" in sql
    names = {p.name for p in job_config.query_parameters}
    assert names == {"banco", "tabela"}


def test_pevs_extraction_half_also_matches_untagged_entries(settings_factory):
    """An UNTAGGED pevs entry belongs to the EXTRACTION half.

    Every pevs entry predates the tabela column — the tag only became meaningful when
    silvicultura (t291) was ingested on 2026-08-29. A strict `=` would drop all of them and
    the extraction ingest would quietly resolve to nothing, which is the exact failure the
    tag exists to prevent. Extraction is both the historical meaning of an untagged entry
    and ~4× the other half, so it is the one defensible default."""
    settings = settings_factory(catalog_authoritative_ingestion=True)
    fake = _FakeBQ(rows=_rows("3405"))
    catalog_resolver.resolve_product_codes(
        settings, "pevs", env_fallback=ENV, tabela="289", bq_client=fake
    )
    sql, _ = fake.calls[0]
    assert "tabela = @tabela or tabela is null" in sql


def test_pevs_silviculture_half_is_strict(settings_factory):
    """The OTHER half gets no such grace: an untagged entry read as silviculture would hand
    t291 the extraction codes — SIDRA answers empty and the run reports a clean no-op."""
    settings = settings_factory(catalog_authoritative_ingestion=True)
    fake = _FakeBQ(rows=_rows("3457"))
    catalog_resolver.resolve_product_codes(
        settings, "pevs", env_fallback=ENV, tabela="291", bq_client=fake
    )
    sql, _ = fake.calls[0]
    assert "is null" not in sql


def test_ppm_never_defaults_an_untagged_entry(settings_factory):
    """ppm keeps the strict `=`: its two tables share no codes, so a NULL there is a
    genuinely unanswered question and guessing would fetch the wrong table."""
    settings = settings_factory(catalog_authoritative_ingestion=True)
    fake = _FakeBQ(rows=_rows("2670"))
    catalog_resolver.resolve_product_codes(
        settings, "ppm", env_fallback=ENV, tabela="3939", bq_client=fake
    )
    sql, _ = fake.calls[0]
    assert "is null" not in sql


def test_max_bytes_billed_applied(settings_factory):
    """The resolver query is bounded by bq_max_bytes_billed (cost guard)."""
    settings = settings_factory(catalog_authoritative_ingestion=True, bq_max_bytes_billed=12345)
    fake = _FakeBQ(rows=_rows("3405"))
    catalog_resolver.resolve_product_codes(settings, "pevs", env_fallback=ENV, bq_client=fake)
    assert fake.calls[0][1].maximum_bytes_billed == 12345
