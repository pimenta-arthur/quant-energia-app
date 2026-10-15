"""Modelo de projeção, versão em `MODELO` (validado no analytics: D029, D030, D031 e σ por grupo).

1. Escolha das séries: as k = 15 séries do NEWAVE com trajetória de ENA do SIN (do mês do deck ao
   mês-alvo) mais próxima da referência, com peso igual em todos os meses.
2. GSF e PLD gatilho = médias dessas mesmas séries; cor pelo ábaco.
3. Probabilidade: X real ~ Normal(X médio, σ), σ dos erros de X de previsões cujo mês-alvo já
   terminou na data do deck, separado para M+1–3 e M+4–6.
"""

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from scipy.stats import norm

from qe_forecast_bandeiras import regra


@dataclass(frozen=True)
class Modelo:
    """Parâmetros de uma versão do modelo. Mudar qualquer um é mudança de método: nova versão,
    decisão registrada no analytics, referências congeladas novas (`qe forecast_bandeiras congelar`) e tag
    `modelo-<versao>` no git."""

    versao: str
    decisoes: str  # decisões do analytics que definem esta versão
    k: int  # séries escolhidas por mês-alvo
    meia_vida: float  # peso da trajetória de ENA (inf = peso igual em todos os meses)
    grupos_horizonte: tuple  # grupos de h com σ separado
    minimo_erros_sigma: int  # menos que isso: probabilidade suspensa
    gsf_verde: float  # GSF a partir do qual a bandeira é verde para qualquer preço
    quantil_li: float  # cenário seco: quantil mensal da ENA dos membros do ECMWF
    quantil_ls: float  # cenário úmido
    horizonte: int  # M+1 a M+horizonte

    def como_dict(self) -> dict:
        d = asdict(self)
        d["meia_vida"] = "inf" if np.isinf(self.meia_vida) else self.meia_vida
        d["grupos_horizonte"] = [list(g) for g in self.grupos_horizonte]
        return d


V1 = Modelo(
    versao="v1",
    decisoes="D029 (k=15, peso igual), D030 (ECMWF média precip + membros recentrados), "
    "D031/D033 (pareamento deck × ECMWF), D032 (patamares), σ por grupo M+1–3/M+4–6 (9.3), "
    "LI/LS pelo P10/P90 mensal dos membros (9.5)",
    k=15,
    meia_vida=np.inf,
    grupos_horizonte=((1, 2, 3), (4, 5, 6)),
    minimo_erros_sigma=8,
    gsf_verde=0.96,
    quantil_li=0.1,
    quantil_ls=0.9,
    horizonte=6,
)
MODELO = V1  # versão em uso
K_PADRAO = MODELO.k
MEIA_VIDA_PADRAO = MODELO.meia_vida
GRUPOS_HORIZONTE = MODELO.grupos_horizonte


def distancia_trajetoria(ena: pd.DataFrame, referencia: pd.Series, meia_vida: float) -> pd.Series:
    """Erro relativo ao quadrado de cada série à trajetória de referência, média ponderada."""
    meses = list(referencia.index)
    idade = np.arange(len(meses))[::-1]
    if meia_vida == 0:
        pesos = (idade == 0).astype(float)
    elif np.isinf(meia_vida):
        pesos = np.ones(len(meses))
    else:
        pesos = 0.5 ** (idade / meia_vida)
    erro = (ena[meses] - referencia.values) / referencia.values
    return (erro**2 * pesos).sum(axis=1) / pesos.sum()


def escolher(
    prep: dict,
    referencia: pd.Series,
    alvo: pd.Period,
    k: int = K_PADRAO,
    meia_vida: float = MEIA_VIDA_PADRAO,
) -> pd.Index:
    """k séries de trajetória de ENA (do mês do deck ao alvo) mais próxima da referência."""
    trajetoria = [prep["inicio"] + i for i in range((alvo - prep["inicio"]).n + 1)]
    ref = pd.Series(referencia.reindex(trajetoria).to_numpy(), index=trajetoria)
    return distancia_trajetoria(prep["ena"][trajetoria], ref, meia_vida).nsmallest(k).index


