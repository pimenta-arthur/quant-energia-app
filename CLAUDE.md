# quant-energia-app

Aplicação com funcionalidades independentes, cada uma com a sua página e o seu pipeline:
**Forecast Bandeiras** (código `forecast_bandeiras`), **Risk Lab DESSEM** (PLD horário; código `risk_lab_dessem`) e
**Pricing Descolamento** (descolamento do NE e do N em relação ao SE; código `pricing_descolamento`). Pastas, pacotes (`qe_<código>`), comandos (`qe <código> …`), páginas
(`web/<código>/`) e chaves (`processed/<código>/`, `serving/<código>/`) usam o código; `raw/` é por fonte.
Roda local primeiro e vai para a AWS depois, sem mudar o código das etapas. Responder sempre em português do Brasil.

## Pesquisa × produto
- A pesquisa (EDA, notebooks, backtest, decisões de método) fica nos repositórios de análise, como
  `../forecast-bandeiras` (GitHub `forecast-bandeiras-analytics`). Aqui entra só código validado lá.
- **Não mudar o método ao portar.** A migração foi validada contra o analytics; hoje os testes usam
  referências congeladas do próprio app (`tests/referencias/`). O app não depende do analytics para rodar.
- **Nenhuma dependência de execução de outro repositório:** os dados entram só pela caixa de entrada
  `data/entrada/<fonte>/` (formato em `docs/entrada.md`); nada de ler pastas do analytics.
- Decisões de método continuam registradas em `docs/metodologia.md` do analytics.
- **Changelog:** `CHANGELOG.md` (Keep a Changelog). Cada promoção ganha uma entrada com data, a tag de origem
  (`promocao-quant-vN`) e as decisões (Dxxx); levas seguintes leem só a seção 11 do pacote de promoção.
- Nova funcionalidade: seguir `docs/nova_funcionalidade.md`. Pesquisa do PLD horário em
  `../risk-lab-dessem-analytics` — repositório independente (não depende deste app, e este app não depende
  dele): ao promover, o método é reimplementado aqui e conferido contra os resultados de referência de lá.

## Ambiente
- uv workspace (raiz + `core`, `features/forecast_bandeiras`, `features/risk_lab_dessem`,
  `features/pricing_descolamento`, `api`). Sempre
  `uv add --package <membro> <pacote>` e `uv run ...`. **Nunca pip.** Python 3.14 do Homebrew.
- Lint/format: `uv run ruff check .` e `uv run ruff format .`; testes: `uv run pytest`.

## Arquitetura
- Etapas por funcionalidade: ingestão → tratamento → projeção → publicação, cada uma um comando
  `qe <funcionalidade> <etapa>` (local) e um worker (AWS).
- **Todo acesso a dados passa por `qe_core.armazenamento`** (chaves `raw/…`, `processed/…`,
  `serving/…`). Nunca abrir caminhos de `data/` diretamente nas etapas: isso quebra a ida para o S3.
- `raw/` é por fonte e imutável (a ingestão não sobrescreve sem `--sobrescrever`); `processed/` e
  `serving/` são por funcionalidade. Fonte usada por mais de uma funcionalidade tem uma ingestão só, em
  `qe_core.fontes`, que grava o que todas usam (a caixa de entrada apaga o original depois de gravar).
- Leitores (`qe_core.leitores`) são funções puras sobre o caminho do arquivo.
- Configuração só por variáveis `QE_*` (ou `.env`).
- `data/` não vai para o git, exceto `data/serving/` (o que as páginas leem, inclusive os registros das rodadas):
  versionado para o app abrir com dados em qualquer máquina, até a fase AWS. Commitar `data/serving/` depois de
  cada `publicar`. `raw/` e `processed/` ficam fora (pesados e binários; o histórico do git cresceria sem limite).
- **Padrão visual em `web/padrao/`** (`base.css`, `painel.css`, `graficos.js`, `modelo.html`, regras em `GUIA.md`):
  todas as páginas importam dali; nada de uma página importar o CSS de outra funcionalidade. Mudança que vale
  para todas as páginas vai para o padrão (e sobe a versão no topo dos arquivos se mudar regra); o resto fica
  na página. Antes de mexer no padrão, comparar prints de todas as páginas (claro e escuro) antes e depois.
- **Pendência da fase AWS:** até lá, `data/raw/` existe só na máquina local (sem backup, por escolha do
  Arthur: arquivos pesados). Na AWS, o bucket com versionamento passa a ser a cópia de segurança.

## Forecast Bandeiras: etapas e testes
- Dia a dia: arquivo baixado em `data/entrada/<fonte>/` → `qe forecast_bandeiras atualizar` (ingere, trata os meses
  afetados, refaz o backtest, mostra status e prévia; não publica) → `qe forecast_bandeiras publicar --motivo …`.
