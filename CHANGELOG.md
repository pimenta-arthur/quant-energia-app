# Changelog

Mudanças do quant-energia-app, no formato [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/): uma entrada
por versão (o app não tem número de versão; a entrada é identificada pela data), com as seções Adicionado, Alterado,
Corrigido e Removido.

Toda entrada que vem de uma pesquisa cita a tag de origem (`promocao-quant-vN` no repositório de pesquisa) e as
decisões (Dxxx) registradas lá. Atualizar a cada promoção. Entradas anteriores a 2026-10-19 foram reconstruídas do
histórico do git.

## [2026-10-25] Pricing Descolamento: leva promocao-quant-v6 (metodologia de compra e venda como tab principal)

Origem: `pricing-descolamento-analytics`, tag `promocao-quant-v6` (seção 11, "v5 → v6"; D056 e D057). **Sem mudança de método, de
modelo, de preço, de faixa nem de rodadas** (modelo v2.2): a metodologia de compra e venda foi reescrita para ser autossuficiente
(trader e comitê) e passou a ser a tab principal. Conferido contra `reports/promocao/2026-10/`: `R13_cv_exemplo` (formato novo, regerada),
`R14_cv_backtest`, `R15_cv_historico` e `R16_cv_cotacoes_se270` sem diferença; o `publicar` não registrou rodada.

### Alterado
- `compra_venda_metodologia.html`: processo do SE à cotação, instrumento, três políticas (Antes = v1 com λ 0,50; λ = 1 sem âncora;
  Conservador), venda modelo × histórico, resultado do backtest das três políticas (NE e N, trimestres e semestres, calculado no navegador
  a partir de `cv_backtest`), "Previsto e realizado, caso a caso" com gráficos, limites do backtest, decisões D041 a D057 e glossário.
- **Menu e tabs:** o item "Metodologia" das páginas abre a metodologia de compra e venda; as tabs ficam "Compra e venda" (padrão) e "Descolamento".
- `cv_exemplo` (`qe_pricing_descolamento.compra_venda.exemplo`): novo formato (SE de R$ 270, valores por ano climático e histórico mês a mês do
  exemplo T1 do ano seguinte, em vez das cotações prontas); recebe o `cv_historico` do mesmo deck.

## [2026-10-25] Pricing Descolamento: leva promocao-quant-v5 (Compra e venda NE e N)

Origem: `pricing-descolamento-analytics`, tag `promocao-quant-v5` (seção 11, "v4 → v5"; D041 a D055). **Sem mudança de método,
de modelo, de preço, de faixa nem de rodadas** (modelo v2.2): página nova e a metodologia dela, com o menu e as tabs da
metodologia. Conferido contra `reports/promocao/2026-10/`: `R13_cv_exemplo`, `R14_cv_backtest` (59 casos) e `R15_cv_historico` sem
diferença; `R16_cv_cotacoes_se270` (162 produtos, produto sozinho e contribuição para o ano, NE e N) dentro de R$ 0,001, no Python e na
página (lida no navegador); painel do passado da política Conservador igual ao do pacote.

### Adicionado
- Página "Compra e venda NE e N" (`web/pricing_descolamento/compra_venda.html` e `compra_venda.js`): curva do SE, cotação por produto
  (compra / venda por ano, semestre, trimestre e mês, com o toggle "Fechar o ano" e o descritivo por clique), resumo por produto (NE e N, descolamento e
  PLD implícito), gráfico do descolamento por mês, fundamentos do deck, descolamento realizado (com o ano de referência da venda ancorada), painel do
  passado e próximos passos. A seção de swap fica oculta (código preservado).
- Metodologia de compra e venda (`compra_venda_metodologia.html`) e **tabs** na Metodologia ("Descolamento", o padrão, e "Compra e venda").
- `compra_venda_conta.js` (cotação: quantil, cauda, venda ancorada, swap) e `qe_pricing_descolamento.compra_venda` (porta de `curvas.precificar`,
  `cv_backtest`, `cv_historico`, `cv_exemplo` e a cotação de um produto, referência em Python da lógica da página), com teste de paridade com node.
