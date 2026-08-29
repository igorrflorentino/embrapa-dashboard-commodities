# Divergências entre os seeds de comércio e a nomenclatura do MDIC

**Gerado por `scripts/audit_nomenclature_seeds.py` — não editar à mão.**

COMEX e COMTRADE não trazem descrição nos dados: o arquivo do MDIC tem código e
números, e o Bronze do COMTRADE também. O nome que aparece na tela vem de um seed
deste repositório. A política é usar o **texto pleno da nomenclatura** e registrar
aqui toda divergência contra o campo de exibição do MDIC.

As quatro classes:

| classe | o que significa |
|---|---|
| `oficial abreviado` | o MDIC encurtou para caber no campo (`Outs.painéis`) |
| `nosso mais pleno` | mesmo sentido, nosso texto carrega mais qualificadores |
| `procedência distinta` | veio de outra fonte (tradução WCO/Comtrade) |
| `ausente no MDIC` | o código não existe na tabela auxiliar — ver a nota abaixo |

**Sobre `ausente no MDIC`.** Não é defeito nem lacuna a preencher: a tabela do MDIC
cobre o SH da nomenclatura BRASILEIRA, e o COMTRADE é comércio mundial numa janela
de 25 anos. Três situações caem nessa classe e nenhuma tem conserto do lado do MDIC:

1. **Código aposentado** numa revisão do SH, presente só nos anos antigos —
   `440331` e `440335` (madeiras tropicais) aparecem no Gold apenas em 2000–2005.
2. **Código vigente que o Brasil não usa** — `440714` (Hem-fir, conífera
   norte-americana) tem 703 linhas em 2022–2025 e nenhuma entrada no MDIC.
3. **Linha de seed sem dado**, que só custa uma linha de CSV.

O seed pode ser mais largo que os dados; o contrário é que quebra, e disso cuida o
teste `assert_trade_codes_have_a_description`.

## comex_ncm (NCM-8 · NO_NCM_POR)

17 divergência(s).

### nosso mais pleno (8)

| código | texto usado | texto do MDIC |
|---|---|---|
| `20079921` | Purês e pastas, cozidos, de açaí (Euterpe oleracea) | Purês de açaí (Euterpe oleracea) |
| `20079926` | Purês e pastas, cozidos, de cupuaçu (Theobroma grandiflorum) | Purês de cupuaçu (Theobroma grandiflorum) |
| `08031000` | Bananas-da-terra (plátanos), frescas ou secas | Bananas-da-terra, frescas ou secas |
| `08039000` | Bananas, exceto bananas-da-terra, frescas ou secas | Bananas frescas ou secas, exceto bananas-da-terra |
| `11062000` | Farinhas, sêmolas e pós de sagu ou de raízes/tubérculos da posição 07.14 (mandioca) | Farinhas, sêmolas e pós, de sagu ou das raízes ou tubérculos, da posição 07.14 |
| `15079090` | Outros óleos de soja e suas frações | Outros óleos de soja |
| `23040010` | Bagaços e outros resíduos sólidos da extração do óleo de soja, em farinhas e pellets | Farinhas e pellets, da extração do óleo de soja |
| `10064000` | Arroz quebrado (trinca de arroz) | Arroz quebrado |

### procedência distinta (9)

| código | texto usado | texto do MDIC |
|---|---|---|
| `19030000` | Tapioca e seus sucedâneos preparados a partir de féculas | Tapioca e seus sucedâneos preparados a partir de féculas, em flocos, grumos, grãos, pérolas ou formas semelhantes |
| `15079011` | Óleo de soja, refinado, em recipientes de conteúdo não superior a 5 litros | Óleo de soja, refinado, em recipientes com capacidade inferior ou igual a 5 litros |
| `15079019` | Óleo de soja, refinado, em outros recipientes | Óleo de soja, refinado, em recipientes com capacidade menor que 5 litros |
| `23040090` | Outros bagaços e resíduos sólidos da extração do óleo de soja | Bagaços e outros resíduos sólidos, da extração do óleo de soja |
| `10059010` | Milho em grão | Milho em grão, exceto para semeadura |
| `10059090` | Outros tipos de milho | Milho, exceto em grão |
| `10062010` | Arroz descascado (arroz cargo ou castanho), parboilizado | Arroz descascado (arroz cargo ou castanho), descascado, parboilizado |
| `10063019` | Arroz semibranqueado ou branqueado, parboilizado, outros | Outros tipode de arroz semibranqueado ou branqueado, parboilizado |
| `10063029` | Arroz semibranqueado ou branqueado, não parboilizado, outros | Outros tipode de arroz semibranqueado ou branqueado, não parboilizado |

## comtrade_hs (SH · NO_SH*_POR)

201 divergência(s).

### oficial abreviado (11)

| código | texto usado | texto do MDIC |
|---|---|---|
| `441012` | Painéis denominados oriented strand board (OSB), de madeira, mesmo aglomerados com resinas ou outros aglutinantes orgânicos | Painéis denominados oriented strand board" (OSB)" |
| `441021` | Painéis de partículas e painéis semelhantes (por exemplo, painéis denominados «  oriented strand board » e painéis denominados «  waferboard »), de madeira ou de outras matérias lenhosas, mesmo aglomeradas com resinas ou com outros aglutinantes orgânicos — Não trabalhados ou apenas lixados | Painéis de particul."waferboard", etc.em bruto |
| `441029` | Painéis de partículas e painéis semelhantes (por exemplo, painéis denominados «  oriented strand board » e painéis denominados «  waferboard »), de madeira ou de outras matérias lenhosas, mesmo aglomeradas com resinas ou com outros aglutinantes orgânicos — Outros | Outros painéis de partículas "waferboard", etc. |
| `441033` | Painéis de partículas e painéis semelhantes (por exemplo, painéis denominados «  oriented strand board » e painéis denominados «  waferboard »), de madeira ou de outras matérias lenhosas, mesmo aglomeradas com resinas ou com outros aglutinantes orgânicos — Revestidos na superfície com laminados decorativos de plásticos | Outs.painéis de madeira recob.placas plástico |
| `441111` | Painéis de fibras de madeira ou de outras matérias lenhosas, mesmo aglomeradas com resinas ou com outros aglutinantes orgânicos — Não trabalhados mecanicamente nem revestidos na superfície | painéis de fibras de madeira, n/trab.mecan.d>0.8g/cm3 |
| `441121` | Painéis de fibras de madeira ou de outras matérias lenhosas, mesmo aglomeradas com resinas ou com outros aglutinantes orgânicos — Não trabalhados mecanicamente nem revestidos na superfície | Painéis de fibras de madeira, n/trab.mec.0.5<d<=0.8g/cm3 |
| `441131` | Painéis de fibras de madeira ou de outras matérias lenhosas, mesmo aglomeradas com resinas ou com outros aglutinantes orgânicos — Não trabalhados mecanicamente nem revestidos na superfície | Painéis de fibras madeira, n/trab.mecan.0.35<d<=0.5g/cm3 |
| `441191` | Painéis de fibras de madeira ou de outras matérias lenhosas, mesmo aglomeradas com resinas ou com outros aglutinantes orgânicos — Não trabalhados mecanicamente nem revestidos na superfície | Outs.painéis de fibras de madeira, n/trab.mecan.n/recob. |
| `441222` | Madeira contraplacada ou compensada, madeira folheada, e madeiras estratificadas semelhantes — Com pelo menos uma folha de madeira tropical especificada na Nota de subposição 1 deste Capítulo | Outs.madeiras compens.face mad.n/conif.camada mad.trop. |
| `441223` | Madeira contraplacada ou compensada, madeira folheada, e madeiras estratificadas semelhantes — Outras, contendo pelo menos uma camada de painel de partículas | Outs.madeiras compens.face mad.n/conif.painel particula |
| `441292` | Madeira compensada; não especificada na posição 4412, com pelo menos uma folha externa de madeira de não coníferas | Outs.madeiras compensadas, c/camada de madeira tropical |

