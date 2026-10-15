"""Projeção de uma rodada: cenários esperado, seco e úmido de M+1 a M+6 (M = mês do deck), com a
probabilidade de cada cor, a partir de um conjunto de insumos (versão do deck + emissão do ECMWF).

σ por grupo de horizonte, só com erros de meses-alvo encerrados antes do mês do deck (mesmo corte
validado no analytics).
"""

import pandas as pd

from qe_core.armazenamento import Armazenamento, gravar_parquet
from qe_forecast_bandeiras import backtest, chaves, ecmwf, modelo, regra, series
from qe_forecast_bandeiras.insumos import Insumos


def projetar(
    arm: Armazenamento, ins: Insumos, historico: pd.DataFrame, gravar: bool = True
) -> pd.DataFrame:
    """`historico` = previsões passadas com erro_x (backtest.referencia)."""
    base = backtest.base_oficial(arm)
    deck = ins.mes_deck
    if deck not in base.index or pd.isna(base.loc[deck, "gf_band_boletim"]):
        raise ValueError(f"sem boletim/PMO tratado para o mês do deck {deck}")
    if not ecmwf.emissao_tratada(arm, ins.ecmwf_emissao):
        raise ValueError(f"emissão do ECMWF {ins.ecmwf_emissao} não tratada")
    prep = series.series_do_deck(arm, deck, ins.deck_versao, base)
    cen = modelo.prever_cenarios(prep, backtest.referencias(arm, ins, base))
    cen = cen[(cen.h >= 1) & (cen.h <= modelo.MODELO.horizonte)].reset_index(drop=True)
    for i, r in cen.iterrows():
        p = modelo.probabilidade_por_grupo(historico, deck, r.h, r.x_esp, r.gsf_esp)
        for c in regra.CORES:
            cen.loc[i, f"p_{c}"] = float(p[c])
    if gravar:
        gravar_parquet(
            arm,
            cen.assign(deck=cen.deck.astype(str), alvo=cen.alvo.astype(str)),
            chaves.proc_projecao(ins.identificador()),
        )
    return cen
