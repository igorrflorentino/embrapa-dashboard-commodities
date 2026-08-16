"""Coverage for the first-class commodity-GROUPS registry (serving/agrupamentos.py):
create (new / duplicate), rename (re-tags the group's members), and delete (tombstone,
rejected while the group still has members). The BQ helpers are monkeypatched so the CRUD
logic is exercised without a live warehouse."""

from types import SimpleNamespace
from unittest import mock

import pytest
from google.api_core.exceptions import NotFound

from embrapa_dashboard.config import Settings
from embrapa_dashboard.serving import iap

pytest.importorskip("flask_caching")

_HEADERS = {iap.IAP_EMAIL_HEADER: "accounts.google.com:alice@embrapa.br"}


def _settings() -> Settings:
    return Settings(gcp_project_id="test-project")


def test_record_group_rejects_overlong_name():
    from embrapa_dashboard.serving import agrupamentos as cg

    with pytest.raises(ValueError, match="excede"):
        cg.record_group(
            "x" * (cg.MAX_NOTE_LEN + 1), _HEADERS, settings=_settings(), client=mock.MagicMock()
        )


def test_delete_group_requires_group_id():
    from embrapa_dashboard.serving import agrupamentos as cg

    with pytest.raises(ValueError, match="group_id"):
        cg.delete_group("  ", _HEADERS, settings=_settings(), client=mock.MagicMock())


def _patch_common(monkeypatch, cg, current):
    """Stub the table-ensure + current-groups read + insert; return the captured inserts."""
    monkeypatch.setattr(cg, "ensure_agrupamento_log_table", lambda *a, **k: "grp")
    monkeypatch.setattr(cg, "_current_groups", lambda bq, t: dict(current))
    # The dedup branch re-reads the stored row (read-after-write). Default it to None so the
    # retry-dedup tests exercise the fallback-echo path; conflict-specific tests override it.
    monkeypatch.setattr(cg, "_group_row_for_change_id", lambda *a, **k: None)
    inserted = []
    monkeypatch.setattr(
        cg,
        "_insert_group_row",
        lambda bq, t, gid, name, active, by, cid: inserted.append(
            {"gid": gid, "name": name, "active": active}
        ),
    )
    return inserted


def test_record_group_creates_new(monkeypatch):
    from embrapa_dashboard.serving import agrupamentos as cg

    inserted = _patch_common(monkeypatch, cg, {})
    out = cg.record_group(
        "Madeira", _HEADERS, settings=_settings(), client=mock.Mock(), invalidate_cache=False
    )
    assert out["group_id"] == "madeira" and out["group_name"] == "Madeira"
    assert out["active"] is True and out["edited_by"] == "alice@embrapa.br"
    assert inserted == [{"gid": "madeira", "name": "Madeira", "active": True}]


def test_record_group_rejects_duplicate(monkeypatch):
    from embrapa_dashboard.serving import agrupamentos as cg

    _patch_common(monkeypatch, cg, {"madeira": "Madeira"})
    with pytest.raises(ValueError):  # slug 'madeira' already active
        cg.record_group(
            "Madeira", _HEADERS, settings=_settings(), client=mock.Mock(), invalidate_cache=False
        )


def test_record_group_rejects_blank_name(monkeypatch):
    from embrapa_dashboard.serving import agrupamentos as cg

    with pytest.raises(ValueError):
        cg.record_group("   ", _HEADERS, settings=_settings(), client=mock.Mock())


def test_record_group_rename_retags_members(monkeypatch):
    from embrapa_dashboard.serving import agrupamentos as cg
    from embrapa_dashboard.serving import curation

    inserted = _patch_common(monkeypatch, cg, {"madeira": "Madeira"})
    member = SimpleNamespace(
        codigo_produto="4403",
        banco="comex",
        descricao_produto=None,
        ciclo_de_vida="Fazer Ingestão e deixar disponível",
    )
    monkeypatch.setattr(cg, "_active_member_rows", lambda bq, t, gid: [member])
    retagged = []

    def _capture(*a, **k):
        retagged.append((k.get("agrupamento_id"), k.get("agrupamento")))
        return {"ok": True}

    monkeypatch.setattr(curation, "record_produto_catalog", _capture)
    out = cg.record_group(
        "Madeira Nova",
        _HEADERS,
        group_id="madeira",
        settings=_settings(),
        client=mock.Mock(),
        invalidate_cache=False,
    )
    assert out["group_name"] == "Madeira Nova"
    assert inserted[0]["name"] == "Madeira Nova"
    # The member was re-tagged with the new name, keeping the same group_id.
    assert retagged == [("madeira", "Madeira Nova")]


