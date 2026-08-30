"""Unit tests for webapi serializers — seam output → contracts.js shapes.

Pure functions, no BigQuery: synthetic DataFrames/dicts in, asserted shapes out.
Locks the magnitude contract (productTS.v in millions, overviewTS.v in billions,
mass quantity ÷1e3, volume ÷1e6) and the pt-BR→en family rename the views need.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from embrapa_dashboard.webapi import serializers as s


def test_serialize_snapshot_shapes_and_scales():
    snap = {
        "products": pd.DataFrame(
            [
                {
                    "code": "001",
                    "name": "Castanha",
                    "unit": "t",
                    "unit_native": "kg",
                    "family": "massa",
                },
                {
                    "code": "777",
                    "name": "Madeira",
                    "unit": "m3",
                    "unit_native": "m3",
                    "family": "volume",
                },
            ]
        ),
        "product_ts": pd.DataFrame(
            [
                # mass: 2_000_000_000 R$ → 2000 mi; 5_000_000 t (q_mass) → 5000 mil t
                {
                    "code": "001",
                    "reference_year": 2020,
                    "total_value": 2_000_000_000,
                    "total_qty_native": 5_000_000,
                    "q_mass": 5_000_000,  # massa CASE column (PEVS: native == base, t)
                    "q_vol": float("nan"),
                    "family": "massa",
                },
                # volume: 6_000_000 m³ (q_vol) → 6 mi m³
                {
                    "code": "777",
                    "reference_year": 2020,
                    "total_value": 1_000_000,
                    "total_qty_native": 6_000_000,
                    "q_mass": float("nan"),
                    "q_vol": 6_000_000,  # volume CASE column (PEVS: native == base, m³)
                    "family": "volume",
                },
                {
                    "code": "2670",
                    "reference_year": 2020,
                    "total_value": float("nan"),
                    "q_mass": float("nan"),
                    "q_vol": float("nan"),
                    "q_count": 238_000_000,  # contagem CASE column (un) — PPM herd
                    "family": "contagem",
                },
            ]
        ),
        "overview_ts": pd.DataFrame(
            [
                {
                    "reference_year": 2020,
                    "total_value": 3_000_000_000,
                    "q_mass": 5_000_000,
                    "q_vol": 6_000_000,
                }
            ]
        ),
        "uf_data": pd.DataFrame(
            [
                {
                    "state_acronym": "PA",
                    "state_name": "Pará",
                    "region": "Norte",
                    "region_abbrev": "N",
                    "total_value": 1_500_000,
                }
            ]
        ),
        "quality": pd.DataFrame(
            [{"source": "ibge_pevs", "data_quality_flag": "OK", "n_rows": 42, "share": 0.8}]
        ),
        "value_label": "Valor real (IPCA) — R$",
    }
    out = s.serialize_snapshot(snap)

    assert {p["code"] for p in out["products"]} == {"001", "777"}
    assert out["products"][0]["family"] == "mass"  # massa→mass for the views

    # productTS: grouped by code, v in millions, q per-family scaled
    mass = out["productTS"]["001"][0]
    assert mass == {"y": 2020, "v": 2000.0, "q": 5000.0, "family": "mass"}
    vol = out["productTS"]["777"][0]
    assert vol["family"] == "volume" and vol["q"] == 6.0  # m³ ÷1e6

    # overviewTS: v in billions; q_mass mil t, q_vol mi m³
    # contagem (PPM herd headcount) — KEYSTONE: q now populated (mi un), not None;
    # family normalizes massa/volume-style to 'count' so the herd renders a quantity.
    herd = out["productTS"]["2670"][0]
    assert herd["family"] == "count" and herd["q"] == 238.0  # 238M head -> 238 mi un

    ov = out["overviewTS"][0]
    assert ov["v"] == 3.0 and ov["q_mass"] == 5000.0 and ov["q_vol"] == 6.0

    uf = out["ufData"][0]
    assert uf["uf"] == "PA" and uf["region"] == "N" and uf["value"] == 1.5
    # no q_mass/q_vol columns in this fixture → safe 0.0 fallback (real values
    # are asserted in test_uf_data_emits_per_family_quantities).
    assert uf["q_mass"] == 0.0 and uf["q_vol"] == 0.0
    # _quality emits a pt-BR label so the donut stays Portuguese even for flags the
    # frontend taxonomy lacks (INCOMPLETE/MISSING_WEIGHT). The healthy row is labeled
    # "Normais" per the Contrato de Dados spreadsheet (not the English "OK" token).
    assert out["quality"][0] == {"id": "OK", "label": "Normais", "count": 42, "share": 0.8}
    assert out["preview"] is False and out["_synthetic"] is False


def test_product_ts_scales_qty_base_not_native_for_kg_native_trade_codes():
    """Regression: COMEX/COMTRADE quantities are mostly kg-NATIVE. The serializer
    must scale the per-family base (q_mass, already t / m³ in the marts) — scaling
    the native kg as if tonnes displayed trade quantities 1000× too large."""
    snap = {
        "products": None,
        "product_ts": pd.DataFrame(
            [
                # kg-native NCM: 5_000_000_000 kg native = 5_000_000 t base → 5000 mil t
                {
                    "code": "08012100",
                    "reference_year": 2022,
                    "total_value": 1_000_000_000,
                    "total_qty_native": 5_000_000_000,
                    "q_mass": 5_000_000,
                    "q_vol": float("nan"),
                    "family": "massa",
                },
                # t-native NCM in the same family: base == native
                {
                    "code": "44012200",
                    "reference_year": 2022,
                    "total_value": 2_000_000,
                    "total_qty_native": 3_000,
                    "q_mass": 3_000,
                    "q_vol": float("nan"),
                    "family": "massa",
                },
            ]
        ),
        "overview_ts": pd.DataFrame(
            [
                {
                    "reference_year": 2022,
                    "total_value": 1_002_000_000,
                    # the seam already aggregated qty_base per family (t)
                    "q_mass": 5_003_000,
                    "q_vol": 0.0,
                }
            ]
        ),
        "uf_data": None,
        "quality": None,
        "value_label": "Valor (US$ FOB)",
    }
    out = s.serialize_snapshot(snap)
    assert out["productTS"]["08012100"][0]["q"] == 5000.0  # mil t, from q_mass
    assert out["productTS"]["44012200"][0]["q"] == 3.0
    assert out["overviewTS"][0]["q_mass"] == 5003.0  # mil t — never kg/1e3


def test_product_ts_q_for_contagem_none_for_energy_area_families():
    """contagem (livestock head / eggs — PPM) now has its OWN ``q_count`` track, so q is
    the headcount scaled to mi un — it was None before, making the herd (the defining
    content of PPM) invisible in every quantity chart. The M1 anti-mis-scale rule still
    holds for energia/area: they have no display convention → q stays None (absent, not
    a raw count divided by 1e6)."""
    snap = {
        "products": None,
        "product_ts": pd.DataFrame(
            [
                # contagem (un): the dedicated q_count carries the headcount → q = mi un.
                {
                    "code": "2670",
                    "reference_year": 2022,
                    "total_value": float("nan"),  # a herd stock has no value
                    "q_mass": float("nan"),
                    "q_vol": float("nan"),
                    "q_count": 238_000_000,
                    "family": "contagem",
                },
                # energia: no q_* track matches → q stays None (no display convention).
                {
                    "code": "9001",
                    "reference_year": 2022,
                    "total_value": 4_000_000,
                    "q_mass": float("nan"),
                    "q_vol": float("nan"),
                    "q_count": float("nan"),
                    "family": "energia",
                },
            ]
        ),
        "overview_ts": None,
        "uf_data": None,
        "quality": None,
        "value_label": "Valor (US$ FOB)",
    }
    out = s.serialize_snapshot(snap)
    herd = out["productTS"]["2670"][0]
    assert herd["q"] == 238.0 and herd["family"] == "count"  # 238M head -> 238 mi un
    energia = out["productTS"]["9001"][0]
    assert energia["q"] is None  # NOT a raw count / 1e6 — energia has no display scale
    assert energia["family"] == "energia"  # raw family passes through for honest labelling
    assert energia["v"] == 4.0  # value still emitted (mi)


def test_serialize_snapshot_empty_is_safe():
    out = s.serialize_snapshot(
        {
            "products": None,
            "product_ts": None,
            "overview_ts": None,
            "uf_data": None,
            "quality": None,
            "value_label": "",
        }
    )
    assert out["products"] == [] and out["productTS"] == {} and out["overviewTS"] == []
    assert out["ufData"] == [] and out["quality"] == []


def test_products_emit_the_sidra_table_only_when_present():
    """A tabela SIDRA viaja na lista de produtos quando o mart a carrega.

    É ela que permite distinguir dois produtos que dividem o NOME — madeira, lenha e carvão
    existem nas duas tabelas do PEVS. Um mart de tabela única omite a chave, mantendo o
    payload daqueles bancos byte-idêntico."""
    snap = {
        "products": pd.DataFrame(
            [
                {
                    "code": "3457",
                    "name": "Madeira em tora",
                    "unit": "m³",
                    "unit_native": "Metros cúbicos",
                    "family": "volume",
                    "sidra_tabela": "291",
                },
                {
                    "code": "3435",
                    "name": "Madeira em tora",
                    "unit": "m³",
                    "unit_native": "Metros cúbicos",
                    "family": "volume",
                    "sidra_tabela": "289",
                },
                # sem a coluna (banco de tabela única) → chave ausente
                {
                    "code": "4403",
                    "name": "Madeira em toras (NCM)",
                    "unit": "t",
                    "unit_native": "kg",
                    "family": "massa",
                    "sidra_tabela": float("nan"),
                },
            ]
        ),
        "product_ts": None,
        "overview_ts": None,
        "uf_data": None,
        "quality": None,
        "value_label": "",
    }
    prods = {p["code"]: p for p in s.serialize_snapshot(snap)["products"]}
    # Dois códigos, o MESMO nome, tabelas diferentes: é isso que a tela precisa receber.
    assert prods["3457"]["name"] == prods["3435"]["name"] == "Madeira em tora"
    assert prods["3457"]["sidra_tabela"] == "291"
    assert prods["3435"]["sidra_tabela"] == "289"
    assert "sidra_tabela" not in prods["4403"]


def test_products_emit_measure_kind_only_when_present():
    """measure_kind (stock|flow) rides along ONLY for livestock (PPM selects it in the
    gateway). A herd code carries 'stock'; a code from a mart without the column omits
    the key entirely (so PEVS/COMEX products stay byte-identical to before)."""
    snap = {
        "products": pd.DataFrame(
            [
                {
                    "code": "2670",
                    "name": "Bovinos",
                    "unit": "un",
                    "unit_native": "Cabeças",
                    "family": "contagem",
                    "measure_kind": "stock",
                },
                # a code WITHOUT measure_kind (e.g. a PEVS row) → key absent
                {
                    "code": "001",
                    "name": "Castanha",
                    "unit": "t",
                    "unit_native": "kg",
                    "family": "massa",
                    "measure_kind": float("nan"),
                },
            ]
        ),
        "product_ts": None,
        "overview_ts": None,
        "uf_data": None,
        "quality": None,
        "value_label": "",
    }
    products = {p["code"]: p for p in s.serialize_snapshot(snap)["products"]}
    assert products["2670"]["measure_kind"] == "stock"
    assert products["2670"]["family"] == "count"  # contagem→count for the views
    assert "measure_kind" not in products["001"]  # NaN/absent → omitted, not null


def test_serialize_cross_camelcase_and_preview():
    assert s.serialize_market_share(
        {
            "unit": "US$ bi",
            "series": [{"y": 2020, "br": 1, "world": 10, "share": 10}],
            "by_product": [{"code": "x", "name": "X", "share": 5}],
        }
    ) == {
        "preview": False,
        "unit": "US$ bi",
        "series": [{"y": 2020, "br": 1, "world": 10, "share": 10}],
        "byProduct": [{"code": "x", "name": "X", "share": 5}],
    }

    ec = s.serialize_export_coef(
        {"unit": "mil t", "incompatible": True, "by_uf": [], "national": {}, "timeseries": []}
    )
    assert ec["byUf"] == [] and ec["incompatible"] is True and ec["preview"] is False


def test_serialize_value_added_pivots_per_level():
    out = s.serialize_value_added(
        {
            "series": [
                {
                    "y": 2020,
                    "levels": {
                        "commodity_pura": {"v": 2.0, "w": 8.0, "price": 0.25},
                        "manufaturado_industrial": {"v": 3.0, "w": 2.0, "price": 1.5},
                    },
                    "totalV": 5.0,
                    "totalW": 10.0,
                }
            ],
            "levels": ["commodity_pura", "manufaturado_industrial"],
            "premium": 6.0,
            "predominant": {"level": "manufaturado_industrial", "shareV": 60.0},
            "n_codes": 4,
        }
    )
    assert out["years"] == [2020] and out["nCodes"] == 4
    assert out["levels"] == ["commodity_pura", "manufaturado_industrial"]
    # value composition (US$ bi) pivoted into a continuous array per level
    assert out["byLevel"]["commodity_pura"] == [{"y": 2020, "v": 2.0}]
    assert out["byLevel"]["manufaturado_industrial"] == [{"y": 2020, "v": 3.0}]
    # volume (mil t) + unit price (US$/kg) pivoted alongside
    assert out["byLevelWeight"]["commodity_pura"] == [{"y": 2020, "v": 8.0}]
    assert out["byLevelPrice"]["manufaturado_industrial"] == [{"y": 2020, "v": 1.5}]
    # scalar rollups pass through
    assert out["premium"] == 6.0 and out["predominant"]["level"] == "manufaturado_industrial"


def test_serialize_value_added_zero_fills_absent_level_year():
    """A level present overall but absent in a given year → 0 in that year's slot,
    so the stacked-area series stays continuous."""
    out = s.serialize_value_added(
        {
            "series": [
                {
                    "y": 2019,
                    "levels": {"commodity_pura": {"v": 1.0, "w": 4.0, "price": 0.25}},
                    "totalV": 1.0,
                    "totalW": 4.0,
                },
                {
                    "y": 2020,
                    "levels": {"manufaturado_industrial": {"v": 2.0, "w": 1.0, "price": 2.0}},
                    "totalV": 2.0,
                    "totalW": 1.0,
                },
            ],
            "levels": ["commodity_pura", "manufaturado_industrial"],
            "premium": 0.0,
            "predominant": {"level": "manufaturado_industrial", "shareV": 100.0},
            "n_codes": 2,
        }
    )
    # commodity_pura has no export in 2020 → filled with v:0 to keep the series continuous
    assert out["byLevel"]["commodity_pura"] == [{"y": 2019, "v": 1.0}, {"y": 2020, "v": 0}]
    assert out["byLevelWeight"]["manufaturado_industrial"] == [
        {"y": 2019, "v": 0},
        {"y": 2020, "v": 1.0},
    ]


def test_cross_series_none_passthrough():
    assert s.serialize_cross_series(None) is None
    assert s.serialize_cross_series({"banco": "ibge_pevs", "points": []})["preview"] is False


def test_quality_ts_pivots_to_per_year_shares():
    # Real Gold flags only: 2020 OK/MISSING_VALUE; 2021 OK/INCOMPLETE (PEVS) +
    # MISSING_WEIGHT (COMEX) — the synthetic ESTIMATED/OUTLIER/BOUNDARY are gone.
    df = pd.DataFrame(
        [
            {"reference_year": 2020, "data_quality_flag": "OK", "n": 90},
            {"reference_year": 2020, "data_quality_flag": "MISSING_VALUE", "n": 10},
            {"reference_year": 2021, "data_quality_flag": "OK", "n": 50},
            {"reference_year": 2021, "data_quality_flag": "INCOMPLETE", "n": 30},
            {"reference_year": 2021, "data_quality_flag": "MISSING_WEIGHT", "n": 20},
        ]
    )
    out = s.serialize_snapshot(
        {
            "products": None,
            "product_ts": None,
            "overview_ts": None,
            "uf_data": None,
            "quality": None,
            "quality_ts": df,
            "value_label": "",
        }
    )["qualityTs"]
    assert [r["y"] for r in out] == [2020, 2021]  # sorted by year
    assert out[0]["ok"] == 0.9 and out[0]["missing_value"] == 0.1
    # every real contract key present (absent ones read 0). The outlier/problemático
    # tiers are part of the taxonomy (emitted by Gold when enable_quality_outliers is on),
    # so they appear here too — as 0 when absent. The inferred_* keys are RESERVED for a
    # future auto-fill pipeline (accepted-but-absent, 0 today). The old SYNTHETIC ids
    # (ESTIMATED/BOUNDARY_HISTORIC) are gone.
    assert set(out[0]) == {
        "y",
        "ok",
        "missing_value",
        "missing_quantity",
        "missing_weight",
        "incomplete",
        "outlier_quantity",
        "problematic_quantity",
        "outlier_value",
        "problematic_value",
        "inferred_quantity",
        "inferred_value",
        "area_inconsistent",  # PAM-only (planted < harvested area)
    }
    assert out[1]["ok"] == 0.5 and out[1]["incomplete"] == 0.3 and out[1]["missing_weight"] == 0.2


def test_quality_flag_taxonomy_complete_and_ptbr():
    """The 11-value taxonomy (9 emitted + 2 reserved inferred tiers) is fully wired: the
    qualityTs-key map and the pt-BR label map cover the SAME ids, and every label is
    Portuguese — never the raw English id (the pt-BR rule; the documented past failure was
    a flag with no server label falling back to the English token)."""
    from embrapa_dashboard.webapi import serializers as s

    assert set(s._FLAG_KEY) == set(s._FLAG_LABEL_PT)
    assert {
        "OUTLIER_QUANTITY",
        "PROBLEMATIC_QUANTITY",
        "OUTLIER_VALUE",
        "PROBLEMATIC_VALUE",
        # Reserved for a future auto-fill pipeline (accepted-but-absent, 0 today).
        "INFERRED_QUANTITY",
        "INFERRED_VALUE",
    } <= set(s._FLAG_KEY)
    assert all(label != flag_id for flag_id, label in s._FLAG_LABEL_PT.items())
    assert "atípica" in s._FLAG_LABEL_PT["OUTLIER_QUANTITY"]
    assert "problemático" in s._FLAG_LABEL_PT["PROBLEMATIC_VALUE"]
    # The reserved inferred tier carries its pt-BR labels + the qualityTs keys.
    assert s._FLAG_KEY["INFERRED_QUANTITY"] == "inferred_quantity"
    assert s._FLAG_KEY["INFERRED_VALUE"] == "inferred_value"
    assert s._FLAG_LABEL_PT["INFERRED_QUANTITY"] == "Quantidade inferida"
    assert s._FLAG_LABEL_PT["INFERRED_VALUE"] == "Valor financeiro inferido"


def test_quality_ts_unmapped_flag_lowers_known_shares_not_dropped():
    # An unexpected flag still counts toward the denominator (so the stack never
    # silently sums to >1 by ignoring it) — it just maps to no output key.
    df = pd.DataFrame(
        [
            {"reference_year": 2020, "data_quality_flag": "OK", "n": 80},
            {"reference_year": 2020, "data_quality_flag": "SOMETHING_NEW", "n": 20},
        ]
    )
    out = s._quality_ts(df)
    assert out[0]["ok"] == 0.8  # 80/100 — the 20 unknown rows are in `total`


def test_quality_by_product_per_product_shares_top_n():
    df = pd.DataFrame(
        [
            # product A: 800 rows (top by volume) — 600 OK + 200 MISSING_VALUE
            {"code": "A", "name": "Prod A", "data_quality_flag": "OK", "n": 600},
            {"code": "A", "name": "Prod A", "data_quality_flag": "MISSING_VALUE", "n": 200},
            # product B: 100 rows — all OK
            {"code": "B", "name": "Prod B", "data_quality_flag": "OK", "n": 100},
        ]
    )
    out = s.serialize_snapshot(
        {
            "products": None,
            "product_ts": None,
            "overview_ts": None,
            "uf_data": None,
            "quality": None,
            "quality_by_product": df,
            "value_label": "",
        }
    )["qualityByProduct"]
    assert [r["code"] for r in out] == ["A", "B"]  # ranked by row volume
    assert out[0]["OK"] == 0.75 and out[0]["MISSING_VALUE"] == 0.25  # flag-id keys, shares
    # absent REAL flags read 0 (MISSING_WEIGHT/INCOMPLETE), and the synthetic
    # OUTLIER/ESTIMATED/BOUNDARY_HISTORIC keys no longer exist at all.
    assert out[1]["OK"] == 1.0 and out[1]["MISSING_WEIGHT"] == 0.0
    assert "OUTLIER" not in out[1] and "BOUNDARY_HISTORIC" not in out[1]


def test_serialize_market_nature_passthrough():
    out = s.serialize_market_nature(
        {
            "years": [2022, 2023],
            "series": [
                {"y": 2022, "consumo": 1.0, "processamento": 2.0},
                {"y": 2023, "consumo": 1.5, "processamento": 2.5},
            ],
            "latest": {"y": 2023, "consumo": 1.5, "processamento": 2.5},
            "n_classified": 3,
        }
    )
    assert out["preview"] is False  # real data, never a synthetic demo banner
    assert out["years"] == [2022, 2023]
    assert out["latest"]["processamento"] == 2.5
    assert len(out["series"]) == 2


def test_serialize_market_nature_empty_is_safe():
    # Pre-classification (no pair curated) → empty shells; the view guards series[0].
    assert s.serialize_market_nature({}) == {
        "preview": False,
        "years": [],
        "series": [],
        "latest": {},
    }


def _productivity_payload():
    # Soja, 2 UFs × 2 years. Yield (kg/ha) = production_t × 1000 / area_harvested_ha,
    # recomputed from the SUMMED totals at each grain — never averaged across UFs.
    rows = pd.DataFrame(
        [
            {
                "reference_year": 2023,
                "state_acronym": "PR",
                "state_name": "Paraná",
                "region": "Sul",
                "region_abbrev": "S",
                "production_t": 1000.0,
                "area_planted_ha": 520.0,
                "area_harvested_ha": 500.0,
            },
            {
                "reference_year": 2023,
                "state_acronym": "MT",
                "state_name": "Mato Grosso",
                "region": "Centro-Oeste",
                "region_abbrev": "CO",
                "production_t": 2000.0,
                "area_planted_ha": 410.0,
                "area_harvested_ha": 400.0,
            },
            {
                "reference_year": 2024,
                "state_acronym": "PR",
                "state_name": "Paraná",
                "region": "Sul",
                "region_abbrev": "S",
                "production_t": 1200.0,
                "area_planted_ha": 520.0,
                "area_harvested_ha": 500.0,
            },
            {
                "reference_year": 2024,
                "state_acronym": "MT",
                "state_name": "Mato Grosso",
                "region": "Centro-Oeste",
                "region_abbrev": "CO",
                "production_t": 2400.0,
                "area_planted_ha": 410.0,
                "area_harvested_ha": 400.0,
            },
        ]
    )
    return {
        "crops": [{"code": "40124", "name": "Soja"}, {"code": "40122", "name": "Milho"}],
        "active": "40124",
        "active_name": "Soja",
        "rows": rows,
    }


def test_serialize_productivity_recomputes_yield_and_aggregates():
    out = s.serialize_productivity(_productivity_payload())
    assert out["preview"] is False  # the contract requires the preview key
    assert out["crop"] == {"code": "40124", "name": "Soja"}
    assert [c["code"] for c in out["crops"]] == ["40124", "40122"]
    assert out["yieldUnit"] == "kg/ha" and out["areaUnit"] == "ha"

    # National series: production + harvested area SUMMED per year; yield from totals.
    assert [d["y"] for d in out["series"]] == [2023, 2024]
    y2023, y2024 = out["series"]
    assert y2023["prodT"] == 3000.0 and y2023["areaHa"] == 900.0
    # 3333.3 kg/ha — from the totals, NOT the average of 2000 & 5000.
    assert y2023["yieldKgHa"] == pytest.approx(3000.0 * 1000 / 900)
    assert y2024["yieldKgHa"] == pytest.approx(3600.0 * 1000 / 900)  # 4000

    # national = the LATEST year's totals (matches the byUF grain) + CAGR.
    assert out["national"]["prodT"] == 3600.0 and out["national"]["areaHa"] == 900.0
    assert out["national"]["yieldKgHa"] == pytest.approx(4000.0)
    # CAGR over the 1-year span: (4000/3333.3)^(1/1) − 1 = 20%.
    assert out["national"]["yieldCagr"] == pytest.approx(20.0, abs=0.1)

    # Per-UF is the LATEST year (2024) only, with yield + summable area/production.
    by_uf = {r["uf"]: r for r in out["byUF"]}
    assert set(by_uf) == {"PR", "MT"}
    assert by_uf["MT"]["yieldKgHa"] == pytest.approx(2400.0 * 1000 / 400)  # 6000
    assert by_uf["PR"]["yieldKgHa"] == pytest.approx(1200.0 * 1000 / 500)  # 2400
    assert by_uf["MT"]["prodT"] == 2400.0 and by_uf["MT"]["areaHa"] == 400.0


def test_serialize_productivity_handles_zero_area_and_empty():
    assert s.serialize_productivity(None) is None  # banco lacks the yield capability
    # Empty frame → a valid contract with empty series (the view renders empty charts).
    empty = s.serialize_productivity(
        {"crops": [], "active": "", "active_name": "", "rows": pd.DataFrame()}
    )
    assert empty["preview"] is False
    assert empty["series"] == [] and empty["byUF"] == []
    # national carries every contracted field, zeroed, even with no data.
    assert empty["national"] == {"yieldKgHa": 0.0, "areaHa": 0.0, "prodT": 0.0, "yieldCagr": 0.0}
    # Zero harvested area must not divide-by-zero → yield 0.
    zero = s.serialize_productivity(
        {
            "crops": [{"code": "1", "name": "X"}],
            "active": "1",
            "active_name": "X",
            "rows": pd.DataFrame(
                [
                    {
                        "reference_year": 2024,
                        "state_acronym": "PR",
                        "state_name": "Paraná",
                        "region": "Sul",
                        "region_abbrev": "S",
                        "production_t": 100.0,
                        "area_planted_ha": 0.0,
                        "area_harvested_ha": 0.0,
                    }
                ]
            ),
        }
    )
    assert zero["series"][0]["yieldKgHa"] == 0.0 and zero["byUF"][0]["yieldKgHa"] == 0.0


def test_uf_data_emits_per_family_quantities():
    """ufData q_mass/q_vol are real (from the by-UF per-family qty_base sums),
    scaled like overviewTS: massa ÷1e3 → mil t, volume ÷1e6 → mi m³."""
    snap = {
        "products": None,
        "product_ts": None,
        "overview_ts": None,
        "uf_data": pd.DataFrame(
            [
                {
                    "state_acronym": "PA",
                    "state_name": "Pará",
                    "region_abbrev": "N",
                    "total_value": 1_500_000,
                    "q_mass": 5_000_000,  # t → 5000 mil t
                    "q_vol": 6_000_000,  # m³ → 6 mi m³
                }
            ]
        ),
        "quality": None,
        "value_label": "",
    }
    uf = s.serialize_snapshot(snap)["ufData"][0]
    assert uf["value"] == 1.5 and uf["q_mass"] == 5000.0 and uf["q_vol"] == 6.0


def test_uf_yearly_emits_real_per_uf_year_rows():
    """ufYearly is REAL per-(UF, year) Gold history (backs the ano × UF heatmap),
    scaled like ufData: value ÷1e6, q_mass ÷1e3 → mil t, q_vol ÷1e6 → mi m³."""
    snap = {
        "products": None,
        "product_ts": None,
        "overview_ts": None,
        "uf_data": None,
        "uf_yearly": pd.DataFrame(
            [
                {
                    "state_acronym": "PA",
                    "state_name": "Pará",
                    "region_abbrev": "N",
                    "reference_year": 2019,
                    "total_value": 1_000_000,
                    "q_mass": 2_000_000,  # t → 2000 mil t
                    "q_vol": 3_000_000,  # m³ → 3 mi m³
                },
                {
                    "state_acronym": "PA",
                    "state_name": "Pará",
                    "region_abbrev": "N",
                    "reference_year": 2020,
                    "total_value": 1_500_000,
                    "q_mass": 2_500_000,
                    "q_vol": float("nan"),  # no volume that year → 0.0
                },
            ]
        ),
        "quality": None,
        "value_label": "",
    }
    rows = s.serialize_snapshot(snap)["ufYearly"]
    assert [(r["uf"], r["year"]) for r in rows] == [("PA", 2019), ("PA", 2020)]
    assert rows[0] == {
        "year": 2019,
        "uf": "PA",
        "name": "Pará",
        "region": "N",
        "value": 1.0,
        "q_mass": 2000.0,
        "q_vol": 3.0,
        "q_count": 0.0,
    }
    assert rows[1]["value"] == 1.5 and rows[1]["q_mass"] == 2500.0 and rows[1]["q_vol"] == 0.0


def test_uf_yearly_empty_is_safe():
    out = s.serialize_snapshot(
        {
            "products": None,
            "product_ts": None,
            "overview_ts": None,
            "uf_data": None,
            "uf_yearly": None,
            "quality": None,
            "value_label": "",
        }
    )
    assert out["ufYearly"] == []


def test_serialize_geo_yearly_wraps_uf_yearly_with_same_scaling():
    """serialize_geo_yearly is the /api/geo-yearly payload: { ufYearly: [...] } with
    the EXACT scaling _uf_yearly applies (value ÷1e6, q_mass ÷1e3, q_vol ÷1e6), so the
    basket cube is byte-interchangeable with the snapshot's ufYearly client-side."""
    df = pd.DataFrame(
        [
            {
                "state_acronym": "PA",
                "state_name": "Pará",
                "region_abbrev": "N",
                "reference_year": 2024,
                "total_value": 1_000_000,
                "q_mass": 2_000_000,
                "q_vol": 3_000_000,
            }
        ]
    )
    out = s.serialize_geo_yearly(df)
    assert out == {
        "ufYearly": [
            {
                "year": 2024,
                "uf": "PA",
                "name": "Pará",
                "region": "N",
                "value": 1.0,
                "q_mass": 2000.0,
                "q_vol": 3.0,
                "q_count": 0.0,
            }
        ]
    }


