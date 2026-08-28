import { describe, it, expect } from 'vitest';
import { colorbarAnchors, ptBrMagnitude } from './_base.jsx';

// The colorbar's three anchors (min / centro / max) exist so the reader can place any
// colour on the scale. Three IDENTICAL labels defeat that: they assert the scale is flat
// when it is not. A narrow value range — few regions, a short year window, a zoomed
// município — is exactly when it happens, and it is silent (no error, just a wrong-
// looking legend). So the rule is swept, not spot-checked.

describe('colorbarAnchors — rótulos', () => {
  it('nunca repete um rótulo, em qualquer magnitude ou largura de faixa', () => {
    const bases = [1, 7, 100, 1e3, 5e3, 1e6, 5e6, 1e9, 3.2e9, 1e12];
    const widths = [1e-6, 1e-5, 1e-4, 1e-3, 1e-2, 0.1, 0.5, 1, 10];
    const falhas = [];
    for (const base of bases) {
      for (const w of widths) {
        for (const sinal of [1, -1]) {
          const min = sinal * base;
          const max = min + base * w;
          const [lo, hi] = min < max ? [min, max] : [max, min];
          if (lo === hi) continue;
          const r = colorbarAnchors(lo, hi);
          if (r === null) continue;                       // devolveu o eixo ao Plotly — ok
          const n = new Set(r.ticktext).size;
          if (n !== r.ticktext.length) {
            falhas.push(`[${lo}, ${hi}] → ${r.ticktext.join(' | ')}`);
          }
        }
      }
    }
    expect(falhas).toEqual([]);
  });

  it('faixa que cruza o zero também separa', () => {
    const r = colorbarAnchors(-5e6, 3e6);
    expect(new Set(r.ticktext).size).toBe(3);
  });

  it('o caso medido que motivou a correção', () => {
    // Antes: ['5 mi', '5 mi', '5 mi'].
    const r = colorbarAnchors(5_000_000, 5_004_000);
    expect(r === null || new Set(r.ticktext).size === 3).toBe(true);
  });

  it('casos REAIS do acervo PEVS, não sintéticos', () => {
    // Medidos sobre /api/geo-yearly (ibge_pevs): 45 combinações de (região × janela de
    // anos) colapsavam os três rótulos. Duas delas, para não perder o alcance real:
    // Centro-Oeste 2018–2019 (t) exibia ['1 mil', '1 mil', '1 mil'], e 2004–2005
    // ['1,5 mil', '1,5 mil', '1,5 mil'] — seleções que qualquer pesquisador faz.
    for (const [lo, hi] of [[1029, 1033], [1473, 1481]]) {
      const r = colorbarAnchors(lo, hi);
      expect(r).not.toBeNull();
      expect(new Set(r.ticktext).size).toBe(3);
    }
  });

  it('faixa degenerada (min === max) continua devolvendo o eixo ao Plotly', () => {
    expect(colorbarAnchors(777, 777)).toBeNull();
    expect(colorbarAnchors(NaN, 10)).toBeNull();
  });

  it('a faixa larga comum não mudou de formato', () => {
    // O caminho quente não pode ganhar decimais: continua na escada bi/mi/mil.
    expect(colorbarAnchors(100, 9_000_000).ticktext).toEqual(['100', '4,5 mi', '9 mi']);
  });

  it('ptBrMagnitude sem `digits` é idêntico ao de antes (nenhum outro consumidor muda)', () => {
    expect(ptBrMagnitude(1_500_000)).toBe('1,5 mi');
    expect(ptBrMagnitude(15_000_000)).toBe('15 mi');
    expect(ptBrMagnitude(0)).toBe('0');
  });
});
