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