def test_serialize_geo_yearly_empty_is_safe():
    assert s.serialize_geo_yearly(None) == {"ufYearly": []}
    assert s.serialize_geo_yearly(pd.DataFrame()) == {"ufYearly": []}


def test_uf_data_flags_real_vs_pseudo_uf_codes():
    """ufData rows carry a `real` flag: True for a Brazilian UF, False for a COMEX
    special trade pseudo-code (EX/ND/ZN…), which has no state_name. Lets the frontend
    count real UFs (27) instead of inflating the tally (FINDING #4)."""
    df = pd.DataFrame(
        [
            {
                "state_acronym": "SP",
                "state_name": "São Paulo",
                "region_abbrev": "SE",
                "total_value": 5_000_000,
                "q_mass": 0.0,
                "q_vol": 0.0,
            },
            {
                "state_acronym": "EX",
                "state_name": None,  # pseudo trade code — no UF lookup match
                "region_abbrev": None,
                "total_value": 9_000_000,
                "q_mass": 0.0,
                "q_vol": 0.0,
            },
        ]
    )
    rows = s._uf_data(df)
    by_uf = {r["uf"]: r for r in rows}
    assert by_uf["SP"]["real"] is True
    assert by_uf["EX"]["real"] is False


def test_uf_data_null_family_quantity_is_zero():
    # A UF with only mass production: q_vol is NULL/NaN → safe 0.0.
    df = pd.DataFrame(
        [
            {
                "state_acronym": "MT",
                "state_name": "Mato Grosso",
                "region_abbrev": "CO",
                "total_value": 2_000_000,
                "q_mass": 3_000_000,
                "q_vol": float("nan"),
            }
        ]
    )
    uf = s._uf_data(df)[0]
    assert uf["q_mass"] == 3000.0 and uf["q_vol"] == 0.0


