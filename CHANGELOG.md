# Changelog

Mudanças do quant-energia-app, no formato [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/): uma entrada
por versão (o app não tem número de versão; a entrada é identificada pela data), com as seções Adicionado, Alterado,
Corrigido e Removido.

Toda entrada que vem de uma pesquisa cita a tag de origem (`promocao-quant-vN` no repositório de pesquisa) e as
decisões (Dxxx) registradas lá. Atualizar a cada promoção. Entradas anteriores a 2026-10-19 foram reconstruídas do
histórico do git.

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