def test_record_group_rename_forwards_the_lifecycle_axes(monkeypatch):
    """A rename must carry each member's stored ingestao/visibilidade through.

    The writer would PRESERVE an omitted axis anyway, but only by issuing an extra read
    per member — and _active_member_rows already fetched the row. Forwarding avoids one
    BigQuery round-trip per member on a bulk path (a large agrupamento has 150+)."""
    from embrapa_dashboard.serving import agrupamentos as cg
    from embrapa_dashboard.serving import curation

    _patch_common(monkeypatch, cg, {"madeira": "Madeira"})
    member = SimpleNamespace(
        codigo_produto="4403",
        banco="comex",
        descricao_produto=None,
        ciclo_de_vida=None,
        ingestao="pausada",
        visibilidade="oculto",
    )
    monkeypatch.setattr(cg, "_active_member_rows", lambda bq, t, gid: [member])
    seen = []
    monkeypatch.setattr(
        curation,
        "record_produto_catalog",
        lambda *a, **k: seen.append((k.get("ingestao"), k.get("visibilidade"))) or {"ok": True},
    )
    cg.record_group(
        "Madeira Nova",
        _HEADERS,
        group_id="madeira",
        settings=_settings(),
        client=mock.Mock(),
        invalidate_cache=False,
    )
    # A hidden + paused member stays hidden + paused after an unrelated rename.
    assert seen == [("pausada", "oculto")]


def test_record_group_rename_tolerates_a_pre_split_log_table(monkeypatch):
    """_active_member_rows selects the two axis columns; on a log table that predates
    them BigQuery raises BadRequest. Without a fallback the whole rename would 500."""
    from google.api_core.exceptions import BadRequest

    from embrapa_dashboard.serving import agrupamentos as cg

    legacy_row = SimpleNamespace(
        codigo_produto="4403", banco="comex", descricao_produto=None, ciclo_de_vida=None
    )

    class _BQ:
        def __init__(self):
            self.queries = []

        def query(self, sql, job_config=None):
            self.queries.append(sql)
            if "ingestao" in sql:
                raise BadRequest("Unrecognized name: ingestao")
            return mock.Mock(result=lambda: [legacy_row])

    bq = _BQ()
    rows = cg._active_member_rows(bq, "proj.ds.tbl", "madeira")
    assert rows == [legacy_row], "rename would have crashed on a pre-split table"
    assert len(bq.queries) == 2, "expected the failed attempt + the legacy retry"


def test_record_group_rename_missing_raises(monkeypatch):
    from embrapa_dashboard.serving import agrupamentos as cg

    _patch_common(monkeypatch, cg, {})
    with pytest.raises(ValueError):  # group_id doesn't exist → nothing to rename
        cg.record_group(
            "X",
            _HEADERS,
            group_id="nope",
            settings=_settings(),
            client=mock.Mock(),
            invalidate_cache=False,
        )


def test_delete_group_rejects_with_members(monkeypatch):
    from embrapa_dashboard.serving import agrupamentos as cg

    _patch_common(monkeypatch, cg, {"madeira": "Madeira"})
    monkeypatch.setattr(
        cg, "_active_member_rows", lambda bq, t, gid: [SimpleNamespace(codigo_produto="4403")]
    )
    with pytest.raises(ValueError):  # non-empty → must reassign/remove members first
        cg.delete_group(
            "madeira", _HEADERS, settings=_settings(), client=mock.Mock(), invalidate_cache=False
        )


def test_delete_group_tombstones_when_empty(monkeypatch):
    from embrapa_dashboard.serving import agrupamentos as cg

    inserted = _patch_common(monkeypatch, cg, {"madeira": "Madeira"})
    monkeypatch.setattr(cg, "_active_member_rows", lambda bq, t, gid: [])
    out = cg.delete_group(
        "madeira", _HEADERS, settings=_settings(), client=mock.Mock(), invalidate_cache=False
    )
    assert out["active"] is False and out["group_id"] == "madeira"
    assert inserted == [{"gid": "madeira", "name": "Madeira", "active": False}]