def test_quality_uses_real_pt_br_labels():
    df = pd.DataFrame(
        [
            {"data_quality_flag": "INCOMPLETE", "n_rows": 5, "share": 0.1},
            {"data_quality_flag": "MISSING_WEIGHT", "n_rows": 3, "share": 0.06},
        ]
    )
    out = s._quality(df)
    by_id = {r["id"]: r["label"] for r in out}
    assert by_id["INCOMPLETE"] == "Incompleto"  # pt-BR, not the raw English id
    assert by_id["MISSING_WEIGHT"] == "Peso ausente"


def test_serialize_source_meta_carries_latest_year_completeness():
    """serialize_source_meta surfaces the FINDING #3 partial-year signal as camelCase
    JSON the frontend can read for an honest YoY (monthsInLatestYear /
    latestYearComplete / latestCompleteYear)."""
    out = s.serialize_source_meta(
        {
            "source": "mdic_comex",
            "gold_table": "gold_comex_flows",
            "cadence": "monthly",
            "year_start": 1997,
            "year_end": 2026,
            "months_in_latest_year": 5,
            "latest_year_complete": False,
            "latest_complete_year": 2025,
        }
    )
    assert out["monthsInLatestYear"] == 5
    assert out["latestYearComplete"] is False
    assert out["latestCompleteYear"] == 2025


