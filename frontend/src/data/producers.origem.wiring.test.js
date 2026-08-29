/**
 * Every PEVS-capable producer must send `origem` AND key its cache by it.
 *
 * The axis shipped on 2026-08-29 wired into the snapshot only. The map, the município
 * cube and both product rankings kept answering with the two halves summed while the chip
 * announced one — and the halves differ ~6x in value, so the number was a different
 * dataset under the user's label.
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

// Producers that read a PEVS table. `flowData`/comex producers are deliberately absent:
// serving_comex_annual has no `origem` column.
const PEVS_PRODUCERS = ['geoYearly', 'municipioYearly', 'productsByUf', 'productsByMunicipio'];

/** The body of one `window.<name> = function ...` assignment, up to the next one. */
function bodyOf(name) {
  const i = SRC.indexOf(`window.${name} = function`);
  expect(i, `produtor ${name} não encontrado — o teste ficou obsoleto, não o código`).toBeGreaterThan(-1);
  const next = SRC.indexOf('\nwindow.', i + 1);
  return SRC.slice(i, next === -1 ? SRC.length : next);
}

describe('origem wiring — producers', () => {
  it.each(PEVS_PRODUCERS)('%s resolves the active origem', (name) => {
    expect(bodyOf(name)).toContain('activeOrigemParam()');
  });

  it.each(PEVS_PRODUCERS)('%s sends origem in the request', (name) => {
    // `origem,` inside the qs({...}) object literal (shorthand property).
    expect(bodyOf(name)).toMatch(/qs\(\{[^}]*\borigem\b/s);
  });

  it.each(PEVS_PRODUCERS)('%s includes origem in its cache key', (name) => {
    const chave = bodyOf(name).match(/const key = `[^`]+`/);
    expect(chave, `${name} não monta chave de cache literal`).toBeTruthy();
    expect(chave[0]).toContain('origem');
  });

  it('the scanner really reads the producers (guards the test, not the code)', () => {
    // A bodyOf() that silently returned '' would make every assertion above vacuous.
    for (const name of PEVS_PRODUCERS) {
      expect(bodyOf(name).length).toBeGreaterThan(200);
      expect(bodyOf(name)).toContain(`window.${name}`);
    }
  });
});
