"""Chaves de armazenamento usadas pela funcionalidade de bandeiras.

raw/ é organizado por fonte (compartilhado entre funcionalidades); processed/ e serving/ por
funcionalidade. As mesmas chaves valem no disco local e no S3.

Insumos que podem ter mais de uma versão no mesmo mês são versionados na chave:
- deck do NEWAVE: deck=AAAA-MM/v=<hash do conteúdo> (uma republicação do deck vira nova versão);
- ECMWF: emissao=AAAA-MM-DD (uma emissão extra no mês não sobrescreve a anterior).
"""

import pandas as pd

from qe_core.periodo import rotulo


def raw_pmo(m: pd.Period, arquivo: str) -> str:
    return f"raw/ons_pmo/{rotulo(m)}/{arquivo}"


def raw_boletim(m: pd.Period) -> str:
    return f"raw/ccee_boletim/{rotulo(m)}/infobandeira.pdf"


def raw_patamares(ano: int) -> str:
    return f"raw/ccee_patamares/{ano}/AAC001.xlsx"


from qe_core.fontes import ARQUIVOS_NEWAVE, RAW_NEWAVE, raw_newave  # noqa: F401 — fonte comum

RAW_ECMWF = "raw/ecmwf"


def raw_ecmwf(emissao: str, arquivo: str = "") -> str:
    return f"{RAW_ECMWF}/emissao={emissao}/{arquivo}"


RAW_HISTORICO = "raw/aneel_bandeiras/historico.csv"

PROC = "processed/forecast_bandeiras"


def proc_patamares(m: pd.Period) -> str:
    return f"{PROC}/patamares/{rotulo(m)}.parquet"


def proc_mensal(m: pd.Period) -> str:
    return f"{PROC}/mensal/{rotulo(m)}.parquet"


def proc_newave(deck: pd.Period, versao: str, tabela: str) -> str:
    return f"{PROC}/newave/deck={rotulo(deck)}/v={versao}/{tabela}.parquet"


def proc_ecmwf(emissao: str, tabela: str) -> str:
    return f"{PROC}/ecmwf/emissao={emissao}/{tabela}.parquet"


PROC_HISTORICO = f"{PROC}/historico_bandeiras.parquet"


def proc_series(deck: pd.Period, versao: str, tabela: str) -> str:
    """GSF e PLD gatilho por série e mês-alvo do deck (cache da parte cara da projeção)."""
    return f"{PROC}/series/deck={rotulo(deck)}/v={versao}/{tabela}.parquet"


def proc_projecao(id_insumos: str) -> str:
    return f"{PROC}/projecao/{id_insumos}.parquet"


PROC_BACKTEST = f"{PROC}/backtest"  # referencia.parquet, oraculo.parquet, rodadas.parquet

SERVING = "serving/forecast_bandeiras"
SERVING_DADOS = f"{SERVING}/produto_dados.js"
# Dados embutidos na página de cálculo pelo relato (fatores, horas por patamar, boletim).
SERVING_RELATO_DADOS = f"{SERVING}/relato_dados.js"
# Registro das rodadas publicadas, como foram publicadas (não apagar nem recalcular).
SERVING_REGISTRO = f"{SERVING}/historico_projecoes.json"

ARQUIVOS_PMO = ["relato.rv0", "ena.pdf", "renovaveis.csv"]
