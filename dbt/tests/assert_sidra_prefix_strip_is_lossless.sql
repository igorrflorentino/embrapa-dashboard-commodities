-- Remover o ordinal de exibição da SIDRA não pode remover texto informativo.
--
-- A SIDRA devolve o nome do produto prefixado com sua posição no menu ("7.1 - Carvão
-- vegetal"). O Silver remove esse prefixo, e o padrão anterior — `^([^-]+)\s-\s` — removia
-- QUALQUER prefixo sem hífen: um produto chamado "Açaí - fruto" teria perdido "Açaí" e
-- apareceria como "fruto". Nenhum valor da SIDRA jamais acionou isso (10 distintos, todos
-- ordinais), mas "ainda não aconteceu" não é garantia.
--
-- O padrão passou a exigir DÍGITOS E PONTOS (`^[0-9]+(?:\.[0-9]+)*\s-\s`), o que torna a
-- perda impossível por construção — texto informativo não casa com [0-9.]+. Este teste
-- prende a propriedade no DADO, não no padrão: reconstrói o nome bruto a partir do Gold e
-- exige que o que foi removido seja exclusivamente um ordinal numérico.
--
-- Falha ⇒ alguém afrouxou o padrão, ou a SIDRA passou a mandar um prefixo de outra forma.

with bruto as (
    select distinct tipo_de_produto_extrativo as nome
    from {{ source('bronze_ibge', 'sidra_raw') }}
    where tipo_de_produto_extrativo is not null

    union distinct

    select distinct tipo_de_produto_da_silvicultura as nome
    from {{ source('bronze_ibge', 'sidra_silvicultura_raw') }}
    where tipo_de_produto_da_silvicultura is not null
),

removido as (
    select
        nome,
        -- o que sobra depois do corte, e o que foi cortado
        trim(regexp_replace(nome, r'^[0-9]+(?:\.[0-9]+)*\s-\s', '')) as depois,
        regexp_extract(nome, r'^([0-9]+(?:\.[0-9]+)*\s-\s)')         as prefixo
    from bruto
)

select nome, depois, prefixo
from removido
-- O corte só é legítimo quando (a) nada foi removido, ou (b) o removido é um ordinal
-- puramente numérico E o que sobrou não ficou vazio.
where not (
    (prefixo is null and depois = trim(nome))
    or (prefixo is not null and length(trim(depois)) > 0)
)