def test_delete_group_missing_raises(monkeypatch):
    from embrapa_dashboard.serving import agrupamentos as cg

    _patch_common(monkeypatch, cg, {})
    with pytest.raises(ValueError):
        cg.delete_group(
            "nope", _HEADERS, settings=_settings(), client=mock.Mock(), invalidate_cache=False
        )


# ── Full-path tests that exercise the REAL BQ-query helpers via a mock client ──────


def _q(rows):
    """A mock query job whose .result() yields ``rows``."""
    job = mock.Mock()
    job.result.return_value = rows
    return job


def test_ensure_group_log_table_creates_with_schema(monkeypatch):
    from embrapa_dashboard.serving import agrupamentos as cg

    monkeypatch.setattr(cg, "ensure_dataset", lambda *a, **k: None)
    client = mock.Mock()
    fqn = cg.ensure_agrupamento_log_table(settings=_settings(), client=client)
    assert fqn.endswith("agrupamento_log")
    tbl = client.create_table.call_args.args[0]
    assert [f.name for f in tbl.schema] == [
        "group_id",
        "group_name",
        "active",
        "edited_by",
        "edited_at",
        "change_id",
    ]
    assert tbl.clustering_fields == ["group_id"]


def test_record_group_create_runs_real_helpers(monkeypatch):
    from embrapa_dashboard.serving import agrupamentos as cg

    monkeypatch.setattr(cg, "ensure_dataset", lambda *a, **k: None)
    client = mock.Mock()
    client.query.return_value.result.return_value = []  # _current_groups empty, then INSERT
    # invalidate_cache=True also exercises invalidate_group_cache (cache unbound → caught).
    out = cg.record_group("Madeira", _HEADERS, settings=_settings(), client=client)
    assert out["group_id"] == "madeira" and out["active"] is True
    sql = client.query.call_args.args[0].lower()  # the LAST call = the INSERT
    assert "insert into" in sql and "current_timestamp()" in sql


def test_record_group_dedupes_supplied_change_id(monkeypatch):
    from embrapa_dashboard.serving import agrupamentos as cg

    monkeypatch.setattr(cg, "ensure_dataset", lambda *a, **k: None)
    monkeypatch.setattr(cg, "_change_id_seen", lambda *a, **k: True)
    client = mock.Mock()
    client.query.return_value.result.return_value = []  # _current_groups empty
    out = cg.record_group(
        "Madeira",
        _HEADERS,
        change_id="k1",
        settings=_settings(),
        client=client,
        invalidate_cache=False,
    )
    assert out["deduped"] is True


def test_record_group_rename_runs_real_member_read(monkeypatch):
    from embrapa_dashboard.serving import agrupamentos as cg
    from embrapa_dashboard.serving import curation

    monkeypatch.setattr(cg, "ensure_dataset", lambda *a, **k: None)
    grp = SimpleNamespace(group_id="madeira", group_name="Madeira")
    member = SimpleNamespace(
        codigo_produto="4403",
        banco="comex",
        descricao_produto=None,
        ciclo_de_vida="Fazer Ingestão e deixar disponível",
    )
    client = mock.Mock()
    # 1) _current_groups → the group; 2) INSERT rename row; 3) _active_member_rows → member.
    client.query.side_effect = [_q([grp]), _q([]), _q([member])]
    retagged = []
    monkeypatch.setattr(
        curation, "record_produto_catalog", lambda *a, **k: retagged.append(k.get("agrupamento"))
    )
    out = cg.record_group(
        "Madeira Nova",
        _HEADERS,
        group_id="madeira",
        settings=_settings(),
        client=client,
        invalidate_cache=False,
    )
    assert out["group_name"] == "Madeira Nova"
    assert retagged == ["Madeira Nova"]


def test_delete_group_empty_runs_real_helpers(monkeypatch):
    from embrapa_dashboard.serving import agrupamentos as cg

    monkeypatch.setattr(cg, "ensure_dataset", lambda *a, **k: None)
    grp = SimpleNamespace(group_id="madeira", group_name="Madeira")
    client = mock.Mock()
    # 1) _current_groups → group; 2) _active_member_rows → empty; 3) INSERT tombstone.
    client.query.side_effect = [_q([grp]), _q([]), _q([])]
    out = cg.delete_group("madeira", _HEADERS, settings=_settings(), client=client)
    assert out["active"] is False
    sql = client.query.call_args.args[0].lower()
    assert "insert into" in sql


