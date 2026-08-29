"""Health-check probes for the local environment.

Run via ``embrapa doctor`` to validate ADC, GCP access, .env parsing, and
upstream API reachability in ~10 seconds — useful before kicking off a
long ingest so credential/connectivity issues surface immediately instead
of mid-run.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import google.auth
import requests
from google.cloud import bigquery, storage
from google.cloud.exceptions import NotFound

from embrapa_dashboard.backup import BACKUP_PREFIX, SUCCESS_MARKER
from embrapa_dashboard.bcb.client import SGS_URL
from embrapa_dashboard.config import Settings, get_credentials, get_settings
from embrapa_dashboard.discover import SIDRA_METADATA_URL

logger = logging.getLogger(__name__)

# All probes use the same short timeout — the whole `embrapa doctor` should
# finish in under ~15s even when something is broken.
PROBE_TIMEOUT_S = 10


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


def _check_env(settings: Settings) -> CheckResult:
    """The .env parsed and every per-source code mapping is well-formed.

    Touches all the lazily-parsed Settings properties (PEVS, PAM, PPM, BCB,
    COMEX, COMTRADE) — each raises ``ValueError`` on malformed input, and a
    mapping that only explodes mid-ingest is exactly what doctor exists to
    pre-empt.
    """
    try:
        infl = settings.inflation_series_map
        curr = settings.currency_series_map
        products = settings.product_codes
        pam_codes = settings.pam_product_codes_list
        ppm_herd_codes = settings.ppm_herd_product_codes_list
        ppm_animal_codes = settings.ppm_animal_product_codes_list
        ppm_herd_vars = settings.ppm_herd_variable_codes_list
        ppm_animal_vars = settings.ppm_animal_variable_codes_list
        comex_flows = settings.comex_flows_list
        comex_codes = {
            **settings.comex_ncm_map,
            **settings.comex_heading_map,
            **settings.comex_chapter_map,
        }
        comtrade_flows = settings.comtrade_flows_list
        comtrade_codes = settings.comtrade_cmd_map
        ppm_codes = len(ppm_herd_codes) + len(ppm_animal_codes)
        ppm_vars = len(ppm_herd_vars) + len(ppm_animal_vars)
        detail = (
            f"products={','.join(products)}  inflation={list(infl.keys())}  "
            f"currency={list(curr.keys())}  pam={len(pam_codes)} codes  "
            f"ppm={ppm_codes} codes/{ppm_vars} vars  "
            f"comex={'/'.join(comex_flows)} {len(comex_codes)} codes  "
            f"comtrade={'/'.join(comtrade_flows)} {len(comtrade_codes)} codes"
        )
        return CheckResult(".env parsed", True, detail)
    except Exception as exc:
        return CheckResult(".env parsed", False, str(exc)[:120])


def _check_inflation_pivot_codes(settings: Settings) -> CheckResult:
    """Each Gold inflation pivot code must be present in BCB_INFLATION_SERIES.

    The Gold ``val_real_{ipca,igpm,igpdi}_*`` columns are built from these codes
    (read by dbt via ``env_var``). A pivot code that is not among the ingested
    series → those columns silently come out NULL. Catch the drift here instead
    of discovering empty real-value columns downstream in Looker / Gold consumers.
    """
    try:
        available = set(settings.inflation_series_map)
        missing = {
            label: code
            for label, code in settings.inflation_pivot_codes.items()
            if code not in available
        }
        if missing:
            return CheckResult(
                "Inflation pivot codes",
                False,
                f"not in BCB_INFLATION_SERIES: {missing} "
                f"(available={sorted(available)}) → Gold val_real_* would be NULL",
            )
        return CheckResult(
            "Inflation pivot codes",
            True,
            f"{settings.inflation_pivot_codes} all present",
        )
    except Exception as exc:
        return CheckResult("Inflation pivot codes", False, str(exc)[:120])


# The canonical daily PTAX "venda" series (BRL per foreign unit): SGS 1 = USD,
# 21619 = EUR. The Gold FX/deflation math keys off these EXACT codes. The earlier
# 3694/4393(/20542) were wrong (3694 is annual, 4393 is not a BRL-per-unit rate),
# and a stale local .env carrying them parses fine but silently regresses every
# Gold ``val_yearfx_*`` column on the next ingest + rebuild — plausible-looking
# drift that slips review, which is exactly what this probe pre-empts.
_CANONICAL_CURRENCY_CODES = {"USD": "1", "EUR": "21619"}
_KNOWN_BAD_CURRENCY_CODES = {
    "3694": "annual USD, not the daily PTAX series",
    "4393": "not a BRL-per-unit FX rate",
    "20542": "deprecated/incorrect EUR series",
}


def _check_currency_series_codes(settings: Settings) -> CheckResult:
    """BCB_CURRENCY_SERIES must resolve to the canonical daily PTAX codes.

    A stale .env with the historical wrong codes (3694/4393/20542) parses fine but
    silently regresses the Gold FX columns on the next ingest + rebuild — the kind
    of plausible drift doctor exists to catch before it ships.
    """
    try:
        currency = settings.currency_series_map  # {code: label}
        by_label = {label.upper(): code for code, label in currency.items()}
        problems = [
            f"{label} should be series {want}, got {by_label.get(label)!r}"
            for label, want in _CANONICAL_CURRENCY_CODES.items()
            if by_label.get(label) != want
        ]
        bad = {code: why for code in currency if (why := _KNOWN_BAD_CURRENCY_CODES.get(code))}
        if bad:
            problems.append(f"known-wrong codes present: {bad}")
        if problems:
            return CheckResult(
                "Currency series codes",
                False,
                "; ".join(problems) + " → Gold val_yearfx_* would regress",
            )
        return CheckResult(
            "Currency series codes",
            True,
            f"canonical {by_label} (USD=1, EUR=21619)",
        )
    except Exception as exc:
        return CheckResult("Currency series codes", False, str(exc)[:120])


# The SIDRA variable codes silver_ibge_pam pivots, keyed to their dbt role (the
# pam_variable_* vars in dbt_project.yml). Each MUST be ingested (present in
# PAM_VARIABLE_CODES) or its Gold column comes out empty. Mirror dbt_project.yml:
# keep this in sync if a PAM variable is added/removed there.
_PAM_REQUIRED_VARIABLE_CODES = {
    "8331": "área plantada",
    "216": "área colhida",
    "214": "quantidade",
    "112": "rendimento",
    "215": "valor",
}


def _check_pam_variable_codes(settings: Settings) -> CheckResult:
    """Each PAM variable code the dbt model relies on must be in PAM_VARIABLE_CODES.

    silver_ibge_pam pivots these SIDRA variables (dbt vars pam_variable_*). A code
    dropped from PAM_VARIABLE_CODES is never fetched into Bronze, so its Gold column
    (área/quantidade/rendimento/valor) silently comes out empty. The config comment
    nominates ``embrapa doctor`` as the place for this parity check — this is it.
    """
    try:
        available = set(settings.pam_variable_codes_list)
        missing = {
            code: role
            for code, role in _PAM_REQUIRED_VARIABLE_CODES.items()
            if code not in available
        }
        if missing:
            return CheckResult(
                "PAM variable codes",
                False,
                f"not in PAM_VARIABLE_CODES: {missing} "
                f"(available={sorted(available)}) → that Gold column would be empty",
            )
        return CheckResult(
            "PAM variable codes",
            True,
            f"all {len(_PAM_REQUIRED_VARIABLE_CODES)} dbt PAM variables present",
        )
    except Exception as exc:
        return CheckResult("PAM variable codes", False, str(exc)[:120])


# The SIDRA t289 variable codes silver_ibge_pevs filters to, keyed to their dbt role
# (ibge_variable_* vars, env-bridged to config.ibge_variable_*_code). PEVS fetches
# v/all into Bronze, then Silver keeps ONLY these — a wrong code empties the matching
# Gold column silently. Mirror dbt_project.yml / config.py: keep in sync if changed.
_IBGE_REQUIRED_VARIABLE_CODES = {
    "144": "quantidade",
    "145": "valor",
}

# The silviculture half's analogues (SIDRA t291). Same failure mode as above: a mistyped
# code silently empties a Gold column instead of erroring.
_SILVICULTURA_REQUIRED_VARIABLE_CODES = {
    "142": "quantidade",
    "143": "valor",
}


def _check_ibge_variable_codes(settings: Settings) -> CheckResult:
    """The PEVS variable codes silver_ibge_pevs filters on must be the intended 144/145.

    silver_ibge_pevs keeps only ``ibge_variable_quantity``/``ibge_variable_value`` (dbt
    vars, env-bridged to ``config.ibge_variable_*_code``). A code mistyped in .env /
    dbt_project.yml silently drops that variable from Silver, emptying its Gold column
    (quantidade or valor) with no downstream error — the PEVS analogue of the PAM check.
    """
    try:
        configured = {settings.ibge_variable_quantity_code, settings.ibge_variable_value_code}
        missing = {
            code: role
            for code, role in _IBGE_REQUIRED_VARIABLE_CODES.items()
            if code not in configured
        }
        if missing:
            return CheckResult(
                "IBGE PEVS variable codes",
                False,
                f"not configured: {missing} (quantity={settings.ibge_variable_quantity_code!r}, "
                f"value={settings.ibge_variable_value_code!r}) → that Gold column would be empty",
            )
        return CheckResult(
            "IBGE PEVS variable codes",
            True,
            f"quantity={settings.ibge_variable_quantity_code}, "
            f"value={settings.ibge_variable_value_code}",
        )
    except Exception as exc:
        return CheckResult("IBGE PEVS variable codes", False, str(exc)[:120])


def _check_silvicultura_variable_codes(settings: Settings) -> CheckResult:
    """The t291 variable codes silver_ibge_silvicultura filters on must be 142/143.

    Exactly the PEVS check one table over. config.py declares the env keys and
    dbt/dbt_project.yml reads the SAME ones; nothing recomputes either from the other, so
    a typo in one drops that variable from Silver and empties its half of the Gold column
    with no downstream error.
    """
    try:
        configured = {
            settings.silvicultura_variable_quantity_code,
            settings.silvicultura_variable_value_code,
        }
        missing = {
            code: role
            for code, role in _SILVICULTURA_REQUIRED_VARIABLE_CODES.items()
            if code not in configured
        }
        if missing:
            return CheckResult(
                "IBGE silvicultura variable codes",
                False,
                f"not configured: {missing} "
                f"(quantity={settings.silvicultura_variable_quantity_code!r}, "
                f"value={settings.silvicultura_variable_value_code!r}) "
                "→ that Gold column would be empty for origem='silvicultura'",
            )
        return CheckResult(
            "IBGE silvicultura variable codes",
            True,
            f"quantity={settings.silvicultura_variable_quantity_code}, "
            f"value={settings.silvicultura_variable_value_code}",
        )
    except Exception as exc:
        return CheckResult("IBGE silvicultura variable codes", False, str(exc)[:120])


def _check_catalog_resolver_parity(settings: Settings) -> CheckResult:
    """Diff the catalog-resolved product codes vs the .env codes per IBGE banco.

    When ``catalog_authoritative_ingestion`` is on, the nightly ingestion pulls whatever the
    Curadoria catalog resolves — so before a run an operator wants to SEE any drift from the
    .env baseline (and confirm ``catalog-seed-from-env`` reproduced it). Informational
    (ok=True) even on drift: a researcher intentionally changing the catalog is the whole
    point, not an error. Reads the catalog directly (independent of the flag) so it also
    previews what a cutover WOULD change; also flags a banco that would trip the safety cap.
    """
    try:
        from embrapa_dashboard.ibge import catalog_resolver

        plan = [
            # PEVS spans two SIDRA tables since 2026-08-29, so it is compared PER TABLE
            # exactly like ppm. Comparing the token as a whole against IBGE_PRODUCT_CODES
            # (t289 only) reported the three silviculture codes as permanent DRIFT — a red
            # herring that is correct-by-design, and an operator who learns to ignore
            # doctor is the real cost.
            ("pevs", settings.ibge_table_id, settings.product_codes),
            ("pevs", settings.silvicultura_table_id, settings.silvicultura_product_codes_list),
            ("pam", None, settings.pam_product_codes_list),
            ("ppm", settings.ppm_herd_table_id, settings.ppm_herd_product_codes_list),
            ("ppm", settings.ppm_animal_table_id, settings.ppm_animal_product_codes_list),
        ]
        parts: list[str] = []
        drift = False
        for banco, sidra_tabela, env_codes in plan:
            cat = set(
                catalog_resolver.read_catalog_codes(settings, banco, sidra_tabela=sidra_tabela)
            )
            label = banco + (f":{sidra_tabela}" if sidra_tabela else "")
            if not cat:
                parts.append(f"{label} vazio→.env({len(env_codes)})")
                continue
            added = sorted(cat - set(env_codes))
            removed = sorted(set(env_codes) - cat)
            if added or removed:
                drift = True
                parts.append(f"{label} +{added} -{removed}")
            else:
                parts.append(f"{label} OK({len(cat)})")
            if len(cat) > settings.catalog_resolver_max_codes:
                drift = True
                parts.append(f"{label} ACIMA-DO-CAP({len(cat)})")
        flag = "ON" if settings.catalog_authoritative_ingestion else "off"
        prefix = "DRIFT — " if drift else ""
        return CheckResult(
            "Catalog↔env product codes", True, f"[authoritative={flag}] {prefix}{' · '.join(parts)}"
        )
    except Exception as exc:  # never fail — this is an advisory diff
        return CheckResult("Catalog↔env product codes", True, f"skipped: {str(exc)[:100]}")


def _check_orphan_lifecycle(settings: Settings) -> CheckResult:
    """Soft-warn on catalog ORPHANS awaiting the auto-marker (the spec's doctor check).

    An orphan is a removal that LEFT DATA BEHIND: the entry's current state is a tombstone
    (active=false) AND its exact code still exists in that banco's Gold. Only those are
    marked by ``mark-orphans``, so only those may be counted here.

    Counting bare tombstones instead was wrong in a way that could never clear: a CLEAN
    removal (no lingering Gold rows) is never marked — correctly, there is nothing to
    purge — so `removed > marked` was the permanent steady state after any tidy-up. The
    check warned forever, blamed a build step that had in fact succeeded, and prescribed a
    `mark-orphans` run that was a guaranteed no-op. This repo's trade catalogs were migrated
    from 4-digit HS to NCM-8/HS-6 on 2026-07-02, leaving 20 such tombstones and a permanently
    red-herring advisory. An operator who learns to ignore doctor's output is the real cost.

    Advisory (ok=True): a legitimately removed product is expected, not an error. Flask-free
    (direct BQ over the small logs + a Gold semi-join) so it runs inside a bare
    ``embrapa doctor`` — hence sqlbuild.GOLD_CODE_SOURCES rather than importing gateway. Any
    fault (tables absent / perms) degrades to 'skipped'."""
    try:
        from embrapa_dashboard.gcp.clients import resolve_bq_client
        from embrapa_dashboard.serving import sql as sqlbuild

        bq = resolve_bq_client(settings)
        catalog_log = sqlbuild.table_ref(
            settings, "bq_research_inputs_dataset", settings.bq_produto_catalog_log_table
        )
        lifecycle_log = sqlbuild.table_ref(
            settings, "bq_research_inputs_dataset", settings.bq_catalog_lifecycle_log_table
        )
        # Same shape as gateway.fetch_orphan_produtos: tombstoned ⋈ Gold on the EXACT code.
        gold_union = " union all ".join(
            f"select '{src}' as src, {col} as code from "
            f"`{sqlbuild.table_ref(settings, 'bq_gold_dataset', tbl)}`"
            for src, (tbl, col) in sqlbuild.GOLD_CODE_SOURCES.items()
        )
        orphan_sql = f"""
            with tombstoned as (
              select codigo_produto, banco from (
                select codigo_produto, banco, active, row_number() over (
                  partition by codigo_produto, banco order by edited_at desc, change_id desc
                ) as _rn from `{catalog_log}`
              ) where _rn = 1 and not active
            ),
            gold_codes as ({gold_union})
            select count(*) as n from (
              select distinct t.codigo_produto, t.banco
              from tombstoned t
              join gold_codes g on g.src = t.banco and g.code = t.codigo_produto
            )
        """
        marked_sql = f"""
            select count(*) as n from (
              select status, row_number() over (
                partition by element_kind, banco, code order by edited_at desc, change_id desc
              ) as _rn from `{lifecycle_log}` where element_kind = 'commodity'
            ) where _rn = 1 and status in ('descontinuado', 'purged')
        """
        orphans = next(iter(bq.query(orphan_sql).result())).n
        marked = next(iter(bq.query(marked_sql).result())).n
        if orphans > marked:
            return CheckResult(
                "Catalog orphan lifecycle",
                True,
                f"{orphans} orphan(s) with Gold data, {marked} marked — {orphans - marked} "
                "unmarked; run `embrapa mark-orphans` (the build-boundary step may have failed).",
            )
        if orphans:
            return CheckResult("Catalog orphan lifecycle", True, f"{orphans} orphan(s), all marked")
        return CheckResult(
            "Catalog orphan lifecycle", True, "no orphans (no removal left Gold data behind)"
        )
    except Exception as exc:  # never fail — advisory
        return CheckResult("Catalog orphan lifecycle", True, f"skipped: {str(exc)[:100]}")


def _check_adc(settings: Settings) -> CheckResult:
    """Application Default Credentials are present; reports impersonation target when set."""
    try:
        _credentials, project = google.auth.default()
        if settings.gcp_impersonation_sa:
            detail = f"project={project or '?'} → impersonating {settings.gcp_impersonation_sa}"
        else:
            detail = f"project={project or '?'}"
        return CheckResult("ADC credentials", True, detail)
    except Exception as exc:
        return CheckResult(
            "ADC credentials",
            False,
            f"{exc} (run `gcloud auth application-default login`)",
        )


def _check_bq(settings: Settings) -> CheckResult:
    """The configured GCP project is reachable for BigQuery."""
    try:
        creds = get_credentials(settings)
        client = bigquery.Client(
            project=settings.gcp_project_id, location=settings.bq_location, credentials=creds
        )
        sa = client.get_service_account_email()
        return CheckResult("BigQuery reachable", True, f"sa={sa}")
    except Exception as exc:
        return CheckResult("BigQuery reachable", False, str(exc)[:120])


def _check_gcs(settings: Settings) -> CheckResult:
    """The landing bucket is accessible (or will be created lazily on first ingest)."""
    try:
        creds = get_credentials(settings)
        client = storage.Client(project=settings.gcp_project_id, credentials=creds)
        # list_blobs requires only storage.objects.list (included in objectViewer).
        # bucket.exists() needs storage.buckets.get which objectViewer does not grant.
        try:
            next(client.list_blobs(settings.gcs_bucket, max_results=1), None)
            return CheckResult("GCS bucket", True, f"gs://{settings.gcs_bucket} (exists)")
        except NotFound:
            return CheckResult(
                "GCS bucket",
                True,
                f"gs://{settings.gcs_bucket} (will be created on first ingest)",
            )
    except Exception as exc:
        return CheckResult("GCS bucket", False, str(exc)[:120])


def _check_ibge(settings: Settings) -> CheckResult:
    """SIDRA metadata endpoint responds for the configured table."""
    url = SIDRA_METADATA_URL.format(table_id=settings.ibge_table_id)
    try:
        response = requests.get(url, timeout=PROBE_TIMEOUT_S)
        response.raise_for_status()
        return CheckResult("IBGE SIDRA reachable", True, f"t{settings.ibge_table_id} 200 OK")
    except Exception as exc:
        return CheckResult("IBGE SIDRA reachable", False, str(exc)[:120])


def _check_silvicultura(settings: Settings) -> CheckResult:
    """SIDRA metadata endpoint responds for the configured silviculture table (291)."""
    url = SIDRA_METADATA_URL.format(table_id=settings.silvicultura_table_id)
    try:
        response = requests.get(url, timeout=PROBE_TIMEOUT_S)
        response.raise_for_status()
        return CheckResult(
            "IBGE SIDRA silvicultura reachable", True, f"t{settings.silvicultura_table_id} 200 OK"
        )
    except Exception as exc:
        return CheckResult("IBGE SIDRA silvicultura reachable", False, str(exc)[:120])


def _check_pam(settings: Settings) -> CheckResult:
    """SIDRA metadata endpoint responds for the configured PAM table (5457)."""
    url = SIDRA_METADATA_URL.format(table_id=settings.pam_table_id)
    try:
        response = requests.get(url, timeout=PROBE_TIMEOUT_S)
        response.raise_for_status()
        return CheckResult("IBGE PAM reachable", True, f"t{settings.pam_table_id} 200 OK")
    except Exception as exc:
        return CheckResult("IBGE PAM reachable", False, str(exc)[:120])


def _check_ppm(settings: Settings) -> CheckResult:
    """SIDRA metadata endpoint responds for BOTH configured PPM tables (3939 + 74)."""
    tables = [settings.ppm_herd_table_id, settings.ppm_animal_table_id]
    try:
        for table_id in tables:
            response = requests.get(
                SIDRA_METADATA_URL.format(table_id=table_id), timeout=PROBE_TIMEOUT_S
            )
            response.raise_for_status()
        return CheckResult("IBGE PPM reachable", True, f"t{'+t'.join(tables)} 200 OK")
    except Exception as exc:
        return CheckResult("IBGE PPM reachable", False, str(exc)[:120])


def _check_bcb(settings: Settings) -> CheckResult:
    """BCB SGS responds for the first inflation series in .env."""
    try:
        code = next(iter(settings.inflation_series_map))
    except StopIteration:
        return CheckResult("BCB SGS reachable", False, "BCB_INFLATION_SERIES is empty")
    # Hit the URL pattern the real client uses, with a tiny 1-year window so
    # we just verify reachability, not data correctness.
    url = SGS_URL.format(code=code, start="01/01/2024", end="31/12/2024")
    try:
        response = requests.get(url, timeout=PROBE_TIMEOUT_S)
        response.raise_for_status()
        return CheckResult("BCB SGS reachable", True, f"sgs.{code} 200 OK")
    except Exception as exc:
        return CheckResult("BCB SGS reachable", False, str(exc)[:120])


def _check_comex(settings: Settings) -> CheckResult:
    """The Comex Stat file host serves a recent year's export file.

    A HEAD against ``EXP_<end_year>.csv`` verifies reachability without pulling
    the (100+ MB) body. Early in the year MDIC has not yet published the
    end-year file — the ingest pipeline classifies that 404 as an expected
    skip (see ``comex.pipeline``), so the probe falls back to the previous
    year's file instead of flagging a healthy environment as broken. Note:
    this host is blocked on Claude Code on the web — it only passes from a
    network with the MDIC domain reachable.
    """
    from embrapa_dashboard.comex.client import FILE_PREFIX, _ca_bundle

    flow = settings.comex_flows_list[0] if settings.comex_flows_list else "export"
    prefix = FILE_PREFIX.get(flow, "EXP")
    end_year = settings.comex_end_year

    def _head(year: int) -> None:
        url = f"{settings.comex_csv_base_url.rstrip('/')}/{prefix}_{year}.csv"
        # The host omits its TLS intermediate — reuse the client's certifi+vendored
        # CA bundle so the probe verifies the same way the real download does.
        response = requests.head(
            url, timeout=PROBE_TIMEOUT_S, allow_redirects=True, verify=_ca_bundle()
        )
        response.raise_for_status()

    try:
        _head(end_year)
        return CheckResult("COMEX reachable", True, f"{prefix}_{end_year}.csv 200 OK")
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status != 404:
            return CheckResult("COMEX reachable", False, str(exc)[:120])
    except Exception as exc:
        return CheckResult("COMEX reachable", False, str(exc)[:120])

    # 404 on the end-year file: expected when MDIC hasn't published it yet
    # (the same condition the ingest treats as a healthy skip). The host is
    # only broken if the previous year's file is unreachable too.
    try:
        _head(end_year - 1)
        return CheckResult(
            "COMEX reachable",
            True,
            f"{prefix}_{end_year - 1}.csv 200 OK "
            f"({prefix}_{end_year}.csv not published yet — expected)",
        )
    except Exception as exc:
        return CheckResult("COMEX reachable", False, str(exc)[:120])


def _check_comtrade(settings: Settings) -> CheckResult:
    """UN Comtrade reachable + whether the API key is configured.

    The Reporters reference (keyless) confirms connectivity; the keyed ingest
    additionally needs COMTRADE_API_KEY — a missing key is a soft warning (the
    source is optional), not a hard failure.
    """
    from embrapa_dashboard.comtrade.client import REPORTERS_REF_URL

    try:
        # The reference host serves this static file over GET only — it 404s on
        # HEAD — so probe with a streamed GET and don't drain the body.
        response = requests.get(
            REPORTERS_REF_URL, timeout=PROBE_TIMEOUT_S, allow_redirects=True, stream=True
        )
        response.close()
        response.raise_for_status()
    except Exception as exc:
        return CheckResult("COMTRADE reachable", False, str(exc)[:120])
    if not settings.comtrade_api_key:
        return CheckResult(
            "COMTRADE reachable", True, "⚠ API 200 OK but COMTRADE_API_KEY unset (keyed ingest)"
        )
    return CheckResult("COMTRADE reachable", True, "API 200 OK; key configured")


def _check_bronze_tables(settings: Settings) -> CheckResult:
    """Report whether Bronze tables already exist (informational, never fails).

    Iterates ``BRONZE_TARGETS`` so new sources extend the check by appending a
    single tuple — see ``docs/adding_a_data_source.md``.
    """
    try:
        client = bigquery.Client(
            project=settings.gcp_project_id,
            location=settings.bq_location,
            credentials=get_credentials(settings),
        )
        targets = [
            (getattr(settings, dataset_attr), getattr(settings, table_attr))
            for dataset_attr, table_attr in BRONZE_TARGETS
        ]
        existing: list[str] = []
        missing: list[str] = []
        for dataset, table in targets:
            fqn = f"{settings.gcp_project_id}.{dataset}.{table}"
            try:
                client.get_table(fqn)
                existing.append(table)
            except NotFound:
                missing.append(table)
        if missing:
            detail = f"present={existing or '∅'}; missing={missing} (run ingest)"
        else:
            detail = f"all present: {existing}"
        return CheckResult("Bronze tables", True, detail)
    except Exception as exc:
        return CheckResult("Bronze tables", False, str(exc)[:120])


# ★ Extension point: each (dataset_attr, table) is an object the dashboard BFF
# reads. _check_serving_marts iterates over this list. dim_code_industrialization_scd2
# (the SCD2 curation view) is DELIBERATELY excluded: it is gated by
# `enable_curation` (make dbt-build-curation), so its absence is expected in a
# standard build and would raise a false alarm here.
SERVING_TARGETS: list[tuple[str, str]] = [
    ("bq_serving_dataset", "serving_pevs_annual"),
    ("bq_serving_dataset", "serving_pam_annual"),
    ("bq_serving_dataset", "serving_ppm_annual"),
    ("bq_serving_dataset", "serving_comex_annual"),
    ("bq_serving_dataset", "serving_comex_seasonality"),
    ("bq_serving_dataset", "serving_comtrade_annual"),
    ("bq_serving_dataset", "serving_quality_by_source"),
    ("bq_gold_dataset", "gold_source_metadata"),
]


def _check_serving_marts(settings: Settings) -> CheckResult:
    """Report whether the serving objects the dashboard BFF reads exist + are populated.

    A deploy-readiness gate for the data layer: the dashboard's ``gateway.fetch_*``
    readers query these marts (+ ``gold_source_metadata`` for provenance). Informational
    like ``_check_bronze_tables`` — a fresh project has none until ``make dbt-build-prod``
    builds them, so a missing mart is reported (with the fix) rather than failing doctor.
    The emptiness check applies only to materialized marts: ``tables.get`` reports
    ``numRows: 0`` for VIEWs (e.g. ``gold_source_metadata``) regardless of their
    contents, so views are existence-only here to avoid a permanent false "empty"
    alarm.
    """
    try:
        client = bigquery.Client(
            project=settings.gcp_project_id,
            location=settings.bq_location,
            credentials=get_credentials(settings),
        )
        present, missing, empty = _classify_serving_marts(client, settings)
        parts: list[str] = []
        if missing:
            parts.append(f"missing={missing} (run `make dbt-build-prod`)")
        if empty:
            parts.append(f"⚠ empty={empty}")
        if not missing and not empty:
            parts.append(f"all present + populated: {present}")
        elif present:
            parts.append(f"present={present}")
        return CheckResult("Serving marts", True, "; ".join(parts))
    except Exception as exc:
        return CheckResult("Serving marts", False, str(exc)[:120])


def _classify_serving_marts(client, settings: Settings) -> tuple[list[str], list[str], list[str]]:
    """Sort each SERVING_TARGETS table into (present, missing, empty).

    A VIEW is existence-only (``tables.get`` reports numRows=0 for views even when
    their query yields rows); only a materialized mart with numRows==0 is "empty".
    """
    present: list[str] = []
    missing: list[str] = []
    empty: list[str] = []
    for dataset_attr, table in SERVING_TARGETS:
        dataset = getattr(settings, dataset_attr)
        fqn = f"{settings.gcp_project_id}.{dataset}.{table}"
        try:
            tbl = client.get_table(fqn)
        except NotFound:
            missing.append(table)
            continue
        present.append(table)
        if tbl.table_type == "VIEW":
            continue
        if tbl.num_rows == 0:  # 0 means an actually-empty materialized mart
            empty.append(table)
    return present, missing, empty


# `embrapa backup-gold` lays down prefixes shaped `backups/run=YYYYMMDDTHHMMSSZ/...`.
# The trailing slash is important — without it `list_blobs(delimiter="/")` would
# return individual blob names instead of the `run=*/` directory prefixes.
_BACKUP_PREFIX = f"{BACKUP_PREFIX}/"
# Derive the run-prefix pattern from BACKUP_PREFIX (the single source of truth in backup.py)
# rather than hardcoding 'backups/' — otherwise changing BACKUP_PREFIX would make this match
# nothing and falsely report "no snapshot" even with valid backups present.
_BACKUP_RUN_RE = re.compile(rf"^{re.escape(BACKUP_PREFIX)}/run=(\d{{8}}T\d{{6}}Z)/$")


def _list_backup_runs(client, settings: Settings) -> list[tuple[datetime, str]]:
    """All ``run=<ts>/`` prefixes under the backup root, parsed to (timestamp, prefix)."""
    # delimiter="/" turns this into a directory listing: blobs.prefixes yields the
    # run=*/ prefixes themselves, not the individual parquet parts beneath them.
    blobs = client.list_blobs(settings.gcs_bucket, prefix=_BACKUP_PREFIX, delimiter="/")
    # Iterating the page iterator is what populates `prefixes` — the
    # google-cloud-storage client only fetches them lazily.
    _ = list(blobs)
    runs: list[tuple[datetime, str]] = []
    for prefix in getattr(blobs, "prefixes", []) or []:
        match = _BACKUP_RUN_RE.match(prefix)
        if not match:
            continue
        try:
            ts = datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        except ValueError:
            continue
        runs.append((ts, prefix))
    return runs


def _snapshot_dataset(marker_blob) -> str | None:
    """The Gold dataset a sealed run snapshotted, read from its ``_SUCCESS`` manifest body;
    ``None`` if the body is unreadable or predates dataset recording (legacy snapshot)."""
    try:
        return json.loads(marker_blob.download_as_text()).get("dataset")
    except Exception:
        return None


def _latest_complete_run(client, settings: Settings, runs: list[tuple[datetime, str]]):
    """Newest run that both carries the ``_SUCCESS`` marker AND snapshotted the dataset now
    configured (``settings.bq_gold_dataset``), and how many newer runs were skipped.

    Returns ``(latest_ts_or_None, skipped)``. Partial/failed runs (no marker) are skipped — a
    crashed half-backup must not satisfy freshness. A COMPLETE run whose manifest records a
    DIFFERENT dataset is also skipped: dev (dbt_dev_gold) and prod (gold) hold identically
    named tables under one bucket prefix, so a dev-pointed-.env snapshot must never satisfy a
    prod freshness/backup gate (nor vice-versa). A legacy manifest with no recorded dataset is
    assumed to match (backward compatibility with snapshots taken before it was recorded).
    """
    bucket = client.bucket(settings.gcs_bucket)
    skipped = 0
    for ts, prefix in sorted(runs, reverse=True):  # newest first
        marker = bucket.blob(f"{prefix}{SUCCESS_MARKER}")
        if not marker.exists():
            skipped += 1
            continue
        snap_dataset = _snapshot_dataset(marker)
        if snap_dataset is not None and snap_dataset != settings.bq_gold_dataset:
            skipped += 1
            continue
        return ts, skipped
    return None, skipped


def _check_backup_freshness(settings: Settings) -> CheckResult:
    """Warn when the most recent COMPLETE Gold snapshot is older than BACKUP_STALENESS_DAYS.

    Only snapshots sealed with the ``_SUCCESS`` manifest (written by
    ``backup.run`` after the last extract) count: a crashed half-backup leaves a
    ``run=<ts>/`` prefix without the marker and must not satisfy freshness —
    the operator would believe the cold-storage rollback path is intact while
    most Gold tables are missing from it.

    Fails (ok=False) when no complete snapshot exists at all — that means the
    operator has never (successfully) run ``make dbt-build-prod-with-backup``
    (or its CLI equivalent), which is a real gap for any project past its
    first prod build.

    Stale (older than threshold) is reported with ok=True + a ⚠ marker so it
    doesn't flip `doctor` to exit-1 — matching the soft-warning pattern in
    `_check_bronze_tables`.
    """
    try:
        creds = get_credentials(settings)
        client = storage.Client(project=settings.gcp_project_id, credentials=creds)
        runs = _list_backup_runs(client, settings)
        if not runs:
            return CheckResult(
                "Gold backup freshness",
                False,
                f"no snapshot under gs://{settings.gcs_bucket}/{_BACKUP_PREFIX} "
                "(run `make dbt-build-prod-with-backup`)",
            )

        latest, incomplete_skipped = _latest_complete_run(client, settings, runs)
        if latest is None:
            return CheckResult(
                "Gold backup freshness",
                False,
                f"{len(runs)} snapshot(s) under gs://{settings.gcs_bucket}/{_BACKUP_PREFIX} "
                f"but none is a COMPLETE snapshot of dataset {settings.bq_gold_dataset!r} "
                f"(missing {SUCCESS_MARKER} marker, or a snapshot of a different dataset) "
                "(run `make dbt-build-prod-with-backup`)",
            )

        skipped_note = (
            f"; ⚠ skipped {incomplete_skipped} newer run(s) (incomplete or other-dataset)"
            if incomplete_skipped
            else ""
        )
        age = datetime.now(UTC) - latest
        age_days = age.days  # whole days, for the human-readable message
        latest_str = latest.strftime("%Y-%m-%d %H:%M UTC")
        threshold = settings.backup_staleness_days
        # Compare on the FRACTIONAL age so a snapshot 14d23h old is already stale at a
        # 14d threshold — `.days` truncates toward zero, which would let it pass for up
        # to a full extra day past the literal threshold (DOC-1).
        if age.total_seconds() / 86400 > threshold:
            return CheckResult(
                "Gold backup freshness",
                True,  # warn, not fail — matches _check_bronze_tables semantics
                f"⚠ stale: latest={latest_str} ({age_days}d ago > {threshold}d threshold)"
                f"{skipped_note}",
            )
        return CheckResult(
            "Gold backup freshness",
            True,
            f"latest={latest_str} ({age_days}d ago, threshold={threshold}d){skipped_note}",
        )
    except Exception as exc:
        return CheckResult("Gold backup freshness", False, str(exc)[:120])


def _check_curation_backup(settings: Settings) -> CheckResult:
    """Does the newest sealed snapshot COVER the researcher-authored data?

    Gold is derivable — losing it costs a ``dbt build``, because every row traces back to
    Bronze. ``research_inputs`` is authored: the produto catalog, the agrupamentos
    registry, the industrialization classifications, the lifecycle log and the editor
    allowlists. Nothing recomputes it. Until 2026-08-29 the backup introspected the Gold
    dataset ALONE, so the one irreplaceable dataset in the project was the one with no
    snapshot, while the reproducible half had a near-daily one.

    FAILS (ok=False) when the newest snapshot predates that coverage: a stale-but-present
    Gold backup would otherwise read as "backed up" on the freshness line while every
    curation decision sits unprotected. An absent ``curation_table_count`` key means "taken
    before coverage existed" — different from ``0``, which means "covered, dataset empty".
    """
    try:
        creds = get_credentials(settings)
        client = storage.Client(project=settings.gcp_project_id, credentials=creds)
        runs = _list_backup_runs(client, settings)
        if not runs:
            return CheckResult("Curation backup coverage", True, "skipped: no snapshot yet")
        bucket = client.bucket(settings.gcs_bucket)
        for ts, prefix in sorted(runs, reverse=True):
            marker = bucket.blob(f"{prefix}{SUCCESS_MARKER}")
            if not marker.exists():
                continue
            corpo = json.loads(marker.download_as_text())
            if corpo.get("dataset") not in (None, settings.bq_gold_dataset):
                continue
            quando = ts.strftime("%Y-%m-%d %H:%M UTC")
            n = corpo.get("curation_table_count")
            if n is None:
                return CheckResult(
                    "Curation backup coverage",
                    False,
                    f"newest snapshot ({quando}) predates curation coverage — the authored "
                    "catalog/classifications are NOT in it; run `make backup-gold`",
                )
            return CheckResult(
                "Curation backup coverage", True, f"{n} curation table(s) in {quando} snapshot"
            )
        return CheckResult("Curation backup coverage", True, "skipped: no sealed snapshot")
    except Exception as exc:
        return CheckResult("Curation backup coverage", True, f"skipped: {str(exc)[:100]}")


def _check_source_data_freshness(settings: Settings) -> CheckResult:
    """Is each source's latest REFERENCE PERIOD as recent as its cadence implies?

    The gap this closes: the ingestion alert fires on a FAILED Cloud Run execution, so a
    monthly job that runs green and ingests nothing looks exactly like "the source has not
    published yet". Nothing else told anyone the difference. For annual sources that quiet
    state is normal ~11 months a year, which is precisely why a silent stall could sit
    unnoticed until someone happened to look.

    So this does NOT ask "did the scheduler run" — that lives in Cloud Run/Logging, not in
    BigQuery, and the pipelines' own events go to a log file. It asks the question the
    researcher actually has: **is the newest reference period here as new as it should be?**
    A stalled cadence eventually shows up as exactly that, when a publication window passes
    and `year_end` does not move.

    Honest limit, stated so nobody over-trusts a green line: between publication windows
    this check CANNOT distinguish a healthy quiet source from a broken one, because the
    data is identical in both cases. It catches the stall at the window, not before it.

    Reads `gold_source_metadata` (one row per source, with `cadence` and `year_end`), so it
    costs one small query and extends automatically when a source is added there.
    """
    try:
        client = bigquery.Client(
            project=settings.gcp_project_id,
            location=settings.bq_location,
            credentials=get_credentials(settings),
        )
        fqn = f"{settings.gcp_project_id}.{settings.bq_gold_dataset}.gold_source_metadata"
        rows = list(client.query(f"select source, cadence, year_end from `{fqn}`").result())
        if not rows:
            return CheckResult(
                "Source data freshness", True, f"⚠ {fqn} is empty — nothing to check yet"
            )

        this_year = datetime.now(UTC).year
        slack = settings.source_freshness_annual_slack_years
        overdue: list[str] = []
        fresh: list[str] = []
        for row in rows:
            cadence = (row.cadence or "annual").strip().lower()
            year_end = row.year_end
            if year_end is None:
                overdue.append(f"{row.source} (no year_end)")
                continue
            # 'monthly' sources should always carry the current year — except in January,
            # when the newest closed month can still belong to the previous one (COMEX is
            # D+30). Anything older than that has stopped arriving.
            floor = this_year - (slack if cadence == "annual" else 1)
            if int(year_end) < floor:
                overdue.append(f"{row.source} {cadence} ends {year_end} < {floor}")
            else:
                fresh.append(f"{row.source}={year_end}")

        if overdue:
            return CheckResult(
                "Source data freshness",
                True,  # warn, not fail — a lagging source is a signal to look, not a broken env
                "⚠ behind its cadence: "
                + " · ".join(sorted(overdue))
                + f" (annual slack={slack}y; check the source's publication calendar and "
                "the monthly trigger before assuming the pipeline broke)",
            )
        return CheckResult(
            "Source data freshness",
            True,
            f"every source current: {' · '.join(sorted(fresh))} (annual slack={slack}y)",
        )
    except Exception as exc:
        return CheckResult("Source data freshness", False, str(exc)[:120])


def _check_ingest_heartbeat(settings: Settings) -> CheckResult:
    """Did each scheduled ingest actually RUN inside its own cadence window?

    The companion to "Source data freshness", and the half that check explicitly cannot
    do. Freshness asks whether the DATA advanced — which stays legitimately still between
    publication windows. This asks whether the RUN happened, which must be true every
    window regardless of whether the source had anything to give.

    Expected window per source is its own `IngestSpec.cadence_days` plus
    `HEARTBEAT_SLACK_DAYS` of grace. The cadence is declared per source rather than
    inferred from `in_all`, which stopped meaning "daily" when the batch went weekly
    (2026-08-28) and only bcb-currency kept a daily trigger.

    A source that has never reported is exempt only while the exemption still MEANS
    something: until the heartbeat table itself has existed longer than that source's
    window. Before that, silence is expected (the table starts empty, and crying wolf on
    day one is how a check gets ignored). After it, silence stops being "not yet" and
    becomes the loudest signal there is — a trigger created wrong and never fired once.
    That case used to be invisible here, and it is exactly the case a NEW scheduler is
    in: the weekly batch (2026-08-28) had never executed, and this check answered
    "every scheduled ingest ran".
    """
    try:
        from embrapa_dashboard import ingestion_heartbeat
        from embrapa_dashboard.cli import INGESTS

        client = bigquery.Client(
            project=settings.gcp_project_id,
            location=settings.bq_location,
            credentials=get_credentials(settings),
        )
        fqn = ingestion_heartbeat.table_fqn(settings)
        rows = {
            r.source: r.last_run
            for r in client.query(
                f"select source, max(run_ts) as last_run from `{fqn}` group by source"
            ).result()
        }
        if not rows:
            return CheckResult(
                "Ingest heartbeat",
                True,
                "⚠ no heartbeat recorded yet — expected until the next scheduled run lands",
            )

        now = datetime.now(UTC)
        # How long we have been in a position to observe anything at all. The table's own
        # creation time is the honest reference: before it existed no source COULD have
        # reported, so absence says nothing; after it has outlived a source's window,
        # absence says everything.
        watched_days = (now - client.get_table(fqn).created).total_seconds() / 86400

        overdue: list[str] = []
        never: list[str] = []
        pending: list[str] = []
        seen: list[str] = []
        for spec in INGESTS:
            last = rows.get(spec.name)
            window = spec.cadence_days + settings.heartbeat_slack_days
            if last is None:
                # Never reported. Only an answer once the table is older than the window.
                if watched_days > window:
                    never.append(f"{spec.name} (nunca, {watched_days:.0f}d observando)")
                else:
                    pending.append(spec.name)
                continue
            age_days = (now - last).total_seconds() / 86400
            # The window is the source's OWN cadence plus a grace margin — not a guess
            # from `in_all`, which stopped meaning "daily" when the batch went weekly.
            if age_days > window:
                overdue.append(f"{spec.name} {age_days:.0f}d ago (> {window}d)")
            else:
                seen.append(f"{spec.name}={age_days:.0f}d")

        if overdue or never:
            parts = []
            if overdue:
                parts.append("parou de rodar: " + " · ".join(sorted(overdue)))
            # Distinct from "stopped": nothing ever arrived, and enough time has passed
            # that something should have. Points at the trigger's CREATION, not its health.
            if never:
                parts.append("nunca rodou: " + " · ".join(sorted(never)))
            return CheckResult(
                "Ingest heartbeat",
                True,  # warn — the trigger may be paused on purpose
                "⚠ "
                + " ; ".join(parts)
                + " (check Cloud Scheduler + the Job's executions — this is the TRIGGER, "
                "not the data)",
            )
        # Never say "every" over the subset that happens to have reported — the sources
        # still inside their first window are named, so the line accounts for all of them.
        msg = f"ran inside its window: {' · '.join(sorted(seen)) or 'nenhuma ainda'}"
        if pending:
            msg += " · sem primeiro registro, ainda dentro da janela: "
            msg += " · ".join(sorted(pending))
        return CheckResult("Ingest heartbeat", True, msg)
    except Exception as exc:
        return CheckResult("Ingest heartbeat", False, str(exc)[:120])


_INFRA_CHECKS: list[tuple[str, Callable[[Settings], CheckResult]]] = [
    ("env", _check_env),
    ("inflation-codes", _check_inflation_pivot_codes),
    ("currency-codes", _check_currency_series_codes),
    ("pam-variable-codes", _check_pam_variable_codes),
    ("ibge-variable-codes", _check_ibge_variable_codes),
    ("silvicultura-variable-codes", _check_silvicultura_variable_codes),
    ("adc", _check_adc),
    ("bq", _check_bq),
    ("gcs", _check_gcs),
]

# ★ Extension point: to register a new source, add it here +
# in BRONZE_TARGETS above. For sources without a public API (e.g. SEFAZ NFe via
# bulk download), the "check" can be a stub that returns
# CheckResult(name, ok=True, detail="no public probe"). See
# docs/adding_a_data_source.md.
SOURCE_CHECKS: list[tuple[str, Callable[[Settings], CheckResult]]] = [
    ("ibge", _check_ibge),
    ("silvicultura", _check_silvicultura),
    ("pam", _check_pam),
    ("ppm", _check_ppm),
    ("bcb", _check_bcb),
    ("comex", _check_comex),
    ("comtrade", _check_comtrade),
]

# ★ Extension point: each (dataset_attr, table_attr) references a field
# in Settings. _check_bronze_tables iterates over this list.
BRONZE_TARGETS: list[tuple[str, str]] = [
    ("bq_bronze_ibge_dataset", "bq_bronze_ibge_table"),
    # Same dataset as t289 — the two halves of one survey — but its own table.
    ("bq_bronze_ibge_dataset", "bq_bronze_silvicultura_table"),
    ("bq_bronze_pam_dataset", "bq_bronze_pam_table"),
    ("bq_bronze_ppm_dataset", "bq_bronze_ppm_herd_table"),
    ("bq_bronze_ppm_dataset", "bq_bronze_ppm_animal_table"),
    ("bq_bronze_bcb_dataset", "bq_bronze_bcb_inflation_table"),
    ("bq_bronze_bcb_dataset", "bq_bronze_bcb_currency_table"),
    ("bq_bronze_comex_dataset", "bq_bronze_comex_flows_table"),
    ("bq_bronze_comtrade_dataset", "bq_bronze_comtrade_flows_table"),
]


def _check_catalog_data_arrival(settings: Settings) -> CheckResult:
    """Cataloged produtos whose data never arrived in Gold — the generic net for the
    "registered, but the pipeline never fetched it" failure, for ANY banco.

    Each pipeline family solves scope growth its own way, because their economics differ:
    IBGE re-queries SIDRA over the full window when a resolved product is absent from
    Bronze; COMEX re-filters its archived raw when the product-filter fingerprint changes
    (no source hit at all); COMTRADE re-fetches a settled year when the recorded
    ``cmd_scope`` lacks a now-configured code. Three mechanisms, one promise — and COMTRADE
    had NO mechanism at all until 2026-08, so bamboo registered against it would have sat
    empty forever with nothing anywhere reporting the fact.

    This check is the source-agnostic backstop for that class: it does not care HOW a banco
    ingests, only whether what a researcher registered actually shows up. A future banco
    gets the same safety net for free, including one whose scope mechanism is missing or
    broken — which is exactly the case no per-pipeline test can cover.

    Advisory (ok=True): a produto registered minutes ago is legitimately still empty, so
    this reports rather than fails. Flask-free (direct BQ) so a bare ``embrapa doctor``
    runs it; any fault degrades to 'skipped'."""
    try:
        from embrapa_dashboard.gcp.clients import resolve_bq_client
        from embrapa_dashboard.serving import sql as sqlbuild

        bq = resolve_bq_client(settings)
        catalog_log = sqlbuild.table_ref(
            settings, "bq_research_inputs_dataset", settings.bq_produto_catalog_log_table
        )
        gold_union = " union all ".join(
            f"select '{src}' as src, {col} as code from "
            f"`{sqlbuild.table_ref(settings, 'bq_gold_dataset', tbl)}`"
            for src, (tbl, col) in sqlbuild.GOLD_CODE_SOURCES.items()
        )
        sql = f"""
            with ativos as (
              select codigo_produto, banco from (
                select codigo_produto, banco, active, row_number() over (
                  partition by codigo_produto, banco order by edited_at desc, change_id desc
                ) as _rn from `{catalog_log}`
              ) where _rn = 1 and active
            ),
            gold as (select distinct src, code from ({gold_union}))
            select a.banco, a.codigo_produto
            from ativos a
            left join gold g on g.src = a.banco and g.code = a.codigo_produto
            where g.code is null
            order by a.banco, a.codigo_produto
        """
        rows = list(bq.query(sql).result())
        if not rows:
            return CheckResult(
                "Catalog → Gold arrival", True, "every cataloged produto has data in Gold"
            )
        by_banco: dict[str, list[str]] = {}
        for r in rows:
            by_banco.setdefault(r.banco, []).append(r.codigo_produto)
        detail = " · ".join(f"{b}: {','.join(c)}" for b, c in sorted(by_banco.items()))
        return CheckResult(
            "Catalog → Gold arrival",
            True,
            f"{len(rows)} cataloged produto(s) with NO Gold data — {detail}. Expected right "
            "after a registration; if it persists past an ingest + dbt build, that banco's "
            "pipeline is not picking the code up.",
        )
    except Exception as exc:  # never fail — advisory
        return CheckResult("Catalog → Gold arrival", True, f"skipped: {str(exc)[:100]}")


def _check_curation_referential_integrity(settings: Settings) -> CheckResult:
    """Do the curation logs still point at things that EXIST?

    Two writes a researcher makes daily reference a vocabulary defined elsewhere, and
    both stored the reference without checking it:

    * a catalog entry names an ``agrupamento_id``, which must exist in the agrupamentos
      registry. On 2026-08-29 a bulk reorganization wrote 37 entries naming groups it
      never created. Nothing failed: the write succeeded, the log was consistent with
      itself, and the products simply vanished from every grouped view — surfacing only
      as the "Sem agrupamento registrado (38)" heading a human happened to read. The
      writer now rejects this; a violation reaching here arrived by some path that
      bypasses the writer (a direct BQ insert, a restored backup, a registry row
      deleted after the fact), which is exactly what a checker is for.
    * a classification names an industrialization level. The writer is deliberately
      OPEN-vocabulary (it stores a level outside the scale), so a typo'd level leaves
      that product invisible to every level slice AND absent from "sem classificação" —
      the same silent hole, one axis over. Measured 2026-08-29: 308 classifications
      across 5 levels, all valid; the invariant holds and nothing was enforcing it.

    FAILS (ok=False) rather than advising: unlike a tombstoned product, neither
    condition is ever legitimate. Reads only the two small append-logs — no Gold scan,
    so it is free. Any fault (tables absent, no perms) degrades to 'skipped', because a
    cold install must not report a red integrity check it has no data to fail.
    """
    try:
        from embrapa_dashboard.gcp.clients import resolve_bq_client
        from embrapa_dashboard.serving import agrupamentos
        from embrapa_dashboard.serving import sql as sqlbuild
        from embrapa_dashboard.webapi.seam_attribute_engineering import CUR_LEVELS

        bq = resolve_bq_client(settings)
        catalog_log = sqlbuild.table_ref(
            settings, "bq_research_inputs_dataset", settings.bq_produto_catalog_log_table
        )
        nivel_log = sqlbuild.table_ref(
            settings,
            "bq_research_inputs_dataset",
            settings.bq_code_industrialization_log_table,
        )
        registered = set(agrupamentos._current_groups(bq, agrupamentos._group_log_ref(settings)))

        # Latest-wins per key, exactly as every reader collapses these logs.
        grupo_sql = f"""
            select codigo_produto, banco, agrupamento_id from (
              select codigo_produto, banco, agrupamento_id, active, row_number() over (
                partition by codigo_produto, banco order by edited_at desc, change_id desc
              ) as _rn from `{catalog_log}`
            ) where _rn = 1 and active
              and agrupamento_id is not null and agrupamento_id != ''
        """
        pendentes = [
            (r.codigo_produto, r.banco, r.agrupamento_id)
            for r in bq.query(grupo_sql).result()
            if r.agrupamento_id not in registered
        ]

        nivel_sql = f"""
            select source, code, industrialization_level from (
              select source, code, industrialization_level, row_number() over (
                partition by source, code order by edited_at desc, change_id desc
              ) as _rn from `{nivel_log}`
            ) where _rn = 1 and industrialization_level != ''
        """
        # '' is the explicit CLEAR (latest-wins un-classification), not a bad value.
        fora_da_escala = [
            (r.source, r.code, r.industrialization_level)
            for r in bq.query(nivel_sql).result()
            if r.industrialization_level not in CUR_LEVELS
        ]

        problemas = []
        if pendentes:
            ids = sorted({g for _, _, g in pendentes})
            problemas.append(
                f"{len(pendentes)} catalog entr(ies) name {len(ids)} unregistered "
                f"agrupamento(s) ({', '.join(ids[:5])}) — those produtos disappear from "
                "every grouped view; register the group (its name must slug to this id) "
                "or re-point the entries"
            )
        if fora_da_escala:
            niveis = sorted({n for _, _, n in fora_da_escala})
            problemas.append(
                f"{len(fora_da_escala)} classification(s) use {len(niveis)} level(s) "
                f"outside the scale ({', '.join(niveis[:5])}) — invisible to every level "
                "filter and absent from 'sem classificação'"
            )
        if problemas:
            return CheckResult("Curation referential integrity", False, "; ".join(problemas))
        return CheckResult(
            "Curation referential integrity",
            True,
            "every agrupamento_id registered, every level within the scale",
        )
    except Exception as exc:  # cold install / no perms — never a red check without data
        return CheckResult("Curation referential integrity", True, f"skipped: {str(exc)[:100]}")


_POSTCHECKS: list[tuple[str, Callable[[Settings], CheckResult]]] = [
    ("bronze", _check_bronze_tables),
    ("serving", _check_serving_marts),
    ("catalog-parity", _check_catalog_resolver_parity),
    ("curation-backup", _check_curation_backup),
    ("curation-integrity", _check_curation_referential_integrity),
    ("orphans", _check_orphan_lifecycle),
    ("catalog-arrival", _check_catalog_data_arrival),
    ("backup", _check_backup_freshness),
    ("source-freshness", _check_source_data_freshness),
    ("heartbeat", _check_ingest_heartbeat),
]

# Total ordering of the checks. Each block can be extended without changing this alias.
CHECKS = _INFRA_CHECKS + SOURCE_CHECKS + _POSTCHECKS


def run_all(settings: Settings | None = None) -> list[CheckResult]:
    """Execute every probe and return the results in the same order as CHECKS."""
    settings = settings or get_settings()
    return [fn(settings) for _, fn in CHECKS]
