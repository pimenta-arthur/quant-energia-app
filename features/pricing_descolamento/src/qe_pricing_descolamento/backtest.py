"""Backtest da página (metodologia): o modelo vigente em 16 decks, com o SE realizado como insumo (pesquisa:
web.backtest_pagina e estrutural.backtest_periodos).

Para cada deck D e mês-alvo m ≥ D: treino com dados até D−2, previsão por cenário climático com o SE médio realizado
do mês, e as variáveis do mês (valor bruto do deck, valor que entrou no modelo e realizado) para a metodologia.
O SE realizado isola o erro do modelo do erro da curva do SE, que é insumo da mesa.
"""

import numpy as np
import pandas as pd

from qe_pricing_descolamento import modelo as M

# decks de jan, mar, mai, jul, set e nov de 2024 a jul/2026; meses-alvo jan/2025 a set/2026
DECKS = [
    f"{a}-{m:02d}"
    for a in (2024, 2025, 2026)
    for m in (1, 3, 5, 7, 9, 11)
    if f"{a}-{m:02d}" <= "2026-07"
]
MESES = ("2025-01", "2026-09")


def backtest(b: M.Base, decks: list[str] = DECKS, meses: tuple[str, str] = MESES) -> pd.DataFrame:
    """Uma linha por (deck, mês-alvo, cenário): previsão do NE e do N, P(trava) e k previstos, e as variáveis do
    mês (deck, modelo, realizado)."""
    real = b.mensal.set_index(pd.PeriodIndex(b.mensal.index, freq="M"))
    alvos = list(pd.period_range(*meses, freq="M"))
    lin = []
    for dk in decks:
        deck = pd.Period(dk, "M")
        mod = M.treinar(b, deck)
        for m in alvos:
            if m < deck:
                continue
            ins = M.insumos_mes(b, deck, m, mod)
            if not ins:
                continue
            p = M.prever(b, deck, m, float(real.loc[m, "SE"]), mod)
            r = b.h[b.h["mes"] == m]
            trav = r[r["desc_NE"].astype(bool)]
            # intensidade realizada: soma das frações e horas travadas (agregação = soma ÷ horas travadas)
            frac = ((trav["SE"] - trav["NE"]) / (trav["SE"] - b.piso(m.year)).clip(lower=1)).clip(
                0, 1
            )
            comum = {
                "deck": dk,
                "mes": m,
                "horas": m.days_in_month * 24,
                "SE_real": float(real.loc[m, "SE"]),
                "NE_real": float(real.loc[m, "d_NE"]),
                "N_real": float(real.loc[m, "d_N"]),
                "trav_real_%": 100 * r["desc_NE"].astype(bool).mean(),
                "k_modelo": mod[("k", M.regime(m), "NE")],
                "k_soma": float(frac.sum()),
                "k_horas": len(trav),
                "renov_NE_deck": b.ren_proj.loc[M._chave(deck, m)] / 1e3,
                "renov_NE_modelo": ins["renovavel_deck_NE"] / 1e3,
                "renov_NE_real": r["renovavel_NE"].mean() / 1e3,
                "carga_NE_deck": b.car_proj.loc[M._chave(deck, m)] / 1e3,
                "carga_NE_modelo": ins["carga_NE"] / 1e3,
                "carga_NE_real": r["demanda_NE"].mean() / 1e3,
                "carga_N_deck": b.car_proj_n.get(M._chave(deck, m), np.nan) / 1e3,
                "carga_N_modelo": ins["carga_N"] / 1e3,
                "carga_N_real": r["demanda_N"].mean() / 1e3,
                "lim_exp_NE_deck": ins["limite_exp_NE"] / 1e3,
                "lim_exp_NE_real": r["lsup_EXP_NE"].mean() / 1e3,
                "hidr_N_modelo": np.average(p["hidraulica_N"], weights=p["peso"]) / 1e3,
                "hidr_N_real": r["hidraulica_N"].mean() / 1e3,
            }
            for c in p.itertuples():
                lin.append(
                    {
                        **comum,
                        "cenario": str(c.ano_hidro),
                        "peso": c.peso,
                        "NE_prev": c.d_NE,
                        "N_prev": c.d_N,
                        "trav_prev_%": 100 * c.p_trava_NE,
                        "k_prev": c.k_prev_NE,
                    }
                )
    return pd.DataFrame(lin)
