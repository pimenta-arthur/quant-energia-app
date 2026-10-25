"""Chaves de armazenamento da projeção de ENA e dos anos similares.

raw/ é por fonte; as cinco fontes daqui são usadas só por esta funcionalidade (ingestão em `ingestao.py`; se
outra funcionalidade passar a usar alguma, ela vai para `qe_core.fontes`):

| fonte | o que vai para raw/ | versão |
|---|---|---|
| `ons_ena_historica` | as duas planilhas 1931–2024 (subsistema e bacia) | imutável |
| `ons_ena_diaria` | CSV anual por nível | por hash: o ONS republica o arquivo do ano (consistência) |
| `noaa_ersst` | grade ERSST v6 | só a publicação mais recente (D2 da promoção); histórico de hashes em `_publicacoes.json` |
| `noaa_indices` | ONI, RONI, SOI, AAO (CPC), PDO, AMO (NCEI) | por hash: a NOAA revisa a série inteira |
| `cpc_enso_previsao` | páginas de probabilidade por fase e por força | por emissão (lida do conteúdo) |

processed/ e serving/ são desta funcionalidade.
"""

CODIGO = "hydro_inflow_similarity"

RAW_HISTORICA = "raw/ons_ena_historica"
PLANILHAS = {"subsistema": "Enas_Subsistemas_1931-2024.xls", "bacia": "Enas_bacias_1931-2024.xls"}
RAW_DIARIA = "raw/ons_ena_diaria"
ARQUIVO_DIARIA = {
    "subsistema": "ENA_DIARIO_SUBSISTEMA_{ano}.csv",
    "bacia": "ENA_DIARIO_BACIAS_{ano}.csv",
}
RAW_ERSST = "raw/noaa_ersst/ersst.v6.sst.mnmean.nc"
RAW_ERSST_PUBLICACOES = "raw/noaa_ersst/_publicacoes.json"
RAW_INDICES = "raw/noaa_indices"
# nome canônico de cada índice em raw/ → nomes com que o arquivo pode chegar na entrada
INDICES = {
    "oni.ascii.txt": ["oni.ascii.txt"],
    "RONI.ascii.txt": ["RONI.ascii.txt"],
    "soi.txt": ["soi.txt", "cpc_soi.txt", "soi"],
    "aao_mensal.txt": [
        "aao_mensal.txt",
        "cpc_aao_mensal.txt",
        "monthly.aao.index.b79.current.ascii",
    ],
    "ersst.v5.pdo.dat": ["ersst.v5.pdo.dat"],
    "ersst.v5.amo.dat": ["ersst.v5.amo.dat"],
}
RAW_CPC = "raw/cpc_enso_previsao"
MARCA = "_ingestao.json"  # gravada ao lado de cada versão: origem e data da ingestão


def raw_diaria(nivel: str, ano: int, versao: str, arquivo: str = "") -> str:
    return f"{RAW_DIARIA}/{nivel}/ano={ano}/v={versao}/{arquivo}"


def raw_indice(nome: str, versao: str, arquivo: str = "") -> str:
    return f"{RAW_INDICES}/{nome}/v={versao}/{arquivo}"


def raw_cpc(emissao: str, arquivo: str = "") -> str:
    """`emissao` = AAAA-MM; arquivo = probabilidades.html ou forca.html."""
    return f"{RAW_CPC}/emissao={emissao}/{arquivo}"


PROC = f"processed/{CODIGO}"
# T1: ENA mensal (planilha 1931–2024 + média da diária 2025–), subsistemas e bacias, Paraná incremental
PROC_ENA = f"{PROC}/ena_mensal.parquet"
# T2: MLT (média 1931–2024 da planilha) por nível, nome e mês
PROC_MLT = f"{PROC}/mlt.parquet"
# T3: índices mensais (ERSST v6 e oficiais)
PROC_INDICES = f"{PROC}/indices_mensais.parquet"
# ENA diária (última versão de cada ano), base da atualização com o mês em curso
PROC_DIARIA = {n: f"{PROC}/ena_diaria_{n}.parquet" for n in ("subsistema", "bacia")}
# backtest fora da amostra (CH, C30, PER, SPLIT, SIM; emissões 1961 até o fim do último ano completo)
PROC_BACKTEST = f"{PROC}/backtest.parquet"

SERVING = f"serving/{CODIGO}"
# registro das rodadas mensais: não apagar nem recalcular; a 2026-09 vem da pesquisa (R10, levada como está)
SERVING_REGISTRO = f"{SERVING}/historico_rodadas.json"


def serving(nome: str) -> str:
    return f"{SERVING}/{nome}.json"
