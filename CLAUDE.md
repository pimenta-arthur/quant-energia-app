# quant-energia-app

Aplicação com funcionalidades independentes (bandeiras tarifárias, PLD horário, descolamento entre
submercados), cada uma com a sua página e o seu pipeline. Roda local primeiro e vai para a AWS
depois, sem mudar o código das etapas. Responder sempre em português do Brasil.

## Pesquisa × produto
- A pesquisa (EDA, notebooks, backtest, decisões de método) fica nos repositórios de análise, como
  `../forecast-bandeiras` (GitHub `forecast-bandeiras-analytics`). Aqui entra só código validado lá.
- **Não mudar o método ao portar.** A migração foi validada contra o analytics; hoje os testes usam
  referências congeladas do próprio app (`tests/referencias/`). O app não depende do analytics para rodar.
- **Nenhuma dependência de execução de outro repositório:** os dados entram só pela caixa de entrada
  `data/entrada/<fonte>/` (formato em `docs/entrada.md`); nada de ler pastas do analytics.
- Decisões de método continuam registradas em `docs/metodologia.md` do analytics.
- Nova funcionalidade: seguir `docs/nova_funcionalidade.md`. Pesquisa do PLD horário em
  `../risk-lab-dessem-analytics` — repositório independente (não depende deste app, e este app não depende
  dele): ao promover, o método é reimplementado aqui e conferido contra os resultados de referência de lá.

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
- **Pendência da fase AWS:** até lá, `data/raw/` existe só na máquina local (sem backup, por escolha do
  Arthur: arquivos pesados). Na AWS, o bucket com versionamento passa a ser a cópia de segurança.

## Bandeiras: etapas e testes
- Dia a dia: arquivo baixado em `data/entrada/<fonte>/` → `qe bandeiras atualizar` (ingere, trata os meses
  afetados, refaz o backtest, mostra status e prévia; não publica) → `qe bandeiras publicar --motivo …`.
- Etapas avulsas: `qe bandeiras ingerir | tratar | backtest | status | projetar | publicar | pagina | congelar`.
- A ingestão grava em `raw/` só o que o modelo usa, confere o hash e apaga o original da entrada (sem
  segunda cópia). O que não for reconhecido fica na entrada, com o motivo.
- Rodadas não são mensais: cada publicação é uma rodada (id = data e hora) com os insumos vigentes
  (último deck com boletim do mês, versão mais recente; emissão mais recente do ECMWF). Deck e ECMWF
  são versionados em raw/ (deck=AAAA-MM/v=<hash>, emissao=AAAA-MM-DD). O backtest segue mensal (D031).
- Modelo versionado em `qe_bandeiras.modelo.MODELO` (hoje `v1`). Mudar parâmetro ou lógica do método
  = versão nova: decisão no analytics, `qe bandeiras congelar`, tag `modelo-<versão>` no git.
- Testes: `tests/referencias/<versão>/` (modelo) e `tests/referencias/tratamento/` (dados tratados), regerados
  com `qe bandeiras congelar`.
- Nunca regenerar referências para "fazer o teste passar" sem entender a diferença.
- Checklist ao criar uma versão nova do modelo (ex.: v2):
  1. decisão registrada no analytics; nova instância de `Modelo` e `MODELO` apontando para ela;
  2. `qe bandeiras congelar`, revisar a diferença e commitar; tag `modelo-<versão>`;
  3. guardar a metodologia anterior como `web/bandeiras/metodologia-<versão anterior>.html`, com aviso
     "versão anterior; em uso de … a …", e atualizar `metodologia.html` e o rótulo do topo para a versão nova;
  4. nessa hora, criar: seletor de versões na Metodologia, link de cada rodada para a metodologia da sua
     versão, quadro de parâmetros gerado de `MODELO` e teste que exige a página de cada versão.
- `serving/bandeiras/historico_projecoes.json` é o registro das rodadas publicadas: não apagar. É o único
  arquivo de `data/` versionado no git (exceção no .gitignore); commitar depois de cada publicação.

## Regras herdadas do analytics (bandeiras)
- PLD gatilho vem do deck do DECOMP da CCEE, nunca do CMO do ONS.
- Backtest e calibração só com informação disponível na data do deck.
- Adicional tarifário projetado é o da bandeira esperada; não existe adicional proporcional.
