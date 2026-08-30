/**
 * "Editar filtros" e "Editar métricas" têm de ter as MESMAS dimensões.
 *
 * Eles ficam no mesmo canto de dois blocos empilhados, e larguras diferentes os fazem ler
 * como dois controles distintos quando são o mesmo controle de dois blocos. A altura já era
 * igual (a classe é compartilhada); a largura vinha do texto, e por isso diferia — 122px
 * contra 138px, medidos no navegador.
 *
 * A igualdade vem de um `min-width` fixo em px na classe compartilhada. O jsdom não aplica
 * CSS, então não dá para medir aqui — mas dá para prender as duas coisas de que a medida
 * depende:
 *
 *   1. a regra existe e é UMA só (se cada botão ganhar a sua, elas divergem em silêncio);
 *   2. o CONJUNTO de rótulos que usa a classe é o que foi medido. Um px não sabe o que o
 *      texto mede: renomear "Editar métricas" para algo mais longo estoura o min-width e as
 *      larguras voltam a divergir, sem erro nenhum. Este teste falha nesse caso e obriga a
 *      medir de novo no navegador.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const AQUI = dirname(fileURLToPath(import.meta.url));
const ler = (f) => readFileSync(join(AQUI, f), 'utf8');
const CSS = readFileSync(join(AQUI, '../../public/assets/filter-menu.css'), 'utf8');
const FONTES = ['FilterTriggerBar.jsx', 'MetricConventions.jsx'];

/** Os rótulos de todo <button className="fm-edit-btn"> — a âncora vem do JSX, não do CSS. */
function rotulos() {
  const achados = [];
  for (const f of FONTES) {
    const src = ler(f);
    for (const m of src.matchAll(/className="fm-edit-btn"[^>]*>([\s\S]*?)<\/button>/g)) {
      const texto = m[1]
        .replace(/<svg[\s\S]*?<\/svg>/g, '')   // o ícone não é rótulo
        .replace(/\{[\s\S]*?\}/g, '')          // expressões JSX
        .replace(/<[^>]*>/g, '')
        .replace(/\s+/g, ' ')
        .trim();
      if (texto) achados.push(texto);
    }
  }
  return achados.sort();
}

/** O corpo da regra `.fm-edit-btn { … }` (a declaração, não os `:hover`/` svg`). */
function regraDoBotao() {
  const m = CSS.match(/^\.fm-edit-btn\s*\{([^}]*)\}/m);
  return m ? m[1] : null;
}

describe('as duas ações de bloco têm as mesmas dimensões', () => {
  it('há UMA regra dimensionando .fm-edit-btn, não uma por botão', () => {
    expect(regraDoBotao()).toBeTruthy();                       // guarda o varredor
    // Nenhum seletor mais específico redefine largura/altura para um dos dois.
    const especificos = [...CSS.matchAll(/([^\n{}]*\.fm-edit-btn[^\n{}]*)\{([^}]*)\}/g)]
      .filter(([, sel]) => sel.trim() !== '.fm-edit-btn')
      .filter(([, , corpo]) => /(^|;|\s)(min-)?width\s*:|(^|;|\s)height\s*:/.test(corpo));
    expect(especificos.map(([, sel]) => sel.trim())).toEqual([]);
    // E nenhum dos dois componentes passa largura por style inline.
    for (const f of FONTES) {
      expect(ler(f), f).not.toMatch(/className="fm-edit-btn"[^>]*style=/);
    }
  });

  it('a regra fixa min-width — é ela que iguala as larguras', () => {
    const corpo = regraDoBotao();
    expect(corpo).toMatch(/min-width:\s*\d+px/);
    // Sem centralizar, o rótulo menor encosta à esquerda e sobra um vão à direita.
    expect(corpo).toMatch(/justify-content:\s*center/);
  });

  it('os rótulos são os que foram medidos — renomear obriga a remedir', () => {
    // Ordem alfabética: o que importa é o conjunto, não onde cada um aparece no arquivo.
    expect(rotulos()).toEqual([
      'Editar filtros',            // 122px
      'Editar métricas',           // 138px ← é este que define o min-width
      'Recolher',                  // 102px
      'Ver dimensões previstas',   // 194px, naturalmente maior; vive sozinho na barra de preview
    ]);
  });
});
