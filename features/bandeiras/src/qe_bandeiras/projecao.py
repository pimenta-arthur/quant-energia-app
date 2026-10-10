"""Projeção da rodada do mês M (deck do NEWAVE + ECMWF de M): cenários esperado, seco e úmido de
M+1 a M+6, com a probabilidade de cada cor (σ por grupo, só com erros já realizados em M)."""

import pandas as pd

from qe_bandeiras import backtest, chaves, ecmwf, modelo, regra, series
from qe_core.armazenamento import Armazenamento, gravar_parquet


def projetar(arm: Armazenamento, deck: pd.Period, historico: pd.DataFrame) -> pd.DataFrame:
    """`historico` = previsões passadas com erro_x (backtest.referencia)."""
    base = backtest.base_oficial(arm)
    if deck not in base.index or pd.isna(base.loc[deck, "gf_band_boletim"]):
        raise ValueError(f"sem boletim/PMO tratado para o mês do deck {deck}")
    if not ecmwf.rodada_disponivel(arm, deck):
        raise ValueError(f"sem rodada do ECMWF tratada para {deck}")
    prep = series.series_do_deck(arm, deck, base)
    cen = modelo.prever_cenarios(prep, backtest.referencias(arm, deck, base))
    cen = cen[(cen.h >= 1) & (cen.h <= 6)].reset_index(drop=True)
    for i, r in cen.iterrows():
        p = modelo.probabilidade_por_grupo(historico, deck, r.h, r.x_esp, r.gsf_esp)
        for c in regra.CORES:
            cen.loc[i, f"p_{c}"] = float(p[c])
    gravar_parquet(
        arm,
        cen.assign(deck=cen.deck.astype(str), alvo=cen.alvo.astype(str)),
        chaves.proc_projecao(deck),
    )
    return cen
