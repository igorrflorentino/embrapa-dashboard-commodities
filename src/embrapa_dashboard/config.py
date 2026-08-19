"""Runtime settings loaded from environment / .env file."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _current_year() -> int:
    return datetime.now(UTC).year


def _parse_code_label(raw: str) -> dict[str, str]:
    """Parse 'CODE:LABEL,CODE:LABEL' into {code: label}.

    Whitespace around items is ignored. Duplicate codes raise ValueError.
    """
    result: dict[str, str] = {}
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" not in item:
            raise ValueError(f"Expected 'CODE:LABEL', got {item!r}")
        code, label = item.split(":", 1)
        code, label = code.strip(), label.strip()
        if not code or not label:
            raise ValueError(f"Empty code or label in {item!r}")
        if not (code.isascii() and code.isdigit()):
            # SGS/NCM ids are ASCII-numeric; a non-numeric code usually means the
            # CODE:LABEL pair was transposed (e.g. 'IPCA:433' instead of
            # '433:IPCA'). `isascii()` also rejects unicode digits (fullwidth
            # '４３３', superscripts) that pass isdigit() but aren't valid ids.
            # Fail loudly here instead of downstream.
            raise ValueError(
                f"Series code must be numeric, got {code!r} in {item!r} "
                "(expected 'CODE:LABEL', e.g. '433:IPCA')"
            )
        if code in result:
            raise ValueError(f"Duplicate series code {code!r}")
        result[code] = label
    return result


def _require_code_lengths(
    mapping: dict[str, str], valid_lengths: set[int], kind: str
) -> dict[str, str]:
    """Raise if any code's digit-length is outside ``valid_lengths``.

    COMEX codes have fixed widths (NCM=8, HS heading=4, HS chapter=2). Without this
    check a misconfigured code — e.g. a 7-digit NCM — passes ``_parse_code_label``
    (numeric+ASCII only) but then matches ZERO rows in the ingest product filter
    (``client.py`` does an exact ``isin``), so the chunk is silently marked
    "skipped — no configured products". Fail loudly at config-load instead.
    """
    for code in mapping:
        if len(code) not in valid_lengths:
            expected = " or ".join(str(n) for n in sorted(valid_lengths))
            raise ValueError(
                f"{kind} code {code!r} has {len(code)} digits; expected {expected}. "
                "A wrong-width code silently matches no rows in the ingest filter."
            )
    return mapping


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── GCP / GCS ────────────────────────────────────────────────────────────
    gcp_project_id: str = Field(..., description="GCP project that owns BigQuery + GCS")
    gcs_bucket: str | None = Field(default=None, description="Defaults to <project>-datalake")
    # Verbatim source extracts (two-phase ingestion): raw/<source>/<dataset>/...
    # Bronze derives from this; re-filtering never re-hits the source.
    gcs_raw_prefix: str = Field(default="raw")
    # "US" multi-region is a portable fallback; .env.example and
    # dbt/profiles.yml use the project's actual region (us-central1). Keep
    # BQ_LOCATION set so this default never silently disagrees with them.
    bq_location: str = Field(default="US")
    gcp_impersonation_sa: str | None = Field(
        default=None,
        description="SA email to impersonate via ADC (enterprise mode). "
        "Set to sa-secret-reader-prod@<project>.iam.gserviceaccount.com.",
    )

    # ─── BigQuery dataset / table names ───────────────────────────────────────
    bq_bronze_ibge_dataset: str = Field(default="bronze_ibge")
    bq_bronze_pam_dataset: str = Field(default="bronze_pam")
    bq_bronze_ppm_dataset: str = Field(default="bronze_ppm")
    bq_bronze_bcb_dataset: str = Field(default="bronze_bcb")
    bq_bronze_comex_dataset: str = Field(default="bronze_comex")
    bq_bronze_ibge_table: str = Field(default="sidra_t289_raw")
    bq_bronze_pam_table: str = Field(default="sidra_t5457_raw")
    # PPM spans two SIDRA tables → two Bronze tables in one dataset (Silver unions).
    bq_bronze_ppm_herd_table: str = Field(default="sidra_t3939_raw")
    bq_bronze_ppm_animal_table: str = Field(default="sidra_t74_raw")
    bq_bronze_bcb_inflation_table: str = Field(default="inflation_series_raw")
    bq_bronze_bcb_currency_table: str = Field(default="currency_series_raw")
    bq_bronze_comex_flows_table: str = Field(default="comex_flows_raw")
    bq_silver_dataset: str = Field(default="silver")  # consumed by dbt, not Python runtime
    # Un-prefixed name. dbt's generate_schema_name macro adds the dev prefix
    # (dev → dbt_dev_gold, prod → gold), so this must stay "gold". Also what
    # `backup-gold` / doctor read.
    bq_gold_dataset: str = Field(default="gold")

    # ─── IBGE ─────────────────────────────────────────────────────────────────
    ibge_table_id: str = Field(default="289")
    ibge_classification_id: str = Field(default="193")
    # The 2 SIDRA t289 variables silver_ibge_pevs pivots: 144 (quantidade) + 145
    # (valor). PEVS fetches v/all into Bronze, then Silver FILTERS to these two.
    # ⚠ NAME coupling: dbt/dbt_project.yml reads the SAME env vars —
    # `env_var('IBGE_VARIABLE_QUANTITY_CODE', '144')` / `..._VALUE_CODE`, '145')`.
    # Keep the key names AND defaults identical in both files: a typo drops that
    # variable from Silver, emptying the Gold column silently. `embrapa doctor`
    # validates parity (doctor._check_ibge_variable_codes), mirroring PAM.
    ibge_variable_quantity_code: str = Field(default="144")
    ibge_variable_value_code: str = Field(default="145")
    # PEVS = EXTRACTIVE vegetal/forestry production. SIDRA t289/c193 codes:
    #   3405 Castanha-do-pará · 3435 Madeira em tora · 3434 Lenha ·
    #   3433 Carvão vegetal · 3450 Pinheiro brasileiro (Araucária, em tora) ·
    #   3403 Açaí (fruto, extractive). Cultivated crops (soja, milho, arroz,
    #   banana, mandioca, açaí cultivated) live in PAM, not here.
    # 3404 Castanha-de-caju (extractive) added 2026-08: the "Castanha-de-caju"
    # agrupamento existed in the catalog with ONLY comtrade codes and NO data at all —
    # an empty group in the dashboard. PEVS carries the extractive angle and PAM the
    # cultivated one, so the produto is now comparable across both, which is the point.
    ibge_product_codes: str = Field(default="3405,3435,3434,3433,3450,3403,3404")
    ibge_start_year: int | None = Field(
        default=None,
        description="None requires user to run `embrapa discover ibge-periods` first.",
    )
    ibge_end_year: int = Field(default_factory=_current_year)
    # Delta overlap (years). A routine `ingest ibge` (and `ingest all`) re-fetches
    # only from (latest Bronze year − this) forward — absorbing PEVS revisions of
    # recent years and picking up a newly published year — instead of re-pulling
    # the whole 1986→today window (a huge SIDRA request that can blow the slow-byte
    # deadline on an unattended Cloud Run job). `--full` ignores this; a cold
    # Bronze table also falls back to the full configured window.
    # ge=0: a NEGATIVE overlap would push the delta floor ABOVE latest_bronze_year,
    # skipping not-yet-absorbed recent years on a warm table (silent data gap).
    ibge_delta_overlap_years: int = Field(default=1, ge=0)

    # ─── IBGE PAM (Produção Agrícola Municipal — SIDRA table 5457) ─────────────
    # The second IBGE/SIDRA source: ANNUAL crop production by municipality. Same
    # SIDRA client + two-phase Bronze as PEVS (see ibge/pam_pipeline.py), just a
    # different table/classification/products and its OWN Bronze + raw-zone segment
    # (dataset "pam"), so the two never collide on --from-raw replays.
    pam_table_id: str = Field(default="5457")
    # Classification 782 = "produto das lavouras temporárias e permanentes".
    pam_classification_id: str = Field(default="782")
    # CULTIVATED crops (PAM is annual ag production by municipality). SIDRA c782:
    #   40124 Soja · 40122 Milho · 40139 Café (Total) · 40106 Cana-de-açúcar ·
    #   40102 Arroz · 40136 Banana (cacho) · 40119 Mandioca · 45982 Açaí
    #   (cultivated — distinct from PEVS extractive açaí 3403). Café/cana are
    #   kept from the first cut though they're outside the core commodity list.
    # 40143 Castanha de caju + 40145 Coco-da-baía added 2026-08 (see ibge_product_codes).
    # 40330 "Caju" (the pseudofruit) is deliberately NOT included: it is a different produto
    # from the nut, and folding it into the "Castanha-de-caju" agrupamento would conflate
    # fruit with nut. It deserves its own agrupamento if a researcher wants it.
    pam_product_codes: str = Field(
        default="40124,40122,40139,40106,40102,40136,40119,45982,40143,40145"
    )
    # Full PAM history (SIDRA 5457 runs to 1974). The monetary value is now
    # reform-correct via the historical_currency_factors join in silver_ibge_pam,
    # so pre-1994 years (Mil Cruzeiros/Cruzados/…) land in nominal R$ — no lean
    # floor needed. The END floats with the current year (like IBGE PEVS) so the
    # delta absorbs PAM's recent-year revisions and auto-picks-up a newly published
    # year; SIDRA simply returns no rows for years not yet published. The first
    # backfill is heavy — use `ingest ibge-pam --full` (or chunk it) once.
    pam_start_year: int | None = Field(default=1974)
    pam_end_year: int = Field(default_factory=_current_year)
    # Same delta semantics as IBGE PEVS (PAM also revises only recent years).
    pam_delta_overlap_years: int = Field(default=1, ge=0)
    # SIDRA variables to FETCH for PAM (the client requests only these, not v/all).
    # Table 5457 publishes 8 variables via v/all, but 3 are useless "percentual"
    # series — fetching all 8 inflates each (state, year) response past SIDRA's
    # per-request cell limit for a dense state (MG × 8 crops), making even a
    # 1-year backfill window impossible. These 5 are exactly the substantive ones
    # silver_ibge_pam keeps. MUST stay in sync with the dbt vars pam_variable_*
    # (dbt_project.yml): 8331 área plantada · 216 área colhida · 214 quantidade ·
    # 112 rendimento · 215 valor. `embrapa doctor` is the place to add a parity check.
    pam_variable_codes: str = Field(default="8331,216,214,112,215")

    # ─── IBGE PPM (Pesquisa da Pecuária Municipal — SIDRA tables 3939 + 74) ────
    # The THIRD IBGE/SIDRA source: ANNUAL livestock survey by municipality. Unlike
    # PEVS/PAM (one SIDRA table each), PPM spans TWO tables with different measures,
    # ingested into two Bronze tables and unioned in silver_ibge_ppm (see
    # ibge/ppm_pipeline.py). Both tables run 1974→latest; END floats like PEVS/PAM.
    #
    # Table 3939 "Efetivo dos rebanhos" — herd HEADCOUNT, a STOCK with NO value.
    # Classification 79 (tipo de rebanho). Variable 105 (Cabeças). The herd codes
    # EXCLUDE the subset categories 32795 (Suíno - matrizes) and 32793 (Galináceos
    # - galinhas): both are SUBSETS of their "- total" parent, so summing a national
    # headcount across products would double-count them.
    ppm_herd_table_id: str = Field(default="3939")
    ppm_herd_classification_id: str = Field(default="79")
    ppm_herd_product_codes: str = Field(default="2670,2675,2672,32794,2681,2677,32796,2680")
    ppm_herd_variable_codes: str = Field(default="105")

    # Table 74 "Produção de origem animal" — milk/eggs/honey/wool, a FLOW with value.
    # Classification 80 (tipo de produto de origem animal). Variables 106 (quantity,
    # unit varies by product: Mil litros / Mil dúzias / Quilogramas) + 215 (Valor da
    # produção, Mil Reais 1994+). The 1000215 "percentual do total geral" series is
    # intentionally EXCLUDED (a derived share, not a substantive measure — like PAM).
    ppm_animal_table_id: str = Field(default="74")
    ppm_animal_classification_id: str = Field(default="80")
    ppm_animal_product_codes: str = Field(default="2682,2685,2686,2687,2683,2684")
    ppm_animal_variable_codes: str = Field(default="106,215")

    # Both PPM tables run 1974→2024 today; END floats with the current year (like
    # PEVS/PAM) so the delta absorbs recent-year revisions and auto-picks-up a newly
    # published year. Same delta semantics as PEVS/PAM (PPM also revises only recent
    # years). The first backfill is heavy — use `ingest ibge-ppm --full` once.
    ppm_start_year: int | None = Field(default=1974)
    ppm_end_year: int = Field(default_factory=_current_year)
    ppm_delta_overlap_years: int = Field(default=1, ge=0)

    # ─── Catalog-driven ingestion (Curadoria as source of truth) ──────────────
    # When TRUE, the IBGE/SIDRA pipelines resolve their product-code list from the
    # editable Curadoria catalog (research_inputs.produto_catalog_log, active rows
    # per banco) instead of the *_product_codes env fields — making the "Cadastro
    # de produtos" admin view the single source of truth for WHAT is ingested. The
    # engineering metadata (table/classification/variable ids, delta windows) stays
    # here regardless. Default FALSE keeps the current env-driven behaviour, so the
    # inversion is a one-flag, fully reversible cutover: flip it per environment
    # only after `embrapa catalog-seed-from-env` + a green `embrapa doctor` parity
    # check. Even when TRUE the resolver ALWAYS falls back to the env codes if the
    # catalog is absent/empty/unreachable, so a missing catalog never breaks a run.
    catalog_authoritative_ingestion: bool = Field(default=False)
    # Safety cap for the catalog-driven resolver: if the catalog resolves MORE than
    # this many codes for a single banco, the resolver refuses it (logs + falls back
    # to the env codes) instead of firing an accidental huge/expensive SIDRA pull —
    # a fat-finger guard, since a researcher edit now drives the nightly job. Well
    # above the real ~6-8 codes per banco, below a runaway. ge=1.
    catalog_resolver_max_codes: int = Field(default=500, ge=1)

    # ─── BCB ──────────────────────────────────────────────────────────────────
    bcb_inflation_series: str = Field(default="433:IPCA,189:IGPM,190:IGPDI")
    # The 3 series codes the Gold pivot wires into val_real_{ipca,igpm,igpdi}_*.
    # dbt reads each via env_var(); each MUST appear in bcb_inflation_series or
    # the matching Gold columns silently come out NULL. `embrapa doctor`
    # validates this (see doctor._check_inflation_pivot_codes).
    #
    # ⚠ NAME coupling: these three env-var NAMES are read INDEPENDENTLY here and in
    # dbt/dbt_project.yml — `env_var('BCB_INFLATION_SERIES_IPCA_CODE', '433')` etc. The
    # literal key names AND the hardcoded fallbacks (433/189/190) must stay identical in
    # both files. Renaming a key in only one place makes dbt silently fall back to its
    # default while config.py reads the new name — a divergence doctor's value-check
    # won't catch. Change both files together.
    bcb_inflation_series_ipca_code: str = Field(default="433")
    bcb_inflation_series_igpm_code: str = Field(default="189")
    bcb_inflation_series_igpdi_code: str = Field(default="190")
    # Daily PTAX "venda" rates (BRL per foreign unit): SGS 1 = USD, 21619 = EUR.
    # The Gold deflation averages these per year (PEVS) / per month (COMEX), so a
    # daily series is the most accurate base. The previous 3694/4393 were
    # wrong: 3694 is annual and 4393 is not a BRL-per-unit FX rate at all.
    bcb_currency_series: str = Field(default="1:USD,21619:EUR")
    # Every configured inflation/FX series is ingested from this single start year. IGP-DI
    # (SGS 190) actually has monthly history back to 1944, but at 1980 the deflated
    # val_real_* columns are honestly NULL for production years before an index's inception
    # (IPCA/IGP-M ~1980/1989) — including 1974–1979 PAM/PPM, which IGP-DI alone could deflate.
    # Lower this (e.g. to 1974) only if full early-history deflation is wanted; IPCA/IGP-M
    # simply 404→empty before they exist (the client maps 404 to an empty concat).
    bcb_start_year: int = Field(default=1980)
    bcb_end_year: int = Field(default_factory=_current_year)

    # ─── COMEX (MDIC Comex Stat bulk CSV) ─────────────────────────────────────
    comex_csv_base_url: str = Field(
        default="https://balanca.economia.gov.br/balanca/bd/comexstat-bd/ncm"
    )
    # Which flows to ingest — closed domain {export, import}, mapped to the
    # EXP_/IMP_ file prefixes by the client.
    comex_flows: str = Field(default="export,import")
    # CODE:LABEL of full 8-digit NCMs to keep regardless of chapter. Codes verified
    # against the official Siscomex NCM table (Res. Gecex 812/2025). Used ONLY for
    # commodities whose HS4 heading is NOT clean (would pull unrelated products):
    #   castanha — 0801 also holds coconut + cashew, so the exact Brazil-nut leaves
    #     (the MDIC NCM already reports 08012100/08012200 across the whole 1997+
    #     series — no pre-split code needed here, unlike COMTRADE's international HS);
    #   açaí/cupuaçu — only the dedicated "purê" leaves (2007.99.21/.26) are
    #     isolable (the generic fruit buckets mix dozens of fruits → omitted);
    #   mandioca — its forms span 0714 (also other roots) / 1106 / 1108 / 1903, so
    #     the exact leaves (these are stable across NCM revisions).
    # Commodities with a CLEAN heading (soja, milho, arroz, banana) use
    # comex_heading_codes instead — that captures EVERY NCM under the heading across
    # all revisions (the MDIC bulk reports each year under the NCM then in force —
    # e.g. soja is 12010090 pre-2017, not 12019000), giving complete history.
    comex_ncm_codes: str = Field(
        default=(
            "08012100:castanha_com_casca,08012200:castanha_sem_casca,"
            "20079921:acai_pure,20079926:cupuacu_pure,"
            "07141000:mandioca_raiz,11062000:mandioca_farinha,"
            "11081400:mandioca_fecula,19030000:tapioca,"
            "14011000:bambu_cestaria,20059100:bambu_brotos,"
            # Coco + castanha de caju (2026-08). Leaves, not the 0801 heading: that
            # heading also holds castanha-do-pará, already listed explicitly above.
            #
            # The three SH6-080111 leaves are one produto across a revision, and the
            # direction is CONSOLIDATION, not a split: 08011110 (secos sem casca) and
            # 08011190 (outros secos) both run 1997-2014 and stop, while 08011100
            # (cocos secos/dessecados) carries it from 2015 on. Ingesting only the two
            # retired codes — as this first shipped — made coco dessecado end in 2014
            # and silently vanish. All three are ingested and the seed maps the retired
            # pair onto 08011100 (a merge has an unambiguous target, unlike a split).
            "08011100:coco_seco,08011110:coco_seco_sem_casca,08011190:coco_seco_outros,"
            "08011200:coco_endocarpo,08011900:coco_fresco,"
            "08013100:caju_com_casca,08013200:caju_sem_casca"
        )
    )
    # CODE:LABEL of 2-digit HS chapters to keep wholesale. Empty by default —
    # madeira moved to explicit 4-digit headings (see comex_heading_codes) to drop
    # manufactured-wood articles (móveis/marcenaria) that polluted the whole-chapter
    # scope and are not comparable to PEVS extractive output.
    # Bambu (2026-08): registrado no catalogo de Curadoria e ingerido por NCM EXPLICITA,
    # nao por heading. Cada SH6 de bambu tem um unico NCM (sem desdobramento brasileiro),
    # e as headings seriam largas demais: 1401 arrasta ratan/vime/junco e 2005 traria todo
    # o capitulo de conservas vegetais. Escopo = materia-prima agricola apenas (bambu para
    # cestaria + brotos comestiveis); manufaturados de bambu (moveis, pisos, utensilios,
    # celulose) ficam FORA, pela mesma razao que a madeira largou o capitulo inteiro.
    comex_chapter_codes: str = Field(default="")
    # CODE:LABEL of 4-digit HS headings (prefix match on NCM[:4]) — captures EVERY
    # 8-digit NCM under the heading across all NCM revisions (so a code retired by a
    # revision is still ingested; retired→current is then normalized in silver via
    # comex_ncm_succession). Wood (raw/primary forms only): 4401 lenha/resíduos ·
    # 4402 carvão · 4403 toras · 4407 serrada. Clean-heading commodities: 0803
    # banana · 1005 milho · 1006 arroz · 1201 soja (grão) · 1507 soja (óleo) ·
    # 2304 soja (farelo). Each heading contains ONLY its commodity.
    comex_heading_codes: str = Field(
        default=(
            "4401:madeira_lenha_residuos,4402:madeira_carvao,"
            "4403:madeira_tora,4407:madeira_serrada,"
            "0803:banana,1005:milho,1006:arroz,"
            "1201:soja_grao,1507:soja_oleo,2304:soja_farelo"
        )
    )
    comex_start_year: int = Field(default=1997)
    comex_end_year: int = Field(default_factory=_current_year)

    # ─── UN COMTRADE (global trade, keyed API) ────────────────────────────────
    # Free registered subscription key — read from .env, never committed. Empty
    # means "not configured" (doctor warns; ingest errors with a clear message).
    comtrade_api_key: str = Field(default="")
    comtrade_api_base_url: str = Field(default="https://comtradeapi.un.org/data/v1/get")
    bq_bronze_comtrade_dataset: str = Field(default="bronze_comtrade")
    bq_bronze_comtrade_flows_table: str = Field(default="comtrade_flows_raw")
    # HS code prefixes to keep (CODE:LABEL) — mirror the COMEX scope so Brazil can
    # be compared against the world for the same commodities. These are the SCOPE
    # codes; the ingest expands each to its 6-digit HS leaves via the public HS
    # reference (Comtrade returns data only at the requested code level). Prefixes
    # of any length work (client.list_hs6_codes does startswith). açaí and cupuaçu
    # have NO isolable HS6 (the purê falls in the mixed 200799 bucket) so they are
    # deliberately absent here.
    #
    # FULL-HISTORY (retired codes): the public HS reference is COMBINED across
    # revisions, so a 4-digit prefix already enumerates BOTH the current and the
    # retired 6-digit leaves under it — banana 0803 → {080300 (pre-HS2012), 080310,
    # 080390}; soja 1201 → {120100, 120110, 120190}; wood 4401/4403/4407 → the old
    # AND new ch.44 leaves. The ONLY retired code a prefix misses is castanha's
    # 080120 (pre-HS2007), because castanha is narrowed to the exact 080121/080122
    # leaves (the bare 0801 would also pull coconut + cashew) — so 080120 is added
    # explicitly below. Retired codes are then TRANSLATED to their current
    # equivalent in silver_comtrade_flows (comtrade_hs_succession seed), so the Gold
    # / serving / dashboard only ever expose current codes.
    comtrade_cmd_codes: str = Field(
        default=(
            "080121:castanha_com_casca,080122:castanha_sem_casca,"
            "080120:castanha_historica,"
            "4401:madeira_lenha_residuos,4402:madeira_carvao,"
            "4403:madeira_tora,4407:madeira_serrada,"
            "0803:banana,"
            "071410:mandioca_raiz,110620:mandioca_farinha,"
            "110814:mandioca_fecula,190300:tapioca,"
            "1201:soja_grao,150710:soja_oleo_bruto,150790:soja_oleo_refinado,"
            "230400:soja_farelo,"
            "1005:milho,"
            "1006:arroz,"
            "140110:bambu_cestaria,200591:bambu_brotos,"
            # Coco + castanha de caju — the HS6 twins of the NCMs in comex_ncm_codes.
            "080111:coco_seco,080112:coco_endocarpo,080119:coco_fresco,"
            "080131:caju_com_casca,080132:caju_sem_casca"
        )
    )
    # Bambu: os SH6 equivalentes aos NCM em comex_ncm_codes (140110 cestaria / 200591
    # brotos), para que o mesmo agrupamento "Bambu" cruze as duas fontes de comercio.
    # Flow codes (UN Comtrade flowCode). TOTALS-ONLY design (2026-07): only the two
    # direction TOTALS are ingested — X=export (grand total, INCLUDES its DX/RX
    # sub-flows) and M=import (grand total, INCLUDES FM/RM/MIP…). The sub-flows
    # (RX/RM/DX/FM/…) are deliberately NOT requested: they are subsets of X/M, so
    # summing them alongside X/M double-counts. Keeping only the totals makes every
    # country's data homogeneous (all report X/M) — see the totals-only rationale on
    # comtrade_customs_code below and the frozen "tipo de mercado" memory.
    comtrade_flows: str = Field(default="X,M")
    # Customs procedure (UN Comtrade customsCode) to pull. TOTALS-ONLY: request ONLY
    # the aggregate C00 ("todos os regimes / total"). Most reporters (Brazil: 100%)
    # provide ONLY C00; where a reporter also breaks C00 into per-regime rows (C01…),
    # C00 = Σ(breakdowns), so keeping only C00 is lossless for the total and avoids the
    # C00-vs-breakdown double-count. This also FREEZES the "tipo de mercado" feature:
    # with no customs-procedure detail in the base, there is nothing to classify. Empty
    # string ⇒ omit the filter (pull every customsCode — the pre-2026-07 behaviour).
    # silver_comtrade_flows also hard-filters customs_code = C00, so this is a
    # download-reduction knob, not the correctness guarantee.
    comtrade_customs_code: str = Field(default="C00")
    # Reporters to pull ("all" = every reporting country, expanded by the client
    # from the Comtrade Reporters reference; or a comma list of M49 codes). The
    # keyed endpoint rejects "all" literally, so the client enumerates and batches.
    # DEFAULT = "all" (2026-07): every reporter × ALL partners, so the base carries the
    # complete bilateral matrix (Brazil's own trade AND the mirror — what every partner
    # declares about Brazil — AND world market-share). Duplication is guarded downstream:
    # the serving readers reporter-pin (never sum a country's exports AND another's
    # imports of the same trade), Silver drops the World partner + keeps only the
    # customs/flow/mode totals, and latest-batch dedup replaces re-published years. A
    # global pull is expensive/slow (multi-day, quota-bounded) — see
    # docs/comtrade_world_backfill.md; narrow to "76" (Brazil) for a cheap partial pull.
    comtrade_reporters: str = Field(default="all")
    # ISO-A3 of the reporter treated as "home" (Brazil) when the serving layer
    # splits Brazil's own trade from the world total — COMTRADE ingests ALL
    # reporters, so this filter is applied at query time (serving), never at
    # ingestion. Backs crossSeries: exp_value/imp_value filter to this reporter;
    # world_exp sums over all reporters.
    comtrade_brazil_iso: str = Field(default="BRA")
    # History window. START = 2000 (2026-07 decision): the all-reporters × all-partners
    # totals-only base is anchored at the year-2000 boundary — earlier years add little
    # for a homogeneous cross-country panel and multiply the (already multi-day) global
    # pull. The END floats with the current year (the pipeline always re-fetches the
    # latest year — Comtrade revises it — and lands an empty sentinel for past years with
    # no data so they resume-skip without re-billing quota). Retired pre-revision codes
    # are fetched (the combined HS reference enumerates them under the 4-digit prefixes,
    # plus the explicit castanha 080120) and then mapped to their current equivalent in
    # silver_comtrade_flows — see comtrade_cmd_codes above. silver_comtrade_flows also
    # floors reference_year at var('comtrade_min_year', 2000) — keep the two in sync.
    comtrade_start_year: int = Field(default=2000)
    comtrade_end_year: int = Field(default_factory=_current_year)
    # How many recent years (at/below comtrade_end_year) get RE-FETCHED on every run so
    # late reporter submissions and revisions are absorbed. UN Comtrade reporters file an
    # annual year with a ~1-2y lag, so a year fetched early lands with only a few of its
    # reporters present (a NON-empty but incomplete raw); without re-fetching that year the
    # other reporters' later submissions — and any revision to the early ones — are frozen
    # out forever (COMTRADE is also excluded from `reconcile`, so this window is the ONLY
    # convergence path). The re-fetch covers real AND empty raws within the window; older
    # years beyond it are settled and resume-skip. Set ≥ the true publication lag; 0 disables.
    comtrade_recent_refetch_years: int = Field(default=2)

    # ─── Cold-storage backup ──────────────────────────────────────────────────
    # `embrapa doctor` warns when the most recent gs://${GCS_BUCKET}/backups/
    # snapshot is older than this. Default 14d matches a typical bi-weekly
    # release cadence — bump it for projects that ship monthly.
    backup_staleness_days: int = Field(default=14)

    # `embrapa backup-gold` lists the Gold dataset and snapshots every table
    # whose name starts with this prefix. "gold_" matches every dbt-produced
    # Gold table while excluding ad-hoc / temp exploration tables.
    backup_gold_prefix: str = Field(default="gold_")

    # ─── Serving layer / dashboard data access ────────────────────────────────
    # Pre-aggregated marts + the SCD2 curation view the dashboard BFF (the Flask
    # webapi serving the React SPA) reads via Pushdown Computing. Un-prefixed
    # name (dbt's generate_schema_name adds the dev prefix: dev →
    # dbt_dev_serving, prod → serving). Point the deployed dashboard at
    # "serving"; a developer testing against dev data sets it to
    # "dbt_dev_serving".
    bq_serving_dataset: str = Field(default="serving")
    # Append-only researcher curation inputs (written by the dashboard, not dbt).
    bq_research_inputs_dataset: str = Field(default="research_inputs")
    # Per-CODE industrialization log — the primary curation grain. Backs
    # dim_code_industrialization_scd2 + the value-added analysis (COMEX exports
    # split by the curated 8-level Commodity → Manufaturado scale).
    bq_code_industrialization_log_table: str = Field(default="code_industrialization_log")
    # (customs procedure × flow) market-nature log — the SECOND curation grain,
    # reverted from the comtrade_market_nature seed (v1.9.0) back to the researcher-
    # editable matrix. Backs dim_flow_market_scd2, LEFT JOINed into
    # serving_comtrade_annual.market_nature (the "Tipo de mercado" filter + the
    # "Finalidade econômica" analysis).
    bq_flow_market_log_table: str = Field(default="flow_market_log")
    # ─── User feedback ("Reportar problema") ──────────────────────────────────
    # Append-only feedback/issue reports (bug/dúvida/sugestão) written by ANY
    # IAP-authenticated user, in the research_inputs dataset (auto-created on first write).
    bq_feedback_log_table: str = Field(default="feedback_log")
    # "Loop fechado": when BOTH are set, each report is ALSO opened as a GitHub issue
    # (best-effort — a failure never blocks/loses the BigQuery write). Repo as
    # "owner/name"; the token needs issues:write and comes from the env/Secret Manager,
    # NEVER committed. Leave both unset to keep feedback BigQuery-only.
    feedback_github_repo: str | None = Field(default=None)
    feedback_github_token: str | None = Field(default=None)
    # Per-author cooldown (seconds) on POST /api/feedback — debounces double-click duplicates
    # and basic abuse (audit SEC-2). 0 disables the throttle.
    feedback_cooldown_seconds: int = Field(default=5)

    # ─── Cache (flask-caching) ────────────────────────────────────────────────
    # SimpleCache (per-instance) scales to N Cloud Run instances for free: marts
    # converge within cache_default_timeout (nightly data), and the curation read
    # uses a SHORT TTL (cache_classification_timeout) so cross-instance staleness
    # is bounded — eventual consistency, no shared Redis. CACHE_TYPE=RedisCache +
    # CACHE_REDIS_URL is optional, only for *instant* cross-instance consistency
    # (see src/embrapa_dashboard/serving/cache.py).
    cache_type: str = Field(default="SimpleCache")
    cache_default_timeout: int = Field(default=600, description="Seconds; mart read TTL.")
    # Short TTL for the curation classification read; gateway.py reads the same
    # env var (CACHE_CLASSIFICATION_TIMEOUT) at decoration time. Keep it small —
    # it's the bound on cross-instance staleness that makes multi-instance free.
    cache_classification_timeout: int = Field(default=30, description="Seconds; curation read TTL.")
    cache_redis_url: str | None = Field(default=None)
    # Author email used when the IAP header is absent (local dev only). Leave
    # unset in production — IAP always supplies the header, and an unset fallback
    # makes an un-attributed write fail loudly instead of writing 'unknown'.
    dev_author: str | None = Field(default=None)
    # IAP backend audience for verifying the signed X-Goog-IAP-JWT-Assertion.
    # When SET (production behind IAP), the curation author is taken from the
    # cryptographically verified JWT, not the spoofable plaintext email header —
    # a direct request to the backend can no longer forge the audit author. With
    # the prod posture (Cloud Run DIRECT IAP) the value is the Cloud-Run-resource
    # audience code (Console → Security → IAP → ⋮ → "Get JWT audience code"); only
    # the future external-LB topology would use the backendServices form
    # /projects/<PROJECT_NUMBER>/global/backendServices/<BACKEND_SERVICE_ID>.
    # Leave UNSET for local dev (no IAP): the plaintext header + dev_author
    # path is used. See src/embrapa_dashboard/serving/iap.py.
    iap_audience: str | None = Field(default=None)

    # ─── Authorization + serving-path cost ceiling ────────────────────────────
    # Attribute editor ALLOWLIST — authorization (may you curate), distinct from IAP
    # authentication (who you are). NON-EMPTY → only these emails may POST a
    # curation edit (others get 403); EMPTY (default) preserves current behaviour:
    # any IAP-authenticated caller may curate. ATTRIBUTE_EDITORS_ALLOWED_EMAILS=a@x,b@y.
    attribute_editors_allowed_emails: str = Field(default="")
    # Attribute editor allowlist TABLE (research_inputs.<this>) — the Console-managed
    # alternative to the env var above: add/remove attribute editors by INSERT/DELETE rows
    # in the BigQuery Console, no redeploy. The effective allowlist is the UNION of
    # this table and ATTRIBUTE_EDITORS_ALLOWED_EMAILS; if BOTH are empty/absent, any
    # IAP-authenticated caller may curate (current behaviour). Auto-created.
    bq_attribute_editors_table: str = Field(default="attribute_editors")
    # Operator-editable banco metadata OVERRIDES (research_inputs.<this>) — the
    # Console-managed way to change a banco's maturity stage / note / planned date /
    # coverage labels WITHOUT a rebuild+redeploy of the SPA. Sparse: a row overrides
    # only the columns it sets; NULL columns (or no row) fall back to the registry
    # default (registries.py / bancos.js), which stays the source of truth. The API
    # merges it into /api/source-meta with the short curation TTL, so a flip like
    # beta→estavel reflects within cache_classification_timeout. Auto-created.
    bq_banco_metadata_table: str = Field(default="banco_metadata")
    # ─── Curadoria (catalog — what enters/exits the dashboard) ────────────────
    # Append-only log of the researcher-managed COMMODITY CATALOG: which commodities
    # are in the dashboard, their agrupamento (cross-source concept) and ciclo de vida
    # (in/out), keyed by the EXACT source code (one code = one entry; no prefixes). The
    # current catalog = latest row per (codigo_produto, banco); a row with
    # active=false is a tombstone (removed → its Gold data becomes an orphan). Backs
    # dim_produto_catalog (→ gold_produto_agrupamento). Auto-created on first write.
    bq_produto_catalog_log_table: str = Field(default="produto_catalog_log")
    # Append-only GROUPS (agrupamentos) registry — the first-class commodity-concept
    # registry keyed by group_id (== a catalog entry's agrupamento_id). Promotes groups
    # from "derived from the distinct agrupamento names" to a real entity with its own
    # lifecycle: create (incl. EMPTY groups), rename, delete (blocked while it has
    # members). Latest-wins per group_id; active=false is a tombstone. Auto-created.
    bq_agrupamento_log_table: str = Field(default="agrupamento_log")
    # Per-CATALOG authorization allowlist (research_inputs.<this>) — distinct from the
    # attribute-engineering `attribute editors` table: each cadastro (resource) has its OWN list
    # of editors, keyed by (resource, email). Empty/absent → no allowlist (any
    # IAP-authenticated caller may edit that catalog). Console-managed, auto-created.
    bq_catalog_editors_table: str = Field(default="catalog_editors")
    # Catalog-editor allowlist ENV override — the env-var twin of the
    # `catalog_editors` table, mirroring ATTRIBUTE_EDITORS_ALLOWED_EMAILS for the attribute-
    # engineering attribute editors. NON-EMPTY → the effective editor allowlist is the UNION of
    # this and the table; EMPTY (default) + empty table preserves current behaviour
    # (any IAP-authenticated caller may edit). CATALOG_EDITORS_ALLOWED_EMAILS=a@x,b@y.
    catalog_editors_allowed_emails: str = Field(default="")
    # Append-only catalog LIFECYCLE log: orphan→Descontinuado events + the eventual
    # human purge. An orphan is a commodity that WAS in the catalog, was removed
    # (tombstoned), and whose Gold data still lingers ("ficou órfão") — auto-marked
    # "descontinuado" with a deletion warning, but NEVER auto-deleted (a human runs the
    # purge, backup-first). Auto-created on first mark.
    bq_catalog_lifecycle_log_table: str = Field(default="catalog_lifecycle_log")
    # Per-query byte ceiling on the /api serving path (gateway.run_query): caps a
    # pathological/cold scan so BigQuery FAILS the job visibly instead of silently
    # billing a runaway read. ~100 GiB default (~US$0.50/query at on-demand pricing)
    # — above the pre-aggregated mart reads, below a true runaway. 0/None disables.
    bq_max_bytes_billed: int | None = Field(default=100 * 1024**3)

    @property
    def attribute_editors_allowed_emails_list(self) -> list[str]:
        """Parsed, lower-cased attribute editor allowlist (empty → any authed caller may curate)."""
        return [
            e.strip().lower() for e in self.attribute_editors_allowed_emails.split(",") if e.strip()
        ]

    @property
    def catalog_editors_allowed_emails_list(self) -> list[str]:
        """Parsed, lower-cased catalog-editor allowlist ENV override (unioned with the
        `catalog_editors` table; empty → any authed caller may edit the catalog)."""
        return [
            e.strip().lower() for e in self.catalog_editors_allowed_emails.split(",") if e.strip()
        ]

    @model_validator(mode="after")
    def _default_bucket(self) -> Settings:
        if not self.gcs_bucket:
            self.gcs_bucket = f"{self.gcp_project_id}-datalake"
        return self

    # ─── Helpers ──────────────────────────────────────────────────────────────
    @property
    def product_codes(self) -> list[str]:
        codes = [c.strip() for c in self.ibge_product_codes.split(",") if c.strip()]
        if not codes:
            raise ValueError("IBGE_PRODUCT_CODES is empty.")
        return codes

    @property
    def pam_product_codes_list(self) -> list[str]:
        """Parsed PAM crop codes (SIDRA c782). Named *_list to avoid shadowing the
        ``pam_product_codes`` raw env field (cf. ``product_codes`` for PEVS)."""
        codes = [c.strip() for c in self.pam_product_codes.split(",") if c.strip()]
        if not codes:
            raise ValueError("PAM_PRODUCT_CODES is empty.")
        return codes

    @property
    def pam_variable_codes_list(self) -> list[str]:
        """Parsed PAM SIDRA variable codes (the substantive 5 fetched into Bronze).
        Named *_list to avoid shadowing the ``pam_variable_codes`` raw env field.
        ``embrapa doctor`` cross-checks these against the dbt pam_variable_* roles."""
        codes = [c.strip() for c in self.pam_variable_codes.split(",") if c.strip()]
        if not codes:
            raise ValueError("PAM_VARIABLE_CODES is empty.")
        return codes

    @property
    def ppm_herd_product_codes_list(self) -> list[str]:
        """Parsed PPM herd codes (SIDRA t3939 c79). ``_list`` avoids shadowing the
        ``ppm_herd_product_codes`` raw env field."""
        codes = [c.strip() for c in self.ppm_herd_product_codes.split(",") if c.strip()]
        if not codes:
            raise ValueError("PPM_HERD_PRODUCT_CODES is empty.")
        return codes

    @property
    def ppm_animal_product_codes_list(self) -> list[str]:
        """Parsed PPM animal-production codes (SIDRA t74 c80)."""
        codes = [c.strip() for c in self.ppm_animal_product_codes.split(",") if c.strip()]
        if not codes:
            raise ValueError("PPM_ANIMAL_PRODUCT_CODES is empty.")
        return codes

    @property
    def ppm_herd_variable_codes_list(self) -> list[str]:
        """Parsed PPM herd SIDRA variable codes (efetivo dos rebanhos)."""
        codes = [c.strip() for c in self.ppm_herd_variable_codes.split(",") if c.strip()]
        if not codes:
            raise ValueError("PPM_HERD_VARIABLE_CODES is empty.")
        return codes

    @property
    def ppm_animal_variable_codes_list(self) -> list[str]:
        """Parsed PPM animal-production SIDRA variable codes (quantity + value)."""
        codes = [c.strip() for c in self.ppm_animal_variable_codes.split(",") if c.strip()]
        if not codes:
            raise ValueError("PPM_ANIMAL_VARIABLE_CODES is empty.")
        return codes

    @property
    def inflation_series_map(self) -> dict[str, str]:
        return _parse_code_label(self.bcb_inflation_series)

    @property
    def inflation_pivot_codes(self) -> dict[str, str]:
        """{label: code} the Gold val_real_* pivot uses; each must be a key in
        ``inflation_series_map`` or the corresponding column comes out NULL."""
        return {
            "IPCA": self.bcb_inflation_series_ipca_code,
            "IGPM": self.bcb_inflation_series_igpm_code,
            "IGPDI": self.bcb_inflation_series_igpdi_code,
        }

    @property
    def currency_series_map(self) -> dict[str, str]:
        return _parse_code_label(self.bcb_currency_series)

    @property
    def comex_flows_list(self) -> list[str]:
        """Validated flow names. Each must be 'export' or 'import' (file prefixes)."""
        allowed = {"export", "import"}
        flows = [f.strip().lower() for f in self.comex_flows.split(",") if f.strip()]
        if not flows:
            raise ValueError("COMEX_FLOWS is empty.")
        invalid = [f for f in flows if f not in allowed]
        if invalid:
            raise ValueError(
                f"COMEX_FLOWS has invalid flow(s) {invalid}; allowed: {sorted(allowed)}"
            )
        return flows

    @property
    def comex_ncm_map(self) -> dict[str, str]:
        return _require_code_lengths(_parse_code_label(self.comex_ncm_codes), {8}, "COMEX NCM")

    @property
    def comex_chapter_map(self) -> dict[str, str]:
        return _require_code_lengths(
            _parse_code_label(self.comex_chapter_codes), {2}, "COMEX HS chapter"
        )

    @property
    def comex_heading_map(self) -> dict[str, str]:
        """4-digit HS headings kept by prefix match on NCM[:4] (e.g. wood)."""
        return _require_code_lengths(
            _parse_code_label(self.comex_heading_codes), {4}, "COMEX HS heading"
        )

    @property
    def comtrade_cmd_map(self) -> dict[str, str]:
        return _parse_code_label(self.comtrade_cmd_codes)

    @property
    def comtrade_flows_list(self) -> list[str]:
        """Validated UN Comtrade flow (trade regime) codes. The DEFAULT ingests ONLY the two
        direction TOTALS (X=export, M=import) — the totals-only design (the sub-flows RX/RM/
        DX/FM/… are subsets of X/M and would double-count). The eight sub-flows stay in the
        allowed set so an operator CAN widen COMTRADE_FLOWS and re-ingest for a bespoke
        analysis — but note silver_comtrade_flows then keeps only X/M anyway (totals-only),
        so a widened flow set surfaces nothing extra without also relaxing Silver."""
        allowed = {"X", "M", "RX", "RM", "DX", "FM", "MIP", "MOP", "XIP", "XOP"}
        flows = [f.strip().upper() for f in self.comtrade_flows.split(",") if f.strip()]
        if not flows:
            raise ValueError("COMTRADE_FLOWS is empty.")
        invalid = [f for f in flows if f not in allowed]
        if invalid:
            raise ValueError(
                f"COMTRADE_FLOWS has invalid flow(s) {invalid}; "
                "allowed: X, M, RX, RM, DX, FM, MIP, MOP, XIP, XOP"
            )
        return flows


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


def get_credentials(settings: Settings | None = None):
    """Return GCP credentials, impersonating GCP_IMPERSONATION_SA when set.

    Returns None to let the google-cloud libraries fall back to ADC directly.
    """
    import google.auth
    from google.auth import impersonated_credentials

    cfg = settings or get_settings()
    if not cfg.gcp_impersonation_sa:
        return None

    source_creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    return impersonated_credentials.Credentials(
        source_credentials=source_creds,
        target_principal=cfg.gcp_impersonation_sa,
        target_scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
