"""Coverage tests for serving/curation.py — the editable commodity-catalog writer.

Targets the currently-uncovered branches: the catalog-editors ensure helper, the
ciclo_de_vida over-length + invalid-enum ValueErrors, the agrupamento /
descricao_produto over-length ValueErrors, the ``_current_prefixes`` NotFound
fall-through, the change_id dedup short-circuits on both record + remove, and the
cache-invalidation paths.

Mirrors the fixture/mock style of tests/test_serving.py: ``pytest.importorskip``
on flask-caching, ``mock.Mock()`` recording-stub BigQuery clients, ``monkeypatch``
of ``ensure_dataset`` / ``_current_prefixes`` / ``_change_id_seen``, the IAP email
header, and the shared ``_isolated_settings`` / ``_bind_simplecache`` helpers.
"""

from __future__ import annotations

from unittest import mock

import pytest
from google.api_core.exceptions import BadRequest, NotFound

from embrapa_dashboard.serving import iap
from tests.test_serving import _bind_simplecache, _isolated_settings


def _settings():
    return _isolated_settings(gcp_project_id="test-project")


_HEADERS = {iap.IAP_EMAIL_HEADER: "accounts.google.com:alice@embrapa.br"}


# ── ensure_catalog_editors_table (lines 119-124) ──────────────────────────────


def test_ensure_catalog_editors_table_creates_with_explicit_schema(monkeypatch):
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import curation

    monkeypatch.setattr(curation, "ensure_dataset", lambda *a, **k: None)
    client = mock.Mock()
    fqn = curation.ensure_catalog_editors_table(settings=_settings(), client=client)

    assert fqn.endswith(".catalog_editors")
    table_arg = client.create_table.call_args.args[0]
    assert {f.name for f in table_arg.schema} >= {"resource", "email", "added_by", "added_at"}
    # exists_ok keeps it idempotent.
    assert client.create_table.call_args.kwargs.get("exists_ok") is True


# ── _validate_catalog_edit: ciclo_de_vida guards (lines 151, 153) ─────────────


def test_validate_catalog_edit_rejects_overlong_ciclo():
    from embrapa_dashboard.serving import curation
    from embrapa_dashboard.serving.research_inputs import MAX_STAGE_LEN

    with pytest.raises(ValueError, match="ciclo_de_vida excede"):
        curation._validate_catalog_edit("4403", "un_comtrade", "x" * (MAX_STAGE_LEN + 1))


def test_validate_catalog_edit_rejects_invalid_ciclo_enum():
    from embrapa_dashboard.serving import curation

    # A non-empty value that is not one of the two F7 ciclo-de-vida literals → reject,
    # keeping the UI dropdown + dbt visibility gate in lockstep.
    with pytest.raises(ValueError, match="inválido"):
        curation._validate_catalog_edit("4403", "un_comtrade", "Talvez disponível")


def test_validate_catalog_edit_rejects_non_numeric_code():
    from embrapa_dashboard.serving import curation

    # Every source code (SIDRA/NCM/HS) is numeric — a non-numeric code is a typo.
    with pytest.raises(ValueError, match="apenas dígitos"):
        curation._validate_catalog_edit("44O3", "un_comtrade", None)  # letter O


def test_validate_catalog_edit_rejects_overlong_code():
    from embrapa_dashboard.serving import curation

    # A pathologically long code is capped before storage (real codes are <=8 digits).
    with pytest.raises(ValueError, match="excede"):
        curation._validate_catalog_edit("1" * (curation.MAX_CODE_LEN + 1), "un_comtrade", None)
    # A normal all-digit code still passes the length + numeric guards.
    curation._validate_catalog_edit("1" * curation.MAX_CODE_LEN, "un_comtrade", None)


# ── _validate_sidra_tabela: PPM herd/animal discriminator ─────────────────────


def test_validate_sidra_tabela_required_for_ppm():
    from embrapa_dashboard.serving import curation

    with pytest.raises(ValueError, match="obrigatória"):
        curation._validate_sidra_tabela("ppm", None, _settings())


def test_validate_sidra_tabela_rejects_bad_value_for_ppm():
    from embrapa_dashboard.serving import curation

    with pytest.raises(ValueError, match="inválida"):
        curation._validate_sidra_tabela("ppm", "9999", _settings())


def test_validate_sidra_tabela_accepts_valid_ppm():
    from embrapa_dashboard.serving import curation

    # Both configured PPM SIDRA tables (herd 3939 / animal 74) are accepted.
    curation._validate_sidra_tabela("ppm", "3939", _settings())
    curation._validate_sidra_tabela("ppm", "74", _settings())


def test_validate_sidra_tabela_rejected_for_single_table_banco():
    """pam/comex/comtrade map to ONE SIDRA table (or none), so a tag is meaningless there."""
    from embrapa_dashboard.serving import curation

    with pytest.raises(ValueError, match="só se aplica"):
        curation._validate_sidra_tabela("pam", "3939", _settings())


def test_validate_sidra_tabela_accepts_both_pevs_halves():
    """PEVS became multi-table on 2026-08-29 (extração t289 + silvicultura t291)."""
    from embrapa_dashboard.serving import curation

    curation._validate_sidra_tabela("pevs", "289", _settings())
    curation._validate_sidra_tabela("pevs", "291", _settings())