- Chaves publicadas `cv_backtest`, `cv_historico` e `cv_exemplo` (`serving/pricing_descolamento/`).

### Alterado
- Menu das páginas do Pricing Descolamento: "Compra e venda NE e N" primeiro. A página inicial do app aponta para a compra e venda.
- `publicar` grava as três chaves novas (mesmo deck e modelo: não registra rodada).

## [2026-10-24] Hydro Inflow Similarity: promoção (promocao-quant-v1)

Origem: `hydro-inflow-similarity-analytics`, tag `promocao-quant-v1` (pacote `docs/promocao_hydro_inflow_similarity.md`;
decisões D005, D013, D016, D018–D026). Conferido contra `reports/promocao/2026-09/` sem diferença: leitores (R1),
tabelas-base (R3), modelo-v1 com membros e ponto da PER (R4), rodada sem a sombra (R5), atualização com 23 dias de
out/2026 (R6), similares e desempenho (R7), camada de El Niño forte (R8) e os quatro JSON das páginas (R9). O backtest
difere da pesquisa só no mês-alvo set/2026 do N e do SE, revisado pelo ONS em 24/10/2026, depois dos backtests de lá.

### Adicionado
- Funcionalidade `hydro_inflow_similarity` (`features/hydro_inflow_similarity/`, `web/hydro_inflow_similarity/`):
  ingestão de cinco fontes novas, tratamento (ENA mensal com o Paraná incremental, MLT, índices da ERSST v6 e oficiais),
  modelo-v1, atualização com o mês em curso, anos similares, backtest (CH, C30, PER, SPLIT, SIM), camada de El Niño
  forte, rodadas mensais com a versão de cada arquivo bruto e as quatro páginas.
- Leitores no `qe_core`: `leitores.ons.ler_planilha_ena`, `ler_ena_diaria`, `nome_bacia`; novo `leitores.noaa` (ONI,
  RONI, SOI, AAO, PDO, AMO e previsão do ENSO do CPC).
- Decisões da promoção (Arthur, 24/10/2026): backtests de PER, C30 e SIM reimplementados e fatos dos notebooks como dado
  estático; modelos-sombra só na pesquisa; ERSST só a publicação mais recente em `raw/`; atualização diária sem registro.

## [2026-10-22] Pricing Descolamento: leva promocao-quant-v4 (degrau do histórico de rodadas)

Origem: `pricing-descolamento-analytics`, tag `promocao-quant-v4` (seção 11, "v3 → v4"; D040). Texto e um dado pequeno,
numa etapa só. **Sem mudança de método, de modelo, de preço, de faixa nem de rodadas** (modelo v2.2). Conferido contra
`reports/promocao/2026-10/`: `R12_hist_marcos` e a chave `hist_marcos` do `R8_metodologia`, sem diferença (um marco:
2025-04, 1º semestre, 8 → 467 horas, mínimo 20, dados até 2025-02).

### Adicionado
- Dado `hist_marcos` (`serving/pricing_descolamento/hist_marcos.json`): decks do histórico de rodadas em que o modelo da
  chance de travar do NE de um regime (1S ou 2S) deixa de ser vazio, isto é, passa a ter pelo menos 20 horas de cada
  classe no treino. Calculado em Python sobre o registro de rodadas e o treino do app (`publicacao.marcos_historico`).
- Metodologia, histórico de rodadas: nota explicando o degrau de abr/25 (o salto de mar/25 para abr/25, NE 2027
  de −7,2 para −19,3, não é erro nem mudança de deck: o 1º semestre passou a ser treinado, e a regra do mínimo cria
  um degrau sempre que um regime ganha dado pela primeira vez); ◆ no gráfico, ao lado de uma linha pontilhada no deck
  do marco, e na linha da tabela.