def test_serialize_source_meta_annual_defaults_to_complete():
    """An annual banco (no completeness keys) → latestYearComplete True,
    monthsInLatestYear None (the serializer's safe default)."""
    out = s.serialize_source_meta(
        {"source": "ibge_pevs", "gold_table": "gold_pevs_production", "year_end": 2024}
    )
    assert out["latestYearComplete"] is True
    assert out["monthsInLatestYear"] is None


def test_serialize_source_meta_empty_is_empty_dict():
    assert s.serialize_source_meta(None) == {}
    assert s.serialize_source_meta({}) == {}


def test_serialize_source_meta_carries_app_version():
    """The running release version (pyproject → importlib.metadata, the SoT the tag bumps) is
    surfaced as appVersion so the SPA shows the REAL version, never the stale frontend
    package.json literal. Absent for empty meta (caught by the guard above). (Asserted against
    the serializer's captured constant, not the live ``embrapa_dashboard.__version__`` global,
    which another test mutates via importlib.reload.)"""
    out = s.serialize_source_meta({"source": "x", "gold_table": "g"})
    assert out["appVersion"] == s._APP_VERSION
    assert isinstance(out["appVersion"], str) and out["appVersion"]  # present + non-empty
    assert "appVersion" not in s.serialize_source_meta({})


