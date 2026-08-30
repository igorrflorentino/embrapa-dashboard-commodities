/**
 * Duas metades do PEVS, o mesmo nome, uma barra só.
 *
 * Madeira em tora, lenha e carvão vegetal existem tanto na extração vegetal (t289) quanto
 * na silvicultura (t291), com o MESMO nome e códigos diferentes. O BarChart usa o nome como
 * categoria do eixo, e o Plotly funde categorias homônimas numa posição só: aparecia UMA
 * barra (a maior) com os DOIS rótulos impressos por cima um do outro — o que o pesquisador
 * viu como "números borrados" em "O que <lugar> produz".
 *
 * Somar as duas seria pior que borrar: a metade plantada é ~5x a nativa, e um total que as
 * mistura em silêncio é "um número errado vestindo um rótulo certo" (CLAUDE.md).
 */
import { beforeEach, describe, expect, it } from 'vitest';

import './filtersSchema.js'; // registra window.TABELA_OPTIONS + window.labelProductRows

const CARVAO_SILV = { code: '3455', name: 'Carvão vegetal', tabela: '291', value: 114564 };
const CARVAO_EXTR = { code: '3433', name: 'Carvão vegetal', tabela: '289', value: 13745 };
const ACAI = { code: '3403', name: 'Açaí (fruto)', tabela: '289', value: 1 };

const nomes = (rows) => window.labelProductRows(rows, 'ibge_pevs').map((r) => r.name);

describe('labelProductRows — desambiguar só quando é preciso', () => {
  beforeEach(() => expect(typeof window.labelProductRows).toBe('function'));

  it('um nome repetido ganha a metade; um nome único não', () => {
    // A asserção que importa é o CONJUNTO de categorias ser único — é o que o Plotly
    // exige e o que faltava. O sufixo é o meio, não o fim.
    const out = nomes([CARVAO_SILV, CARVAO_EXTR, ACAI]);
    expect(out).toEqual(['Carvão vegetal · silvicultura', 'Carvão vegetal · extração', 'Açaí (fruto)']);
    expect(new Set(out).size, 'categorias homônimas voltariam a fundir no gráfico').toBe(out.length);
  });

  it('filtrado a UMA metade, os nomes ficam limpos', () => {
    // Cada nome é único, e o chip de Origem já diz qual metade está em tela — repetir isso
    // em toda barra seria ruído.
    expect(nomes([CARVAO_SILV, ACAI])).toEqual(['Carvão vegetal', 'Açaí (fruto)']);
  });

  it('linha sem origem nunca ganha sufixo, mesmo com nome repetido', () => {
    // Bancos sem metades (COMEX): não há o que dizer sobre a linha, e inventar um sufixo
    // seria pior que a fusão. Elas continuam homônimas de propósito — o defeito ali, se
    // existisse, seria outro (dois NCMs com a mesma descrição).
    const semOrigem = [
      { code: '4403', name: 'Madeira em tora', value: 9 },
      { code: '4407', name: 'Madeira em tora', value: 3 },
    ];
    expect(window.labelProductRows(semOrigem, 'mdic_comex').map((r) => r.name))
      .toEqual(['Madeira em tora', 'Madeira em tora']);
  });

  it('não muta as linhas recebidas', () => {
    // O chamador ordena/fatia a mesma lista; mutar o `name` na origem faria o rótulo
    // vazar para outras leituras da mesma referência.
    const entrada = [{ ...CARVAO_SILV }, { ...CARVAO_EXTR }];
    window.labelProductRows(entrada, 'ibge_pevs');
    expect(entrada.map((r) => r.name)).toEqual(['Carvão vegetal', 'Carvão vegetal']);
  });

  it('o rótulo curto vem do MESMO registro que o filtro usa', () => {
    // Âncora externa: se alguém renomear uma metade no TABELA_OPTIONS, o sufixo do gráfico
    // acompanha. Sem isso nasceria um segundo vocabulário da metade do PEVS.
    const opts = window.TABELA_OPTIONS.ibge_pevs.filter((o) => o.short);
    expect(opts.length).toBe(2);
    for (const o of opts) {
      const out = window.labelProductRows(
        [{ name: 'X', tabela: o.value }, { name: 'X', tabela: 'outra' }], 'ibge_pevs',
      );
      expect(out[0].name).toBe(`X · ${o.short}`);
    }
  });

  it('lista vazia e banco sem metades não quebram', () => {
    expect(window.labelProductRows([], 'ibge_pevs')).toEqual([]);
    expect(window.labelProductRows(undefined, 'ibge_pevs')).toEqual([]);
    expect(window.labelProductRows([{ name: 'X' }], 'banco_inexistente').map((r) => r.name))
      .toEqual(['X']);
  });
});
