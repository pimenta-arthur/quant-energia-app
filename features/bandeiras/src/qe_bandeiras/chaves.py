"""Chaves de armazenamento usadas pela funcionalidade de bandeiras.

raw/ é organizado por fonte (compartilhado entre funcionalidades); processed/ e serving/ por
funcionalidade. As mesmas chaves valem no disco local e no S3.
"""

import pandas as pd

from qe_core.periodo import rotulo


def raw_pmo(m: pd.Period, arquivo: str) -> str:
    return f"raw/ons_pmo/{rotulo(m)}/{arquivo}"


def raw_boletim(m: pd.Period) -> str:
    return f"raw/ccee_boletim/{rotulo(m)}/infobandeira.pdf"


def raw_patamares(ano: int) -> str:
    return f"raw/ccee_patamares/{ano}/AAC001.xlsx"


def raw_newave(m: pd.Period, arquivo: str = "") -> str:
    return f"raw/ccee_newave/{rotulo(m)}/{arquivo}"


def raw_ecmwf(m: pd.Period, arquivo: str = "") -> str:
    return f"raw/ecmwf/{rotulo(m)}/{arquivo}"


RAW_HISTORICO = "raw/aneel_bandeiras/historico.csv"

PROC = "processed/bandeiras"


def proc_patamares(m: pd.Period) -> str:
    return f"{PROC}/patamares/{rotulo(m)}.parquet"


def proc_mensal(m: pd.Period) -> str:
    return f"{PROC}/mensal/{rotulo(m)}.parquet"


def proc_newave(m: pd.Period, tabela: str) -> str:
    return f"{PROC}/newave/{rotulo(m)}/{tabela}.parquet"


def proc_ecmwf(m: pd.Period, tabela: str) -> str:
    return f"{PROC}/ecmwf/{rotulo(m)}/{tabela}.parquet"


PROC_HISTORICO = f"{PROC}/historico_bandeiras.parquet"

ARQUIVOS_NEWAVE = (
    ["ghtotsin.out", "sistema.dat", "c_adic.dat"]
    + [f"eafbm00{i}.out" for i in range(1, 5)]
    + [f"cmarg00{i}.out" for i in range(1, 5)]
    + [f"cmarg00{i}-med.out" for i in range(1, 5)]
)
ARQUIVOS_PMO = ["relato.rv0", "ena.pdf", "renovaveis.csv"]