def test_current_groups_and_members_empty_on_not_found():
    from embrapa_dashboard.serving import agrupamentos as cg

    client = mock.Mock()
    client.query.side_effect = NotFound("absent")
    assert cg._current_groups(client, "t") == {}
    assert cg._active_member_rows(client, "t", "madeira") == []


def test_record_group_rejects_unsluggable_name(monkeypatch):
    from embrapa_dashboard.serving import agrupamentos as cg

    _patch_common(monkeypatch, cg, {})
    with pytest.raises(ValueError):  # '###' slugs to '' → cannot mint a group_id
        cg.record_group(
            "###", _HEADERS, settings=_settings(), client=mock.Mock(), invalidate_cache=False
        )


def test_record_group_create_retry_dedupes_before_duplicate_check(monkeypatch):
    """A retried CREATE whose first attempt landed (group now in `current`) must return the
    deduped echo via the change_id, NOT fail the 'já existe' duplicate-name check."""
    from embrapa_dashboard.serving import agrupamentos as cg

    inserted = _patch_common(monkeypatch, cg, {"madeira": "Madeira"})
    monkeypatch.setattr(cg, "_change_id_seen", lambda *a, **k: True)
    out = cg.record_group(
        "Madeira",
        _HEADERS,
        change_id="k1",
        settings=_settings(),
        client=mock.Mock(),
        invalidate_cache=False,
    )
    assert out["deduped"] is True and out["group_id"] == "madeira"
    assert inserted == []  # dedup short-circuits BEFORE any insert


def test_delete_group_retry_dedupes_before_missing_check(monkeypatch):
    """A retried delete (tombstone already landed → group NOT in `current`) must return the
    deduped echo via the change_id, NOT fail the 'não existe (nada a excluir)' check."""
    from embrapa_dashboard.serving import agrupamentos as cg

    inserted = _patch_common(monkeypatch, cg, {})  # group already tombstoned → empty current
    monkeypatch.setattr(cg, "_change_id_seen", lambda *a, **k: True)
    out = cg.delete_group(
        "madeira",
        _HEADERS,
        change_id="k1",
        settings=_settings(),
        client=mock.Mock(),
        invalidate_cache=False,
    )
    assert out["deduped"] is True and out["active"] is False and out["group_id"] == "madeira"
    assert inserted == []  # dedup short-circuits BEFORE any insert


def test_record_group_rename_dedupe_reruns_restamp(monkeypatch):
    """A retried RENAME (same change_id, already seen) re-runs the idempotent member re-stamp
    to CONVERGE and echoes deduped — without a second registry insert."""
    from embrapa_dashboard.serving import agrupamentos as cg
    from embrapa_dashboard.serving import curation

    inserted = _patch_common(monkeypatch, cg, {"madeira": "Madeira"})
    monkeypatch.setattr(cg, "_change_id_seen", lambda *a, **k: True)
    member = SimpleNamespace(
        codigo_produto="4403",
        banco="comex",
        descricao_produto=None,
        ciclo_de_vida="Fazer Ingestão e deixar disponível",
    )
    monkeypatch.setattr(cg, "_active_member_rows", lambda bq, t, gid: [member])
    retagged = []
    monkeypatch.setattr(
        curation,
        "record_produto_catalog",
        lambda *a, **k: retagged.append(k.get("agrupamento")) or {"ok": True},
    )
    out = cg.record_group(
        "Madeira",
        _HEADERS,
        group_id="madeira",
        change_id="k1",
        settings=_settings(),
        client=mock.Mock(),
        invalidate_cache=False,
    )
    assert out["deduped"] is True
    assert inserted == []  # dedup short-circuits the registry insert
    assert retagged == ["Madeira"]  # but the re-stamp re-ran (convergence)


def test_record_group_rename_rejects_duplicate_name(monkeypatch):
    """Renaming a group to a name ANOTHER active group already uses is rejected (it would
    silently MERGE the two in the name-keyed UI/aggregation)."""
    from embrapa_dashboard.serving import agrupamentos as cg

    _patch_common(monkeypatch, cg, {"madeira": "Madeira", "castanha": "Castanha"})
    with pytest.raises(ValueError, match="Já existe"):
        cg.record_group(
            "Castanha",
            _HEADERS,
            group_id="madeira",
            settings=_settings(),
            client=mock.Mock(),
            invalidate_cache=False,
        )


