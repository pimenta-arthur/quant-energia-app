"""Regra de acionamento da bandeira tarifária (memória de cálculo do boletim InfoBandeira da CCEE).

GH_band a partir do PMO, GSF_band = GH_band / GF_band e a cor pelo ábaco da REH ANEEL 3.306/2024.
Validado no forecast-bandeiras-analytics (46 de 46 meses de jan/2023 a out/2026).
"""

import numpy as np
import pandas as pd

# Fatores da CCEE aplicados à geração (Tabela 3 do boletim), em fração; cada conjunto vale a partir
# do mês indicado (média do ano anterior, atualizada por volta de março).
FATORES = {
    "2023-01": {"perda_bruta_conexao": 0.01458, "perda_conexao_cg": 0.02506, "part_pch_mre": 0.62464, "perda_pch_cg": 0.00125},
    "2023-03": {"perda_bruta_conexao": 0.01275, "perda_conexao_cg": 0.02595, "part_pch_mre": 0.65089, "perda_pch_cg": 0.00085},
    "2024-04": {"perda_bruta_conexao": 0.01391, "perda_conexao_cg": 0.02342, "part_pch_mre": 0.64795, "perda_pch_cg": 0.00082},
    "2025-03": {"perda_bruta_conexao": 0.01335, "perda_conexao_cg": 0.02151, "part_pch_mre": 0.64973, "perda_pch_cg": 0.00076},
    "2026-03": {"perda_bruta_conexao": 0.01283, "perda_conexao_cg": 0.02454, "part_pch_mre": 0.61153, "perda_pch_cg": 0.00063},
}  # fmt: skip

# Limites do índice X = PLD × (1 − GSF) para cada cor (Anexo I da REH 3.306/2024), em R$/MWh.
LIMITES_X = {"Verde": 27.48, "Amarela": 68.99, "Vermelha 1": 95.05}
CORES = ["Verde", "Amarela", "Vermelha 1", "Vermelha 2"]


def fatores_vigentes(periodo: pd.Period) -> dict:
    """Fatores da CCEE vigentes no mês (o conjunto mais recente com início até o mês)."""
    validos = [k for k in FATORES if pd.Period(k, "M") <= periodo]
    if not validos:
        raise KeyError(
            f"sem fatores da CCEE para {periodo}; incluir em FATORES a partir do boletim"
        )
    return FATORES[max(validos)]


def media_mensal(valores: np.ndarray, horas: pd.DataFrame) -> float:
    """Média mensal (MWmed) de valores patamar × semana, ponderada pelas horas no mês."""
    h = horas.to_numpy()
    if valores.shape != h.shape:
        raise ValueError(f"valores com {valores.shape} (patamar × semana), patamares com {h.shape}")
    return float((valores * h).sum() / h.sum())


def media_mensal_df(df: pd.DataFrame, coluna: str, horas: pd.DataFrame) -> float:
    """Média mensal de uma coluna de tabela longa (semana, pat), somando as demais chaves."""
    if df.empty:
        return 0.0
    tabela = df.groupby(["pat", "semana"])[coluna].sum().unstack()
    tabela = tabela.reindex(index=[1, 2, 3], columns=horas.columns).fillna(0)
    return media_mensal(tabela.to_numpy(), horas)


def gsf_band(gh_band: float, gf_band: float) -> float:
    """GSF_band = GH_band / GF_band, arredondado em 2 casas como pede a ANEEL."""
    return round(gh_band / gf_band, 2)


def cor_bandeira(gsf: float, pld_gatilho: float) -> str:
    """Cor pelo ábaco (sem GFOM), via X = PLD_gatilho × (1 − GSF).

    O PLD gatilho vem do deck do DECOMP da CCEE, não do CMO do ONS.
    """
    x = pld_gatilho * max(0.0, 1 - gsf)
    for cor, limite in LIMITES_X.items():
        if x <= limite:
            return cor
    return "Vermelha 2"