def test_validate_sidra_tabela_required_for_every_multi_table_banco():
    """A tag virou OBRIGATÓRIA nos dois bancos multi-tabela quando a identidade de um
    produto passou a ser (banco, tabela, código): sem ela a entrada não cai em nenhuma das
    duas metades, cai numa TERCEIRA identidade (a sentinela) que não corresponde a dado
    nenhum. Era opcional no pevs enquanto a chave a ignorava."""
    from embrapa_dashboard.serving import curation

    for banco in ("pevs", "ppm"):
        with pytest.raises(ValueError, match="obrigatória"):
            curation._validate_sidra_tabela(banco, None, _settings())


def test_validate_sidra_tabela_preserved_on_update():
    """Num UPDATE o chamador preserva a tag guardada, então a ausência é legítima."""
    from embrapa_dashboard.serving import curation

    curation._validate_sidra_tabela("pevs", None, _settings(), require_for_ppm=False)


def test_validate_sidra_tabela_rejects_the_other_bancos_table():
    """A multi-table banco accepts ONLY its own tables — ppm's 3939 is not a pevs half."""
    from embrapa_dashboard.serving import curation

    with pytest.raises(ValueError, match="inválida para o banco"):
        curation._validate_sidra_tabela("pevs", "3939", _settings())


def test_writer_rejects_a_bad_tag_before_touching_bigquery():
    """The early gate must DELEGATE to _validate_sidra_tabela, not restate it. It was a
    verbatim copy, and when pevs became multi-table only the validator was updated — so
    every pevs stamp was still refused with the stale "só se aplica ao banco 'ppm'".
    No client/settings are needed: a correct gate rejects before resolving either."""
    from embrapa_dashboard.serving import curation

    with pytest.raises(ValueError, match="inválida para o banco"):
        curation.record_produto_catalog(
            "3457",
            "pevs",
            {},
            agrupamento="Madeira",
            sidra_tabela="3939",
            settings=_settings(),
        )


def test_validate_sidra_tabela_optional_for_ppm_update():
    from embrapa_dashboard.serving import curation

    # On an UPDATE (require_for_ppm=False) a missing tag is allowed (the caller preserves it).
    curation._validate_sidra_tabela("ppm", None, _settings(), require_for_ppm=False)


def test_record_produto_catalog_new_ppm_requires_sidra_tabela(monkeypatch):
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import curation

    monkeypatch.setattr(curation, "ensure_dataset", lambda *a, **k: None)
    monkeypatch.setattr(curation, "_is_active_entry", lambda *a, **k: False)  # NEW entry
    monkeypatch.setattr(curation, "_check_code_status", lambda *a, **k: None)
    with pytest.raises(ValueError, match="obrigatória"):
        curation.record_produto_catalog(
            "2670",
            "ppm",
            _HEADERS,
            agrupamento="Bovino",
            settings=_settings(),
            client=mock.Mock(),
            invalidate_cache=False,
        )


def test_record_produto_catalog_ppm_update_preserves_sidra_tabela(monkeypatch):
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import curation

    monkeypatch.setattr(curation, "ensure_dataset", lambda *a, **k: None)
    monkeypatch.setattr(curation, "_is_active_entry", lambda *a, **k: True)  # UPDATE
    monkeypatch.setattr(curation, "_check_code_status", lambda *a, **k: None)
    monkeypatch.setattr(curation, "_current_sidra_tabela", lambda *a, **k: "3939")  # stored tag
    client = mock.Mock()
    client.query.return_value.result.return_value = []
    # Inline ciclo edit re-sends no sidra_tabela → the stored '3939' must be preserved.
    curation.record_produto_catalog(
        "2670",
        "ppm",
        _HEADERS,
        agrupamento="Bovino",
        ciclo_de_vida="Fazer Ingestão e deixar disponível",
        settings=_settings(),
        client=client,
        invalidate_cache=False,
    )
    params = {p.name: p.value for p in client.query.call_args.kwargs["job_config"].query_parameters}
    assert params["sidra_tabela"] == "3939"


# ── record_produto_catalog: descricao_produto is preserve-on-omit ─────────────


def _record_with(monkeypatch, curation, **kwargs):
    """Drive record_produto_catalog as an UPDATE and return the written parameters."""
    monkeypatch.setattr(curation, "ensure_dataset", lambda *a, **k: None)
    monkeypatch.setattr(curation, "_is_active_entry", lambda *a, **k: True)  # UPDATE
    monkeypatch.setattr(curation, "_check_code_status", lambda *a, **k: None)
    monkeypatch.setattr(curation, "_current_lifecycle", lambda *a, **k: ("ativa", "visivel"))
    client = mock.Mock()
    client.query.return_value.result.return_value = []
    curation.record_produto_catalog(
        "3405",
        "pevs",
        _HEADERS,
        agrupamento="Castanha-do-pará",
        settings=_settings(),
        client=client,
        invalidate_cache=False,
        **kwargs,
    )
    return {p.name: p.value for p in client.query.call_args.kwargs["job_config"].query_parameters}


def test_record_produto_catalog_update_preserves_descricao_produto(monkeypatch):
    """An edit that changes only another field must NOT erase the researcher's note.

    The writer overwrites the whole row, so omitting descricao_produto used to store NULL —
    a free-text annotation gone for good (unlike an axis, which can be re-picked)."""
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import curation

    monkeypatch.setattr(curation, "_current_descricao", lambda *a, **k: "anotação do pesquisador")
    params = _record_with(monkeypatch, curation, ingestao="pausada")
    assert params["descricao_produto"] == "anotação do pesquisador"