### Alterado
- Metodologia: as duas tabelas do histórico (as 3 últimas e "Rodadas anteriores") passam a ter largura de coluna fixa
  e alinham coluna a coluna.

### Verificação de que nada mudou
`publicar` respondeu "mesmo deck e modelo da última"; o registro de rodadas ficou idêntico e a única chave nova do
`serving` é `hist_marcos.json`. Suíte do app e paridade com a pesquisa passando.

## [2026-10-21] Pricing Descolamento: leva promocao-quant-v3, etapa C (acompanhamento da hidráulica do NE)

Origem: `pricing-descolamento-analytics`, tag `promocao-quant-v3` (seção 11, "v2 → v3", etapa C; D039, item 26 da fila).
**O modelo não muda (v2.2):** preço justo, faixa e rodadas ficam iguais. Conferido contra `reports/promocao/2026-10/`:
`R8_dados` (com o campo novo), `R11_hidr_ne` e as duas colunas novas do `R7_cenarios`, todos sem diferença.

### Adicionado
- Acompanhamento do nível da hidráulica do NE: o nível que o modelo usou (média do perfil do ano mais recente, igual em
  todos os cenários) contra o realizado, por mês-alvo, com o deck do mês anterior; só meses com 60% das horas do
  DESSEM. Gatilho para repetir os testes de hidráulica (itens 24 e 25): erro médio absoluto acima de 30% por 6 meses
  seguidos, fixado antes de ver a série. Hoje: 21 meses, erro 18,6% (viés −4,4%); últimos 6 meses 23,8% (viés −23,8%,
  6 de 6 no mesmo sentido); o gatilho não dispara.
- Chave `hidr_ne.json` no `publicar`; seção "Acompanhamento do nível da hidráulica do NE" e bullet "Hidráulica do NE" em
  Limitações na metodologia.
- Coluna "Hidr. NE" na tabela de fundamentos do deck (sem gráfico: os 9 gráficos não mudam). Campo `hidr_NE` (GW) em
  `fund`, `real` e `historico` dos dados da página.
- `modelo.cenarios` informa `hidraulica_NE` (MW) e `ano_hidr_ne` (só informativo; não entra em nenhuma conta).
- Testes: referência `hidr_ne` (meses fechados, até set/2026) e as colunas novas em `modelo_cenarios`; teste de que o
  nível usado só depende de horas até D−2.

### Verificação de que o modelo não mudou
As colunas antigas de `modelo_cenarios` saem **idênticas bit a bit** (`check_exact`) entre o código antigo e o novo, na
mesma máquina; as demais chaves publicadas mudam só pelo campo `hidr_NE`; o registro de rodadas ficou inalterado
(`publicar` respondeu "mesmo deck e modelo da última"); e o teste com SE plano de R$ 200 continua passando sem alteração.

## [2026-10-21] Pricing Descolamento: leva promocao-quant-v3, etapa B (só texto da metodologia)

Origem: `pricing-descolamento-analytics`, tag `promocao-quant-v3` (seção 11, "v2 → v3"; conteúdo = commit `8b6cfb7`),
itens 24 e 25 da fila (D037 e D038). **Sem mudança de método, de código nem de referências** (modelo v2.2; preço justo,
faixa e rodadas iguais). Aplicado como remendo sobre a página do app. A etapa C (acompanhamento do nível da hidráulica
do NE: código, dados e a seção correspondente da metodologia) entrou na entrada seguinte (etapa C).

### Alterado
- Metodologia, passo 5: a nota sobre a hidráulica do NE passa de "Questão em aberto" para "Testado, não adotado". Somá-la
  à margem melhora o ajuste no histórico (AUC do NE no 2º semestre de 0,90 para 0,93), mas piora a previsão (erro
  médio do NE nos trimestres de 2026 de 10,4 para 10,7; 15,7 nas duas medidas); usar a hidráulica do próprio ano
  climático também piorou (14,6). A definição fica como está.
- Metodologia, tabela "O que foi testado depois da v2.2 e não entrou": linha nova "Hidráulica do NE".

