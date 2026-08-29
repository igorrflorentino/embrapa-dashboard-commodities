// filterSummary.wiring.test.js — every CALL SITE must pass the sub-UF recorte.
//
// The unit tests next door lock what geoChipText/geoHeaderText DO with `subUf`. They
// cannot see whether anyone actually hands it over — and that gap is precisely where
// the bug lived: the two functions were correct for the inputs they got, and three
// call sites never mentioned the four sub-UF facets, so the chip announced
// "Brasil · 27 UFs" over a 16-município slice of the Pará and the ABNT citation
// repeated it beside a permalink that carried the recorte.
//
// Deleting the wiring left all 1012 other tests green. This one is the only thing that
// notices, so it scans the sources rather than the behaviour: for a summary whose whole
// job is to not over-claim, a forgotten argument IS the defect.

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const SRC = join(dirname(fileURLToPath(import.meta.url)), '..');

function sourceFiles(dir) {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) return sourceFiles(full);
    if (!/\.jsx?$/.test(name) || /\.test\.jsx?$/.test(name)) return [];
    return [full];
  });
}

/** The argument object of `fn({ … })`, matched by balancing braces — a regex would
 *  stop at the first nested `}` and read half the call. */
function callArgs(source, fn) {
  const out = [];
  let from = 0;
  for (;;) {
    const at = source.indexOf(`${fn}({`, from);
    if (at === -1) return out;
    let depth = 0;
    let i = source.indexOf('{', at);
    const start = i;
    for (; i < source.length; i += 1) {
      if (source[i] === '{') depth += 1;
      else if (source[i] === '}') {
        depth -= 1;
        if (depth === 0) break;
      }
    }
    out.push(source.slice(start, i + 1));
    from = i;
  }
}

describe('geoChipText / geoHeaderText — nenhuma chamada pode esquecer o recorte', () => {
  const files = sourceFiles(SRC).filter((f) => !f.endsWith('filterSummary.js'));

  for (const fn of ['geoChipText', 'geoHeaderText']) {
    it(`toda chamada de ${fn} passa subUf`, () => {
      const found = [];
      for (const file of files) {
        for (const args of callArgs(readFileSync(file, 'utf-8'), fn)) {
          found.push({ file, hasSubUf: /\bsubUf\s*:/.test(args) });
        }
      }
      // Guard the guard: if the call sites move or get renamed, this test must fail
      // loudly rather than pass over an empty list.
      expect(found.length).toBeGreaterThan(0);
      expect(found.filter((c) => !c.hasSubUf).map((c) => c.file)).toEqual([]);
    });
  }
});