### nosso mais pleno (132)

| código | texto usado | texto do MDIC |
|---|---|---|
| `200591` | Brotos de bambu, preparados ou conservados, exceto em vinagre ou em ácido acético, não congelados | Brotos de bambu preparados ou conservados, exceto em vinagre ou em ácido acético, não congelados |
| `0801` | Frutas de casca rija, comestíveis; cocos, castanha-do-pará e castanha de caju, frescas ou secas, com ou sem casca ou pele | Cocos, castanha do Brasil e castanha de caju, frescos ou secos, mesmo sem casca ou pelados |
| `4405` | Lã (palha) de madeira; farinha de madeira | Lã de madeira; farinha de madeira |
| `4407` | Madeira serrada ou fendida longitudinalmente, cortada transversalmente ou desenrolada, mesmo aplainada, lixada ou unida pelas extremidades, de espessura superior a 6 mm | Madeira serrada ou endireitada longitudinalmente, cortada ou desenrolada, mesmo aplainada, polida ou unida pelas extremidades, de espessura superior a 6 mm |
| `4408` | Folhas para folheados (incluindo as obtidas por corte de madeira estratificada), para compensados ou madeiras estratificadas semelhantes e outras madeiras, serradas longitudinalmente, cortadas transversalmente ou desenroladas, mesmo aplainadas, lixadas, unidas pelas bordas ou extremidades, de espessura não superior a 6 mm | Folhas para folheados (incluindo as obtidas por corte de madeira estratificada), folhas para contraplacados ou compensados ou para outras madeiras estratificadas semelhantes e madeira serrada longitudinalmente, cortada ou desenrolada, mesmo aplainada, pol |
| `4409` | Madeira (incluindo tacos e frisos para soalhos, não montados) perfilada (com espigas, ranhuras, filetes, entalhes, chanfrada, com juntas em V, boleada ou semelhantes) ao longo de uma ou mais bordas, faces ou extremidades, mesmo aplainada, lixada ou unida pelas extremidades | Madeira (incluídos os tacos e frisos para soalhos, não montados) perfilada (com espigas, ranhuras, filetes, entalhes, chanfrada, com juntas em V, com cercadura, boleada ou semelhantes) ao longo de uma ou mais bordas, faces ou extremidades, mesmo aplainada |
| `4416` | Barris, cubas, balsas, dornas, selhas e outras obras de tanoeiro e respectivas partes, de madeira, incluindo as aduelas | Barris, cubas, balsas, dornas e outras obras de tanueiro, de madeira |
| `4418` | Obras de marcenaria ou de carpintaria para construções, incluindo painéis celulares, painéis montados para revestimento de pisos (pavimentos) e fasquias para telhados (shingles e shakes), de madeira | Obras de carpintaria para construções, incluídos os painéis celulares, os painéis para soalhos e as fasquias para telhados (shingles e shakes), de madeira |
| `4421` | Outras obras de madeira não classificadas nas posições 4414 a 4420 | Outras obras de madeira |
| `080111` | Frutas de casca rija, comestíveis; cocos, dessecados | Cocos secos, mesmo sem casca ou ralados |
| `080112` | Frutas de casca rija, comestíveis; cocos, com casca interna (endocarpo) | Cocos na casca interna (endocarpo) |
| `080119` | Frutas de casca rija, comestíveis; cocos, frescos ou secos, exceto dessecados ou com casca interna (endocarpo) | Cocos frescos, mesmo sem casca ou pelados |
| `080121` | Frutas de casca rija, comestíveis; castanha-do-pará, fresca ou seca, com casca | Castanha-do-pará, fresca ou seca, com casca |
| `080122` | Frutas de casca rija, comestíveis; castanha-do-pará, fresca ou seca, sem casca | Castanha-do-pará, fresca ou seca, sem casca |
| `080131` | Frutas de casca rija, comestíveis; castanha de caju, fresca ou seca, com casca | Castanha de caju, fresca ou seca, com casca |
| `080132` | Frutas de casca rija, comestíveis; castanha de caju, fresca ou seca, sem casca | Castanha de caju, fresca ou seca, sem casca |
| `440111` | Madeira; para combustível, em toras, achas, galhos, feixes ou formas semelhantes, mesmo aglomerada, de coníferas | Lenha em qualquer forma, de coníferas |
| `440112` | Madeira; para combustível, em toras, achas, galhos, feixes ou formas semelhantes, mesmo aglomerada, de não coníferas | Lenha em qualquer forma, de não coníferas |
| `440121` | Madeira; para combustível, em estilhas ou partículas, de coníferas, mesmo aglomerada | Madeira de coníferas, em estilhas ou em partículas |
| `440122` | Madeira; para combustível, em estilhas ou partículas, de não coníferas, mesmo aglomerada | Madeira de não coníferas, em estilhas ou em partículas |
| `440131` | Madeira; para combustível, serragem, desperdícios e resíduos, aglomerados em pellets de madeira | Pellets de madeira |
| `440132` | Madeira; para combustível, serragem, desperdícios e resíduos, aglomerados em briquetes de madeira | Briquetes de madeira |
| `440139` | Madeira; para combustível, serragem, desperdícios e resíduos, aglomerados em toras ou formas semelhantes, exceto pellets ou briquetes de madeira | Outras serragens, desperdícios e resíduos, de madeira |
| `440140` | Madeira; para combustível, serragem, desperdícios e resíduos, não aglomerados | Serragem (serradura), desperdícios e resíduos, de madeira, não aglomerados |
| `440141` | Madeira; para combustível, serragem, desperdícios e resíduos, não aglomerados; serragem | Serradura, não aglomerada |
| `440200` | Carvão vegetal (incluindo o carvão de cascas ou de caroços), mesmo aglomerado. | carvão vegetal |
| `440210` | Madeira; carvão de bambu, mesmo aglomerado | Carvão vegetal de bambu, mesmo aglomerado |
| `440290` | Madeira; carvão vegetal exceto de bambu, cascas ou caroços, mesmo aglomerado | Outros carvões vegetais, mesmo aglomerados |
| `440311` | Madeira; de coníferas, em bruto, mesmo descascada, desalburnada ou esquadriada; tratada com tinta, creosoto ou outros agentes de conservação | Madeira em bruto, mesmo descascada, desalburnada ou esquadriada, tratada com tinta, creosoto ou outros agentes de conservação, de coníferas |
| `440312` | Madeira; de não coníferas, em bruto, mesmo descascada, desalburnada ou esquadriada; tratada com tinta, creosoto ou outros agentes de conservação | Madeira em bruto, mesmo descascada, desalburnada ou esquadriada, tratada com tinta, creosoto ou outros agentes de conservação, de não coníferas |
| `440321` | Madeira; de coníferas, de pinho (Pinus spp.), em bruto, mesmo descascada, desalburnada ou esquadriada, não tratada, cuja menor dimensão da seção transversal seja igual ou superior a 15 cm | Madeira em bruto, mesmo descascada, desalburnada ou esquadriada, de pinheiro (Pinus spp.), cuja maior dimensão da seção transversal é igual ou superior a 15 cm |
| `440322` | Madeira; de coníferas, de pinho (Pinus spp.), em bruto, mesmo descascada, desalburnada ou esquadriada, não tratada, cuja menor dimensão da seção transversal seja inferior a 15 cm | Madeira em bruto, mesmo descascada, desalburnada ou esquadriada, de pinheiro (Pinus spp.) |
| `440324` | Madeira; de coníferas, de abeto (Abies spp.) e de espruce (Picea spp.), em bruto, não tratada, cuja menor dimensão da seção transversal seja inferior a 15 cm | Madeira de abeto (Abies spp.), e de espruce (Picea spp.) em bruto, mesmo descascada, desalburnada ou esquadriada |
| `440325` | Madeira; de coníferas não especificadas nas subposições 4403.21 ou 4403.23, em bruto, não tratada, cuja menor dimensão da seção transversal seja igual ou superior a 15 cm | Outras madeiras em bruto, mesmo descascada, desalburnada ou esquadriada, de coníferas, cuja maior dimensão da seção transversal é igual ou superior a 15 cm |
| `440326` | Madeira; de coníferas não especificadas nas subposições 4403.22 ou 4403.24, em bruto, não tratada, cuja menor dimensão da seção transversal seja inferior a 15 cm | Outras madeiras em bruto, mesmo descascada, desalburnada ou esquadriada, de coníferas |
| `440341` | Madeira tropical; conforme a Nota de subposição 2 deste Capítulo, meranti vermelho-escuro, meranti vermelho-claro e meranti bakau, em bruto, mesmo descascada, desalburnada ou esquadriada, não tratada | Dark Red Meranti, Light Red Meranti e Meranti Bakau, em bruto, mesmo descascadas, desalburnadas ou esquadriadas |
| `440342` | Madeira tropical; teca, em bruto, mesmo descascada, desalburnada ou esquadriada, não tratada | Madeira em bruto, descascada ou não, descascada ou esquadriada, de teca |
| `440349` | Madeira tropical; exceto meranti vermelho-escuro, meranti vermelho-claro, meranti bakau e teca, em bruto, mesmo descascada, desalburnada ou esquadriada, não tratada | Outras madeiras tropicais, em bruto |
| `440391` | Madeira; de carvalho (Quercus spp.), em bruto, mesmo descascada, desalburnada ou esquadriada, não tratada | Madeira de carvalho (Quercus spp.), em bruto, mesmo descascada, desalburnada ou esquadriada |
| `440394` | Madeira; de faia (Fagus spp.), em bruto, não tratada, cuja menor dimensão da seção transversal seja inferior a 15 cm | Madeira em bruto, mesmo descascada, desalburnada ou esquadriada, de faia (Fagus spp.), outras |
| `440396` | Madeira; de bétula (Betula spp.), em bruto, não tratada, cuja menor dimensão da seção transversal seja inferior a 15 cm | Madeira em bruto, mesmo descascada, desalburnada ou esquadriada, de bétula (vidoeiro) (Betula spp.), outras |
| `440397` | Madeira; de choupo e álamo (Populus spp.), em bruto, mesmo descascada, desalburnada ou esquadriada, não tratada | Madeira em bruto, mesmo descascada, desalburnada ou esquadriada, de choupo (álamo) (Populus spp.) |
| `440398` | Madeira; de eucalipto (Eucalyptus spp.), em bruto, mesmo descascada, desalburnada ou esquadriada, não tratada | Madeira em bruto, mesmo descascada, desalburnada ou esquadriada, de eucalipto (Eucalyptus spp.) |
| `440399` | Madeira; em bruto, mesmo descascada, desalburnada ou esquadriada, não tratada, não especificada na posição 4403 | Outras madeiras em bruto |
| `440410` | Madeira; de coníferas, estacas fendidas, estacas, postes e piquetes aguçados mas não serrados longitudinalmente; varas para guarda-chuvas, cabos de ferramentas e semelhantes, simplesmente desbastadas mas não torneadas nem curvadas; estilhas e madeira para arcos | Arcos de madeira, estacas fendidas, estacas aguçadas; madeira simplesmente desbastada ou arredondada para fabricação de bengalas, cabos de ferramenta e semelhantes; de coníferas |
| `440420` | Madeira; de não coníferas, estacas fendidas, estacas, postes e piquetes aguçados mas não serrados longitudinalmente; varas para guarda-chuvas, cabos de ferramentas e semelhantes, simplesmente desbastadas mas não torneadas nem curvadas; estilhas e madeira para arcos | Arcos de madeira, estacas fendidas, estacas aguçadas; madeira simplesmente desbastada ou arredondada para fabricação de bengalas, cabos de ferramenta e semelhantes; madeira em fasquias, lâminas, fitas e semelhantes; de não coníferas |
| `440500` | Madeira; lã (palha) de madeira e farinha de madeira | Lã de madeira e farinha de madeira |
| `440691` | Madeira; dormentes para vias férreas ou semelhantes, impregnados, de coníferas | Dormentes de madeira para vias férreas ou semelhantes, de coníferas |
| `440692` | Madeira; dormentes para vias férreas ou semelhantes, impregnados, de não coníferas | Dormentes de madeira para vias férreas ou semelhantes, de não coníferas |
| `440711` | Madeira; de coníferas, de pinho (Pinus spp.), serrada ou fendida longitudinalmente, cortada transversalmente ou desenrolada, mesmo aplainada, lixada ou unida pelas extremidades, de espessura superior a 6 mm | Madeira serrada ou fendida longitudinalmente, cortada transversalmente ou desenrolada, mesmo aplainada, lixada ou unida pelas extremidades, de espessura superior a 6 mm, de pinheiro (Pinus spp.) |
| `440712` | Madeira; de coníferas, de abeto (Abies spp.) e de espruce (Picea spp.), serrada ou fendida longitudinalmente, cortada transversalmente ou desenrolada, mesmo aplainada, lixada ou unida pelas extremidades, de espessura superior a 6 mm | Madeira serrada ou fendida longitudinalmente, cortada transversalmente ou desenrolada, mesmo aplainada, lixada ou unida pelas extremidades, de espessura superior a 6 mm, de abeto (Abies spp.) e de espruce (pícea) (Picea spp.) |
| `440713` | Madeira; de coníferas, de S-P-F (espruce (Picea spp.), pinho (Pinus spp.) e abeto (Abies spp.)), serrada ou fendida longitudinalmente, mesmo aplainada, lixada ou unida pelas extremidades, de espessura superior a 6 mm | Madeira serrada ou fendida longitudinalmente, cortada ou descascada, mesmo aplainada, lixada ou unida pelas extremidades, de espessura superior a 6 mm de S-P-F (Picea spp.), pinus (Pinus spp.) e abeto (Abies spp.) |
| `440719` | Madeira; de coníferas, exceto de pinho (Pinus spp.), abeto (Abies spp.) ou espruce (Picea spp.), serrada ou fendida longitudinalmente, mesmo aplainada, lixada ou unida pelas extremidades, de espessura superior a 6 mm | Madeira serrada ou fendida longitudinalmente, cortada transversalmente ou desenrolada, mesmo aplainada, lixada ou unida pelas extremidades, de espessura superior a 6 mm, de outras coníferas |
| `440721` | Madeira tropical; conforme a Nota de subposição 2 deste Capítulo, mogno (Swietenia spp.), serrada ou fendida longitudinalmente, cortada transversalmente ou desenrolada, mesmo aplainada, lixada ou unida pelas extremidades, de espessura superior a 6 mm | Madeira de mogno (Swietenia spp), serrada, cortada em folhas ou desenrolada, de espessura > 6mm |
| `440723` | Madeira tropical; teca, serrada ou fendida longitudinalmente, cortada transversalmente ou desenrolada, aplainada, esquadriada, estrutural, de espessura superior a 6 mm | Madeira serrada ou lascada longitudinalmente, cortada ou descascada, mesmo aplainada, lixada ou unida pelas extremidades, de espessura superior a 6 mm, de teca |
| `440725` | Madeira tropical; meranti vermelho-escuro, meranti vermelho-claro e meranti bakau, serrada ou fendida longitudinalmente, mesmo aplainada, lixada ou unida pelas extremidades, de espessura superior a 6 mm | Madeira de Dark Red Meranti, Light Red Meranti e Meranti Bakau, serrada, cortada em folhas ou desenrolada, de espessura > 6 mm |
| `440726` | Madeira tropical; lauan branco, meranti branco, seraya branco, meranti amarelo e alan, serrada ou fendida longitudinalmente, mesmo aplainada, lixada ou unida pelas extremidades, de espessura superior a 6 mm | Madeira de White Lauan, White Meranti, White Seraya Yellow Meranti e Alan, serradas, cortadas em folhas ou desenroladas, de espessura > 6 mm |
| `440728` | Madeira tropical; iroko, serrada ou fendida longitudinalmente, mesmo aplainada, lixada ou unida pelas extremidades, de espessura superior a 6 mm | Madeira de iroco, serrada, cortada em folhas ou desenrolada, de espessura > 6mm |
| `440729` | Madeira tropical; não especificada no item 4407.2, serrada ou fendida longitudinalmente, mesmo aplainada, lixada ou unida pelas extremidades, de espessura superior a 6 mm | Outras madeiras tropicais (cedro, ipê, pau-marfim, louro, etc), serradas, cortadas em folhas ou desenroladas, de espessura > 6 mm |
| `440791` | Madeira; de carvalho (Quercus spp.), serrada ou fendida longitudinalmente, mesmo aplainada, lixada ou unida pelas extremidades, de espessura superior a 6 mm | Madeira de carvalho (Quercus spp.), serrada, cortada em folhas ou desenrolada, de espessura > 6 mm |
| `440792` | Madeira; de faia (Fagus spp.), serrada ou fendida longitudinalmente, mesmo aplainada, lixada ou unida pelas extremidades, de espessura superior a 6 mm | Madeira de faia (Fagus spp.), serrada, cortada em folhas ou desenrolada, de espessura > 6 mm |
| `440793` | Madeira; de bordo (Acer spp.), serrada ou fendida longitudinalmente, mesmo aplainada, lixada ou unida pelas extremidades, de espessura superior a 6 mm | Madeira de ácer (Acer spp.), serrada, cortada em folhas ou desenrolada, de espessura > 6mm |
| `440794` | Madeira; de cerejeira (Prunus spp.), serrada ou fendida longitudinalmente, mesmo aplainada, lixada ou unida pelas extremidades, de espessura superior a 6 mm | Madeira de cerejeira (Prunus spp.), serrada, cortada em folhas ou desenrolada, de espessura > 6mm |
| `440799` | Madeira; serrada ou fendida longitudinalmente, cortada transversalmente ou desenrolada, de espessura superior a 6 mm, mesmo aplainada, lixada ou unida pelas extremidades, não especificada na posição 4407 | Outras madeiras, serradas, cortadas em folhas ou desenroladas, de espessura > 6 mm |
| `440810` | Madeira; de coníferas, folhas para folheados (incluindo as obtidas por corte de madeira estratificada), para compensados ou madeiras estratificadas semelhantes e outras madeiras, serradas longitudinalmente, cortadas transversalmente ou desenroladas, mesmo aplainadas, lixadas, unidas pelas bordas ou extremidades, de espessura não superior a 6 mm | Folhas de madeira para folheados e para compensados, de coníferas, de espessura <= 6 mm |
| `440831` | Madeira tropical; conforme a Nota de subposição 2 deste Capítulo, meranti vermelho-escuro, meranti vermelho-claro e meranti bakau, folhas para folheados, compensados ou outras madeiras, serradas longitudinalmente, cortadas transversalmente ou desenroladas, mesmo aplainadas, lixadas ou unidas pelas extremidades, de espessura não superior a 6 mm | Folhas de madeira para folheados e para compensados, de dark ou light red meranti ou meranti bakau, de espessura <= 6 mm |
| `440839` | Madeira tropical; conforme a Nota de subposição 2 deste Capítulo, não especificada na subposição 4408.31, folhas para folheados ou compensados, outras madeiras serradas longitudinalmente, cortadas transversalmente ou desenroladas, mesmo aplainadas, lixadas ou unidas pelas extremidades, de espessura não superior a 6 mm | Folhas para folheados (incluindo as obtidas por corte de madeira estratificada),folhas para compensados ou para madeiras estratificadas semelhantes e outras madeiras, etc..., espessura <= 6 mm,obtidas por corte de madeira estratificada, madeiras tropicais |
| `440890` | Madeira; não especificada na posição 4408, folhas para folheados ou compensados, outras madeiras serradas longitudinalmente, cortadas transversalmente ou desenroladas, mesmo aplainadas, lixadas ou unidas pelas extremidades, de espessura não superior a 6 mm | Folhas para folheados e para compensados, de outras madeiras, de espessura <= 6 mm |
| `440910` | Madeira; de coníferas (incluindo tacos e frisos para soalhos, não montados), perfilada ao longo de uma ou mais bordas, faces ou extremidades, mesmo aplainada, lixada ou unida pelas extremidades | Madeira de coníferas, perfilada |
| `440921` | Madeira; de bambu (incluindo tacos e frisos para soalhos, não montados), perfilada ao longo de uma ou mais bordas, faces ou extremidades, mesmo aplainada, lixada ou unida pelas extremidades | Madeira de bambu, perfilada |
| `440929` | Madeira; de não coníferas, exceto bambu ou madeira tropical (incluindo tacos e frisos para soalhos, não montados), perfilada ao longo de uma ou mais bordas, faces ou extremidades, mesmo aplainada, lixada ou unida pelas extremidades | Outras madeiras perfiladas de não coníferas |
| `441011` | Painéis de partículas de madeira, mesmo aglomerados com resinas ou outros aglutinantes orgânicos | Painéis de partículas, de madeira |
| `441019` | Painéis waferboard e painéis semelhantes de madeira não especificados no item 4410.1, mesmo aglomerados com resinas ou outros aglutinantes orgânicos | Outros painéis de madeira (waferboard e outros) |
| `441090` | Painéis de partículas, painéis denominados oriented strand board (OSB) e painéis semelhantes, de matérias lenhosas exceto madeira, mesmo aglomerados com resinas ou outros aglutinantes orgânicos | Outros painéis de matérias lenhosas, mesmo aglomeradas com resinas ou aglutinantes |
| `441112` | Painéis de fibras de média densidade (MDF), de espessura não superior a 5 mm | Painéis de média densidade (MDF), de espessura não superior a 5mm |
| `441113` | Painéis de fibras de média densidade (MDF), de espessura superior a 5 mm mas não superior a 9 mm | Painéis de média densidade (MDF) de espessura superior a 5mm, mas não superior a 9mm |
| `441114` | Painéis de fibras de média densidade (MDF), de espessura superior a 9 mm | Painéis de média densidade (MDF), de espessura superior a 9 mm |
| `441192` | Painéis de fibras (exceto MDF) de densidade superior a 0,8 g/cm³, de madeira ou de outras matérias lenhosas, mesmo aglomerados com resinas ou outras substâncias orgânicas | Painéis de fibra de madeira ou de outras matérias lenhosas, mesmo aglomeradas com resinas ou outros algutinantes orgânicos, com densidade superior a 0,8g/cm3 |
| `441193` | Painéis de fibras (exceto MDF) de densidade superior a 0,5 g/cm³ mas não superior a 0,8 g/cm³, de madeira ou de outras matérias lenhosas, mesmo aglomerados com resinas ou outras substâncias orgânicas | Painéis de fibra de madeira ou de outras matérias lenhosas, mesmo aglomeradas com resinas ou outros algutinantes orgânicos, com densidade superior a 0,5g/cm3 mas não superior a 0,8g/cm3 |
| `441194` | Painéis de fibras (exceto MDF) de densidade não superior a 0,5 g/cm³, de madeira ou de outras matérias lenhosas, mesmo aglomerados com resinas ou outras substâncias orgânicas | Painéis de fibra de madeira ou de outras matérias lenhosas, mesmo aglomeradas com resinas ou outros algutinantes orgânicos, com densidade não superior a 0,5g/cm3 |
| `441210` | Madeira compensada (contraplacada), madeira folheada e madeiras estratificadas semelhantes; de bambu | Madeira compensada ou folheada, e madeiras estratificadas semelhantes, de bambu |
| `441231` | Madeira compensada; constituída exclusivamente por folhas de madeira (exceto bambu), cada folha de espessura não superior a 6 mm, com pelo menos uma folha externa de madeira tropical | Madeira compensada, constituída por folhas de madeira (exceto bambu), cada uma das quais de espessura não superior a 6 mm, com pelo menos uma face de madeira tropicais |
| `441233` | Madeira compensada; constituída exclusivamente por folhas de madeira; exceto bambu; cada folha de espessura não superior a 6 mm, com pelo menos uma folha externa de amieiro, freixo, faia, bétula, cerejeira, castanheiro, olmo, eucalipto, nogueira-americana (hickory), castanha-da-índia, tília, bordo, carvalho, plátano, choupo, álamo, robínia, liriodendro ou nogueira | Outras, com, pelo menos, uma camada exterior de madeira não conífera, das espécies amieiro freixo, faia, bétula, prunóidea, castanheiro, olmo eucalipto, nogueira, castanheiro-da-índia, tília, bordo, carvalho, plátano, choupo,robínia,tulipeiro  ou nogueira |
| `441234` | Madeira compensada; constituída exclusivamente por folhas de madeira (exceto bambu), cada folha de espessura não superior a 6 mm, com pelo menos uma folha externa de madeira de não coníferas não relacionada na subposição 4412.33 | Outras madeiras compensadas com, pelo menos, uma camada exterior de madeira não conífera, não especificadas na subposição 4412.33 |
| `441239` | Madeira compensada; constituída exclusivamente por folhas de madeira (exceto bambu), cada folha de espessura não superior a 6 mm, com ambas as folhas externas de madeira de coníferas | Outras madeiras compensadas constituídas por folhas de madeira, cada uma das quais de espessura não superior a 6 mm |
| `441241` | Madeira compensada, madeira folheada e madeiras estratificadas semelhantes; madeira laminada folheada (LVL); com pelo menos uma folha externa de madeira tropical | Madeira folheada laminada (LVL), com pelo menos uma camada externa de madeira tropical |
| `441251` | Painéis alveolados (blockboard, laminboard e battenboard); com pelo menos uma camada externa de madeira tropical | Placas, laminas e ripas, com pelo menos uma lona externa de madeira tropical |
| `441252` | Painéis alveolados (blockboard, laminboard e battenboard); com pelo menos uma folha externa de madeira de não coníferas (não contendo painel de partículas) | Outros blockboard, laminboard e battenboard, com pelo menos uma camada externa de madeira não conífera |
| `441259` | Painéis alveolados (blockboard, laminboard e battenboard); com ambas as folhas externas de madeira de coníferas | Outras placas, lâminas e ripas, com ambas as camadas externas de madeira de coníferas |
| `441294` | Painéis alveolados (blockboard, laminboard e battenboard) (exceto bambu e exceto madeira compensada constituída exclusivamente por folhas de madeira, cada folha de espessura não superior a 6 mm) | Outras madeiras compensadas com alma aglomerada, alveolada ou lamelada |
| `441299` | Madeira compensada; não especificada na posição 4412, com ambas as folhas externas de madeira de coníferas | Outras madeiras compensadas, folheadas ou estratificadas |
| `441300` | Madeira; densificada, em blocos, pranchas, lâminas ou perfis | Madeira densificada, em blocos, pranchas, lâminas ou perfis |
| `441410` | Molduras de madeira para quadros, fotografias, espelhos ou objetos semelhantes; de madeira tropical | Molduras de madeira para pinturas, fotografias, espelhos ou objetos similares, de madeira tropical |
| `441520` | Madeira; paletes simples, paletes-caixas e outros estrados para carga; taipais de paletes | Paletes simples, paletes-caixas e estrados para carga, de madeira; taipais de paletes |
| `441600` | Madeira; barris, cubas, balsas, dornas e outras obras de tanoeiro e respectivas partes, de madeira, incluindo as aduelas | Barris, cubas, balsas, dornas e outras obras de tanueiro, de madeira |
| `441811` | Madeira; janelas, portas-janelas e respectivos caixilhos e alizares; de madeira tropical | Janelas, janelas francesas e seus caixilhos, de madeira tropical |
| `441819` | Madeira; janelas, portas-janelas e respectivos caixilhos e alizares; (exceto de madeira tropical) | Outras janelas, janelas francesas e seus caixilhos, não classificados nos códigos anteriores |
| `441821` | Madeira; portas e respectivos caixilhos, alizares e soleiras, de madeira tropical | Portas e seus caixilhos e soleiras, de madeira tropical |
| `441829` | Madeira; portas e respectivos caixilhos, alizares e soleiras, (exceto de madeira tropical) | Outras portas e seus caixilhos e soleiras, não classificados nos códigos anteriores |
| `441830` | Madeira; postes e vigas, exceto os produtos das subposições 4418.81 a 4418.89 | painéis de madeira, para soalhos |
| `441840` | Madeira; formas (cofragens) para trabalhos de concreto (betão) | Armações de madeira, para concreto |
| `441873` | Madeira; painéis montados para revestimento de pisos (pavimentos), de bambu ou com pelo menos a camada superior (camada de uso) de bambu | Painéis montados para revestimento de pisos (pavimentos), de bambu ou com, pelo menos, a camada superior de bambu |
| `441874` | Madeira; painéis montados para revestimento de pisos (pavimentos), exceto de bambu ou com pelo menos a camada superior (camada de uso) de bambu, para pisos em mosaico | Outros painéis montados para revestimento de pisos (pavimentos), para pisos (pavimentos) em mosaico |
| `441875` | Madeira; painéis montados para revestimento de pisos (pavimentos), exceto de bambu ou com pelo menos a camada superior (camada de uso) de bambu, multicamadas | Outros painéis montados para revestimento de pisos (pavimentos), de camadas múltiplas |
| `441879` | Madeira; painéis montados para revestimento de pisos (pavimentos), não especificados nas subposições 4418.73, 4418.74 ou 4418.75 | Outros painéis montados para soalhos |
| `441881` | Madeira; produtos estruturais de madeira engenheirada, madeira laminada colada (glulam) | Madeira laminada com cola (glulam) |
| `441882` | Madeira; produtos estruturais de madeira engenheirada, madeira laminada cruzada (CLT ou X-lam) | Madeira laminada (lamelada) cruzada (CLT ou X-lam) |
| `441883` | Madeira; produtos estruturais de madeira engenheirada, vigas em I | Vigas de madeira I |
| `441889` | Madeira; produtos estruturais de madeira engenheirada, exceto madeira laminada colada (glulam), madeira laminada cruzada (CLT ou X-lam) ou vigas em I | Outros produtos de engenharia estrutural de madeira, não classificados nos códigos anteriores |
| `441892` | Madeira; obras de marcenaria ou de carpintaria para construções não especificadas na posição 4418, painéis celulares | Painéis celulares de madeira |
| `441911` | Artigos de mesa ou de cozinha, de madeira; de bambu, tábuas para pão, tábuas para cortar e tábuas semelhantes | Tábuas para cortar pão, outras tábuas para cortar e artigos semelhantes, de bambu |
| `441912` | Artigos de mesa ou de cozinha, de madeira; de bambu, palitos (pauzinhos) hashis | Pauzinhos (hashi ou fachi), de bambu |
| `441919` | Artigos de mesa ou de cozinha, de madeira; de bambu, não especificados na posição 4419 | Outros artigos de madeira para mesa ou cozinha, de bambu |
| `441920` | Artigos de mesa ou de cozinha, de madeira; de madeira tropical | Artigos de mesa e de cozinha, de madeira tropical |
| `441990` | Artigos de mesa ou de cozinha, de madeira; exceto de bambu ou de madeira tropical | Outros artigos de madeira para mesa ou cozinha |
| `442010` | Madeira; estatuetas e outros objetos de ornamentação, de madeira | Estatuetas e outros objetos, de madeira, para ornamentação |
| `442011` | Madeira; estatuetas e outros objetos de ornamentação, de madeira tropical | Estatuetas e outros ornamentos, de madeira tropical |
| `442090` | Madeira; marchetada e incrustada, estojos para joias, ourivesaria ou cutelaria e obras semelhantes, de madeira, artigos de mobiliário de madeira não classificados no Capítulo 94 | Madeira marchetada e madeira incrustada; cofres e estojos para joalharia, de madeira |
| `442120` | Madeira; caixões (esquifes) | Caixões de madeira |
| `442191` | Madeira; de bambu, obras não especificadas nas posições 4414 a 4420 (exceto cabides para vestuário) | Outras obras em bambu |
| `442199` | Madeira; exceto de bambu, obras não especificadas nas posições 4414 a 4420 (exceto cabides para vestuário) | Outras obras em madeira |
| `080310` | Frutas, comestíveis; bananas-da-terra (plátanos), frescas ou secas | Bananas-da-terra, frescas ou secas |
| `080390` | Frutas, comestíveis; bananas (exceto bananas-da-terra), frescas ou secas | Bananas frescas ou secas, exceto bananas-da-terra |
| `110620` | Farinhas, sêmolas e pós; de sagu ou de raízes ou tubérculos da posição 0714 (inclui mandioca) | Farinhas, sêmolas e pós, de sagu ou de raízes e tubérculos da posição 0714 |
| `110814` | Amidos e féculas; fécula de mandioca | Fécula de mandioca |
| `150710` | Óleos vegetais; óleo de soja em bruto, mesmo degomado | Óleo de soja, em bruto, mesmo degomado |
| `230400` | Tortas e outros resíduos sólidos; da extração do óleo de soja | Tortas e outros resíduos sólidos da extração do óleo de soja |
| `100510` | Cereais; milho, para semeadura | Milho para semeadura |
| `100590` | Cereais; milho, exceto para semeadura | Milho, exceto para semeadura |
| `100610` | Cereais; arroz com casca (arroz paddy) | Arroz (paddy) com casca |
| `100620` | Cereais; arroz descascado (arroz cargo ou castanho) | Arroz (cargo ou castanho), descascado |
| `100640` | Cereais; arroz quebrado (trinca de arroz) | Arroz quebrado (trinca de arroz) |