- Etapas avulsas: `qe forecast_bandeiras ingerir | tratar | backtest | status | projetar | publicar | pagina | congelar`.
- A ingestão grava em `raw/` só o que o modelo usa, confere o hash e apaga o original da entrada (sem
  segunda cópia). O que não for reconhecido fica na entrada, com o motivo.
- Rodadas não são mensais: cada publicação é uma rodada (id = data e hora) com os insumos vigentes
  (último deck com boletim do mês, versão mais recente; emissão mais recente do ECMWF). Deck e ECMWF
  são versionados em raw/ (deck=AAAA-MM/v=<hash>, emissao=AAAA-MM-DD). O backtest segue mensal (D031).
- Modelo versionado em `qe_forecast_bandeiras.modelo.MODELO` (hoje `v1`). Mudar parâmetro ou lógica do método
  = versão nova: decisão no analytics, `qe forecast_bandeiras congelar`, tag `modelo-<versão>` no git.
- Testes: `tests/referencias/forecast_bandeiras/<versão>/` (modelo; só decks e meses-alvo até `referencias.ATE`,
  para dados novos não quebrarem o teste) e `…/tratamento/` (dados tratados), regerados
  com `qe forecast_bandeiras congelar`.
- Nunca regenerar referências para "fazer o teste passar" sem entender a diferença.
- Checklist ao criar uma versão nova do modelo (ex.: v2):
  1. decisão registrada no analytics; nova instância de `Modelo` e `MODELO` apontando para ela;
  2. `qe forecast_bandeiras congelar`, revisar a diferença e commitar; tag `modelo-<versão>`;
  3. guardar a metodologia anterior como `web/forecast_bandeiras/metodologia-<versão anterior>.html`, com aviso
     "versão anterior; em uso de … a …", e atualizar `metodologia.html` e o rótulo do topo para a versão nova;
  4. nessa hora, criar: seletor de versões na Metodologia, link de cada rodada para a metodologia da sua
     versão, quadro de parâmetros gerado de `MODELO` e teste que exige a página de cada versão.
- `serving/forecast_bandeiras/historico_projecoes.json` é o registro das rodadas publicadas: não apagar.
  Versionado no git com o resto de `serving/`.

## Risk Lab DESSEM (PLD horário): etapas e testes
- Promovido de `../risk-lab-dessem-analytics` em 2026-10-14 pelo pacote `docs/promocao_pld_horario.md` de lá,
  bloco a bloco (seção 6 do pacote). Escopo: só a página v1 e o simulador v1 simplificado; **não trazer** carga
  líquida, página v2 nem as outras versões do simulador, nem como contexto.
- Dia a dia: deck do DESSEM (diário), DECOMP (semanal) e csv do PLD em `data/entrada/<fonte>/` →
  `qe risk_lab_dessem atualizar` (ingere, trata o que mudou, mostra status) → `qe risk_lab_dessem publicar`.
- Etapas avulsas: `qe risk_lab_dessem ingerir | tratar [--refazer] | status | conferir | publicar | congelar`.
- DESSEM e DECOMP ficam em `raw/` como `.gz` (exceção decidida pelo Arthur; motivo em `docs/entrada.md`).
- Tratamento incremental: as tabelas do DESSEM são particionadas por mês (`processed/risk_lab_dessem/dessem/…/mes=`)
  e só refeitas quando os dias completos do mês mudam; DECOMP e T1–T5 são refeitos inteiros (segundos).
- Acompanhamento (blocos 1–6) é descritivo: `publicar` regrava `serving/risk_lab_dessem/<chave>.json` sem registro de
  rodada. O simulador (bloco 7) registra uma rodada a cada `publicar` com insumo novo (deck do DESSEM, PLD publicado,
  DECOMP ou modelo); insumos iguais não geram rodada (`--forcar --motivo` para forçar).
- `serving/risk_lab_dessem/historico_simulador.json` é o registro das rodadas do simulador: não apagar nem recalcular;
  versionado no git com o resto de `serving/`.
- A conta do simulador roda no navegador (`web/risk_lab_dessem/simulador_conta.js`) e no Python
  (`qe_risk_lab_dessem.simulador`): mudar uma exige mudar a outra; o teste de paridade compara as duas (precisa de node).
- Rótulos obrigatórios do simulador: janela de 14 dias escolhida dentro da amostra (D057); backtest condicional ao
  DECOMP (entra o realizado); premissas fora da amostra.
