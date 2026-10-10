# quant-energia-app

Aplicação com funcionalidades independentes (bandeiras tarifárias, PLD horário, descolamento entre
submercados), cada uma com a sua página e o seu pipeline. Roda local primeiro e vai para a AWS
depois, sem mudar o código das etapas. Responder sempre em português do Brasil.

## Pesquisa × produto
- A pesquisa (EDA, notebooks, backtest, decisões de método) fica nos repositórios de análise, como
  `../forecast-bandeiras` (GitHub `forecast-bandeiras-analytics`). Aqui entra só código validado lá.
- **Não mudar o método ao portar.** Toda migração tem teste de aceitação comparando com o analytics
  (`tests/`, variável `QE_ANALYTICS`, padrão `../forecast-bandeiras`).
- Decisões de método continuam registradas em `docs/metodologia.md` do analytics.

## Ambiente
- uv workspace (raiz + `core`, `features/bandeiras`, `api`). Sempre `uv add --package <membro> <pacote>`
  e `uv run ...`. **Nunca pip.** Python 3.14 do Homebrew.
- Lint/format: `uv run ruff check .` e `uv run ruff format .`; testes: `uv run pytest`.

## Arquitetura
- Etapas por funcionalidade: ingestão → tratamento → projeção → publicação, cada uma um comando
  `qe <funcionalidade> <etapa>` (local) e um worker (AWS).
- **Todo acesso a dados passa por `qe_core.armazenamento`** (chaves `raw/…`, `processed/…`,
  `serving/…`). Nunca abrir caminhos de `data/` diretamente nas etapas: isso quebra a ida para o S3.
- `raw/` é por fonte e imutável (a ingestão não sobrescreve sem `--sobrescrever`); `processed/` e
  `serving/` são por funcionalidade.
- Leitores (`qe_core.leitores`) são funções puras sobre o caminho do arquivo.
- Configuração só por variáveis `QE_*` (ou `.env`).
- `data/` nunca vai para o git.

## Bandeiras: etapas e testes
- `qe bandeiras ingerir | tratar | backtest | status | projetar | publicar | pagina | rodar`.
- Rodadas não são mensais: cada publicação é uma rodada (id = data e hora) com os insumos vigentes
  (último deck com boletim do mês, versão mais recente; emissão mais recente do ECMWF). Deck e ECMWF
  são versionados em raw/ (deck=AAAA-MM/v=<hash>, emissao=AAAA-MM-DD). O backtest segue mensal (D031).
- Modelo versionado em `qe_bandeiras.modelo.MODELO` (hoje `v1`). Mudar parâmetro ou lógica do método
  = versão nova: decisão no analytics, `qe bandeiras congelar`, tag `modelo-<versão>` no git.
- Testes: `tests/referencias/<versão>/` (referências congeladas, a proteção principal) e tratamento idêntico
  à base do analytics. A paridade da publicação com o analytics é opt-in (`QE_PARIDADE_ANALYTICS=1`).
- Nunca regenerar referências para "fazer o teste passar" sem entender a diferença.
- `serving/bandeiras/historico_projecoes.json` é o registro das rodadas publicadas: não apagar. É o único
  arquivo de `data/` versionado no git (exceção no .gitignore); commitar depois de cada publicação.

## Regras herdadas do analytics (bandeiras)
- PLD gatilho vem do deck do DECOMP da CCEE, nunca do CMO do ONS.
- Backtest e calibração só com informação disponível na data do deck.
- Adicional tarifário projetado é o da bandeira esperada; não existe adicional proporcional.
