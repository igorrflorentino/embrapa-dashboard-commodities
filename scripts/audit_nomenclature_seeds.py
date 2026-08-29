"""Compara as descrições dos seeds de comércio com a nomenclatura oficial do MDIC.

Por que existe: COMEX e COMTRADE **não trazem descrição nos dados**. O arquivo do MDIC tem
`CO_NCM` e números, mais nada; o Bronze do COMTRADE idem. O nome que o pesquisador lê vem
de um seed que este repositório mantém — ou seja, é um artefato editorial nosso, e a
pergunta "de onde veio esse texto?" precisa ter resposta.

A política (decidida em 2026-08-29): usar o **texto pleno da nomenclatura** e **registrar a
divergência**. Isso porque o campo mais óbvio do MDIC, `NO_NCM_POR` / `NO_SH6_POR`, é um
campo de EXIBIÇÃO com limite de tamanho — ele produz `Outs.painéis`,
`n/trab.mecan.d>0.8g/cm3` — e às vezes está factualmente errado (`15079019`, o código
"outros", recebe lá a descrição do irmão "até 5 litros"). Copiá-lo cegamente degradaria
rótulos hoje corretos.

Uso:
    uv run python scripts/audit_nomenclature_seeds.py            # regrava o registro
    uv run python scripts/audit_nomenclature_seeds.py --check    # falha se estiver defasado

Precisa de rede (baixa as tabelas do MDIC), por isso é operado à mão e não roda no CI.
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
from pathlib import Path

import requests

from embrapa_dashboard.comex.client import _ca_bundle

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "docs/nomenclatura_divergencias.md"
BASE_MDIC = "https://balanca.economia.gov.br/balanca/bd/tabelas"


def _baixar(nome: str) -> list[dict]:
    """Reusa o bundle de CAs do cliente COMEX: o servidor do MDIC serve uma cadeia
    incompleta, e `comex.client._ca_bundle()` já é certifi + o intermediário Sectigo
    vendorizado justamente por isso. Refazer a verificação aqui seria uma segunda cópia
    da mesma decisão."""
    r = requests.get(f"{BASE_MDIC}/{nome}", timeout=180, verify=_ca_bundle())
    r.raise_for_status()
    return list(csv.DictReader(io.StringIO(r.content.decode("latin-1")), delimiter=";"))


def _degradado(t: str) -> bool:
    """A marca de um texto encurtado à força pelo MDIC: aspas internas, ponto colado numa
    minúscula (`Outs.painéis`, `n/trab.mecan.`) ou brevidade implausível."""
    return ('"' in t) or bool(re.search(r"\.[a-zà-ú]", t)) or len(t) < 12


def _classe(nosso: str, oficial: str) -> str:
    if not oficial:
        return "ausente no MDIC"
    if _degradado(oficial):
        return "oficial abreviado"
    if len(nosso) > len(oficial):
        return "nosso mais pleno"
    return "procedência distinta"


def coletar() -> dict[str, list[tuple[str, str, str, str]]]:
    ncm = {r["CO_NCM"].strip('"'): r["NO_NCM_POR"].strip() for r in _baixar("NCM.csv")}
    sh: dict[tuple[int, str], str] = {}
    for r in _baixar("NCM_SH.csv"):
        for nivel, cc, nn in (
            (6, "CO_SH6", "NO_SH6_POR"),
            (4, "CO_SH4", "NO_SH4_POR"),
            (2, "CO_SH2", "NO_SH2_POR"),
        ):
            c = r[cc].strip('"')
            if c and (nivel, c) not in sh:
                sh[(nivel, c)] = r[nn].strip()

    out: dict[str, list[tuple[str, str, str, str]]] = {}
    with (RAIZ / "dbt/seeds/comex_ncm.csv").open(encoding="utf-8") as f:
        out["comex_ncm (NCM-8 · NO_NCM_POR)"] = [
            (
                r["co_ncm"],
                r["ncm_description"],
                ncm.get(r["co_ncm"], ""),
                _classe(r["ncm_description"], ncm.get(r["co_ncm"], "")),
            )
            for r in csv.DictReader(f)
            if ncm.get(r["co_ncm"]) != r["ncm_description"]
        ]
    with (RAIZ / "dbt/seeds/comtrade_hs.csv").open(encoding="utf-8") as f:
        out["comtrade_hs (SH · NO_SH*_POR)"] = [
            (
                r["cmd_code"],
                r["description"],
                sh.get((int(r["hs_level"]), r["cmd_code"]), ""),
                _classe(r["description"], sh.get((int(r["hs_level"]), r["cmd_code"]), "")),
            )
            for r in csv.DictReader(f)
            if sh.get((int(r["hs_level"]), r["cmd_code"])) != r["description"]
        ]
    return out


def renderizar(dados: dict[str, list[tuple[str, str, str, str]]]) -> str:
    def esc(t: str) -> str:
        return t.replace("|", "\\|")

    linhas = [
        "# Divergências entre os seeds de comércio e a nomenclatura do MDIC",
        "",
        "**Gerado por `scripts/audit_nomenclature_seeds.py` — não editar à mão.**",
        "",
        "COMEX e COMTRADE não trazem descrição nos dados: o arquivo do MDIC tem código e",
        "números, e o Bronze do COMTRADE também. O nome que aparece na tela vem de um seed",
        "deste repositório. A política é usar o **texto pleno da nomenclatura** e registrar",
        "aqui toda divergência contra o campo de exibição do MDIC.",
        "",
        "As quatro classes:",
        "",
        "| classe | o que significa |",
        "|---|---|",
        "| `oficial abreviado` | o MDIC encurtou para caber no campo (`Outs.painéis`) |",
        "| `nosso mais pleno` | mesmo sentido, nosso texto carrega mais qualificadores |",
        "| `procedência distinta` | veio de outra fonte (tradução WCO/Comtrade) |",
        "| `ausente no MDIC` | o código não existe na tabela auxiliar |",
        "",
    ]
    for nome, itens in dados.items():
        linhas += [f"## {nome}", "", f"{len(itens)} divergência(s).", ""]
        for classe in (
            "oficial abreviado",
            "nosso mais pleno",
            "procedência distinta",
            "ausente no MDIC",
        ):
            do_grupo = [x for x in itens if x[3] == classe]
            if not do_grupo:
                continue
            linhas += [
                f"### {classe} ({len(do_grupo)})",
                "",
                "| código | texto usado | texto do MDIC |",
                "|---|---|---|",
            ]
            linhas += [f"| `{c}` | {esc(n)} | {esc(o) or '—'} |" for c, n, o, _ in do_grupo]
            linhas.append("")
    return "\n".join(linhas) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="falha se o registro estiver defasado")
    args = ap.parse_args()
    novo = renderizar(coletar())
    if args.check:
        atual = DESTINO.read_text(encoding="utf-8") if DESTINO.exists() else ""
        if atual != novo:
            print(f"{DESTINO.relative_to(RAIZ)} está defasado — rode o script sem --check.")
            return 1
        print(f"{DESTINO.relative_to(RAIZ)} está em dia.")
        return 0
    DESTINO.write_text(novo, encoding="utf-8")
    print(f"escrito: {DESTINO.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