- Definições e parâmetros do método (vale, ponta, tolerância do piso, janela, 12 meses, limiar de direção…) só em
  `qe_risk_lab_dessem.modelo.MODELO` (hoje `v2`: desconto das outras horas único, D087; metodologia do v1 em
  `web/risk_lab_dessem/metodologia-v1.html`). Mudar = versão nova (decisão na pesquisa, `congelar`, tag
  `risk_lab_dessem-modelo-<versão>`, metodologia da versão anterior guardada, como nas bandeiras).
- Feriados dos meses sem deck: lista `FERIADOS_FUTUROS` (até mar/2027). Equivalência "sem patamar pesado" × AAC001
  conferida em 2026-10-14 (1.347 dias, 34 feriados, sem divergência): trocar pelo AAC001 é decisão da pesquisa.
- Testes: `tests/referencias/risk_lab_dessem/` (períodos fechados: jul–set/2026), regerados com
  `qe risk_lab_dessem congelar`. Paridade com a pesquisa é opt-in (`QE_PARIDADE_RISK_LAB_DESSEM=<pasta do pacote>`).
- Submercado (D084): filtro por bloco, sem filtro global. Blocos de preço (1, 2, 5): SE/CO, S, NE, N (padrão SE/CO);
  blocos 3 e 4: SIN, SE/CO, S, NE, N (padrão SIN; no SIN, PLD e DECOMP mostram o SE/CO, com aviso); 6 e 7 fixos.
  SIN = soma dos quatro submercados hora a hora, só nas variáveis em MW e só nas horas com os quatro (T4).
- Contas que não dependem do usuário ficam no Python; o JS da página só desenha (exceção: a conta do simulador,
  com teste de paridade Python × JS).

## Pricing Descolamento (descolamento NE e N): etapas e testes
- Promovido de `../pricing-descolamento-analytics` em 2026-10-19 (tag `promocao-quant-v1`, pacote
  `docs/promocao_descolamento.md` de lá), bloco a bloco; R1 a R10 conferidos sem diferença. Escopo: só o modelo v2.2 e as três páginas
  (Descolamento NE e N, Metodologia, Fundamentos); **não trazer** a v1, as versões testadas (inclusive o 7d-1S),
  DECOMP, LPP nem o site do GitHub Pages, nem como contexto.
- Fontes, todas comuns (`qe_core.fontes`): deck do NEWAVE (conjunto `sistema_agrint`, última publicação),
  DESSEM (`PDO_SIST` e `PDO_RESTOPER`, guardado inteiro em `.gz`), PLD **publicado** e limites.
- Etapas: `qe pricing_descolamento ingerir | tratar [--refazer] | backtest | publicar | status | congelar`.
  Páginas: Descolamento NE e N, Metodologia (desempenho do backtest e alternativas) e Fundamentos (o realizado). T3 e T4 (DESSEM) particionados
  por mês, refeitos quando os dias do mês mudam; T1, T2 e T5 inteiros.
- Modelo em `qe_pricing_descolamento.modelo.MODELO` (hoje `v2.2`: P(trava) logística por regime, k pareado com o
  ano climático, D015, D022); definições de "descolado" e "travada" da base horária também vêm dele. Mudar = versão
  nova (decisão na pesquisa, `congelar`, tag `pricing_descolamento-modelo-<versão>`). Os coeficientes por cenário
  reproduzem o modelo para qualquer SE (teste): é o que a página vai usar.
- Dia a dia: `qe pricing_descolamento tratar` → `publicar`. Rodada = publicação com o deck do NEWAVE vigente e a
  versão do modelo (DESSEM e PLD novos não geram rodada sozinhos; `--forcar --motivo` para forçar).
  `serving/pricing_descolamento/historico_rodadas.json` é o registro das rodadas: não apagar nem recalcular; as linhas
  de jan/2025 a out/2026 vêm da pesquisa (R10, levado como está; até set/2026 são reconstruídas).
- Página: contas que não dependem da curva digitada no Python (`publicacao`: histórico realizado por período e
  fundamentos por produto); a conta da curva (resolver do ano ao mês, d por cenário, justo e faixa, choque) em
  `web/pricing_descolamento/descolamento_conta.js` e em `qe_pricing_descolamento.conta`: mudar uma exige mudar a outra
  (teste de paridade com node).
- Testes: `tests/referencias/pricing_descolamento/` (períodos fechados até set/2026), regerados com `congelar`.
  Paridade com a pesquisa é opt-in (`QE_PARIDADE_PRICING_DESCOLAMENTO=<pasta do pacote>`).

## Regras herdadas do analytics (bandeiras)
- PLD gatilho vem do deck do DECOMP da CCEE, nunca do CMO do ONS.
- Backtest e calibração só com informação disponível na data do deck.
- Adicional tarifário projetado é o da bandeira esperada; não existe adicional proporcional.