### procedência distinta (44)

| código | texto usado | texto do MDIC |
|---|---|---|
| `4401` | Lenha em qualquer estado; madeira em estilhas ou em partículas; serragem, desperdícios e resíduos de madeira, mesmo aglomerados em toras, briquetes, pellets ou formas semelhantes | Lenha em qualquer estado, madeira em estilhas ou em partículas; serradura, desperdícios e resíduos de madeira, mesmo aglomerados em bolas, briquetes, pellets ou em formas semelhantes |
| `4404` | Madeira para arcos; estacas fendidas; estacas aguçadas, não serradas longitudinalmente; madeira simplesmente desbastada para bengalas, guarda-chuvas, cabos de ferramentas e semelhantes | Arcos de madeira; estacas fendidas; estacas aguçadas, não serradas longitudinalmente; madeira simplesmente desbastada ou arredondada, não torneada, não recurvada nem trabalhada de qualquer outro modo, para fabricação de bengalas, guarda-chuvas, cabos de f |
| `4410` | Painéis de partículas, painéis denominados oriented strand board (OSB) e painéis semelhantes (por exemplo, waferboard), de madeira ou de outras matérias lenhosas, mesmo aglomerados com resinas ou outros aglutinantes orgânicos | Painéis de partículas e painéis semelhantes (por exemplo, painéis denominados «  oriented strand board » e painéis denominados «  waferboard »), de madeira ou de outras matérias lenhosas, mesmo aglomeradas com resinas ou com outros aglutinantes orgânicos |
| `4411` | Painéis de fibras de madeira ou de outras matérias lenhosas, mesmo aglomerados com resinas ou outras substâncias orgânicas | Painéis de fibras de madeira ou de outras matérias lenhosas, mesmo aglomeradas com resinas ou com outros aglutinantes orgânicos |
| `4412` | Madeira compensada (contraplacada), madeira folheada e madeiras estratificadas semelhantes | Madeira contraplacada ou compensada, madeira folheada, e madeiras estratificadas semelhantes |
| `4415` | Caixotes, caixas, engradados, barricas e embalagens semelhantes, de madeira; carretéis para cabos, de madeira; paletes simples, paletes-caixas e outros estrados para carga, de madeira; taipais de paletes de madeira | Caixotes, caixas, engradados, barricas e embalagens semelhantes, de madeira; carretéis para cabos, de madeira; paletes simples, « paletes-caixas » e outros estrados para carga, de madeira; taipais de paletes de madeira |
| `4417` | Ferramentas, armações e cabos de ferramentas, de escovas e de vassouras, de madeira; formas, alargadeiras e esticadores para calçado, de madeira | Ferramentas, armações e cabos de ferramentas, de escovas e de vassouras, de madeira; formas, alargadeiras e esticadores, de madeira, para calçados |
| `4419` | Artigos de mesa ou de cozinha, de madeira | Artefatos de madeira para mesa ou cozinha |
| `4420` | Madeira marchetada e incrustada; estojos para joias ou ourivesaria e obras semelhantes, de madeira; estatuetas e outros objetos de ornamentação, de madeira; artigos de mobiliário, de madeira, não classificados no Capítulo 94 | Madeira marchetada e madeira incrustada; estojos e guarda-jóias, para joalharia e ourivesaria, e obras semelhantes, de madeira; estatuetas e outros objectos de ornamentação, de madeira; artigos de mobiliário, de madeira, que não se incluam no Capítulo 94 |
| `440149` | Madeira; para combustível, serragem, desperdícios e resíduos, não aglomerados, exceto serragem | Outros resíduos e aparas de serradura e madeira, não aglomerados, não classificados nos códigos anteriores |
| `440220` | Madeira; carvão de cascas ou de caroços, mesmo aglomerado | Carvão vegetal (incluindo carvão vegetal de casca ou castanha), aglomerado ou não, de casca ou castanha |
| `440323` | Madeira; de coníferas, de abeto (Abies spp.) e de espruce (Picea spp.), em bruto, não tratada, cuja menor dimensão da seção transversal seja igual ou superior a 15 cm | Madeira em bruto, mesmo descascada, desalburnada ou esquadriada, de abeto (Abies spp.) e de espruce (Picea spp.), cuja maior dimensão da seção transversal é igual ou superior a 15 cm |
| `440393` | Madeira; de faia (Fagus spp.), em bruto, não tratada, cuja menor dimensão da seção transversal seja igual ou superior a 15 cm | Madeira em bruto, mesmo descascada, desalburnada ou esquadriada, de faia (Fagus spp.), cuja maior dimensão da seção transversal é igual ou superior a 15 cm |
| `440395` | Madeira; de bétula (Betula spp.), em bruto, não tratada, cuja menor dimensão da seção transversal seja igual ou superior a 15 cm | Madeira em bruto, mesmo descascada, desalburnada ou esquadriada, de bétula (vidoeiro) (Betula spp.), cuja maior dimensão da seção transversal é igual ou superior a 15 cm |
| `440611` | Madeira; dormentes para vias férreas ou semelhantes, não impregnados, de coníferas | Dormentes de madeira para vias férreas ou semelhantes, não impregnados, de coníferas |
| `440612` | Madeira; dormentes para vias férreas ou semelhantes, não impregnados, de não coníferas | Dormentes de madeira para vias férreas ou semelhantes, não impregnados, de não coníferas |
| `440722` | Madeira tropical; virola, imbuia e balsa, serrada ou fendida longitudinalmente, mesmo aplainada, lixada ou unida pelas extremidades, de espessura superior a 6 mm | Madeira de virola, imbuia e balsa, serrada ou fendida longitudinalmente, cortada transversalmente ou desenrolada, mesmo aplainada, lixada ou unida pelas extremidades, de espessura superior a 6 mm |
| `440727` | Madeira tropical; sapelli, serrada ou fendida longitudinalmente, mesmo aplainada, lixada ou unida pelas extremidades, de espessura superior a 6 mm | Madeira de Sapelli, serrada ou fendida longitudinalmente, cortada transversalmente ou desenrolada, mesmo aplainada, lixada ou unida pelas extremidades, de espessura superior a 6 mm |
| `440795` | Madeira; de freixo (Fraxinus spp.), serrada ou fendida longitudinalmente, mesmo aplainada, lixada ou unida pelas extremidades, de espessura superior a 6 mm | Madeira de freixo (Fraxinus spp.), serrada ou fendida longitudinalmente, cortada transversalmente ou desenrolada, mesmo aplainada, lixada ou unida pelas extremidades, de espessura superior a 6 mm |
| `440796` | Madeira; de bétula (Betula spp.), serrada ou fendida longitudinalmente, de espessura superior a 6 mm, mesmo aplainada, lixada ou unida pelas extremidades | Madeira serrada ou fendida longitudinalmente, cortada transversalmente ou desenrolada, mesmo aplainada, lixada ou unida pelas extremidades, de espessura superior a 6 mm, de bétula (vidoeiro) (Betula spp.) |
| `440797` | Madeira; de choupo e álamo (Populus spp.), serrada ou fendida longitudinalmente, de espessura superior a 6 mm, mesmo aplainada, lixada ou unida pelas extremidades | Madeira serrada ou fendida longitudinalmente, cortada transversalmente ou desenrolada, mesmo aplainada, lixada ou unida pelas extremidades, de espessura superior a 6 mm, de choupo (álamo) (Populus spp.) |
| `440922` | Madeira; tropical (incluindo tacos e frisos para soalhos, não montados), perfilada ao longo de uma ou mais bordas, faces ou extremidades, mesmo aplainada, lixada ou unida pelas extremidades | Madeiras tropicais perfilada (com espigas, ranhuras, filetes, entalhes, chanfrada, com juntas em V, com cercadura, boleada ou semelhantes) ao longo de uma ou mais bordas, faces ou extremidades, mesmo aplainada, lixada ou unida pelas extremidades |
| `441242` | Madeira laminada folheada (LVL); com pelo menos uma folha externa de madeira de não coníferas | Outras madeiras folheadas laminadas (LVL), com pelo menos uma camada externa de madeira não conífera |
| `441249` | Madeira laminada folheada (LVL); com ambas as folhas externas de madeira de coníferas | Outras madeiras folheadas laminadas (LVL), com ambas as camadas externas de madeira de coníferas |
| `441291` | Madeira compensada; não especificada na posição 4412, com pelo menos uma folha externa de madeira tropical | Outros compensados, painéis folheados e madeira laminada similar, com pelo menos uma folha exterior de madeira tropical, não classificados nos códigos anteriores |
| `441400` | Molduras de madeira para quadros, fotografias, espelhos ou objetos semelhantes | Molduras de madeira, para quadros, fotografias, espelho ou objetos semelhantes |
| `441490` | Molduras de madeira para quadros, fotografias, espelhos ou objetos semelhantes; exceto de madeira tropical | Outras molduras de madeira para quadros, fotografias, espelhos ou objetos similares, não classificados nos códigos anteriores |
| `441510` | Madeira; caixotes, caixas, engradados, barricas, embalagens semelhantes e carretéis para cabos | Caixotes, caixas, engradados, barricas e embalagens semelhantes, de madeira; carretéis para cabos, de madeira |
| `441700` | Madeira; ferramentas, armações e cabos de ferramentas, de escovas e de vassouras, formas, alargadeiras e esticadores para calçado, de madeira | Ferramentas, armações e cabos de ferramentas, de escovas e de vassouras, de madeira; formas, alargadeiras e esticadores, de madeira, para calçados |
| `441810` | Madeira; janelas, portas-janelas e respectivos caixilhos e alizares | Janelas, janelas de sacada e respectivos caixilhos e alizares, de madeira |
| `441820` | Madeira; portas e respectivos caixilhos, alizares e soleiras | Portas e respectivos caixilhos, alizares e soleiras, de madeira |
| `441850` | Madeira; fasquias para telhados (shingles e shakes) | Fasquias de madeira, para telhados (shingles e shakes) |
| `441860` | Madeira; postes e vigas | Postes e vigas de madeira |
| `441891` | Madeira; obras de marcenaria ou de carpintaria para construções não especificadas na posição 4418, de bambu | Outras obras de marcenaria e peças de carpintaria para construções, incluindo os painéis celulares, os painéis montados para revestimento de pisos (pavimentos) e as fasquias para telhados (shingles e shakes), de bambu |
| `441899` | Madeira; obras de marcenaria ou de carpintaria para construções não especificadas na posição 4418, exceto de bambu ou painéis celulares | Outras obras de marcenaria e peças de carpintaria para construções, incluindo os painéis celulares, os painéis montados para revestimento de pisos (pavimentos) e as fasquias para telhados (shingles e shakes) |
| `441900` | Artigos de mesa ou de cozinha, de madeira. | Artefatos de madeira, para mesa ou cozinha |
| `442019` | Madeira; estatuetas e outros objetos de ornamentação, exceto de madeira tropical | Outras estatuetas e outros ornamentos, de madeira tropical, não classificados nos códigos anteriores |
| `442110` | Madeira; cabides para vestuário | Cabides de madeira, para vestuário |
| `071410` | Raízes e tubérculos; raízes de mandioca, frescas, refrigeradas, congeladas ou secas | Raízes de mandioca cassava, frescas ou secas, mesmo cortadas em pedaços ou em pellets |
| `190300` | Tapioca e seus sucedâneos preparados a partir de féculas, em flocos, grumos, grãos ou formas semelhantes | Tapioca e seus sucedâneos preparados a partir de féculas, em flocos, grumos, grãos, pérolas ou formas semelhantes |
| `120110` | Soja; para semeadura, mesmo triturada | Soja, mesmo triturada, para semeadura |
| `120190` | Soja; exceto para semeadura, mesmo triturada | Soja, mesmo triturada, exceto para semeadura |
| `150790` | Óleos vegetais; óleo de soja e suas frações, exceto em bruto | Óleo de soja e respectivas frações, mesmo refinados, mas não quimicamente modificados |
| `100630` | Cereais; arroz semibranqueado ou branqueado, mesmo polido ou brunido | Arroz semibranqueado ou branqueado, mesmo polido ou brunido (glaceado) |

