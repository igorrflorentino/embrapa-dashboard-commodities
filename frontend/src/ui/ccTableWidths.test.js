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

const CSS = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), '../../public/assets/dashboard.css'),
  'utf8',
);

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
});