## [2026-10-21] Pricing Descolamento: leva promocao-quant-v2 (só texto da metodologia)

Origem: `pricing-descolamento-analytics`, tag `promocao-quant-v2` (seção 11, "v1 → v2"). **Só texto: sem mudança de
método, de código nem de referências** (R1 a R10 não mudam). A página difere da v2 da pesquisa só nas adaptações do
app (título, navegação e leitura dos dados do `serving`). Não portado: o pré-registro do item 24 (D037) em
`docs/metodologia.md` da pesquisa, que não foi executado.

### Alterado
- Metodologia: novo passo 5, "O balanço físico: de onde vêm as duas medidas" (equações das features 1 e 2, origem de
  cada termo no treino e na projeção, e a questão em aberto sobre a hidráulica do NE). Os antigos passos 5 a 8 viram 6
  a 9, e o exemplo do T1/27 passa ao passo 8.
- O passo 3 aponta para o passo 5 em vez de repetir as definições; o passo 6 (cenários) ganha a referência.
- Glossário: "Feature 1 (sobra N+NE)" e "Feature 2 (margem de exportação)"; ajuste de "Folga até o limite".

## [2026-10-19] Pricing Descolamento: metodologia e fundamentos (blocos 5 e 6)

Origem: `pricing-descolamento-analytics`, tag `promocao-quant-v1` (seção 5, blocos 5 e 6; D025, D031–D035).
Conferido contra `reports/promocao/2026-10/`: `R8_metodologia` (desempenho) e `R8_fundamentos` iguais. Com isso a
promoção do descolamento está completa (R1 a R10 sem diferença).

### Adicionado
- Página de metodologia (`metodologia.html`): passo a passo, desempenho do backtest por trimestre e semestre,
  comparação com assumir zero, repetir o ano anterior e a climatologia estatística, casos, histórico de rodadas,
  versões e glossário; dados de `qe_pricing_descolamento.desempenho`.
- Página de fundamentos (`fundamentos.html`): série mensal, mapa mês × hora, gargalos por semestre, poder explicativo
  (AUC), curvas de resposta e k × sobra N+NE; dados de `qe_pricing_descolamento.fundamentos`.

## [2026-10-19] Pricing Descolamento: página principal e rodadas (blocos 3 e 4)

Origem: `pricing-descolamento-analytics`, tag `promocao-quant-v1` (seção 5, blocos 3 e 4; seção 7). Conferido contra
`reports/promocao/2026-10/`: dados da página (R8_dados: meta, sazonalidade do SE, histórico mensal e os 50 meses com
coeficientes, fundamentos e realizado) iguais; resumo das rodadas igual ao R10 (decks de jan/2025, jun/2025, jan/2026
e out/2026).

### Adicionado
- Página `web/pricing_descolamento/` (Descolamento NE e N): curva do SE do ano ao mês, descolamento por produto com
  preço justo e faixa, gráfico mensal, choque no SE, descolamento realizado e fundamentos do deck.
- `qe pricing_descolamento publicar`: chaves em `serving/pricing_descolamento/` e registro das rodadas
  (`historico_rodadas.json`); o histórico da pesquisa (R10) entra como legado, como está.
- Conta da curva no navegador (`descolamento_conta.js`) e em Python (`conta.py`), com teste de paridade e teste de
  que, com o SE plano de R$ 200, reproduz as faixas do modelo.

### Alterado
- Contas que a página da pesquisa fazia no navegador e não dependem do usuário (histórico realizado por período com a
  comparação entre anos; fundamentos por produto) passam para o Python; conferidas contra as funções originais da
  pesquisa (109 células e 81 produtos, sem diferença).

## [2026-10-19] Pricing Descolamento: backtest da página (bloco 5, dados)

Origem: `pricing-descolamento-analytics`, tag `promocao-quant-v1` (seção 5, bloco 5; D025). Conferido contra o R9 de
`reports/promocao/2026-10/`: 955 linhas (16 decks, meses-alvo jan/2025–set/2026) com diferença zero.