def test_record_produto_catalog_update_honours_an_explicit_empty_descricao(monkeypatch):
    """`''` is an explicit CLEAR (the ✎ field emptied), NOT an omission — it must win over
    the stored note. Collapsing '' to None would make the note impossible to erase."""
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import curation

    def _boom(*a, **k):  # preservation must not even be consulted for an explicit value
        raise AssertionError("_current_descricao consulted for an explicit '' clear")

    monkeypatch.setattr(curation, "_current_descricao", _boom)
    params = _record_with(monkeypatch, curation, descricao_produto="")
    assert params["descricao_produto"] == ""


# ── _is_active_entry: NotFound fall-through (log table absent) ────────────────


def test_is_active_entry_false_when_table_absent():
    from embrapa_dashboard.serving import curation

    client = mock.Mock()
    client.query.side_effect = NotFound("table does not exist yet")
    # No log table yet → the entry can't be active → False.
    assert curation._is_active_entry(client, "proj.ds.tbl", "4403", "un_comtrade") is False


# ── record_produto_catalog: over-length text guards (lines 241, 243) ────────


def test_record_produto_catalog_rejects_overlong_agrupamento(monkeypatch):
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import curation
    from embrapa_dashboard.serving.research_inputs import MAX_NOTE_LEN

    monkeypatch.setattr(curation, "ensure_dataset", lambda *a, **k: None)
    with pytest.raises(ValueError, match="agrupamento excede"):
        curation.record_produto_catalog(
            "4403",
            "un_comtrade",
            _HEADERS,
            agrupamento="a" * (MAX_NOTE_LEN + 1),
            settings=_settings(),
            client=mock.Mock(),
            invalidate_cache=False,
        )


def test_record_produto_catalog_rejects_overlong_descricao(monkeypatch):
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import curation
    from embrapa_dashboard.serving.research_inputs import MAX_NOTE_LEN

    monkeypatch.setattr(curation, "ensure_dataset", lambda *a, **k: None)
    with pytest.raises(ValueError, match="descricao_produto excede"):
        curation.record_produto_catalog(
            "4403",
            "un_comtrade",
            _HEADERS,
            agrupamento="Madeira",
            descricao_produto="d" * (MAX_NOTE_LEN + 1),
            settings=_settings(),
            client=mock.Mock(),
            invalidate_cache=False,
        )


# ── record_produto_catalog: change_id dedup short-circuit (lines 257-260) ───


def test_record_produto_catalog_rejects_overlong_agrupamento_id(monkeypatch):
    """agrupamento_id is user-writable (a client may send it, winning over the _slug default),
    so it is length-capped like its siblings — a pathologically long value is rejected."""
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import curation
    from embrapa_dashboard.serving.research_inputs import MAX_STAGE_LEN

    monkeypatch.setattr(curation, "ensure_dataset", lambda *a, **k: None)
    with pytest.raises(ValueError, match="agrupamento_id excede"):
        curation.record_produto_catalog(
            "4403",
            "un_comtrade",
            _HEADERS,
            agrupamento="Madeira",
            agrupamento_id="a" * (MAX_STAGE_LEN + 1),
            settings=_settings(),
            client=mock.Mock(),
            invalidate_cache=False,
        )


def test_record_produto_catalog_dedupes_on_seen_change_id(monkeypatch):
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import curation

    monkeypatch.setattr(curation, "ensure_dataset", lambda *a, **k: None)
    monkeypatch.setattr(curation, "_check_code_status", lambda *a, **k: None)
    # A client-supplied change_id already present in the log → the write is a no-op.
    monkeypatch.setattr(curation, "_change_id_seen", lambda *a, **k: True)
    client = mock.Mock()
    client.query.return_value.result.return_value = []

    rec = curation.record_produto_catalog(
        "4403",
        "un_comtrade",
        _HEADERS,
        agrupamento="Madeira",
        change_id="retry-key-1",
        settings=_settings(),
        client=client,
        invalidate_cache=False,
    )

    assert rec["deduped"] is True
    assert rec["active"] is True
    assert "code_prefix" not in rec
    assert rec["change_id"] == "retry-key-1"
    # No INSERT was issued on the dedup path — the existence gate is monkeypatched away,
    # so query() was never called for an insert.
    insert_calls = [c for c in client.query.call_args_list if "insert into" in c.args[0].lower()]
    assert insert_calls == []


def test_record_produto_catalog_change_id_conflict_different_key(monkeypatch):
    """Reusing a change_id whose STORED row is a different (codigo_produto, banco) → 409, so the
    caller can't silently receive an unrelated prior product's row."""
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import curation
    from embrapa_dashboard.serving.research_inputs import ChangeIdConflictError

    monkeypatch.setattr(curation, "ensure_dataset", lambda *a, **k: None)
    monkeypatch.setattr(curation, "_is_active_entry", lambda *a, **k: False)
    monkeypatch.setattr(curation, "_check_code_status", lambda *a, **k: None)
    monkeypatch.setattr(curation, "_change_id_seen", lambda *a, **k: True)
    monkeypatch.setattr(
        curation,
        "_row_for_change_id",
        lambda *a, **k: {"codigo_produto": "9999", "banco": "un_comtrade", "active": True},
    )
    with pytest.raises(ChangeIdConflictError):
        curation.record_produto_catalog(
            "4403",
            "un_comtrade",
            _HEADERS,
            agrupamento="Madeira",
            change_id="reused",
            settings=_settings(),
            client=mock.Mock(),
            invalidate_cache=False,
        )