def test_serialize_source_meta_carries_the_release_date_of_that_version(monkeypatch):
    """appReleaseDate is the date the RUNNING version shipped, pt-BR formatted.

    Sobre renders it right beside the version. It used to render the PEVS Gold refresh
    stamp there instead, under a lone "Versão" label — so a build released today showed
    a weeks-old date and read as stale, while also speaking for one banco out of five."""
    from embrapa_dashboard import release

    monkeypatch.setattr(s, "_APP_RELEASE_LABEL", s._UNRESOLVED)  # bypass the process cache
    monkeypatch.setattr(release, "release_date", lambda *a, **k: date(2026, 8, 16))
    out = s.serialize_source_meta({"source": "x", "gold_table": "g"})
    assert out["appReleaseDate"] == "16 ago 2026"


def test_serialize_source_meta_omits_the_release_date_when_unknown(monkeypatch):
    """No CHANGELOG section (dev build, or the file absent from the image) ⇒ None, so the
    SPA shows the version alone. Substituting today's date would present an OLD build as
    fresh — the exact dishonesty this field exists to remove."""
    from embrapa_dashboard import release

    monkeypatch.setattr(s, "_APP_RELEASE_LABEL", s._UNRESOLVED)
    monkeypatch.setattr(release, "release_date", lambda *a, **k: None)
    out = s.serialize_source_meta({"source": "x", "gold_table": "g"})
    assert out["appReleaseDate"] is None