def test_record_group_rejects_unsluggable_name_message(monkeypatch):
    """A non-empty name that slugs to empty ('###') reports the real cause (not the internal
    'group_id' term) — the reworded pt-BR message names the fix for the researcher."""
    from embrapa_dashboard.serving import agrupamentos as cg

    _patch_common(monkeypatch, cg, {})
    with pytest.raises(ValueError, match="identificador válido"):
        cg.record_group(
            "###", _HEADERS, settings=_settings(), client=mock.Mock(), invalidate_cache=False
        )


def test_record_group_retry_returns_stored_row(monkeypatch):
    """A retried CREATE (same change_id) returns the STORED row — not the retry's request body
    or author — even if the retry arrives under a different IAP header."""
    from embrapa_dashboard.serving import agrupamentos as cg

    _patch_common(monkeypatch, cg, {"madeira": "Madeira"})
    monkeypatch.setattr(cg, "_change_id_seen", lambda *a, **k: True)
    stored = {
        "group_id": "madeira",
        "group_name": "Madeira Original",
        "active": True,
        "edited_by": "orig@x",
        "change_id": "k1",
        "deduped": True,
    }
    monkeypatch.setattr(cg, "_group_row_for_change_id", lambda *a, **k: stored)
    out = cg.record_group(
        "Madeira",  # same slug, but the STORED name wins
        {iap.IAP_EMAIL_HEADER: "accounts.google.com:someone-else@embrapa.br"},
        change_id="k1",
        settings=_settings(),
        client=mock.Mock(),
        invalidate_cache=False,
    )
    assert out["group_name"] == "Madeira Original"
    assert out["edited_by"] == "orig@x"
    assert out["deduped"] is True


def test_delete_group_retry_returns_stored_name(monkeypatch):
    """A retried delete returns the stored row's REAL name, not the group_id placeholder."""
    from embrapa_dashboard.serving import agrupamentos as cg

    _patch_common(monkeypatch, cg, {})
    monkeypatch.setattr(cg, "_change_id_seen", lambda *a, **k: True)
    stored = {
        "group_id": "madeira",
        "group_name": "Madeira",
        "active": False,
        "edited_by": "orig@x",
        "change_id": "k1",
        "deduped": True,
    }
    monkeypatch.setattr(cg, "_group_row_for_change_id", lambda *a, **k: stored)
    out = cg.delete_group(
        "madeira",
        _HEADERS,
        change_id="k1",
        settings=_settings(),
        client=mock.Mock(),
        invalidate_cache=False,
    )
    assert out["group_name"] == "Madeira"  # NOT the 'madeira' id placeholder
    assert out["active"] is False


def test_record_group_change_id_conflict_raises(monkeypatch):
    """Reusing a change_id whose stored row is a DIFFERENT group → ChangeIdConflictError (409)."""
    from embrapa_dashboard.serving import agrupamentos as cg
    from embrapa_dashboard.serving.research_inputs import ChangeIdConflictError

    _patch_common(monkeypatch, cg, {"madeira": "Madeira"})
    monkeypatch.setattr(cg, "_change_id_seen", lambda *a, **k: True)
    stored = {
        "group_id": "castanha",
        "group_name": "Castanha",
        "active": True,
        "edited_by": "orig@x",
        "change_id": "k1",
        "deduped": True,
    }
    monkeypatch.setattr(cg, "_group_row_for_change_id", lambda *a, **k: stored)
    with pytest.raises(ChangeIdConflictError):
        cg.record_group(
            "Madeira",
            _HEADERS,
            change_id="k1",
            settings=_settings(),
            client=mock.Mock(),
            invalidate_cache=False,
        )


def test_delete_group_change_id_conflict_on_active_flip(monkeypatch):
    """A record's change_id (stored active=True) reused for a delete → ChangeIdConflictError."""
    from embrapa_dashboard.serving import agrupamentos as cg
    from embrapa_dashboard.serving.research_inputs import ChangeIdConflictError

    _patch_common(monkeypatch, cg, {"madeira": "Madeira"})
    monkeypatch.setattr(cg, "_change_id_seen", lambda *a, **k: True)
    stored = {
        "group_id": "madeira",
        "group_name": "Madeira",
        "active": True,
        "edited_by": "orig@x",
        "change_id": "k1",
        "deduped": True,
    }
    monkeypatch.setattr(cg, "_group_row_for_change_id", lambda *a, **k: stored)
    with pytest.raises(ChangeIdConflictError):
        cg.delete_group(
            "madeira",
            _HEADERS,
            change_id="k1",
            settings=_settings(),
            client=mock.Mock(),
            invalidate_cache=False,
        )