def test_record_produto_catalog_same_key_different_attr_no_conflict(monkeypatch):
    """A stable change_id whose stored row shares the KEY but differs only on a mutable attribute
    (agrupamento) stays a benign no-op — protects seed_catalog_from_env's idempotent re-seed."""
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import curation

    monkeypatch.setattr(curation, "ensure_dataset", lambda *a, **k: None)
    monkeypatch.setattr(curation, "_is_active_entry", lambda *a, **k: False)
    monkeypatch.setattr(curation, "_check_code_status", lambda *a, **k: None)
    monkeypatch.setattr(curation, "_change_id_seen", lambda *a, **k: True)
    stored = {
        "codigo_produto": "4403",
        "banco": "un_comtrade",
        "active": True,
        "agrupamento": "Madeira Antiga",
        "deduped": True,
    }
    monkeypatch.setattr(curation, "_row_for_change_id", lambda *a, **k: stored)
    rec = curation.record_produto_catalog(
        "4403",
        "un_comtrade",
        _HEADERS,
        agrupamento="Madeira Nova",  # differs, but same key ⇒ no conflict
        change_id="seed-key",
        settings=_settings(),
        client=mock.Mock(),
        invalidate_cache=False,
    )
    assert rec is stored  # returns the STORED row, not the retried agrupamento


# ── record_produto_catalog: cache invalidation on save (line 291) ───────────


def test_record_produto_catalog_invalidates_cache_on_save(monkeypatch):
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import curation

    monkeypatch.setattr(curation, "ensure_dataset", lambda *a, **k: None)
    monkeypatch.setattr(curation, "_check_code_status", lambda *a, **k: None)
    client = mock.Mock()
    client.query.return_value.result.return_value = []

    seen = {"called": False}

    def _spy():
        seen["called"] = True

    monkeypatch.setattr(curation, "invalidate_produto_catalog_cache", _spy)

    rec = curation.record_produto_catalog(
        "4403",
        "un_comtrade",
        _HEADERS,
        agrupamento="Madeira",
        settings=_settings(),
        client=client,
        invalidate_cache=True,
    )
    assert rec["deduped"] is False
    assert seen["called"] is True


# ── remove_produto_catalog: change_id dedup short-circuit (line 333) ────────


def test_remove_produto_catalog_dedupes_on_seen_change_id(monkeypatch):
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import curation

    monkeypatch.setattr(curation, "ensure_dataset", lambda *a, **k: None)
    monkeypatch.setattr(curation, "_change_id_seen", lambda *a, **k: True)
    client = mock.Mock()
    client.query.return_value.result.return_value = []

    rec = curation.remove_produto_catalog(
        "4403",
        "un_comtrade",
        _HEADERS,
        change_id="retry-remove-1",
        settings=_settings(),
        client=client,
        invalidate_cache=False,
    )

    assert rec["deduped"] is True
    assert rec["active"] is False
    assert rec["change_id"] == "retry-remove-1"
    # The dedup path echoes the codigo as the prefix and never inserts a tombstone.
    insert_calls = [c for c in client.query.call_args_list if "insert into" in c.args[0].lower()]
    assert insert_calls == []


def test_remove_produto_catalog_change_id_conflict_active_flip(monkeypatch):
    """A record's change_id (its stored row is active=True) reused for a REMOVE → 409, not a
    silent replay that echoes the active row as if it were a tombstone."""
    # Desde v1.39.2 o tombstone resolve a tabela SIDRA da entrada (ela faz parte da
    # chave que decide se um change_id repetido é replay do MESMO produto). Este teste
    # exercita o conflito, não a resolução — então ela é dublada.
    monkeypatch.setattr(
        "embrapa_dashboard.serving.curation._current_sidra_tabela", lambda *a, **k: "289"
    )
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import curation
    from embrapa_dashboard.serving.research_inputs import ChangeIdConflictError

    monkeypatch.setattr(curation, "ensure_dataset", lambda *a, **k: None)
    monkeypatch.setattr(curation, "_change_id_seen", lambda *a, **k: True)
    monkeypatch.setattr(
        curation,
        "_row_for_change_id",
        lambda *a, **k: {"codigo_produto": "4403", "banco": "un_comtrade", "active": True},
    )
    with pytest.raises(ChangeIdConflictError):
        curation.remove_produto_catalog(
            "4403",
            "un_comtrade",
            _HEADERS,
            change_id="reused",
            settings=_settings(),
            client=mock.Mock(),
            invalidate_cache=False,
        )


# ── remove_produto_catalog: cache invalidation on tombstone (line 374) ──────


def test_remove_produto_catalog_invalidates_cache_on_tombstone(monkeypatch):
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import curation

    monkeypatch.setattr(curation, "ensure_dataset", lambda *a, **k: None)
    monkeypatch.setattr(curation, "_is_active_entry", lambda *a, **k: True)
    client = mock.Mock()
    client.query.return_value.result.return_value = []

    seen = {"called": False}
    monkeypatch.setattr(
        curation,
        "invalidate_produto_catalog_cache",
        lambda: seen.__setitem__("called", True),
    )

    rec = curation.remove_produto_catalog(
        "4403",
        "un_comtrade",
        _HEADERS,
        settings=_settings(),
        client=client,
        invalidate_cache=True,
    )
    assert rec["active"] is False
    assert seen["called"] is True


# ── invalidate_produto_catalog_cache: the real body (lines 467-468) ─────────


def test_invalidate_produto_catalog_cache_drops_memoized():
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import curation

    app, _cache = _bind_simplecache()
    with app.app_context():
        # cache is bound to a live SimpleCache backend → delete_memoized succeeds,
        # exercising the happy path (not the except branch).
        curation.invalidate_produto_catalog_cache()