def test_serialize_monthly_empty_emits_twelve_values():
    """serialize_monthly must always emit 12 monthlyAvg entries — an empty list
    crashed ViewSeasonality's peak/low/amplitude math. Both metrics (value +
    weight) ship the 12-value contract."""
    out = s.serialize_monthly(None)
    assert out["monthlyAvg"] == [0.0] * 12
    assert out["weightMonthlyAvg"] == [0.0] * 12  # volume metric, same contract
    assert out["weightUnit"] == "mil t"
    assert len(out["months"]) == 12 and out["years"] == [] and out["matrix"] == {}
    assert out["weightMatrix"] == {}
    out_empty_df = s.serialize_monthly(pd.DataFrame())
    assert out_empty_df["monthlyAvg"] == [0.0] * 12
    assert out_empty_df["weightMonthlyAvg"] == [0.0] * 12


def test_serialize_monthly_populated_emits_value_and_weight():
    """A populated frame yields BOTH the Capital (US$ mi) and Volume (mil t)
    monthly matrices + 12-month averages, plus per-row v/w on the series."""
    df = pd.DataFrame(
        [
            {
                "reference_year": 2020,
                "reference_month": 1,
                "total_value_usd": 6_000_000,
                "total_weight_kg": 2_000_000,
            },
            {
                "reference_year": 2021,
                "reference_month": 1,
                "total_value_usd": 12_000_000,
                "total_weight_kg": 4_000_000,
            },
            {
                "reference_year": 2020,
                "reference_month": 7,
                "total_value_usd": 3_000_000,
                "total_weight_kg": 1_000_000,
            },
        ]
    )
    out = s.serialize_monthly(df)
    assert out["years"] == [2020, 2021]
    # January value avg = (6+12)/2 = 9 (US$ mi); weight avg = (2+4)/2 = 3 (mil t)
    assert out["monthlyAvg"][0] == 9.0
    assert out["weightMonthlyAvg"][0] == 3.0
    # July only in 2020 → its own value (no averaging over an absent 2021 cell)
    assert out["monthlyAvg"][6] == 3.0 and out["weightMonthlyAvg"][6] == 1.0
    assert out["matrix"]["2020"][0] == 6.0 and out["weightMatrix"]["2020"][0] == 2.0
    assert out["series"][0]["v"] == 6.0 and out["series"][0]["w"] == 2.0


def test_serialize_flow_builds_sankey_nodes_links_and_node_value_totals():
    """serialize_flow is the Sankey builder the route test stubs out — so its
    node-id assignment, origin/dest dedup, ÷1e6 scaling, and bidirectional
    per-node value accumulation are exercised here, not at the route layer."""
    links = pd.DataFrame(
        [
            {
                "origin_code": "SP",
                "origin_name": "São Paulo",
                "dest_code": "USA",
                "dest_name": "Estados Unidos",
                "value_usd": 2_000_000,
            },
            {
                "origin_code": "SP",
                "origin_name": "São Paulo",
                "dest_code": "CHN",
                "dest_name": "China",
                "value_usd": 3_000_000,
            },
            {
                "origin_code": "MG",
                "origin_name": "Minas Gerais",
                "dest_code": "USA",
                "dest_name": "Estados Unidos",
                "value_usd": 1_000_000,
            },
        ]
    )
    out = s.serialize_flow(
        {"links": links, "origin_label": "UF de origem", "dest_label": "País de destino"}
    )

    assert out["preview"] is False and out["unit"] == "US$"
    assert out["originLabel"] == "UF de origem" and out["destLabel"] == "País de destino"

    by_id = {n["id"]: n for n in out["nodes"]}
    # Origins/dests get separate id namespaces, assigned in first-seen order.
    assert by_id["o0"]["label"] == "São Paulo" and by_id["o0"]["side"] == "origin"
    assert by_id["o1"]["label"] == "Minas Gerais"
    assert by_id["d0"]["label"] == "Estados Unidos" and by_id["d0"]["side"] == "dest"
    assert by_id["d1"]["label"] == "China"
    # A repeated origin/dest must dedup to ONE node (4 nodes, not 6).
    assert len(out["nodes"]) == 4

    # Links carry the ÷1e6 (US$ mi) value, source/target by node id.
    assert out["links"] == [
        {"source": "o0", "target": "d0", "value": 2.0},
        {"source": "o0", "target": "d1", "value": 3.0},
        {"source": "o1", "target": "d0", "value": 1.0},
    ]
    # Each node's value accumulates EVERY incident link (both sides).
    assert by_id["o0"]["value"] == 5.0  # 2 + 3
    assert by_id["o1"]["value"] == 1.0
    assert by_id["d0"]["value"] == 3.0  # 2 + 1
    assert by_id["d1"]["value"] == 3.0


