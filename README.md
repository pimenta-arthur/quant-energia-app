# quant-energia-app

Aplicação quant de energia elétrica. Cada funcionalidade é uma página com o seu próprio pipeline,
independente das outras:

| Funcionalidade | Situação | Pesquisa (repositório de análise) |
|---|---|---|
| Bandeiras tarifárias | pipeline completo (ingestão → publicação) e página | `forecast-bandeiras-analytics` |
| PLD horário | análise exploratória | `risk-lab-dessem-analytics` |
| Descolamento entre submercados | planejado | (a criar) |

Roda local de forma simples e já usa as mesmas chaves e etapas que vão para a AWS.
Nova funcionalidade a partir de uma pesquisa: `docs/nova_funcionalidade.md`.

## Rodar local

```bash
uv sync                                   # instala tudo (Python 3.14 do Homebrew)
cp .env.example .env                      # opcional: QE_DADOS, QE_ARMAZENAMENTO

# bandeiras: sempre que algum insumo mudar (deck novo ou republicado, PMO, boletim, emissão do ECMWF…)
# 1. solte o arquivo como baixou em data/entrada/<fonte>/ (formato e fontes: docs/entrada.md)
uv run qe bandeiras atualizar                    # entrada → raw/ → tratamento → backtest → status e prévia
uv run qe bandeiras publicar --motivo "deck do NEWAVE de out/26"   # registra a rodada e atualiza a página
# etapas avulsas: ingerir | tratar --mes AAAA-MM [--ate AAAA-MM] | backtest | status | projetar | pagina
# fixar insumos: --deck 2026-09 --versao <hash> --ecmwf 2026-09-01 (projetar/publicar)

uv run qe servir                          # http://localhost:8000 → /bandeiras/
uv run pytest                             # testes contra as referências congeladas (tests/referencias)
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
| `entrada/` | arquivos como baixados, até a ingestão (fica vazia) | por fonte: `entrada/ccee_newave/`, `entrada/ecmwf/`… |
| `raw/` | arquivo original, imutável | por fonte e versão: `raw/ccee_newave/deck=2026-09/v=<hash>/…`, `raw/ecmwf/emissao=2026-09-01/…`, `raw/ons_pmo/2026-09/…` |
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

`serving/bandeiras/historico_projecoes.json` guarda cada rodada como foi publicada: identificador
(data e hora), motivo, insumos usados (mês e versão do deck, emissão do ECMWF) e as projeções.
Pode haver várias rodadas no mesmo mês; nenhuma é recalculada ou apagada depois de publicada.
`publicar` recusa repetir os insumos da última rodada, a não ser com `--forcar --motivo`.
Não apagar: é o que mostra, na página, como a projeção de cada mês mudou de uma rodada para outra.
É o único arquivo de `data/` versionado no git: depois de cada `publicar`, fazer commit dele.

## Versões do modelo e testes

- Os parâmetros do modelo ficam em `qe_bandeiras.modelo` como uma versão nomeada (`MODELO`, hoje `v1`:
  k = 15, peso igual na trajetória, σ por grupo M+1–3/M+4–6, LI/LS pelo P10/P90 dos membros do ECMWF…).
  Cada rodada publicada grava a versão usada, e a página mostra "Modelo v1".
- `tests/referencias/<versão>/` guarda os resultados esperados (backtest, oráculo, rodadas reconstruídas e a
  projeção da rodada de referência de set/2026). `uv run pytest` recalcula e compara.
- **Mudança sem querer** → o teste falha → corrigir o código.
- **Mudança intencional** (dados novos no histórico, ou versão nova do modelo decidida no analytics) →
  `uv run qe bandeiras congelar`, revisar a diferença no git e commitar. Versão nova do modelo: nova
  instância de `Modelo`, `MODELO` apontando para ela, decisão registrada no analytics e tag `modelo-<versão>`.
- A paridade com o forecast-bandeiras-analytics validou a migração (2026-10-09); desde então a proteção
  são as referências congeladas, e o app não lê nada do analytics.
