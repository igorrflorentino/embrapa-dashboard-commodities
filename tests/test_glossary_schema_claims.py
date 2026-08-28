"""Every Gold name the glossary asserts must exist in the Gold schema.

The glossary is a reference surface: a researcher reads it to learn what to look for in
the exported CSV or in BigQuery. A name here that resolves to nothing sends them looking
for something that was renamed or never existed.

Not every `cat: 'Coluna'` entry is a physical identifier — most are the researcher's
vocabulary ("Área colhida", "Via", "Município"), and several bancos deliberately name the
SOURCE's variables rather than the Gold ones (`ncm`, `codigo_pevs`, `valor_producao`).
Guessing physical-ness from the shape of the string would flag all of those. The entry's
own `tag` is the explicit signal instead: `tag: 'gold'` claims a Gold column, and
`cat: 'Tabela'` + `tag: 'Base final'` claims a Gold table that exists today.

The schema side comes from `dbt/models/gold/_gold.yml`, which documents every column of
every Gold model as of v1.33.9 — that completeness is what makes this check possible
offline, with no BigQuery round-trip.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
GLOSSARY = REPO / "frontend" / "src" / "ui" / "glossary.js"
GOLD_YML = REPO / "dbt" / "models" / "gold" / "_gold.yml"

# term, cat, tag — the three fields always appear in this order on a tagged entry.
_ENTRY = re.compile(r"\{ term: '([^']+)',\s*cat: '([^']+)',\s*tag: '([^']+)'")


def _schema() -> tuple[set[str], set[str]]:
    doc = yaml.safe_load(GOLD_YML.read_text(encoding="utf-8"))
    models = {m["name"] for m in doc["models"]}
    columns = {c["name"] for m in doc["models"] for c in (m.get("columns") or [])}
    return models, columns


def _tagged_claims() -> list[tuple[str, str, str]]:
    return _ENTRY.findall(GLOSSARY.read_text(encoding="utf-8"))


def _resolves(name: str, columns: set[str]) -> bool:
    """A term may name one column, or a family via a trailing `*` (`val_real_*`)."""
    if name in columns:
        return True
    if name.endswith("*"):
        prefix = name.rstrip("*")
        return any(c.startswith(prefix) for c in columns)
    return False


def test_every_gold_tagged_term_names_a_real_column() -> None:
    _, columns = _schema()
    unresolved = []
    for term, _cat, tag in _tagged_claims():
        if tag != "gold":
            continue
        # A term may list a family pair, e.g. "val_yearfx_* · val_real_*".
        for part in (p.strip() for p in term.split("·")):
            if not _resolves(part, columns):
                unresolved.append(f"{term!r} → {part!r} matches no Gold column")
    assert unresolved == []


def test_every_table_tagged_base_final_exists() -> None:
    """`tag: 'Base final'` is the chip a reader scans to mean "this table is there now".
    A planned table carries `tag: 'Planejada'` instead — `gold_nfe_flows` wore the wrong
    one until v1.33.9, reading as existing while SEFAZ NFe has no pipeline at all."""
    models, _ = _schema()
    missing = [
        term
        for term, cat, tag in _tagged_claims()
        if cat == "Tabela" and tag == "Base final" and term not in models
    ]
    assert missing == []


def test_planned_tables_are_not_claimed_to_exist() -> None:
    """The other direction: a table tagged 'Planejada' must NOT already exist, or the
    glossary is telling the researcher to wait for something they could query today."""
    models, _ = _schema()
    wrong = [
        term
        for term, cat, tag in _tagged_claims()
        if cat == "Tabela" and tag == "Planejada" and term in models
    ]
    assert wrong == []


def test_gold_yml_declares_each_column_once() -> None:
    """A duplicated entry silently shadows the first — and it is how two descriptions of
    the same column start disagreeing."""
    doc = yaml.safe_load(GOLD_YML.read_text(encoding="utf-8"))
    dupes = []
    for model in doc["models"]:
        names = [c["name"] for c in (model.get("columns") or [])]
        for name in sorted({n for n in names if names.count(n) > 1}):
            dupes.append(f"{model['name']}.{name}")
    assert dupes == []
