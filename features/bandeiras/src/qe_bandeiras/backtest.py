"""Backtest sem vazamento: refaz, para cada deck com rodada do ECMWF, a projeção como teria sido feita.

Serve a duas coisas:
1. os erros de X das previsões passadas, que dão o σ da probabilidade (só erros de meses-alvo
   já encerrados na data de cada deck);
2. as rodadas reconstruídas (esperado, seco e úmido) e o desempenho mostrados na página.
Saídas em processed/bandeiras/backtest/: referencia, oraculo e rodadas (Parquet).
"""

import numpy as np
import pandas as pd

from qe_bandeiras import chaves, ecmwf, insumos, modelo, series, tratamento
from qe_core.armazenamento import Armazenamento, gravar_parquet, ler_parquet

AB = {"Verde": "Vd", "Amarela": "Am", "Vermelha 1": "V1", "Vermelha 2": "V2"}


def br(v: float, casas: int = 0) -> str:
    return f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def texto_prob(prob: pd.Series) -> str:
    if prob.isna().all():
        return "sem histórico para a probabilidade"
    return " ".join(f"{AB[c]} {v:.0%}" for c, v in prob.items() if v >= 0.05)


def base_oficial(arm: Armazenamento) -> pd.DataFrame:
    """Base mensal tratada com a cor oficial e o X oficial de cada mês."""
    base = tratamento.base_mensal(arm)
    base["cor_oficial"] = [
        c if isinstance(c, str) else r for c, r in zip(base.cor_boletim, base.cor_regra)
    ]
    base["x_real"] = base.pld_gatilho_boletim * (1 - base.gsf_band_boletim).clip(lower=0)
    return base


def decks_com_rodada(arm: Armazenamento, base: pd.DataFrame) -> list[insumos.Insumos]:
    """Uma rodada histórica por mês de deck (pareamento mensal, D031): a versão mais recente do deck
    de M com a emissão do ECMWF de M, se houver boletim do mês do deck."""
    saida = []
    for d in series.decks_disponiveis(arm):
        emissao = insumos.emissao_do_mes(arm, d)
        if (
            ecmwf.emissao_tratada(arm, emissao)
            and d in base.index
            and pd.notna(base.loc[d, "gf_band_boletim"])
        ):
            saida.append(insumos.Insumos(str(d), insumos.versao_atual(arm, d), emissao))
    return saida


def referencias(arm: Armazenamento, ins: insumos.Insumos, base: pd.DataFrame) -> dict:
    deck, emissao = ins.mes_deck, ins.ecmwf_emissao
    return {
        "esp": ecmwf.referencia_media(arm, deck, emissao, base),
        "li": ecmwf.referencia_quantil(arm, deck, emissao, base, modelo.MODELO.quantil_li),
        "ls": ecmwf.referencia_quantil(arm, deck, emissao, base, modelo.MODELO.quantil_ls),
    }


def _com_oficial(p: pd.DataFrame, base: pd.DataFrame) -> pd.DataFrame:
    cols = ["cor_oficial", "x_real", "gsf_band_boletim", "pld_gatilho_boletim"]
    p = p[(p.h >= 1) & (p.h <= modelo.MODELO.horizonte)].merge(
        base[cols], left_on="alvo", right_index=True
    )
    return p.assign(erro_x=p.x_real - p.x_medio).reset_index(drop=True)


def rodar(arm: Armazenamento, gravar: bool = True) -> dict[str, pd.DataFrame]:
    base = base_oficial(arm)
    real_ena = base.ena_sin.dropna()
    ref_l, ora_l, cen_l = [], [], []
    for ins in decks_com_rodada(arm, base):
        prep = series.series_do_deck(arm, ins.mes_deck, ins.deck_versao, base)
        refs = referencias(arm, ins, base)
        ref_l.append(modelo.prever(prep, refs["esp"]))
        ora_l.append(modelo.prever(prep, real_ena))  # ORÁCULO: ENA oficial no lugar da prevista
        cen = modelo.prever_cenarios(prep, refs)
        cen_l.append(cen[(cen.h >= 1) & (cen.h <= modelo.MODELO.horizonte)])
    referencia = _com_oficial(pd.concat(ref_l, ignore_index=True), base)
    oraculo = _com_oficial(pd.concat(ora_l, ignore_index=True), base)

    rodadas = pd.concat(cen_l, ignore_index=True)
    probs = [
        modelo.probabilidade_por_grupo(referencia, r.deck, r.h, r.x_esp, r.gsf_esp)
        for r in rodadas.itertuples()
    ]
    rodadas["prob"] = [texto_prob(p) for p in probs]
    for c in modelo.regra.CORES:
        rodadas[f"p_{c}"] = [float(p[c]) for p in probs]
    rodadas["gp"] = [
        f"GSF {br(g, 2)} · R$ {br(p)}" for g, p in zip(rodadas.gsf_esp, rodadas.pld_esp)
    ]
    oficial = base.cor_oficial
    rodadas["real"] = [
        oficial.get(a) if isinstance(oficial.get(a), str) else None for a in rodadas.alvo
    ]

    saida = {"referencia": referencia, "oraculo": oraculo, "rodadas": rodadas}
    for nome, df in saida.items() if gravar else ():
        gravar_parquet(
            arm,
            df.assign(deck=df.deck.astype(str), alvo=df.alvo.astype(str)),
            f"{chaves.PROC_BACKTEST}/{nome}.parquet",
        )
    return saida


def carregar(arm: Armazenamento) -> dict[str, pd.DataFrame]:
    saida = {}
    for nome in ("referencia", "oraculo", "rodadas"):
        df = ler_parquet(arm, f"{chaves.PROC_BACKTEST}/{nome}.parquet")
        df["deck"] = pd.PeriodIndex(df.deck, freq="M")
        df["alvo"] = pd.PeriodIndex(df.alvo, freq="M")
        saida[nome] = df.replace({None: np.nan}) if nome != "rodadas" else df
    return saida