def test_invalidate_produto_catalog_cache_swallows_unbound_backend(monkeypatch):
    """When the cache is unbound / backend down, ``delete_memoized`` raises and the
    helper logs a warning instead of propagating (best-effort invalidation)."""
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import curation

    def _boom(*_a, **_k):
        raise RuntimeError("cache backend unbound")

    monkeypatch.setattr(curation.cache, "delete_memoized", _boom)
    # Must not raise.
    curation.invalidate_produto_catalog_cache()


# ── add/remove_catalog_editor + add/remove_attribute_editor (CLI-backed writers) ───────


def test_add_catalog_editor_inserts_normalized_row(monkeypatch):
    from embrapa_dashboard.serving import curation

    monkeypatch.setattr(
        curation, "ensure_catalog_editors_table", lambda *a, **k: "p.ds.catalog_editors"
    )
    client = mock.Mock()
    e = curation.add_catalog_editor(
        "produto_catalog",
        "  Alice@Embrapa.BR ",
        added_by="boss@x",
        settings=_settings(),
        client=client,
    )
    assert e == "alice@embrapa.br"  # trimmed + lower-cased
    sql = client.query.call_args.args[0].lower()
    assert "insert into" in sql
    params = {p.name: p.value for p in client.query.call_args.kwargs["job_config"].query_parameters}
    assert params["resource"] == "produto_catalog" and params["email"] == "alice@embrapa.br"


def test_remove_catalog_editor_returns_affected_rows(monkeypatch):
    from embrapa_dashboard.serving import curation

    monkeypatch.setattr(
        curation, "ensure_catalog_editors_table", lambda *a, **k: "p.ds.catalog_editors"
    )
    client = mock.Mock()
    client.query.return_value.num_dml_affected_rows = 2
    n = curation.remove_catalog_editor(
        "produto_catalog", "alice@embrapa.br", settings=_settings(), client=client
    )
    assert n == 2
    assert "delete from" in client.query.call_args.args[0].lower()


def test_add_and_remove_attribute_editor(monkeypatch):
    from embrapa_dashboard.serving import research_inputs

    monkeypatch.setattr(
        research_inputs, "ensure_attribute_editors_table", lambda *a, **k: "p.ds.attribute_editors"
    )
    client = mock.Mock()
    e = research_inputs.add_attribute_editor(" Bob@X.BR ", settings=_settings(), client=client)
    assert e == "bob@x.br"
    params = {p.name: p.value for p in client.query.call_args.kwargs["job_config"].query_parameters}
    assert params["email"] == "bob@x.br"

    client.query.return_value.num_dml_affected_rows = 1
    assert (
        research_inputs.remove_attribute_editor("bob@x.br", settings=_settings(), client=client)
        == 1
    )


# ── seed_catalog_from_env (the CATALOG_AUTHORITATIVE_INGESTION cutover backfill) ──


def test_seed_catalog_from_env_routes_and_reuses(monkeypatch):
    pytest.importorskip("flask_caching")
    import pandas as pd

    from embrapa_dashboard.serving import curation
    from tests.test_serving import _isolated_settings

    cfg = _isolated_settings(
        gcp_project_id="test-project",
        ibge_product_codes="3405",
        pam_product_codes="40124",
        ppm_herd_product_codes="2670",
        ppm_animal_product_codes="2682",
    )
    # One pre-existing entry (pam:40124) → its agrupamento must be reused, not overwritten.
    monkeypatch.setattr(
        curation.gateway,
        "fetch_produto_catalog",
        lambda banco=None: pd.DataFrame(
            [
                {
                    "codigo_produto": "40124",
                    "banco": "pam",
                    "agrupamento": "Soja",
                    "agrupamento_id": "soja",
                    "descricao_produto": None,
                    "ciclo_de_vida": None,
                }
            ]
        ),
    )
    calls = []

    def _rec(code, banco, headers, **k):
        calls.append({"code": code, "banco": banco, **k})
        return {"deduped": False}

    monkeypatch.setattr(curation, "record_produto_catalog", _rec)
    monkeypatch.setattr(curation, "invalidate_produto_catalog_cache", lambda: None)

    res = curation.seed_catalog_from_env({}, settings=cfg, client=mock.Mock())
    assert res == {"seeded": 4, "skipped": 0}
    by_code = {c["code"]: c for c in calls}
    # PEVS/PAM carry no sidra_tabela; PPM herd→3939, animal→74.
    assert by_code["3405"]["banco"] == "pevs" and by_code["3405"]["sidra_tabela"] is None
    assert by_code["2670"]["sidra_tabela"] == "3939"
    assert by_code["2682"]["sidra_tabela"] == "74"
    # New codes fall back to the code as its own agrupamento; existing ones are reused.
    assert by_code["3405"]["agrupamento"] == "3405"
    assert by_code["40124"]["agrupamento"] == "Soja"