def test_serialize_flow_truncates_to_max_links():
    links = pd.DataFrame(
        [
            {
                "origin_code": "SP",
                "origin_name": "São Paulo",
                "dest_code": "USA",
                "dest_name": "EUA",
                "value_usd": 9_000_000,
            },
            {
                "origin_code": "MG",
                "origin_name": "Minas",
                "dest_code": "CHN",
                "dest_name": "China",
                "value_usd": 8_000_000,
            },
        ]
    )
    out = s.serialize_flow({"links": links}, max_links=1)
    assert len(out["links"]) == 1 and len(out["nodes"]) == 2  # only the first row survived
    assert out["links"][0]["value"] == 9.0


def test_serialize_flow_none_and_empty_are_safe():
    none_out = s.serialize_flow(None)
    assert none_out["nodes"] == [] and none_out["links"] == []
    assert none_out["originLabel"] == "Origem" and none_out["destLabel"] == "Destino"
    empty_out = s.serialize_flow({"links": pd.DataFrame(), "origin_label": "A", "dest_label": "B"})
    assert empty_out["nodes"] == [] and empty_out["links"] == []
    assert empty_out["originLabel"] == "A"  # provided labels survive the empty path


def test_serialize_partner_populated_path_scales_and_truncates():
    """serialize_partner's exp/imp/value ÷1e6 (US$ mi) + weight ÷1e6 (mil t) +
    price (US$/kg) scaling, and head(max_rows) truncation (otherwise only the
    empty path was covered)."""
    df = pd.DataFrame(
        [
            {
                "partner_name": "China",
                "exp_value_usd": 5_000_000,
                "imp_value_usd": 1_000_000,
                "value_usd": 6_000_000,
                "total_weight_kg": 2_000_000,
                "price_usd_per_kg": 3.0,
            },
            {
                "partner_name": "EUA",
                "exp_value_usd": 3_000_000,
                "imp_value_usd": 2_000_000,
                "value_usd": 5_000_000,
                "total_weight_kg": 1_000_000,
                "price_usd_per_kg": 5.0,
            },
        ]
    )
    out = s.serialize_partner(df, max_rows=1)
    assert out["preview"] is False and out["unit"] == "US$"
    assert len(out["partners"]) == 1  # truncated to max_rows
    assert out["partners"][0] == {
        "name": "China",
        "exp": 5.0,
        "imp": 1.0,
        "value": 6.0,
        "weight": 2.0,  # 2_000_000 kg ÷1e6 → mil t
        "price": 3.0,  # US$/kg, passthrough
    }


def test_serialize_partner_null_weight_yields_none_price():
    """A partner with no net weight (e.g. a COMTRADE row with missing quantity) →
    weight 0 and price None, so the view renders '—' instead of a div-by-zero."""
    df = pd.DataFrame(
        [
            {
                "partner_name": "X",
                "exp_value_usd": 0,
                "imp_value_usd": 0,
                "value_usd": 10,
                "total_weight_kg": None,
                "price_usd_per_kg": None,
            }
        ]
    )
    out = s.serialize_partner(df)
    assert out["partners"][0]["weight"] == 0.0
    assert out["partners"][0]["price"] is None


def test_serialize_products_by_uf_carries_the_sidra_table_when_the_reader_selects_it() -> None:
    """A TABELA viaja junto quando o leitor a seleciona (só bancos multi-tabela a têm).

    Madeira, lenha e carvão existem nas DUAS metades com o MESMO nome. Sem esta coluna a
    tela não tem como distinguir duas linhas legítimas — e o gráfico "O que <lugar>
    produz" desenhava uma barra só, com os dois rótulos por cima um do outro."""
    import pandas as pd

    from embrapa_dashboard.webapi import serializers as s

    df = pd.DataFrame(
        [
            {
                "product_code": "3455",
                "product_name": "Carvão vegetal",
                "sidra_tabela": "291",
                "total_value": 114_000_000,
            },
            {
                "product_code": "3433",
                "product_name": "Carvão vegetal",
                "sidra_tabela": "289",
                "total_value": 13_000_000,
            },
        ]
    )
    out = s.serialize_products_by_uf(df)
    # Duas linhas com o MESMO nome e códigos/metades diferentes — é isso que a tela precisa.
    assert [p["name"] for p in out["products"]] == ["Carvão vegetal", "Carvão vegetal"]
    assert [p["sidra_tabela"] for p in out["products"]] == ["291", "289"]
    assert [p["code"] for p in out["products"]] == ["3455", "3433"]


def test_serialize_products_by_uf_scales_value_and_quantities():
    """serialize_products_by_uf → value ÷1e6 (mi), q_mass ÷1e3 (mil t), q_vol ÷1e6
    (mi m³) — the SAME magnitudes the snapshot's productTS/ufData use; empty → []."""
    assert s.serialize_products_by_uf(None) == {"products": []}
    df = pd.DataFrame(
        [
            {
                "product_code": "4407",
                "product_name": "Madeira serrada",
                "total_value": 19_000_000,
                "q_mass": 2_000,
                "q_vol": 19_000_000,
            },
            {
                "product_code": "4403",
                "product_name": "Madeira em tora",
                "total_value": 5_000_000,
                "q_mass": None,
                "q_vol": 5_000_000,
            },
        ]
    )
    out = s.serialize_products_by_uf(df)
    assert out["products"][0] == {
        "code": "4407",
        "name": "Madeira serrada",
        "value": 19.0,  # 19_000_000 ÷1e6 → mi
        "q_mass": 2.0,  # 2_000 ÷1e3 → mil t
        "q_vol": 19.0,  # 19_000_000 ÷1e6 → mi m³
        "q_count": 0.0,  # absent → 0 (a herd row carries it for the 'Produtos do estado' rank)
        # Sem coluna `sidra_tabela` no df (banco de tabela única) → None, e a chave CONTINUA
        # presente: uma chave que aparece e some por banco faz o consumidor adivinhar.
        "sidra_tabela": None,
    }
    assert out["products"][1]["q_mass"] == 0.0  # None → 0
    # A livestock row carries q_count (mi un) so a value-less herd ranks by headcount.
    herd = s.serialize_products_by_uf(
        pd.DataFrame(
            [
                {
                    "product_code": "2670",
                    "product_name": "Bovino",
                    "total_value": 0,
                    "q_count": 238_000_000,
                }
            ]
        )
    )["products"][0]
    assert herd["q_count"] == 238.0 and herd["value"] == 0.0  # 238M head → 238 mi un


