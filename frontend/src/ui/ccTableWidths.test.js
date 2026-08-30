/**
 * As larguras da tabela do Cadastro são POSICIONAIS (`nth-child`) e somam 100%.
 *
 * Inserir uma coluna desloca todas as seguintes, e a largura de cada uma passa a valer para
 * a vizinha. Foi exatamente o que aconteceu ao acrescentar "Tabela": "Código" herdou os 16%
 * de "Descrição", "Exibição" caiu para 42px e o cabeçalho quebrou em "Ex/ib/iç/ão" — visível
 * só a olho, porque o jsdom não aplica CSS.
 *
 * O que dá para prender é o arquivo: os índices têm de ser contíguos de 1 a N, sem repetir e
 * sem furo, e a soma tem de fechar 100%. Um deslocamento quebra pelo menos uma dessas três.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const AQUI = dirname(fileURLToPath(import.meta.url));
const CSS = readFileSync(join(AQUI, '../../public/assets/dashboard.css'), 'utf8');
const JSX = readFileSync(join(AQUI, 'ViewCadastroProdutos.jsx'), 'utf8');

/** Os <th> do cabeçalho da tabela do Cadastro — a âncora vem do JSX, não do CSS. */
function colunasNoJsx() {
  const thead = JSX.match(/<thead>\s*<tr[^>]*>([\s\S]*?)<\/tr>/);
  if (!thead) return [];
  return [...thead[1].matchAll(/<th\b/g)].map((_, k) => k + 1);
}

/** [{i, w}] das regras `.cc-table thead th:nth-child(i) { width: w% }`. */
function larguras() {
  const re = /\.cc-table thead th:nth-child\((\d+)\)[^{]*\{\s*width:\s*([\d.]+)%/g;
  return [...CSS.matchAll(re)].map((m) => ({ i: Number(m[1]), w: Number(m[2]) }));
}

describe('larguras da tabela do Cadastro', () => {
  it('o varredor acha as regras (guarda o teste, não o código)', () => {
    expect(larguras().length).toBeGreaterThanOrEqual(10);
  });

  it('os índices são contíguos, sem repetição nem furo', () => {
    const is = larguras().map((x) => x.i).sort((a, b) => a - b);
    expect(is).toEqual(Array.from({ length: is.length }, (_, k) => k + 1));
  });

  it('somam exatamente 100%', () => {
    const total = larguras().reduce((s, x) => s + x.w, 0);
    expect(Math.round(total * 10) / 10).toBe(100);
  });

  /* O modo de falha real não é o CSS ficar inconsistente consigo mesmo — é ele descrever uma
     tabela que o JSX não tem mais. Por isso a âncora vem do OUTRO arquivo: o cabeçalho é
     mantido por quem edita a tela, não por quem edita as larguras, e some do CSS sem avisar.
     Acrescentar um <th> sem acrescentar uma regra desloca todas as colunas seguintes. */
  it('há exatamente uma largura por <th> do cabeçalho no JSX', () => {
    const noJsx = colunasNoJsx();
    expect(noJsx.length).toBeGreaterThan(1);            // guarda o varredor, não o código
    expect(larguras().length).toBe(noJsx.length);
  });
});

/**
 * A rolagem horizontal (v1.46.9): a tabela para de apertar num piso MEDIDO e o cartão rola.
 *
 * O piso não pode ser um número solto — ele é a soma das necessidades das 11 colunas. Se
 * alguém reequilibrar as porcentagens sem mexer no `min-width`, a tabela volta a apertar
 * (piso baixo demais) ou passa a rolar numa tela em que cabia (piso alto demais). A âncora
 * aqui é a largura disponível declarada no próprio comentário do CSS — medida na tela real,
 * mantida por outro motivo.
 */
describe('rolagem horizontal da tabela do Cadastro', () => {
  const pisoDeclarado = () => {
    const m = CSS.match(/\.cc-table\s*\{[^}]*min-width:\s*(\d+)px/);
    return m ? Number(m[1]) : null;
  };

  it('o varredor acha as regras (guarda os testes abaixo)', () => {
    expect(pisoDeclarado()).not.toBeNull();
    expect(CSS).toMatch(/\.cc-dt-wrap\s*\{[^}]*overflow-x:\s*auto/);
  });

  it('o cartão rola em vez de esconder o transbordo', () => {
    // `overflow: hidden` era o valor anterior: a tabela apertava e nada rolava.
    const regra = CSS.match(/\.cc-dt-wrap\s*\{([^}]*)\}/)[1];
    expect(regra).toMatch(/overflow-x:\s*auto/);
    expect(regra).not.toMatch(/overflow:\s*hidden/);
  });

  it('sem `max-height`, para nenhuma barra VERTICAL nascer e roubar largura', () => {
    // O defeito que isto evita já aconteceu: uma barra vertical de 15px em 7 dos 31
    // cartões os media 1074px contra 1089px, desalinhando a grade que as larguras criam.
    expect(CSS.match(/\.cc-dt-wrap\s*\{([^}]*)\}/)[1]).toMatch(/max-height:\s*none/);
  });

  it('o piso cabe na largura disponível — senão rolaria numa tela onde cabia', () => {
    const disponivel = Number(CSS.match(/come to \d+px against (\d+)px available/)[1]);
    expect(pisoDeclarado()).toBeLessThanOrEqual(disponivel);
  });

  it('o piso é a soma medida das colunas, não um número redondo', () => {
    const somaMedida = Number(CSS.match(/they come to (\d+)px against/)[1]);
    expect(pisoDeclarado()).toBe(somaMedida);
  });

  // A sincronização entre cartões é COMPORTAMENTO, e está em ViewCadastroProdutos.test.jsx
  // ('rolar um cartão move os outros'). Afirmá-la aqui só daria para procurar o texto-fonte
  // do handler — que passa verde com o corpo da função esvaziado.
});