def prever(
    prep: dict, referencia: pd.Series, k: int = K_PADRAO, meia_vida: float = MEIA_VIDA_PADRAO
) -> pd.DataFrame:
    """GSF, PLD, X e cor da média das k séries escolhidas, por mês-alvo coberto pela referência."""
    linhas = []
    for alvo in prep["alvos"]:
        if alvo not in referencia.index or referencia.reindex([alvo]).isna().any():
            continue
        idx = escolher(prep, referencia, alvo, k, meia_vida)
        gsf_medio = round(prep["gsf"].loc[idx, alvo].mean(), 2)
        pld_medio = float(prep["pld"].loc[idx, alvo].mean())
        linhas.append(
            {
                "deck": prep["inicio"],
                "alvo": alvo,
                "h": (alvo - prep["inicio"]).n,
                "gsf_medio": gsf_medio,
                "pld_medio": pld_medio,
                "x_medio": pld_medio * max(0.0, 1 - gsf_medio),
                "cor_media": regra.cor_bandeira(gsf_medio, pld_medio),
            }
        )
    return pd.DataFrame(linhas)


def prever_cenarios(prep: dict, referencias: dict) -> pd.DataFrame:
    """Uma previsão por cenário (ex.: esp, li, ls) lado a lado: gsf_<n>, pld_<n>, x_<n>, cor_<n>."""
    tabelas = []
    for nome, ref in referencias.items():
        p = prever(prep, ref).set_index(["deck", "alvo", "h"])
        tabelas.append(
            p[["gsf_medio", "pld_medio", "x_medio", "cor_media"]].set_axis(
                [f"gsf_{nome}", f"pld_{nome}", f"x_{nome}", f"cor_{nome}"], axis=1
            )
        )
    return pd.concat(tabelas, axis=1, join="inner").reset_index()


def probabilidade_calibrada(x_medio: float, sigma: float, gsf_medio: float) -> pd.Series:
    """Probabilidade de cada cor com X real ~ Normal(X médio, σ); GSF ≥ 0,96 é verde com 100%."""
    if gsf_medio >= MODELO.gsf_verde:
        return pd.Series([1.0, 0.0, 0.0, 0.0], index=regra.CORES)
    acumulada = norm.cdf(list(regra.LIMITES_X.values()), loc=x_medio, scale=sigma)
    return pd.Series(np.diff(np.r_[0.0, acumulada, 1.0]), index=regra.CORES)


def sigma_disponivel(
    previsoes: pd.DataFrame,
    deck: pd.Period,
    minimo: int = MODELO.minimo_erros_sigma,
    horizontes=None,
) -> tuple[float, int]:
    """σ do erro de X só com previsões cujo mês-alvo terminou antes do deck (sem vazamento)."""
    ok = (
        (previsoes.alvo < deck)
        & (previsoes.gsf_medio < MODELO.gsf_verde)
        & previsoes.erro_x.notna()
    )
    if horizontes is not None:
        ok &= previsoes.h.isin(list(horizontes))
    erros = previsoes.loc[ok, "erro_x"]
    return (erros.std() if len(erros) >= minimo else np.nan), len(erros)


def grupo_horizonte(h: int) -> tuple[int, ...]:
    return next(g for g in GRUPOS_HORIZONTE if h in g)


def probabilidade_por_grupo(
    historico: pd.DataFrame, deck: pd.Period, h: int, x_medio: float, gsf_medio: float
) -> pd.Series:
    """Probabilidade com σ do grupo de horizonte; sem histórico suficiente, NaN (método suspenso)."""
    sigma, _ = sigma_disponivel(historico, deck, horizontes=grupo_horizonte(h))
    if np.isnan(sigma):
        return pd.Series(np.nan, index=regra.CORES)
    return probabilidade_calibrada(x_medio, sigma, gsf_medio)