### ausente no MDIC (14)

| código | texto usado | texto do MDIC |
|---|---|---|
| `080110` | Cocos, frescos ou secos | — |
| `080120` | Castanha-do-pará, fresca ou seca | — |
| `080130` | Castanha de caju, fresca ou seca | — |
| `440331` | Toras de Meranti (vermelho claro ou escuro) e Bakau | — |
| `440332` | Toras de Lauan branco, Meranti branco, Seraya, Meranti amarelo e Alan | — |
| `440333` | Toras de Keruing, Ramin, Kapur, Teca, Jongkong, Merbau e semelhantes | — |
| `440334` | Toras de Okoumé, Obeche, Sapelli, Sipo, Acaju da África e semelhantes | — |
| `440335` | Toras de Tiama, Mansonia, Ilomba, Dibetou, Limba e Azobé | — |
| `440714` | Madeira; de coníferas, de Hem-fir (tsuga ocidental (Tsuga heterophylla) e abeto (Abies spp.)) | — |
| `440820` | Folhas para folheados ou compensados, de madeiras tropicais, de espessura não superior a 6 mm | — |
| `441010` | Painéis de partículas de madeira | — |
| `441211` | Madeira compensada com 1 ou 2 folhas externas de madeira tropical (folhas de espessura não superior a 6 mm) | — |
| `441212` | Madeira compensada com 1 ou 2 folhas externas de não coníferas não especificadas (folhas de espessura não superior a 6 mm) | — |
| `441221` | Painéis com 1 folha externa de não coníferas e 1 folha de painel de partículas | — |