def test_seed_catalog_from_env_coerces_null_agrupamento_id(monkeypatch):
    """A NULL agrupamento_id/agrupamento (NaN float from BigQuery→pandas) must not crash the
    seed on ``.strip()`` — it is coerced to None (record_produto_catalog then re-slugs)."""
    pytest.importorskip("flask_caching")
    import pandas as pd

    from embrapa_dashboard.serving import curation
    from tests.test_serving import _isolated_settings

    cfg = _isolated_settings(
        gcp_project_id="test-project",
        ibge_product_codes="3405",
        pam_product_codes="40124",
        ppm_herd_product_codes="2670",
        ppm_animal_product_codes="2682",
    )
    monkeypatch.setattr(
        curation.gateway,
        "fetch_produto_catalog",
        lambda banco=None: pd.DataFrame(
            [
                {
                    "codigo_produto": "3405",
                    "banco": "pevs",
                    "agrupamento": "Castanha",
                    "agrupamento_id": float("nan"),
                    "descricao_produto": None,
                    "ciclo_de_vida": None,
                }
            ]
        ),
    )
    calls = []
    monkeypatch.setattr(
        curation,
        "record_produto_catalog",
        lambda code, banco, headers, **k: calls.append({"code": code, **k}) or {"deduped": False},
    )
    monkeypatch.setattr(curation, "invalidate_produto_catalog_cache", lambda: None)
    curation.seed_catalog_from_env({}, settings=cfg, client=mock.Mock())  # must not raise
    p = {c["code"]: c for c in calls}["3405"]
    assert p["agrupamento"] == "Castanha"  # valid string preserved
    assert p["agrupamento_id"] is None  # NaN coerced to None


# ── Cross-layer coupling: the visibility gate's vocabulary (#1 audit) ───────────
def test_visibility_gate_vocabulary_matches_across_layers():
    """The gate's vocabulary couples Python to dbt, and a drift fails it OPEN — a produto
    the researcher marked hidden would pass validation and still show on every chart.

    Since the two-axis split the coupling moved: the MODEL filters on the coded value, and
    the LEGACY prose lives only in the catalog_lifecycle macro, which is the single place
    that translates history (the log is append-only, so those old rows are read forever).
    Pin all three so any of them drifting is a red test, not a silent leak."""
    import pathlib

    from embrapa_dashboard.serving import curation

    repo = pathlib.Path(__file__).resolve().parents[1]
    macro = (repo / "dbt/macros/catalog_lifecycle.sql").read_text(encoding="utf-8")
    model = (repo / "dbt/models/core/dim_produto_visibility.sql").read_text(encoding="utf-8")

    # 1. The macro still knows how to translate BOTH legacy prose values. Losing either
    #    would silently reclassify every pre-split row (the OCULTO one fails the gate open).
    for legacy in (curation.CICLO_DE_VIDA_OCULTO, curation.CICLO_DE_VIDA_VISIVEL):
        assert legacy in macro, (
            f"catalog_lifecycle macro no longer translates the legacy value {legacy!r} — "
            "pre-split rows would be misread (hidden produtos could reappear)."
        )
    # 2. The macro emits the SAME codes Python validates/writes.
    for code in (curation.VISIBILIDADE_OCULTO, curation.VISIBILIDADE_VISIVEL):
        assert f"'{code}'" in macro, f"macro lost the coded visibility value {code!r}."
    assert f"'{curation.INGESTAO_ATIVA}'" in macro, "macro lost the ingestao default."

    # 3. The gate filters on the CODE (not the retired prose).
    assert f"= '{curation.VISIBILIDADE_OCULTO}'" in model, (
        "dim_produto_visibility no longer filters on VISIBILIDADE_OCULTO — the gate would "
        "stop hiding anything."
    )


def test_lifecycle_translation_matches_the_dbt_macro():
    """visibilidade_efetiva/ingestao_efetiva are the Python twins of the dbt macro: one
    drives the admin editor, the other the researcher-facing gate. If they disagree, the
    editor shows a produto as visible while the gate hides it (or worse, the reverse).
    Assert the exact truth table both must implement."""
    from embrapa_dashboard.serving import curation as c

    # Coded value wins.
    assert c.visibilidade_efetiva("oculto", None) == "oculto"
    assert c.visibilidade_efetiva("visivel", c.CICLO_DE_VIDA_OCULTO) == "visivel"
    # Legacy prose translated when the code is absent.
    assert c.visibilidade_efetiva(None, c.CICLO_DE_VIDA_OCULTO) == "oculto"
    assert c.visibilidade_efetiva(None, c.CICLO_DE_VIDA_VISIVEL) == "visivel"
    # Unknown / empty NEVER hides (fail-safe: the gate is a NOT EXISTS over hidden codes).
    assert c.visibilidade_efetiva(None, None) == "visivel"
    assert c.visibilidade_efetiva("ocluto", None) == "visivel"  # typo → not hidden
    assert c.visibilidade_efetiva(None, "algo inesperado") == "visivel"

    # Ingestion: NULL predates the axis and everything active was ingested → 'ativa'.
    assert c.ingestao_efetiva(None) == "ativa"
    assert c.ingestao_efetiva("pausada") == "pausada"
    assert c.ingestao_efetiva("ativa") == "ativa"
    assert c.ingestao_efetiva("lixo") == "ativa"


def test_current_sidra_tabela_reads_stored_absent_and_pre_migration(monkeypatch):
    """_current_sidra_tabela returns the stored PPM tag, None when absent, and None ONLY on
    the pre-migration NotFound/BadRequest — a transient fault must NOT be swallowed here."""
    from types import SimpleNamespace

    from google.api_core.exceptions import BadRequest

    from embrapa_dashboard.serving import curation

    client = mock.Mock()
    client.query.return_value.result.return_value = [SimpleNamespace(sidra_tabela="3939")]
    assert curation._current_sidra_tabela(client, "t.r.log", "3405", "ppm") == "3939"

    client.query.return_value.result.return_value = []
    assert curation._current_sidra_tabela(client, "t.r.log", "3405", "ppm") is None

    boom = mock.Mock()
    boom.query.side_effect = NotFound("no table yet")
    assert curation._current_sidra_tabela(boom, "t.r.log", "3405", "ppm") is None

    boom2 = mock.Mock()
    boom2.query.side_effect = BadRequest("Unrecognized name: sidra_tabela")
    assert curation._current_sidra_tabela(boom2, "t.r.log", "3405", "ppm") is None


