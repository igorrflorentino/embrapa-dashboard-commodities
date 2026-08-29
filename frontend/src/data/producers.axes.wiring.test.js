/**
 * Every basket-honouring producer must forward EVERY filter axis and key its cache by it.
 *
 * Two axes shipped on 2026-08-29, a day apart, both wired into the snapshot only:
 * `origem` (which half of PEVS) and `niveis` (nível de industrialização). The map, the
 * município cube and both product rankings answered over a dataset the user had not
 * selected — the halves differ ~6x in value, and the snapshot showed 1,3 bi for
 * commodity_pura beside a map showing the whole 1.063,5 bi.
 *
 * Two failure modes, one test each, because either alone is enough to break it:
 *  - not sending the param → the BFF sums both halves;
 *  - sending it but not keying by it → the previous half's answer is served from memory,
 *    which looks exactly like not sending it.
 *
 * Scans the SOURCE rather than the behaviour: each producer had a passing test, and what
 * nobody checked was whether the parameter reached the call.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const SRC = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'producers.js'), 'utf8');

// The producers that fetch filtered data. Both axes ride together through one helper —
// which is the point: the next axis is added there, not remembered at four call sites.
const PRODUCERS = ['geoYearly', 'municipioYearly', 'productsByUf', 'productsByMunicipio'];

/** The body of one `window.<name> = function ...` assignment, up to the next one. */
function bodyOf(name) {
  const i = SRC.indexOf(`window.${name} = function`);
  expect(i, `produtor ${name} não encontrado — o teste ficou obsoleto, não o código`).toBeGreaterThan(-1);
  const next = SRC.indexOf('\nwindow.', i + 1);
  return SRC.slice(i, next === -1 ? SRC.length : next);
}

describe('filter-axis wiring — producers', () => {
  it.each(PRODUCERS)('%s resolves the active axes', (name) => {
    expect(bodyOf(name)).toContain('activeAxisParams()');
  });

  it.each(PRODUCERS)('%s spreads every axis into the request', (name) => {
    // `...ax` inside the qs({...}) literal — spreading is what makes a NEW axis arrive
    // without touching this producer; naming one axis explicitly would not.
    expect(bodyOf(name)).toMatch(/qs\(\{[^}]*\.\.\.ax\b/s);
  });

  it.each(PRODUCERS)('%s includes every axis in its cache key', (name) => {
    const chave = bodyOf(name).match(/const key = `[^`]+`/);
    expect(chave, `${name} não monta chave de cache literal`).toBeTruthy();
    expect(chave[0]).toContain('axisKey(ax)');
  });

  it('the axis helper RETURNS both axes — a missing one is silent, not an error', () => {
    // Asserts on the returned object, not on the function text: an axis that is still
    // read from the store but dropped from the return leaves its name in the body, so a
    // substring check over the whole helper passes while the axis never ships. (That is
    // exactly what this test did until an injection exposed it.)
    const helper = SRC.slice(SRC.indexOf('function activeAxisParams'), SRC.indexOf('function axisKey'));
    const retorno = helper.slice(helper.indexOf('return {'), helper.lastIndexOf('};'));
    for (const eixo of ['origem', 'niveis']) {
      expect(retorno, `o helper nao devolve ${eixo}`).toMatch(new RegExp(`\\b${eixo}\\s*:`));
    }
  });

  it('the scanner really reads the producers (guards the test, not the code)', () => {
    // A bodyOf() that silently returned '' would make every assertion above vacuous.
    for (const name of PRODUCERS) {
      expect(bodyOf(name).length).toBeGreaterThan(200);
      expect(bodyOf(name)).toContain(`window.${name}`);
    }
  });
});
