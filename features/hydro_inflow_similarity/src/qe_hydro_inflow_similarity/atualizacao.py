"""Atualização com o mês em curso (pesquisa: seção 23, D021, U1b; pacote, seção 5, bloco 3).

No dia N do mês M: o mês M é estimado pela média dos N dias observados, e o modelo-v1 é reemitido em M com essa
estimativa no lugar do observado. O mês M em si tem como membros a estimativa ÷ (parcial ÷ mês inteiro) de meses
anteriores do mesmo mês do calendário (U1b; se houver menos de `min_fatores_mesmo_mes`, de todos os meses).
A atualização não é rodada: não é registrada; vale até o mês fechar.
"""

import numpy as np
import pandas as pd

from qe_hydro_inflow_similarity import modelo as M

NOMES = ["SE", "S", "NE", "N", "SE-sul", "SE-resto"]


def mwmed_diario(sub: pd.DataFrame, bac: pd.DataFrame, m: M.Modelo = M.MODELO) -> pd.DataFrame:
    """ENA bruta diária (MWmed) por subsistema e bloco do SE: colunas NOMES, índice = data."""
    d = sub.pivot(index="data", columns="nome", values="bruta_mwmed")
    d["SE-sul"] = bac[bac.nome.isin(m.bacias_se_sul)].groupby("data").bruta_mwmed.sum()
    d["SE-resto"] = d["SE"] - d["SE-sul"]
    return d[NOMES]


def fator_parcial(diario: pd.DataFrame, dias: int) -> pd.DataFrame:
    """Média dos primeiros `dias` dias ÷ média do mês inteiro, por mês completo (índice = 1º dia) e nome."""
    mes = diario.index.to_period("M").to_timestamp()
    cheio = diario.groupby(mes).mean()
    filtro = diario.index.day <= dias
    parcial = diario[filtro].groupby(mes[filtro]).mean()
    completos = (
        diario.groupby(mes).size() == mes.to_series().groupby(mes).first().dt.days_in_month.values
    )
    return (parcial / cheio)[completos.values]


def razoes_passadas(passados: pd.DataFrame, mes: int, m: M.Modelo = M.MODELO) -> dict:
    """Fatores de meses anteriores: só do mesmo mês do calendário, se houver o mínimo; senão todos (U1b)."""
    saida = {}
    for k in NOMES:
        x = passados[k].dropna()
        if (x.index.month == mes).sum() >= m.min_fatores_mesmo_mes:
            x = x[x.index.month == mes]
        saida[k] = x.to_numpy()
    return saida


def _com_mes_estimado(s: M.Serie, t: int, valor: float) -> M.Serie:
    pct = s.pct.copy()
    pct[t] = valor
    return M.Serie(s.nome, pct, s.enso3)


def prever_atualizacao(
    series, blocos, mlts, t: int, estimativas: dict, fatores: dict, h_max: int
) -> dict:
    """Membros por (nome, h), h = 0 (o próprio mês em curso) até h_max; o SE pela soma dos blocos."""
    mod = {k: _com_mes_estimado(series[k], t, estimativas[k]) for k in ["S", "NE", "N"]}
    mod.update({k: _com_mes_estimado(blocos[k], t, estimativas[k]) for k in ["SE-sul", "SE-resto"]})
    saida = {(nome, 0): estimativas[nome] / fatores[nome] for nome in NOMES}
    for h in range(1, h_max + 1):
        for nome in ["S", "NE", "N", "SE-sul", "SE-resto"]:
            saida[(nome, h)] = M.membros_per(mod[nome], t, h)
        sul = M.membros_per_por_ano(mod["SE-sul"], t, h)
        resto = M.membros_per_por_ano(mod["SE-resto"], t, h)
        saida[("SE", h)] = M.juntar(sul, resto, mlts, t, h)
    return saida


def atualizacao(
    ena: pd.DataFrame, indices: pd.DataFrame, diario: pd.DataFrame, h_max: int = 11
) -> dict | None:
    """Atualização emitida com os dias observados do último mês da ENA; None se esse mês estiver completo.

    `diario` = `mwmed_diario` da ENA diária. Saída por (nome, h): membros (array) e o mês, os dias e a data final.
    """
    sub = ena[ena.nivel == "subsistema"]
    data = sub.data.max()
    if sub[sub.data == data].completo.all():
        return None
    dias = int((diario.index.to_period("M") == data.to_period("M")).sum())
    fatores = fator_parcial(diario[diario.index < data], dias)
    e = ena.assign(
        completo=ena.completo | (ena.data == data)
    )  # o mês parcial entra como estimativa
    series = M.montar_series(e, indices)
    blocos, mlts = M.montar_blocos(e, indices)
    t = M.posicao(data)
    estimativas = {k: (blocos[k].pct[t] if k in blocos else series[k].pct[t]) for k in NOMES}
    membros = prever_atualizacao(
        series, blocos, mlts, t, estimativas, razoes_passadas(fatores, data.month), h_max
    )
    return {
        "data": data,
        "dias": dias,
        "ate": diario.index.max(),
        "t": t,
        "mlts": mlts,
        "membros": membros,
    }


def _r(v, c=1):
    return None if v is None or not np.isfinite(v) else round(float(v), c)


def resumo_atualizacao(a: dict) -> dict:
    """O que a página mostra: média, p10, p50, p90 e anomalia em GWmed (SE e blocos) por (nome, h)."""
    previsoes = []
    for (nome, h), x in a["membros"].items():
        if x is None:
            continue
        linha = {
            "nome": nome,
            "h": h,
            "alvo": f"{a['data'] + pd.DateOffset(months=h):%Y-%m}",
            "media": _r(np.mean(x)),
            "p10": _r(np.quantile(x, 0.1)),
            "p50": _r(np.quantile(x, 0.5)),
            "p90": _r(np.quantile(x, 0.9)),
        }
        if nome in a["mlts"]:
            mlt = M.mlt_do_alvo(a["mlts"], nome, a["t"], h) if h else a["mlts"][nome][a["t"]]
            linha["anomalia_gw"] = _r((np.mean(x) / 100 - 1) * mlt / 1000, 2)
        previsoes.append(linha)
    return {
        "mes": f"{a['data']:%Y-%m}",
        "dias": a["dias"],
        "ate": f"{a['ate']:%Y-%m-%d}",
        "previsoes": previsoes,
    }