# ── the guards that were never exercised (coverage-gate re-arm, 2026-08-20) ────
#
# Every test below covers a REJECTION or a FALL-THROUGH: the paths that decide what
# the Curadoria writer refuses, and what it treats as "nothing stored yet". They are
# the cheapest place for a silent data defect to hide, which is why they are worth a
# test rather than a coverage waiver.


def test_ensure_log_table_warns_but_survives_a_failed_column_backfill(monkeypatch, caplog):
    """A late-added column that cannot be ALTERed in must not abort the write path.

    `create_table(exists_ok=True)` never adds columns to a table that predates one, so
    the writer ALTERs them in. If that ALTER fails (permissions, a concurrent DDL), the
    caller still needs the table reference back — raising here would take down every
    catalog edit over a column that may not even be needed by this write.
    """
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import curation

    monkeypatch.setattr(curation, "ensure_dataset", lambda *a, **k: None)
    bq = mock.Mock()
    bq.query.side_effect = RuntimeError("denied")

    with caplog.at_level("WARNING"):
        fqn = curation.ensure_produto_catalog_log_table(_settings(), bq)

    assert fqn.endswith("produto_catalog_log")
    assert any("Could not ensure" in r.message for r in caplog.records)


def test_add_catalog_editor_rejects_a_blank_email(monkeypatch):
    """An empty email would append an allowlist row matching nobody — or, worse, be
    read back as an entry that silently widens who can edit."""
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import curation

    monkeypatch.setattr(curation, "ensure_catalog_editors_table", lambda *a, **k: "t.editors")
    bq = mock.Mock()

    with pytest.raises(ValueError, match="email is required"):
        curation.add_catalog_editor("produto_catalog", "   ", settings=_settings(), client=bq)
    bq.query.assert_not_called()


@pytest.mark.parametrize(
    ("ingestao", "visibilidade", "trecho"),
    [
        ("pausadaa", None, "ingestao"),
        (None, "ocluto", "visibilidade"),  # the typo the docstring calls out by name
    ],
)
def test_validate_lifecycle_rejects_a_misspelled_axis(ingestao, visibilidade, trecho):
    """A typo must RAISE, never pass through. 'ocluto' silently stored would leave a
    produto the researcher meant to hide still on display for every reader."""
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import curation

    with pytest.raises(ValueError, match=trecho):
        curation._validate_lifecycle(ingestao, visibilidade)


@pytest.mark.parametrize("boom", [NotFound("no table"), BadRequest("no column")])
def test_current_descricao_reads_the_pre_migration_shapes_as_nothing_stored(boom):
    """Absent table / absent column = "no annotation yet", which is a legitimate state
    before the migration. Narrow on purpose: any OTHER fault propagates, so a transient
    BQ error can never be mistaken for "the researcher had no note" and erase one."""
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import curation

    bq = mock.Mock()
    bq.query.side_effect = boom
    assert curation._current_descricao(bq, "t.log", "3405", "ibge_pevs") is None


@pytest.mark.parametrize("boom", [NotFound("no table"), BadRequest("no column")])
def test_current_lifecycle_reads_the_pre_migration_shapes_as_nothing_stored(boom):
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import curation

    bq = mock.Mock()
    bq.query.side_effect = boom
    assert curation._current_lifecycle(bq, "t.log", "3405", "ibge_pevs") == (None, None)


def test_current_lifecycle_returns_none_pair_when_the_code_has_no_row():
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import curation

    bq = mock.Mock()
    bq.query.return_value.result.return_value = []
    assert curation._current_lifecycle(bq, "t.log", "3405", "ibge_pevs") == (None, None)


def test_check_code_status_hard_rejects_an_unknown_banco():
    """The ONLY layer that validates the banco. A junk token writes a row that never
    joins in gold_produto_agrupamento — orphaned data nobody would notice."""
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import curation

    with pytest.raises(ValueError, match="banco"):
        curation._check_code_status(mock.Mock(), "t.log", "3405", "ibge_pevsx", is_active=False)


def test_check_code_status_is_advisory_when_gold_is_not_built_yet(monkeypatch):
    """A code with no Gold table behind it is NOT an error: the catalog now drives
    ingestion, so a researcher registers a produto precisely so the next run fetches it."""
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import curation

    monkeypatch.setattr(
        curation.gateway,
        "fetch_source_code_stats",
        mock.Mock(side_effect=NotFound("gold not built")),
    )
    curation._check_code_status(mock.Mock(), "t.log", "3405", "pevs", is_active=False)


def test_check_code_status_is_advisory_when_gold_has_no_codes(monkeypatch):
    pytest.importorskip("flask_caching")
    import pandas as pd

    from embrapa_dashboard.serving import curation

    monkeypatch.setattr(
        curation.gateway, "fetch_source_code_stats", mock.Mock(return_value=pd.DataFrame())
    )
    curation._check_code_status(mock.Mock(), "t.log", "3405", "pevs", is_active=False)


