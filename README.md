# quant-energia-app

Aplicação quant de energia elétrica. Cada funcionalidade é uma página com o seu próprio pipeline,
independente das outras:

| Funcionalidade | Situação | Pesquisa (repositório de análise) |
|---|---|---|
| Bandeiras tarifárias | pipeline completo (ingestão → publicação) e página | `forecast-bandeiras-analytics` |
| PLD horário | análise exploratória | (a criar) |
| Descolamento entre submercados | planejado | (a criar) |

Roda local de forma simples e já usa as mesmas chaves e etapas que vão para a AWS.

## Rodar local

```bash
uv sync                                   # instala tudo (Python 3.14 do Homebrew)
cp .env.example .env                      # opcional: QE_DADOS, QE_ARMAZENAMENTO

# bandeiras: rodada do mês (deck do NEWAVE + ECMWF de M)
uv run qe bandeiras ingerir --origem ../forecast-bandeiras/data/raw --mes 2026-09   # bruto → raw/
uv run qe bandeiras tratar --mes 2026-09                                            # raw/ → processed/ (Parquet)
uv run qe bandeiras backtest                     # previsões passadas sem vazamento (σ e rodadas)
uv run qe bandeiras projetar --mes 2026-09       # M+1 a M+6: esperado, seco, úmido e probabilidade
uv run qe bandeiras publicar --mes 2026-09       # serving/bandeiras/ + registro da rodada publicada
# tudo de uma vez: uv run qe bandeiras rodar --mes 2026-09 [--origem ...]
# primeira carga do histórico: ingerir e tratar com --mes 2023-01 --ate 2026-10

uv run qe servir                          # http://localhost:8000 → /bandeiras/
uv run pytest                             # testes (comparam com o analytics, se disponível)
```

## Organização

```
core/                  qe_core: configuração, armazenamento (local|S3), leitores CCEE/ONS/NEWAVE/ECMWF/ANEEL
features/bandeiras/    qe_bandeiras: ingestão → tratamento → projeção → publicação
api/                   qe_api: FastAPI que serve as páginas e o serving local
web/                   páginas (uma pasta por funcionalidade)
src/qe/                linha de comando `qe`
tests/                 testes de aceitação
data/                  (fora do git) imita o bucket: raw/ processed/ serving/
```

## Dados em camadas

| Camada | Conteúdo | Organização |
|---|---|---|
| `raw/` | arquivo original, imutável | por fonte: `raw/ccee_newave/2026-09/…`, `raw/ons_pmo/…`, `raw/ecmwf/…` |
| `processed/` | tabelas tratadas (Parquet) | por funcionalidade: `processed/bandeiras/mensal/2026-09.parquet` |
| `serving/` | o que as páginas leem (JSON/JS) | por funcionalidade |

As etapas só acessam dados pelo módulo de armazenamento. Na AWS, `QE_ARMAZENAMENTO=s3` e
`QE_BUCKET=<bucket>`: as mesmas chaves passam a ser objetos no S3.

## Caminho para a AWS (fase futura)

| Local | AWS |
|---|---|
| `qe bandeiras ingerir` | worker agendado (EventBridge → ECS Fargate/Lambda) baixando das fontes |
| `qe bandeiras tratar` | worker disparado por novo objeto em `raw/` |
| `data/` | S3 |
| `qe servir` | S3 + CloudFront (páginas e serving); API em Lambda/ECS quando houver consulta interativa |
| sequência manual | Step Functions |

Dados de terceiros (curvas Dcide, ECMWF) têm licença: o bucket de `raw/` é privado e as páginas
publicam só resultados derivados.

## Registro das rodadas publicadas

`serving/bandeiras/historico_projecoes.json` guarda cada rodada como foi publicada (data incluída).
Publicar de novo no mesmo mês substitui só aquela rodada; as anteriores nunca são recalculadas.
Não apagar: é o que mostra, na página, como a projeção de cada mês mudou de uma rodada para outra.
É o único arquivo de `data/` versionado no git: depois de cada `publicar`, fazer commit dele.
