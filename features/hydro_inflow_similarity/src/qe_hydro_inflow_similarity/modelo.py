"""Modelo-v1 (pesquisa: D018, tag `modelo-v1`; pacote de promoção, seção 5, bloco 2).

Persistência ajustada (PER) em cada série: log(ENA do alvo ÷ normal de 30 anos) = a + b·log(ENA dos 3 meses ÷ normal),
ajustada no passado, por mês de emissão e antecedência h; membros = ponto + resíduo de cada ano passado.
N, NE e S: PER direto. SE: PER no SE-sul (Paranapanema + Tietê + Paraná incremental) e no SE-resto, somados em
MWmed membro a membro (SPLIT, D016). Só o caminho do v1: os métodos testados na pesquisa (AN1, T1–T8, SIM-A) não
entram.

Posições mensais: t = (ano − 1931)·12 + mês − 1. Toda função que recebe t só lê posições ≤ t (sem vazamento),
exceto `anomalia_alvo`, que usa o alvo de emissões passadas.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Modelo:
    versao: str
    ano_base: int  # posição 0 = janeiro deste ano
    janela_clim: int  # anos do normal do mesmo mês (clim30)
    h_max: int  # antecedência máxima da rodada (meses)
    min_pares: int  # pares mínimos para ajustar a PER; senão a série fica sem previsão
    limiar_regime: float  # |Niño 3.4 relativo de 3 meses| de ENSO forte (camada de El Niño forte)
    k_similares: int  # anos similares
    fase: float  # limiar de fase dos anos similares (N ≥ fase: El Niño; ≤ −fase: La Niña)
    bacias_se_sul: tuple[str, ...]  # bacias do SE-sul (PARANA já incremental)
    min_fatores_mesmo_mes: int  # atualização (U1b): mínimo de meses do mesmo mês do calendário


V1 = Modelo(
    versao="modelo-v1",
    ano_base=1931,
    janela_clim=30,
    h_max=18,
    min_pares=20,
    limiar_regime=1.5,
    k_similares=5,
    fase=0.5,
    bacias_se_sul=("PARANAPANEMA", "TIETE", "PARANA"),
    min_fatores_mesmo_mes=10,
)
MODELO = V1
SUBSISTEMAS = ["SE", "S", "NE", "N"]
SUBSISTEMAS_PER = ["N", "NE", "S"]
NOMES = ["SE", "SE-sul", "SE-resto", "S", "NE", "N"]


@dataclass
class Serie:
    """ENA de uma série (% MLT) e o Niño 3.4 relativo de 3 meses, alinhados por posição mensal."""

    nome: str
    pct: np.ndarray  # % MLT; NaN onde não há mês completo
    enso3: np.ndarray  # média dos 3 meses até a posição


def posicao(data, m: Modelo = MODELO) -> int:
    d = pd.Timestamp(data)
    return (d.year - m.ano_base) * 12 + d.month - 1


def data_da_posicao(t: int, m: Modelo = MODELO) -> pd.Timestamp:
    return pd.Timestamp(year=m.ano_base + t // 12, month=t % 12 + 1, day=1)


def _datas_e_enso(ena: pd.DataFrame, indices: pd.DataFrame, m: Modelo):
    datas = pd.date_range(f"{m.ano_base}-01-01", ena.data.max(), freq="MS")
    enso3 = indices["nino34_rel"].rolling(3, min_periods=3).mean().reindex(datas).to_numpy()
    return datas, enso3


def montar_series(ena: pd.DataFrame, indices: pd.DataFrame, m: Modelo = MODELO) -> dict[str, Serie]:
    """Subsistemas, só meses completos."""
    ena = ena[(ena.nivel == "subsistema") & ena.completo]
    datas, enso3 = _datas_e_enso(ena, indices, m)
    return {
        nome: Serie(nome, g.set_index("data").pct_mlt.reindex(datas).to_numpy(), enso3)
        for nome, g in ena.groupby("nome")
    }


def montar_blocos(ena: pd.DataFrame, indices: pd.DataFrame, m: Modelo = MODELO):
    """(séries, MLT por posição) de SE, SE-sul e SE-resto, somados em MWmed e em MLT; só meses completos."""
    ena = ena[ena.completo]
    datas, enso3 = _datas_e_enso(ena, indices, m)
    se = ena[(ena.nivel == "subsistema") & (ena.nome == "SE")].set_index("data")
    sul = (
        ena[(ena.nivel == "bacia") & ena.nome.isin(m.bacias_se_sul)]
        .groupby("data")[["mwmed", "mlt"]]
        .sum()
    )
    mw = {"SE": se.mwmed, "SE-sul": sul.mwmed, "SE-resto": se.mwmed - sul.mwmed}
    mlt = {"SE": se.mlt, "SE-sul": sul.mlt, "SE-resto": se.mlt - sul.mlt}
    series, mlts = {}, {}
    for nome, energia in mw.items():
        x = mlt[nome].reindex(datas)
        series[nome] = Serie(nome, (energia.reindex(datas) / x * 100).to_numpy(), enso3)
        mlts[nome] = x.to_numpy()
    return series, mlts


# --- normais conhecidos na emissão --------------------------------------------------------------------------


def _valores_do_mes(pct: np.ndarray, t: int, mes_cal: int) -> np.ndarray:
    """Valores do mês do calendário `mes_cal` (0–11) com posição ≤ t, em ordem cronológica."""
    v = pct[np.arange(mes_cal, t + 1, 12)]
    return v[~np.isnan(v)]


def clim30(pct: np.ndarray, t: int, mes_cal: int, m: Modelo = MODELO) -> float:
    """Normal do mês do calendário: média dos últimos `janela_clim` valores com posição ≤ t."""
    return float(np.mean(_valores_do_mes(pct, t, mes_cal)[-m.janela_clim :]))


def anomalia_inicial(s: Serie, t: int) -> float:
    """log(ENA média dos 3 meses até t ÷ média dos normais desses 3 meses), com os normais conhecidos em t."""
    meses = [t - 2, t - 1, t]
    obs = np.mean(s.pct[meses])
    ref = np.mean([clim30(s.pct, t, x % 12) for x in meses])
    return float(np.log(obs / ref))


def anomalia_alvo(s: Serie, t: int, h: int) -> float:
    """log(ENA em t+h ÷ normal do mês-alvo conhecido em t). Usa o alvo: só para emissões passadas."""
    return float(np.log(s.pct[t + h] / clim30(s.pct, t, (t + h) % 12)))


# --- PER --------------------------------------------------------------------------------------------------------


def _emissoes_passadas(t: int, h: int) -> np.ndarray:
    """Emissões do mesmo mês do calendário de t com o alvo p + h já conhecido em t (um ano de margem no início)."""
    return np.arange(t % 12 + 12, t - h + 1, 12)


def ajuste_per(
    s: Serie, t: int, h: int, m: Modelo = MODELO
) -> tuple[float, dict[int, float]] | None:
    """Regressão da PER ajustada em t: (ponto em log para a emissão t, resíduo de cada emissão passada p)."""
    passadas = [
        p
        for p in _emissoes_passadas(t, h)
        if not np.isnan(s.pct[p + h]) and not np.isnan(s.pct[p - 2 : p + 1]).any()
    ]
    if len(passadas) < m.min_pares:
        return None
    x = np.array([anomalia_inicial(s, p) for p in passadas])
    y = np.array([anomalia_alvo(s, p, h) for p in passadas])
    b, a = np.polyfit(x, y, 1)
    residuos = y - (a + b * x)
    return a + b * anomalia_inicial(s, t), dict(zip(passadas, residuos, strict=True))


def membros_per_por_ano(s: Serie, t: int, h: int) -> dict[int, float] | None:
    """Membros da PER (% MLT) indexados pela emissão passada p."""
    ajuste = ajuste_per(s, t, h)
    if ajuste is None:
        return None
    ponto, residuos = ajuste
    base = clim30(s.pct, t, (t + h) % 12)
    return {p: base * np.exp(ponto + r) for p, r in residuos.items()}


def membros_per(s: Serie, t: int, h: int) -> np.ndarray | None:
    por_ano = membros_per_por_ano(s, t, h)
    return None if por_ano is None else np.array(list(por_ano.values()))


def membros_c30(s: Serie, t: int, h: int, m: Modelo = MODELO) -> np.ndarray:
    """Climatologia dos últimos 30 anos do mês-alvo (referência do desempenho)."""
    return _valores_do_mes(s.pct, t, (t + h) % 12)[-m.janela_clim :]


def membros_ch(s: Serie, t: int, h: int) -> np.ndarray:
    """Climatologia de todos os anos do mês-alvo (referência do desempenho)."""
    return _valores_do_mes(s.pct, t, (t + h) % 12)


def mlt_do_alvo(mlts: dict, nome: str, t: int, h: int) -> float:
    """MLT do mês-alvo t+h: igual em todos os anos (MLT vigente), lida numa posição ≤ t do mesmo mês."""
    return mlts[nome][t + h - 12 * ((h + 11) // 12)]


def juntar(sul: dict | None, resto: dict | None, mlts: dict, t: int, h: int) -> np.ndarray | None:
    """SE (% MLT) = (SE-sul em MWmed + SE-resto em MWmed) ÷ MLT do SE, membro a membro pelo mesmo ano p."""
    if sul is None or resto is None:
        return None
    comuns = sorted(set(sul) & set(resto))
    ms, mr, mse = (mlt_do_alvo(mlts, n, t, h) for n in ("SE-sul", "SE-resto", "SE"))
    total = [sul[p] / 100 * ms + resto[p] / 100 * mr for p in comuns]
    return np.array(total) / mse * 100


def membros_v1(
    series: dict, blocos: dict, mlts: dict, nome: str, t: int, h: int
) -> np.ndarray | None:
    """Membros (% MLT) do modelo-v1 para um subsistema ou bloco do SE."""
    if nome in SUBSISTEMAS_PER:
        return membros_per(series[nome], t, h)
    if nome == "SE":
        sul = membros_per_por_ano(blocos["SE-sul"], t, h)
        resto = membros_per_por_ano(blocos["SE-resto"], t, h)
        return juntar(sul, resto, mlts, t, h)
    return membros_per(blocos[nome], t, h)  # SE-sul ou SE-resto


def resumo(membros: np.ndarray) -> dict:
    p10, p50, p90 = np.quantile(membros, [0.1, 0.5, 0.9])
    return {"media": float(np.mean(membros)), "p10": p10, "p50": p50, "p90": p90}


def prever_v1(
    ena: pd.DataFrame, indices: pd.DataFrame, emissao=None, h_max: int | None = None
) -> pd.DataFrame:
    """Previsão do modelo-v1 emitida no fim do mês `emissao` (padrão: último mês completo), h = 1..h_max."""
    m = MODELO
    h_max = h_max or m.h_max
    series = montar_series(ena, indices)
    blocos, mlts = montar_blocos(ena, indices)
    pct_se = blocos["SE"].pct
    t = int(np.flatnonzero(~np.isnan(pct_se))[-1]) if emissao is None else posicao(emissao)
    linhas = []
    for nome in NOMES:
        for h in range(1, h_max + 1):
            x = membros_v1(series, blocos, mlts, nome, t, h)
            if x is None:
                continue
            linha = {
                "versao": m.versao,
                "nome": nome,
                "emissao": data_da_posicao(t),
                "h": h,
                "alvo": data_da_posicao(t + h),
                **resumo(x),
                "n_membros": len(x),
            }
            if nome in mlts:
                linha["anomalia_gw"] = (
                    (linha["media"] / 100 - 1) * mlt_do_alvo(mlts, nome, t, h) / 1000
                )
            linhas.append(linha)
    return pd.DataFrame(linhas)


def crps_justo(membros: np.ndarray, obs: float) -> float:
    """CRPS "justo" de um conjunto (Ferro, 2014): não penaliza conjuntos pequenos."""
    k = len(membros)
    termo_obs = np.mean(np.abs(membros - obs))
    termo_disp = np.abs(membros[:, None] - membros[None, :]).sum() / (2 * k * (k - 1))
    return float(termo_obs - termo_disp)