### Adicionado
- `qe pricing_descolamento backtest`: modelo vigente nos decks de jan, mar, mai, jul, set e nov de 2024 a jul/2026,
  com o SE realizado como insumo, por cenário climático e com as variáveis do mês (deck, modelo, realizado).

## [2026-10-19] Pricing Descolamento: bloco 2 (modelo v2.2)

Origem: `pricing-descolamento-analytics`, tag `promocao-quant-v1` (seção 5, bloco 2; D015, D022, D025). Conferido
contra `reports/promocao/2026-10/`: R6 (modelo treinado no deck de out/2026) e R7 (282 cenários com SE = R$ 200,
coeficientes, insumos, faixas e o exemplo do T1/2027: NE −28,09, faixa −45,07 a −18,69) com diferença zero.

### Adicionado
- `qe_pricing_descolamento.modelo`: `MODELO` = v2.2 com os parâmetros nomeados (início do treino 2024-01-01, C = 1,0,
  mínimos de 20/50 horas, folga mínima de R$ 50 para o k pareado, viés da carga em 12 meses, 20 dias por cenário);
  treino na data do deck, cenários, previsão com coeficientes por hora e agregação em preço justo e faixa.
- Dependência `scikit-learn` (1.9.1, a mesma da pesquisa) no pacote do descolamento.

## [2026-10-19] Pricing Descolamento: bloco 1 (tabelas-base) e ingestão comum das fontes

Origem: `pricing-descolamento-analytics`, tag `promocao-quant-v1` (pacote `docs/promocao_descolamento.md`, seções 2 a
4 e 10). Conferido contra `reports/promocao/2026-10/`, com os mesmos dados brutos (hashes do manifesto): R1 a R5
iguais (leitores nos três formatos do PDO_RESTOPER e nos decks de jan/2024 e out/2026; PLD; 70 decks; base horária de
49.704 horas).

### Adicionado
- Funcionalidade `pricing_descolamento` (`qe pricing_descolamento ingerir | tratar | status | congelar`): T1 PLD
  publicado horário e mensal, T2 projeções dos decks do NEWAVE, T3 balanço horário e T4 restrições de intercâmbio do
  DESSEM (particionados por mês), T5 base horária.
- Leitores no `qe_core`: `dessem.ler_re_inte` (PDO_RESTOPER), `newave.ler_sistema` e `newave.ler_agrint`.
- Recarga do histórico: SISTEMA.DAT e AGRINT.DAT dos 70 decks (jan/2021–out/2026) e PDO_RESTOPER.DAT de 2.081 dias.

### Alterado
- Ingestão comum das fontes usadas por mais de uma funcionalidade (`qe_core.fontes`: NEWAVE, DESSEM, PLD e limites),
  porque a caixa de entrada apaga o original depois de gravar. O deck do NEWAVE ganha o conjunto `sistema_agrint`,
  ao lado do das bandeiras (que não muda); o dia do DESSEM ganha o PDO_RESTOPER.DAT, guardado inteiro em .gz.

## [2026-10-19] Risk Lab DESSEM: simulador, leva promocao-quant-v3 (modelo v2)

Origem: `risk-lab-dessem-analytics`, tag `promocao-quant-v3` (seção 11, "v2 → v3"). Conferido contra
`reports/promocao/2026-10-15_v3/` com os mesmos dados brutos da v2 (decks até 15/10/2026, PLD publicado até
10/10/2026): R9, R10 e R11 dentro de R$ 0,01; R1 a R8 iguais. Não trazidas: D085, D086 e D088 (calibração, só
pesquisa).