def test_serialize_product_uf_carries_per_family_quantities():
    """serialize_product_uf feeds the herd-by-UF map + ranking (ViewProductProfile +
    ViewRebanho). A value-less stock must rank by q_count, so the per-family quantities
    ride along (same ÷1e3/÷1e6 scaling as ufData). Empty df → {uf: []}."""
    assert s.serialize_product_uf(None) == {"uf": []}
    df = pd.DataFrame(
        [
            {
                "state_acronym": "MT",
                "state_name": "Mato Grosso",
                "region_abbrev": "CO",
                "total_value": 0,
                "q_mass": float("nan"),
                "q_vol": float("nan"),
                "q_count": 32_000_000,
            },
            {
                "state_acronym": "PA",
                "state_name": "Pará",
                "region_abbrev": "N",
                "total_value": 0,
                "q_mass": float("nan"),
                "q_vol": float("nan"),
                "q_count": 25_000_000,
            },
        ]
    )
    rows = s.serialize_product_uf(df)["uf"]
    assert {r["uf"] for r in rows} == {"MT", "PA"}
    mt = next(r for r in rows if r["uf"] == "MT")
    assert mt["q_count"] == 32.0 and mt["value"] == 0.0  # 32M head → 32 mi un, no value
    assert mt["q_mass"] == 0.0 and mt["q_vol"] == 0.0  # NaN → 0 (a herd has no mass/vol)


def test_serialize_table_page_shapes_columns_rows_total():
    """The raw-table page is a faithful window (the 'Dados' view): columns carry name+type,
    rows are the values aligned to schema order, NaN rides through (the app's
    SafeJSONProvider coerces it to null on the wire). None (non-live banco) → empty page."""
    import math

    assert s.serialize_table_page(None) == {
        "columns": [],
        "rows": [],
        "total": 0,
        "table": None,
        "label": None,
        "grain": None,
    }
    df = pd.DataFrame(
        [
            {"reference_year": 2024, "product_code": "2670", "val": 1.5},
            {"reference_year": 2023, "product_code": "2670", "val": float("nan")},
        ]
    )
    page = {
        "columns": [
            {"name": "reference_year", "type": "INTEGER"},
            {"name": "product_code", "type": "STRING"},
            {"name": "val", "type": "FLOAT"},
        ],
        "df": df,
        "total": 1234,
        "table": "gold_ppm_production",
        "label": "Gold · pecuária PPM",
        "grain": "linha por (ano, UF, …)",
    }
    out = s.serialize_table_page(page)
    assert [c["name"] for c in out["columns"]] == ["reference_year", "product_code", "val"]
    assert out["columns"][0]["type"] == "INTEGER"
    assert out["total"] == 1234 and out["table"] == "gold_ppm_production"
    # rows are verbatim values aligned to the schema order (numpy scalars coerce on ==)
    assert int(out["rows"][0][0]) == 2024 and out["rows"][0][1] == "2670"
    assert float(out["rows"][0][2]) == 1.5
    assert int(out["rows"][1][0]) == 2023
    assert math.isnan(out["rows"][1][2])  # NaN preserved here; → null via SafeJSONProvider


def test_serialize_table_page_bq_nullable_na_serializes_to_json_null():
    """The REAL BigQuery path the plain-dict test above MISSES. ``to_dataframe`` defaults
    ``int_dtype=Int64`` / ``bool_dtype=BooleanDtype`` (nullable), so a NULL INTEGER/BOOLEAN
    cell is pandas ``pd.NA``, and a NULL DATE/TIMESTAMP is ``pd.NaT`` — both reach
    ``serialize_table_page``'s ``df.values.tolist()`` uncoerced. Neither is JSON-serializable
    (``pd.NA`` raises ``TypeError`` in the encoder → HTTP 500; ``pd.NaT.isoformat()`` leaks the
    string ``"NaT"``), so the app's ``SafeJSONProvider`` MUST map both to ``null`` on the wire.

    The frame is deliberately MIXED-dtype: ``df.values`` then stays an *object* array that
    PRESERVES the ``pd.NA``/``pd.NaT`` scalars. A single Int64 column would upcast NA to float
    ``nan`` (handled by a different branch) and never exercise the ``pd.NA`` path at all."""
    import json

    pytest.importorskip("flask")
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.webapi import app as app_mod

    cols = {
        "reference_year": pd.array([2024, None], dtype="Int64"),  # nullable INTEGER → pd.NA
        "flag": pd.array([True, None], dtype="boolean"),  # nullable BOOLEAN → pd.NA
        "name": pd.Series(["a", None], dtype="object"),  # STRING → None (JSON-native control)
        "ts": pd.to_datetime(pd.Series(["2024-01-01T00:00:00", None])),  # TIMESTAMP → pd.NaT
    }
    try:  # DATE → db_dtypes 'dbdate', NULL → pd.NaT (present via the webapi/bigquery extra)
        import db_dtypes  # noqa: F401

        cols["d"] = pd.array([pd.Timestamp("2024-06-01").date(), None], dtype="dbdate")
    except Exception:
        pass

    df = pd.DataFrame(cols)
    assert df.values.dtype == object  # mixed dtypes → object array → NA scalars survive
    page = {
        "columns": [{"name": c, "type": "STRING"} for c in df.columns],
        "df": df,
        "total": 2,
        "table": "gold_ppm_production",
        "label": "Gold",
        "grain": "g",
    }
    payload = s.serialize_table_page(page)
    # The serializer does NO per-cell coercion, so the raw missing scalars ride through …
    null_row = payload["rows"][1]
    assert any(c is pd.NA for c in null_row), "nullable INT/BOOL NULL must be pd.NA in the row"
    assert any(c is pd.NaT for c in null_row), "DATE/TIMESTAMP NULL must be pd.NaT in the row"

    # … and SafeJSONProvider must turn the WHOLE payload into valid JSON without raising
    # (a raise here is exactly the HTTP 500 in prod), with every NA cell as JSON null.
    app = app_mod.create_app()
    reparsed = json.loads(app.json.dumps(payload))  # must NOT raise on pd.NA / pd.NaT
    out_null = reparsed["rows"][1]
    assert all(v is None for v in out_null), f"every NULL cell → JSON null, got {out_null!r}"
    # the non-null row round-trips intact (no collateral damage)
    assert reparsed["rows"][0][0] == 2024 and reparsed["rows"][0][1] is True
    assert reparsed["rows"][0][2] == "a"
