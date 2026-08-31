/**
 * Os controles de "Território em análise" formam UMA barra, não texto com uma caixa no meio.
 *
 * O defeito que isto guarda: o `<select>` de UF usava `.seg-opt`, uma classe que é
 * `border: none; background: transparent` porque foi feita para viver DENTRO da caixa do
 * `.seg` — que é quem fornece a borda. Solto ao lado dela, o controle virava texto com uma
 * setinha: não parecia clicável e não se distinguia do rótulo. E `.uf-scope`, a classe do
 * rótulo+campo, não tinha regra NENHUMA no CSS.
 *
 * A âncora da altura é o próprio `.seg`, mantido para o segmentado: se alguém mudar a
 * altura de um sem o outro, a linha desalinha e este teste acusa.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const AQUI = dirname(fileURLToPath(import.meta.url));
const CSS = readFileSync(join(AQUI, '../../public/assets/dashboard.css'), 'utf8');
const JSX = readFileSync(join(AQUI, 'ViewTerritoryProfile.jsx'), 'utf8');

/** O corpo de uma regra CSS pelo seletor exato (primeira ocorrência). */
function regra(seletor) {
  const re = new RegExp(`(^|\\n)\\s*${seletor.replace('.', '\\.')}\\s*\\{([^}]*)\\}`);
  const m = CSS.match(re);
  return m ? m[2] : null;
}

const alturaDe = (seletor) => {
  const corpo = regra(seletor);
  const m = corpo && corpo.match(/height:\s*(\d+)px/);
  return m ? Number(m[1]) : null;
};

describe('controles do "Território em análise"', () => {
  it('o extrator acha as duas regras (guarda os testes abaixo)', () => {
    expect(regra('.scope-select')).toBeTruthy();
    expect(regra('.seg')).toBeTruthy();
    expect(regra('.uf-scope')).toBeTruthy(); // era uma classe fantasma, sem regra nenhuma
  });

  it('o select é DELIMITADO — borda e fundo próprios', () => {
    const corpo = regra('.scope-select');
    expect(corpo).toMatch(/border:\s*1px solid/);
    expect(corpo).toMatch(/background:\s*#fff/);
    expect(corpo).not.toMatch(/background:\s*transparent/);
  });

  it('tem a mesma altura do segmentado ao lado — é o que alinha a linha', () => {
    expect(alturaDe('.scope-select')).toBe(alturaDe('.seg'));
  });

  it('tem afordância: hover, foco visível e estado desabilitado', () => {
    // O select de município nasce desabilitado ("carregando municípios…") e sem estado
    // próprio convidava um clique que não faz nada.
    expect(CSS).toMatch(/\.scope-select:hover:not\(:disabled\)/);
    expect(CSS).toMatch(/\.scope-select:focus-visible/);
    expect(CSS).toMatch(/\.scope-select:disabled/);
  });

  it('NENHUM select do projeto usa `.seg-opt` — a regra, não a tela', () => {
    // Varredura de domínio. A versão anterior olhava só ViewTerritoryProfile, e o MESMO
    // defeito estava no átomo compartilhado `UfScopePicker` (Atoms.jsx), renderizado em
    // CINCO pontos: ViewCrossSource, ViewsMultiSource ×3 e ViewCuratedAnalyses. Consertar
    // a tela onde o defeito foi APONTADO e não varrer o resto é o padrão que este
    // repositório repete; o teste agora é sobre a classe, não sobre um arquivo.
    const arquivos = readdirSync(AQUI).filter(
      (f) => f.endsWith('.jsx') && !f.includes('.test.'),
    );
    const infratores = [];
    let vistos = 0;
    for (const f of arquivos) {
      const src = readFileSync(join(AQUI, f), 'utf8');
      // `<select …>` até o `>` que o fecha, com className em qualquer posição.
      for (const m of src.match(/<select\b[^>]*>/g) || []) {
        vistos += 1;
        if (/\bseg-opt\b/.test(m)) infratores.push(`${f}: ${m.slice(0, 70)}`);
      }
    }
    // Guarda o varredor: um regex quebrado veria zero selects e passaria para sempre.
    expect(vistos).toBeGreaterThan(5);
    expect(infratores).toEqual([]);
  });

  it('nenhum BOTÃO usa `.seg-opt` nu — a classe só vale dentro de um segmentado', () => {
    // `.seg-opt` é `border: none; background: transparent` porque a caixa vem do `.seg`.
    // Um botão que a usa SOLTO vira texto: medido em "Estrutura de dados", os quatro
    // (Exportar CSV, Filtrar, ‹ Anterior, Próxima ›) tinham 14px de altura, sem borda nem
    // fundo. O diagnóstico e o conserto (`btn-secondary`) já estavam escritos em
    // ViewGeography.jsx desde antes — para UMA ocorrência, sem varredura.
    //
    // O que distingue uso legítimo de defeito: dentro de um `.seg` a classe SEMPRE alterna
    // `on`, porque é o estado do segmentado. `className="seg-opt"` literal, sem
    // concatenação, é botão solto.
    const arquivos = readdirSync(AQUI).filter(
      (f) => f.endsWith('.jsx') && !f.includes('.test.'),
    );
    const infratores = [];
    let vistos = 0;
    for (const f of arquivos) {
      const src = readFileSync(join(AQUI, f), 'utf8');
      for (const m of src.match(/className=\{?'?"?[^"'}]*seg-opt[^"'}]*"?'?\}?/g) || []) {
        vistos += 1;
        if (/className="seg-opt"/.test(m)) infratores.push(`${f}: ${m}`);
      }
    }
    expect(vistos).toBeGreaterThan(10); // guarda o varredor
    expect(infratores).toEqual([]);
  });

  it('`.btn-secondary` tem estado desabilitado', () => {
    // Os 13 botões migrados têm TODOS uma condição `disabled`; sem este estado a migração
    // teria trocado um defeito de afordância por outro.
    expect(CSS).toMatch(/\.btn-secondary:disabled/);
    expect(CSS).toMatch(/\.btn-secondary:hover:not\(:disabled\)/);
  });

  it('o átomo compartilhado usa a classe delimitada', () => {
    // `UfScopePicker` é o único select fora das views — um átomo, logo o defeito nele
    // aparecia em cinco telas de uma vez.
    const atoms = readFileSync(join(AQUI, 'Atoms.jsx'), 'utf8');
    expect(atoms).toMatch(/className="scope-select"/);
    expect(atoms).not.toMatch(/className="caption" style=\{\{ marginRight: 6 \}\}/);
  });

  it('o rótulo e o campo são um par, sem margem inline', () => {
    expect(regra('.uf-scope')).toMatch(/display:\s*inline-flex/);
    expect(regra('.uf-scope')).toMatch(/gap:/);
    expect(JSX).not.toMatch(/className="caption" style=\{\{ marginRight: 6 \}\}/);
  });
});