# ── a guarda do agrupamento registrado ───────────────────────────────────────
def test_record_produto_catalog_rejects_an_unregistered_agrupamento(monkeypatch):
    """Um produto pode apontar para um agrupamento que nenhum grupo respalda — e nada
    quebra: o catálogo aceita, a Gold materializa o id, e o produto some numa seção "Sem
    agrupamento registrado" que só um humano olhando a tela nota.

    Aconteceu em 2026-08-29: uma reorganização escreveu 37 entradas apontando para grupos
    que nunca foram criados. A tela já sabia dizer "registrado"; faltava recusar antes.
    """
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import curation

    monkeypatch.setattr(curation, "ensure_dataset", lambda *a, **k: None)
    monkeypatch.setattr(curation, "_is_active_entry", lambda *a, **k: False)
    monkeypatch.setattr(curation, "_check_code_status", lambda *a, **k: None)
    monkeypatch.setattr(curation, "_registered_group_ids", lambda cfg, bq: {"madeira", "acai"})
    with pytest.raises(ValueError, match="não existe no registro"):
        curation.record_produto_catalog(
            "3455",
            "pevs",
            _HEADERS,
            agrupamento="Carvão vegetal",  # id `carvao_vegetal` — não registrado
            settings=_settings(),
            client=mock.Mock(),
            invalidate_cache=False,
        )


def test_record_produto_catalog_accepts_a_registered_agrupamento(monkeypatch):
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import curation

    monkeypatch.setattr(curation, "ensure_dataset", lambda *a, **k: None)
    monkeypatch.setattr(curation, "_is_active_entry", lambda *a, **k: False)
    monkeypatch.setattr(curation, "_check_code_status", lambda *a, **k: None)
    monkeypatch.setattr(curation, "_registered_group_ids", lambda cfg, bq: {"madeira"})
    client = mock.Mock()
    client.query.return_value.result.return_value = []
    curation.record_produto_catalog(
        "3457",
        "pevs",
        _HEADERS,
        agrupamento="Madeira",
        # Entrada NOVA em banco multi-tabela exige a tag desde v1.40.1 — sem ela a entrada
        # não pertence a metade nenhuma. Estes testes exercitam o registro de agrupamentos.
        sidra_tabela="291",
        settings=_settings(),
        client=client,
        invalidate_cache=False,
    )
    client.query.assert_called()


def test_an_absent_group_registry_does_not_block_the_first_product(monkeypatch):
    """Instalação fria: sem registro nenhum não há contra o que validar, e recusar tudo
    impediria cadastrar o primeiro produto. Vazio = nada a checar, não = tudo inválido."""
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import curation

    monkeypatch.setattr(curation, "ensure_dataset", lambda *a, **k: None)
    monkeypatch.setattr(curation, "_is_active_entry", lambda *a, **k: False)
    monkeypatch.setattr(curation, "_check_code_status", lambda *a, **k: None)
    monkeypatch.setattr(curation, "_registered_group_ids", lambda cfg, bq: set())
    client = mock.Mock()
    client.query.return_value.result.return_value = []
    curation.record_produto_catalog(
        "3457",
        "pevs",
        _HEADERS,
        sidra_tabela="291",  # entrada nova em banco multi-tabela exige a tag (v1.40.1)
        agrupamento="Qualquer",
        settings=_settings(),
        client=client,
        invalidate_cache=False,
    )
    client.query.assert_called()


# ── tabela_do_produto: o catálogo é a fonte de verdade da identidade ──────────
def test_tabela_do_produto_aceita_token_de_banco_e_de_fonte(monkeypatch):
    """Os registros por-código falam `ibge_pevs` (fonte); o catálogo fala `pevs` (banco).
    Sem a normalização a busca não acha nada, devolve None e a escrita cai na sentinela —
    silenciosamente, que é o modo de falha que este helper existe para evitar."""
    from embrapa_dashboard.serving import curation

    vistos = []

    def _fake(bq, table_fqn, codigo_produto, banco):
        vistos.append(banco)
        return "291"

    monkeypatch.setattr(curation, "_current_sidra_tabela", _fake)
    monkeypatch.setattr(curation, "_bq_client", lambda cfg: object())

    for token in ("pevs", "ibge_pevs"):
        assert curation.tabela_do_produto(token, "3457", settings=_settings()) == "291"
    assert vistos == ["pevs", "pevs"], f"token de fonte não normalizado: {vistos}"


def test_tabela_do_produto_devolve_none_sem_entrada(monkeypatch):
    """Banco de uma tabela só (ou código sem catálogo): None é o certo — o `ifnull` da
    chave colapsa na sentinela, e para esses bancos a coluna não carrega informação."""
    from embrapa_dashboard.serving import curation

    monkeypatch.setattr(curation, "_current_sidra_tabela", lambda *a, **k: None)
    monkeypatch.setattr(curation, "_bq_client", lambda cfg: object())

    assert curation.tabela_do_produto("comex", "44011000", settings=_settings()) is None


def test_tabela_do_produto_reusa_o_cliente_recebido(monkeypatch):
    """Os escritores já têm um cliente; abrir outro por escrita seria desperdício e,
    nos testes, exigiria dublar duas vezes o mesmo BigQuery."""
    from embrapa_dashboard.serving import curation

    sentinela = object()
    recebidos = []
    monkeypatch.setattr(
        curation, "_current_sidra_tabela", lambda bq, *a: recebidos.append(bq) or "289"
    )

    def _nao_chamar(cfg):
        raise AssertionError("abriu um cliente novo tendo recebido um")

    monkeypatch.setattr(curation, "_bq_client", _nao_chamar)

    curation.tabela_do_produto("pevs", "3405", settings=_settings(), client=sentinela)
    assert recebidos == [sentinela]