### Alterado
- Desconto das outras horas num número só para os três tipos de dia: média dos 12 meses encerrados com espaço
  ≥ R$ 20 do desconto medido em todas as horas fora da ponta e do piso (D087). **Muda o resultado do simulador e o
  backtest** (até R$ 8,26 por mês; exemplo de out/2026 com DECOMP 88,31: 102,77 → 102,93; erro médio M+1 desde
  mar/2025: 14,5 → 13,7). Por isso o modelo do simulador passa a `v2` (`MODELO.desconto_unico`); a metodologia do
  v1 fica em `metodologia-v1.html`. Os valores por tipo de dia continuam visíveis, só para leitura (`ref_fora_tipo`).
- Layout do bloco de simulação (D090, D092–D094): linha de entrada (mês, DECOMP com "vigente", janela e
  "↺ Premissas padrão"); tabela única com premissa × tipo de dia, "No mês", "Peso" e a linha "Desvio do mês";
  desconto das outras horas num campo só; sensibilidade presa à tabela; rodapé curto com o texto completo na dica;
  resumo à direita com altura mínima de 481 px (antes da tabela abaixo de 1100 px).
- Histórico do desconto das outras horas numa curva só, com a média de 12 meses única.

### Adicionado
- Resumo para a mesa (D091): PLD previsto e direção; histórico da direção ("pouco histórico" abaixo de 5 previsões
  desde mar/2025); faixa 10–90%; de onde vem o desvio; estresse de ponta; quando muda (RV0 e erro médio); alertas
  de DECOMP no piso (comparado com `piso_hist`, meses no piso desde 2021), de ponta afastada da média de 12 meses e
  de premissas editadas. Conta em `simulador_conta.js` e `simulador.resumo_mesa`, com teste de paridade.
- Dias do mês com tabela e CSV (D095): tipo de cada dia em `calendario[].dias`; a média dos dias é o PLD previsto e a
  da coluna de estresse, o PLD com a sensibilidade. Conta em `simulador_conta.js` e `simulador.dias_mes`.
- Sinalização da janela com DECOMP no piso (D089): no histórico, trecho esmaecido quando o espaço médio é < R$ 20 ou
  ≥ 25% dos dias estão no piso (`premissas_hist`, coluna `frac_dias_piso`); dias da janela no piso vazados; no
  campo do desconto, o desvio em R$/h quando a janela está no piso (`desvio_fora`, `espaco_fora`).
- Rodada do simulador de 2026-10-19 (modelo v2) no registro `historico_simulador.json`.

### Corrigido
- "↺ Premissas padrão" volta também a janela de 14 dias (antes ficava na janela escolhida e parecia não fazer nada).
- Dicas não são mais cortadas: quebram linha e trocam de lado perto da borda da tela.

## [2026-10-16] Risk Lab DESSEM: leva promocao-quant-v2

Origem: `risk-lab-dessem-analytics`, tag `promocao-quant-v2`; conferido contra `reports/promocao/2026-10-15/`.

### Adicionado
- Séries do SIN nas variáveis em MW (soma dos quatro submercados hora a hora, só nas horas com os quatro) (D084).
- `data/serving/` versionado no git, para o app abrir com dados em qualquer máquina.

### Alterado
- Filtro de submercado por bloco, no lugar do filtro global (D084).
- Título do bloco 1: "PLD médio do dia: DESSEM e DECOMP".

## [2026-10-14] Risk Lab DESSEM: promoção inicial (promocao-quant-v1)

Origem: `risk-lab-dessem-analytics`, tag `promocao-quant-v1`; conferido contra `reports/promocao/2026-10-13/`.

### Adicionado
- Funcionalidade `risk_lab_dessem`: ingestão (DESSEM, DECOMP, PLD), tratamento incremental e página de
  acompanhamento (blocos 1 a 6).
- Simulador do PLD médio do mês, v1 simplificada (bloco 7; D057, D061), com backtest, registro de rodadas e teste de
  paridade Python × JS; modelo `v1`.

## [2026-10-09] Forecast Bandeiras: primeira versão

### Adicionado
- Ingestão, tratamento, projeção, backtest, publicação e página das bandeiras; modelo versionado (`v1`) com
  referências congeladas; rodadas por atualização de insumo.
