"""Trajetórias de ENA do SIN de referência a partir da rodada do ECMWF (D030, D031 do analytics).

O deck do mês M usa a rodada do ECMWF do mesmo mês M. Para o próprio mês M a referência é a ENA do
PMO (já publicada); de M+1 em diante, a do ECMWF:
- média: média da abordagem `precip`, somando os quatro subsistemas;
- membros: 51 membros recentrados na média `precip` (membro × média / média dos membros, por
  mês-alvo e subsistema); LI e LS = P10 e P90 mensais desses membros.
"""

import pandas as pd

from qe_core.armazenamento import Armazenamento, ler_parquet
from qe_forecast_bandeiras import chaves


def _media(arm: Armazenamento, emissao: str) -> pd.Series:
    est = ler_parquet(arm, chaves.proc_ecmwf(emissao, "estatisticas"))
    est = est[(est.estatistica == "av") & (est.abordagem == "precip") & (est.alvo >= est.emissao)]
    return est.set_index(["alvo", "subsistema"]).ena


def referencia_media(
    arm: Armazenamento, deck: pd.Period, emissao: str, base: pd.DataFrame
) -> pd.Series:
    """ENA do SIN de referência: PMO no mês do deck, média `precip` do ECMWF depois."""
    sin = _media(arm, emissao).groupby(level="alvo").sum()
    sin.index = pd.PeriodIndex(sin.index, freq="M")
    return pd.concat([pd.Series({deck: base.loc[deck, "ena_sin"]}), sin[sin.index > deck]])


def referencia_membros(
    arm: Armazenamento, deck: pd.Period, emissao: str, base: pd.DataFrame
) -> pd.DataFrame:
    """ENA do SIN por membro recentrado (membro × período), do mês do deck em diante."""
    mem = ler_parquet(arm, chaves.proc_ecmwf(emissao, "membros"))
    mem = mem[mem.alvo >= mem.emissao]
    media = _media(arm, emissao)
    chave = pd.MultiIndex.from_arrays([mem.alvo, mem.subsistema])
    media_membros = mem.groupby(["alvo", "subsistema"]).ena.transform("mean")
    mem = mem.assign(ena_recentrada=mem.ena * chave.map(media).to_numpy() / media_membros)
    mem = mem[pd.PeriodIndex(mem.alvo, freq="M") > deck]
    tab = mem.groupby(["membro", "alvo"]).ena_recentrada.sum().unstack()
    tab.columns = pd.PeriodIndex(tab.columns, freq="M")
    tab.insert(0, deck, base.loc[deck, "ena_sin"])
    return tab


def referencia_quantil(
    arm: Armazenamento, deck: pd.Period, emissao: str, base: pd.DataFrame, q: float
) -> pd.Series:
    """Cenário de ENA do SIN = quantil q mês a mês dos membros (0,1: LI seco; 0,9: LS úmido)."""
    return referencia_membros(arm, deck, emissao, base).quantile(q).rename(None)


def referencia_climatologia(arm: Armazenamento, deck: pd.Period, emissao: str) -> pd.Series:
    """MLT do SIN por mês-alvo (a que vem com a emissão do ECMWF), a partir de M+1."""
    mem = ler_parquet(arm, chaves.proc_ecmwf(emissao, "membros"))
    m0 = mem[(mem.membro == 0) & (pd.PeriodIndex(mem.alvo, freq="M") > deck)]
    mlt = m0.groupby("alvo").mlt.sum()
    mlt.index = pd.PeriodIndex(mlt.index, freq="M")
    return mlt


def emissao_tratada(arm: Armazenamento, emissao: str | None) -> bool:
    return (
        emissao is not None
        and arm.existe(chaves.proc_ecmwf(emissao, "estatisticas"))
        and arm.existe(chaves.proc_ecmwf(emissao, "membros"))
    )
