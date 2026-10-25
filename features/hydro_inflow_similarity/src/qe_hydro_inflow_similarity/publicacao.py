"""Publicação: serving/hydro_inflow_similarity/<página>.json (o que as páginas leem) e a rodada do mês.

Pesquisa: web.py (dados_produto, dados_fundamentos, dados_metodologia, dados_clima). Contas no Python, desenho no
JS. Quatro arquivos, um por página: produto.json, fundamentos.json, metodologia.json e clima.json.

Os fatos descritivos da página de fundamentos que vêm dos notebooks da pesquisa (correlações defasadas, memória
entre estações, ENA por década, bacias em El Niño forte, pesos do T7) entram como dado estático da versão
(`estaticos/`, decisão 4 da promoção); o resto é calculado aqui.
"""

import datetime as dt
from importlib import resources
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from qe_core.armazenamento import Armazenamento, gravar_json, ler_parquet
from qe_core.leitores import noaa
from qe_hydro_inflow_similarity import atualizacao as U
from qe_hydro_inflow_similarity import backtest as B
from qe_hydro_inflow_similarity import chaves, rodadas
from qe_hydro_inflow_similarity import modelo as M
from qe_hydro_inflow_similarity import similares as S

MESES_HISTORICO = 24
NOMES = ["SE", "SE-sul", "SE-resto", "S", "NE", "N"]
SUBS = ["SE", "S", "NE", "N"]
BACIAS_SE_SUL = list(M.MODELO.bacias_se_sul)
FORTES = [
    1965,
    1972,
    1982,
    1997,
    2015,
]  # El Niños fortes pelo Niño 3.4 relativo OND ≥ 1,5 (pesquisa, seção 3.1)
MESES_UMIDO = [11, 12, 1, 2, 3, 4]
CLASSES_ENSO = [("El Niño forte", 1.5), ("El Niño moderado", 1.0), ("El Niño fraco", 0.5), ("Neutro", -0.5),
                ("La Niña", -np.inf)]  # fmt: skip
GRUPOS_BACIA = {  # bacias que o subsistema contém por inteiro; "demais" = subsistema − Σ (fecha exatamente)
    "SE": ["PARANAPANEMA", "TIETE", "PARANA", "GRANDE", "PARANAIBA"],
    "S": ["IGUACU", "URUGUAI", "JACUI"],
    "NE": ["SAO FRANCISCO"],
    "N": [],
}


def _r(v, c=1):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), c)


def _agora() -> str:
    return dt.datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat(timespec="seconds")


def _estatico(nome: str) -> pd.DataFrame:
    arq = resources.files("qe_hydro_inflow_similarity") / "estaticos" / nome
    with resources.as_file(arq) as p:
        return pd.read_parquet(p) if nome.endswith(".parquet") else pd.read_csv(p)


# --- fatos (pesquisa: fatos.py) -------------------------------------------------------------------------------


def ena_umido(ena: pd.DataFrame) -> pd.DataFrame:
    """ENA do período úmido (nov/Y–abr/Y+1) em % MLT, ponderada por energia; só períodos com os 6 meses."""
    u = ena[ena.mes.isin(MESES_UMIDO) & ena.completo].copy()
    u["ano"] = np.where(u.mes >= 11, u.ano, u.ano - 1)
    g = u.groupby(["nivel", "nome", "ano"]).agg(
        mwmed=("mwmed", "sum"), mlt=("mlt", "sum"), n=("mes", "size")
    )
    g = g[g.n == len(MESES_UMIDO)]
    return (g.mwmed / g.mlt * 100).rename("pct_mlt").reset_index()


def pct_estacao(ena: pd.DataFrame, meses) -> pd.DataFrame:
    """% MLT ponderado por energia num conjunto de meses do mesmo ano civil, por subsistema e ano."""
    s = ena[(ena.nivel == "subsistema") & ena.completo & ena.mes.isin(meses)]
    g = s.groupby(["nome", "ano"]).agg(
        mwmed=("mwmed", "sum"), mlt=("mlt", "sum"), n=("mes", "size")
    )
    g = g[g.n == len(meses)]
    return (g.mwmed / g.mlt * 100).unstack(0)


def fase_enso(indices: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por ano: Niño 3.4 relativo médio de out–dez e classe (e o ONI de out–dez)."""
    ond = indices[indices.index.month.isin([10, 11, 12])]
    por_ano = ond.groupby(ond.index.year).agg(
        valor=("nino34_rel", "mean"), oni=("oni", "mean"), n=("nino34_rel", "count")
    )
    por_ano = por_ano[por_ano.n == 3].drop(columns="n")
    por_ano["classe"] = por_ano.valor.map(lambda v: next(r for r, lim in CLASSES_ENSO if v >= lim))
    por_ano.index.name = "ano"
    return por_ano.reset_index()


def compostos_enso(umido: pd.DataFrame, fases: pd.DataFrame, defasagem: int = 0) -> pd.DataFrame:
    """ENA do período úmido com a classe do ENSO do ano Y − defasagem."""
    f = fases.assign(ano=fases.ano + defasagem)
    return umido.merge(f[["ano", "classe", "valor"]], on="ano")


# --- página de produto -------------------------------------------------------------------------------------------


def historico_observado(ena: pd.DataFrame, fim: pd.Timestamp) -> dict:
    """% MLT e anomalia em GWmed dos últimos meses, por subsistema e bloco do SE (o último mês pode ser parcial)."""
    inicio = fim - pd.DateOffset(months=MESES_HISTORICO - 1)
    e = ena[(ena.data >= inicio) & (ena.data <= fim)]
    sub = e[e.nivel == "subsistema"].pivot(index="data", columns="nome", values=["mwmed", "mlt"])
    bac = (
        e[(e.nivel == "bacia") & e.nome.isin(BACIAS_SE_SUL)].groupby("data")[["mwmed", "mlt"]].sum()
    )
    completo = e[(e.nivel == "subsistema") & (e.nome == "SE")].set_index("data").completo
    mw = {n: sub["mwmed"][n] for n in SUBS}
    mlt = {n: sub["mlt"][n] for n in SUBS}
    mw["SE-sul"], mlt["SE-sul"] = bac.mwmed, bac.mlt
    mw["SE-resto"], mlt["SE-resto"] = mw["SE"] - bac.mwmed, mlt["SE"] - bac.mlt
    principais = ["PARANAPANEMA", "PARANA", "GRANDE", "PARANAIBA"]
    b = e[(e.nivel == "bacia") & e.nome.isin(principais)].pivot(
        index="data", columns="nome", values="pct_mlt"
    )
    return {
        "meses": [f"{d:%Y-%m}" for d in sub.index],
        "parcial": [not bool(completo.get(d, True)) for d in sub.index],
        "pct": {n: [_r(v) for v in (mw[n] / mlt[n] * 100)] for n in NOMES},
        "gw": {n: [_r(v, 2) for v in (mw[n] - mlt[n]) / 1000] for n in NOMES},
        "bacias": {nome: [_r(v) for v in b[nome]] for nome in principais},
    }


def ano_atual(emissao: str) -> int:
    """Ano Y do ciclo jul/Y–jun/Y+1 que contém a emissão."""
    ano, mes = int(emissao[:4]), int(emissao[5:7])
    return ano if mes >= 7 else ano - 1


def contribuicao(ena: pd.DataFrame, fim: pd.Timestamp) -> dict:
    """Anomalia em GWmed (MWmed − MLT) por bacia e o resto de cada subsistema, últimos meses."""
    inicio = fim - pd.DateOffset(months=MESES_HISTORICO - 1)
    e = ena[(ena.data >= inicio) & (ena.data <= fim)].assign(
        anom=lambda d: (d.mwmed - d.mlt) / 1000
    )
    sub = e[e.nivel == "subsistema"].pivot(index="data", columns="nome", values="anom")
    bac = e[e.nivel == "bacia"].pivot(index="data", columns="nome", values="anom")
    saida = {}
    for nome, grupo in GRUPOS_BACIA.items():
        partes = {b: bac[b] for b in grupo}
        partes["demais"] = sub[nome] - (bac[grupo].sum(axis=1) if grupo else 0)
        saida[nome] = {k: [_r(v, 2) for v in serie] for k, serie in partes.items()}
    return saida


def umido_por_ano(ena: pd.DataFrame, indices: pd.DataFrame) -> dict:
    """ENA de cada período úmido (% MLT) por subsistema e bloco do SE, com a fase do ENSO de Y."""
    fases = fase_enso(indices).set_index("ano").valor
    sub = (
        ena_umido(ena)
        .query("nivel == 'subsistema'")
        .pivot(index="ano", columns="nome", values="pct_mlt")
    )
    e = ena[ena.completo & ena.mes.isin(MESES_UMIDO)].assign(
        ano_u=lambda d: np.where(d.mes >= 11, d.ano, d.ano - 1)
    )
    se = e[(e.nivel == "subsistema") & (e.nome == "SE")].groupby("ano_u")[["mwmed", "mlt"]].sum()
    sul = (
        e[(e.nivel == "bacia") & e.nome.isin(BACIAS_SE_SUL)]
        .groupby("ano_u")[["mwmed", "mlt"]]
        .sum()
    )
    blocos = {
        "SE-sul": sul.mwmed / sul.mlt * 100,
        "SE-resto": (se.mwmed - sul.mwmed) / (se.mlt - sul.mlt) * 100,
    }

    def fase(v):
        if np.isnan(v):
            return None
        return "El Niño forte" if v >= 1.5 else "La Niña forte" if v <= -1.0 else "outro"

    dados = {
        "anos": sub.index.tolist(),
        "fase": [fase(v) for v in fases.reindex(sub.index)],
        "enso": [_r(v, 2) for v in fases.reindex(sub.index)],
    }
    dados.update({k: [_r(v) for v in sub[k]] for k in SUBS})
    dados.update({k: [_r(v) for v in serie.reindex(sub.index)] for k, serie in blocos.items()})
    return dados


def enso_recente(indices: pd.DataFrame, fim: pd.Timestamp) -> dict:
    inicio = fim - pd.DateOffset(months=MESES_HISTORICO - 1)
    i = indices[(indices.index >= inicio) & (indices.index <= fim)]
    tres = indices.nino34_rel.rolling(3).mean().reindex(i.index)
    return {
        "meses": [f"{d:%Y-%m}" for d in i.index],
        "mensal": [_r(v, 2) for v in i.nino34_rel],
        "tres_meses": [_r(v, 2) for v in tres],
        "oni": [_r(v, 2) for v in i.oni],
    }


def enso_similares(
    indices: pd.DataFrame, fim: pd.Timestamp, anos, ano_ref: int, meses_depois: int = 9
) -> dict:
    """Niño 3.4 relativo dos anos similares no calendário de hoje, nos 24 meses até `fim` e `meses_depois` meses."""
    inicio = fim - pd.DateOffset(months=MESES_HISTORICO - 1)
    datas = pd.date_range(inicio, fim + pd.DateOffset(months=meses_depois), freq="MS")
    n34 = indices.nino34_rel
    return {
        "meses": [f"{d:%Y-%m}" for d in datas],
        "anos": {
            str(a): [_r(v, 2) for v in n34.reindex(datas - pd.DateOffset(years=ano_ref - a))]
            for a in anos
        },
    }


def trajetorias_mensais(ena: pd.DataFrame, anos) -> dict:
    """ENA mensal (% MLT) de jul/Y a jun/Y+2 de cada ano Y, por subsistema e bloco do SE; marca o mês parcial."""
    mensal = ena[ena.nivel == "subsistema"].pivot(index="data", columns="nome", values="pct_mlt")
    b = (
        ena[(ena.nivel == "bacia") & ena.nome.isin(BACIAS_SE_SUL)]
        .groupby("data")[["mwmed", "mlt"]]
        .sum()
    )
    s_se = ena[(ena.nivel == "subsistema") & (ena.nome == "SE")].set_index("data")
    mensal["SE-sul"] = b.mwmed / b.mlt * 100
    mensal["SE-resto"] = (s_se.mwmed - b.mwmed) / (s_se.mlt - b.mlt) * 100
    parcial = s_se.completo
    saida = {}
    for ano in anos:
        janela = mensal.loc[f"{ano}-07-01" : f"{ano + 2}-06-01"]
        saida[str(ano)] = {
            "parcial": [not bool(parcial.get(d, True)) for d in janela.index],
            **{k: [_r(v) for v in janela[k]] for k in NOMES},
        }
    return saida


def armazenavel_mensal(sub_d: pd.DataFrame, bac_d: pd.DataFrame) -> pd.DataFrame:
    """ENA armazenável mensal em % da MLT da época (ENA diária, 2000–hoje), por subsistema e bloco do SE.
    Para os blocos, a MLT da época vem da própria ENA bruta (MWmed ÷ % MLT), somada nas bacias."""

    def mes(d):
        return d.data.dt.to_period("M").dt.to_timestamp()

    sub = sub_d.assign(mes=mes(sub_d)).groupby(["mes", "nome"]).armazenavel_pct_mlt.mean().unstack()
    bac = bac_d[bac_d.nome.isin(BACIAS_SE_SUL)].assign(
        mlt_epoca=lambda d: d.bruta_mwmed / d.bruta_pct_mlt * 100
    )
    bac = (
        bac.assign(mes=mes(bac)).groupby(["mes", "data"])[["armazenavel_mwmed", "mlt_epoca"]].sum()
    )
    bac = bac.groupby(level="mes").mean()
    sub["SE-sul"] = bac.armazenavel_mwmed / bac.mlt_epoca * 100
    se = sub_d.query("nome == 'SE'")
    se = (
        se.assign(mes=mes(se), mlt_epoca=se.bruta_mwmed / se.bruta_pct_mlt * 100)
        .groupby("mes")[["armazenavel_mwmed", "mlt_epoca"]]
        .mean()
    )
    sub["SE-resto"] = (
        (se.armazenavel_mwmed - bac.armazenavel_mwmed) / (se.mlt_epoca - bac.mlt_epoca) * 100
    )
    return sub


def trajetorias_produto(ena, indices, arm_mensal: pd.DataFrame, anos) -> dict:
    """% MLT, anomalia em GWmed, ENA armazenável (desde 2000) e Niño 3.4 relativo, jul/Y a jun/Y+2."""
    base = trajetorias_mensais(ena, anos)
    e = ena.assign(anom=(ena.mwmed - ena.mlt) / 1000)
    gw = e[e.nivel == "subsistema"].pivot(index="data", columns="nome", values="anom")
    b = e[(e.nivel == "bacia") & e.nome.isin(BACIAS_SE_SUL)].groupby("data").anom.sum()
    gw["SE-sul"], gw["SE-resto"] = b, gw["SE"] - b
    n34 = indices.nino34_rel
    for ano in anos:
        datas = pd.date_range(f"{ano}-07-01", f"{ano + 2}-06-01", freq="MS")
        g, a = gw.reindex(datas), arm_mensal.reindex(datas)
        base[str(ano)]["gw"] = {k: [_r(v, 2) for v in g[k]] for k in NOMES}
        base[str(ano)]["armazenavel"] = (
            {k: [_r(v) for v in a[k]] for k in NOMES} if ano >= 2000 else None
        )
        base[str(ano)]["enso"] = [_r(v, 2) for v in n34.reindex(datas)]
    return base


def mlt_blocos(mlt: pd.DataFrame) -> dict:
    """MLT mensal (MWmed) do SE-sul (soma das bacias) e do SE-resto (SE − SE-sul)."""
    sul = mlt[(mlt.nivel == "bacia") & mlt.nome.isin(BACIAS_SE_SUL)].groupby("mes").mlt.sum()
    se = mlt[(mlt.nivel == "subsistema") & (mlt.nome == "SE")].set_index("mes").mlt
    return {
        "SE-sul": [_r(sul[m], 0) for m in range(1, 13)],
        "SE-resto": [_r(se[m] - sul[m], 0) for m in range(1, 13)],
    }


def _desempenho_similares(res: pd.DataFrame, enso3) -> list[dict]:
    t = B.desempenho_similares(res, enso3)
    return [
        {
            "nome": r.nome,
            "recorte": r.recorte,
            "ref": r.ref,
            "crpss": _r(r.crpss, 3),
            "ic05": _r(r.ic05, 3),
            "ic95": _r(r.ic95, 3),
        }
        for r in t.itertuples()
    ]


def _habilidade(res: pd.DataFrame) -> dict:
    """CRPSS do modelo-v1 (PER) contra o C30 por h, fora da amostra."""
    t = B.skill_modelo(res)
    t = t[t.metodo == "PER"].sort_values("h")
    return {
        n: {
            "h": t[t.nome == n].h.tolist(),
            "crpss": [_r(v, 3) for v in t[t.nome == n].crpss],
            "ic05": [_r(v, 3) for v in t[t.nome == n].ic05],
            "ic95": [_r(v, 3) for v in t[t.nome == n].ic95],
        }
        for n in SUBS
    }


def dados_produto(arm: Armazenamento, ena, indices, res) -> dict:
    rods = rodadas.ler_historico(arm)
    ultima = rods[-1]
    fim = ena.data.max()
    similares = ultima.get("similares")
    calculado_depois = similares is None
    data = pd.Timestamp(f"{ultima['emissao']}-01")
    e_ate, i_ate = ena[ena.data <= data], indices[indices.index <= data]
    if calculado_depois:  # rodada legada, sem similares: calcula com os dados até a emissão
        blocos, mlts = M.montar_blocos(e_ate, i_ate)
        similares = S.recompor(M.montar_series(e_ate, i_ate), blocos, mlts, M.posicao(data))
    mlt = ler_parquet(arm, chaves.PROC_MLT)
    mlt_sub = mlt.query("nivel == 'subsistema'").set_index(["nome", "mes"]).mlt
    sub_d, bac_d = (ler_parquet(arm, chaves.PROC_DIARIA[n]) for n in ("subsistema", "bacia"))
    atual = U.atualizacao(ena, indices, U.mwmed_diario(sub_d, bac_d))
    atual = None if atual is None else {**U.resumo_atualizacao(atual), "gerada_em": _agora()}
    anos_sim = [a["ano"] for a in similares.get("anos", [])]
    y = ano_atual(ultima["emissao"])
    enso_fim = indices.nino34_rel.dropna().index.max()
    enso3 = M.montar_series(ena[ena.data <= res.alvo.max()], indices)["SE"].enso3
    return {
        "atualizacao": atual,
        "similares": {**similares, "calculado_depois": calculado_depois},
        "similares_desempenho": _desempenho_similares(res, enso3),
        "umido": umido_por_ano(ena, indices),
        "trajetorias": {
            "ano_atual": y,
            "fortes": FORTES,
            "anos": trajetorias_produto(
                ena, indices, armazenavel_mensal(sub_d, bac_d), sorted({*anos_sim, *FORTES, y})
            ),
        },
        "contribuicao": contribuicao(ena, fim),
        "mlt_sub": {
            **{n: [_r(mlt_sub[(n, m)], 0) for m in range(1, 13)] for n in SUBS},
            **mlt_blocos(mlt),
        },
        "gerado_em": _agora(),
        "rodada": ultima,
        "rodadas": [
            {
                "id": r["id"],
                "emissao": r["emissao"],
                "tipo": r["tipo"],
                "registrada_em": r["registrada_em"],
                "versao": r["versao"],
                "regime": r["insumos"]["regime_enso"],
                "nino3m": r["insumos"]["nino34_rel_3m"],
            }
            for r in rods
        ],
        "observado": historico_observado(ena, fim),
        "enso": enso_recente(indices, enso_fim),
        "enso_similares": enso_similares(indices, enso_fim, anos_sim, int(ultima["emissao"][:4])),
        "habilidade": _habilidade(res),
    }


# --- fundamentos -------------------------------------------------------------------------------------------------


def dados_fundamentos(ena, indices) -> dict:
    """Fatos da pesquisa (seção 3 da metodologia), descritivos, amostra inteira."""
    from scipy import stats

    fases = fase_enso(indices)
    fortes = fases.loc[fases.classe == "El Niño forte", "ano"].tolist()
    umido = ena_umido(ena)
    j0, j1 = compostos_enso(umido, fases, 0), compostos_enso(umido, fases, 1)

    def pontos(j):
        j = j[j.nivel == "subsistema"]
        return {
            nome: [
                {"ano": int(r.ano), "classe": r.classe, "v": _r(r.pct_mlt)} for r in g.itertuples()
            ]
            for nome, g in j.groupby("nome")
        }

    sub = umido[umido.nivel == "subsistema"].pivot(index="ano", columns="nome", values="pct_mlt")
    e = ena[ena.completo & ena.mes.isin(MESES_UMIDO)].copy()
    e["ano_u"] = np.where(e.mes >= 11, e.ano, e.ano - 1)
    se = e[(e.nivel == "subsistema") & (e.nome == "SE")].groupby("ano_u")[["mwmed", "mlt"]].sum()
    sul = (
        e[(e.nivel == "bacia") & e.nome.isin(BACIAS_SE_SUL)]
        .groupby("ano_u")[["mwmed", "mlt"]]
        .sum()
    )
    n_meses = e[(e.nivel == "subsistema") & (e.nome == "SE")].groupby("ano_u").size()
    ok = n_meses[n_meses == 6].index
    blocos = pd.DataFrame(
        {
            "SE-sul": sul.mwmed / sul.mlt * 100,
            "SE-resto": (se.mwmed - sul.mwmed) / (se.mlt - sul.mlt) * 100,
            "SE": se.mwmed / se.mlt * 100,
        }
    ).loc[ok]
    neutros = fases.loc[fases.classe == "Neutro", "ano"]
    trajetorias = trajetorias_mensais(ena, [*fortes, 2023, 2026])
    anual = pct_estacao(ena, range(1, 13))
    normal = anual.rolling(30, min_periods=30).mean()
    janelas = [(1931, 1960), (1961, 1990), (1995, 2024), (2015, 2024)]
    normais = {f"{a}–{b}": {k: _r(anual.loc[a:b, k].mean()) for k in SUBS} for a, b in janelas}

    def fase_ampliada(v):
        if v >= 1.5:
            return "El Niño forte"
        if v >= 1.0:
            return "El Niño moderado"
        if v >= 0.5:
            return "El Niño fraco"
        if v > -0.5:
            return "Neutro"
        return "La Niña fraca" if v > -1.0 else "La Niña forte"

    fases_amp = fases.assign(classe=fases.valor.map(fase_ampliada))
    umido_b = umido[umido.nivel == "bacia"].merge(fases_amp[["ano", "classe"]], on="ano")
    classes = ["El Niño forte", "El Niño moderado", "La Niña fraca", "La Niña forte"]
    bacias_fase = {}
    for classe in classes:
        linhas = []
        for nome, g in umido_b.groupby("nome"):
            a_, b_ = g[g.classe == classe].pct_mlt, g[g.classe == "Neutro"].pct_mlt
            linhas.append(
                {
                    "nome": nome,
                    "mediana": _r(a_.median()),
                    "p10": _r(a_.quantile(0.1)),
                    "p90": _r(a_.quantile(0.9)),
                    "neutro": _r(b_.median()),
                    "n": len(a_),
                    "p": _r(stats.mannwhitneyu(a_, b_).pvalue, 3),
                }
            )
        bacias_fase[classe] = linhas
    anos_fase = {
        c: sorted(
            int(a)
            for a in fases_amp.loc[
                (fases_amp.classe == c) & fases_amp.ano.between(1931, 2025), "ano"
            ]
        )
        for c in classes
    }
    corr = _estatico("correlacoes_subsistema.parquet")
    corr = corr[
        (corr.preditor == "nino34_rel") & (corr.mes_emissao == 9) & (corr.h <= 12)
    ].sort_values("h")
    memoria = _estatico("memoria_estacoes.csv")
    memoria = memoria[memoria.periodo == "1931–2025"]
    decadas = _estatico("ena_anual_por_decada.csv").set_index("nome")
    bacias = _estatico("bacias_el_nino_forte.csv").sort_values("mediana")
    pesos = _estatico("coeficientes_t7.csv").set_index("nome")
    oni = indices.oni.dropna()
    seguinte = []
    for ano in [1957, 1965, 1972, 1982, 1991, 1997, 2009, 2015, 2023]:
        pico = oni[f"{ano}-06-01" : f"{ano + 1}-04-01"].max()
        depois = oni[f"{ano + 1}-10-01" : f"{ano + 2}-02-01"].mean()
        seguinte.append({"ano": ano, "pico": _r(pico, 2), "seguinte": _r(depois, 2)})
    return {
        "fortes": fortes,
        "umido_anual": {
            "anos": sub.index.tolist(),
            **{k: [_r(v) for v in sub[k]] for k in SUBS},
            "classe": [
                fase_ampliada(v) if not np.isnan(v) else None
                for v in fases.set_index("ano").valor.reindex(sub.index)
            ],
        },
        "umido_blocos": {
            k: [_r(v) for v in blocos[k].reindex(sub.index)] for k in ["SE-sul", "SE-resto"]
        },
        "anual": {
            "anos": anual.index.tolist(),
            **{k: [_r(v) for v in anual[k]] for k in SUBS},
            "normal": {k: [_r(v) for v in normal[k]] for k in SUBS},
        },
        "normais": normais,
        "bacias_fase": bacias_fase,
        "anos_fase": anos_fase,
        "decadas": {
            "decadas": [int(c) for c in decadas.columns],
            **{k: [_r(v) for v in decadas.loc[k]] for k in decadas.index},
        },
        "compostos": {"evento": pontos(j0), "seguinte": pontos(j1)},
        "bacias": [
            {
                "nome": r.nome,
                "mediana": _r(r.mediana),
                "p10": _r(r.p10),
                "p90": _r(r.p90),
                "neutro": _r(r.mediana_neutro),
                "p": _r(r.p, 3),
            }
            for r in bacias.itertuples()
        ],
        "blocos_eventos": {
            str(a): {k: _r(blocos.loc[a, k]) for k in blocos.columns} for a in fortes
        },
        "blocos_neutros": {
            k: _r(blocos.loc[blocos.index.isin(neutros), k].median()) for k in blocos.columns
        },
        "trajetorias": trajetorias,
        "correlacao_set": {
            k: {
                "mes_alvo": g.mes_alvo.tolist(),
                "r": [_r(v, 2) for v in g.r],
                "q": [_r(v, 3) for v in g.q],
            }
            for k, g in corr.groupby("nome")
        },
        "memoria": {r.par: {k: _r(getattr(r, k), 2) for k in SUBS} for r in memoria.itertuples()},
        "pesos_t7": {k: {c: _r(pesos.loc[k, c], 3) for c in pesos.columns} for k in pesos.index},
        "oni_seguinte": seguinte,
    }


# --- metodologia -------------------------------------------------------------------------------------------------


def exemplo_se_sul(ena, indices, emissao: str, h: int = 1) -> dict:
    """Conta de ponta a ponta do modelo-v1 e da recomposição para o SE-sul, com dados só até a emissão."""
    data = pd.Timestamp(f"{emissao}-01")
    e, i = ena[ena.data <= data], indices[indices.index <= data]
    blocos, mlts = M.montar_blocos(e, i)
    s, t = blocos["SE-sul"], M.posicao(data)
    meses = [t - 2, t - 1, t]
    ponto, residuos = M.ajuste_per(s, t, h)
    passadas = list(residuos)
    x_p = np.array([M.anomalia_inicial(s, p) for p in passadas])
    y_p = np.array([M.anomalia_alvo(s, p, h) for p in passadas])
    b, a = np.polyfit(x_p, y_p, 1)
    m = M.membros_per(s, t, h)
    c_hoje = M.clim30(s.pct, t, (t + h) % 12)
    pos, _ = S.anos_similares(blocos["SE"].enso3, t, pct=blocos["SE"].pct)
    anos = [
        {
            "ano": int(M.data_da_posicao(p).year),
            "pct": _r(s.pct[p + h]),
            "normal_epoca": _r(M.clim30(s.pct, p, (p + h) % 12)),
            "razao": _r(np.exp(M.anomalia_alvo(s, p, h)), 3),
            "hoje": _r(c_hoje * np.exp(M.anomalia_alvo(s, p, h))),
        }
        for p in pos
    ]
    alvo = data + pd.DateOffset(months=h)
    obs = ena[(ena.nivel == "bacia") & ena.nome.isin(BACIAS_SE_SUL) & (ena.data == alvo)]
    return {
        "emissao": emissao,
        "alvo": f"{alvo:%Y-%m}",
        "meses": [f"{data - pd.DateOffset(months=k):%Y-%m}" for k in (2, 1, 0)],
        "pct": [_r(s.pct[k]) for k in meses],
        "normal": [_r(M.clim30(s.pct, t, k % 12)) for k in meses],
        "x": _r(M.anomalia_inicial(s, t), 3),
        "a": _r(a, 3),
        "b": _r(b, 3),
        "n_pares": len(passadas),
        "ponto_log": _r(ponto, 3),
        "normal_alvo": _r(c_hoje),
        "mediana": _r(c_hoje * np.exp(ponto)),
        "media": _r(m.mean()),
        "p10": _r(np.quantile(m, 0.1)),
        "p90": _r(np.quantile(m, 0.9)),
        "dp_residuos": _r(np.std(list(residuos.values())), 3),
        "mlt_alvo": _r(mlts["SE-sul"][t + h - 12], 0),
        "n3": _r(blocos["SE"].enso3[t], 2),
        "dn3": _r(blocos["SE"].enso3[t] - blocos["SE"].enso3[t - 3], 2),
        "anos": anos,
        "media_similares": _r(np.mean([q["hoje"] for q in anos])),
        "realizado": _r(obs.mwmed.sum() / obs.mlt.sum() * 100) if len(obs) == 3 else None,
        "realizado_parcial": bool(len(obs) == 3 and not obs.completo.all()),
    }


def dados_metodologia(arm: Armazenamento, ena, indices, res) -> dict:
    rods = rodadas.ler_historico(arm)
    enso3 = M.montar_series(ena[ena.data <= res.alvo.max()], indices)["SE"].enso3
    comp = B.desempenho_comparado(res)
    return {
        "exemplo": exemplo_se_sul(ena, indices, rods[0]["emissao"]),
        "desempenho": [
            {
                "metodo": r.metodo,
                "nome": r.nome,
                "crpss": _r(r.crpss, 3),
                "ic05": _r(r.ic05, 3),
                "ic95": _r(r.ic95, 3),
                "cobertura": _r(r.cobertura_p10_p90, 0),
            }
            for r in comp.itertuples()
        ],
        "habilidade": _habilidade(res),
        "similares_desempenho": _desempenho_similares(res, enso3),
        "rodadas": [
            {
                "emissao": r["emissao"],
                "registrada_em": r["registrada_em"],
                "versao": r["versao"],
                "tipo": r["tipo"],
                "regime": r["insumos"]["regime_enso"],
            }
            for r in rods
        ],
    }


# --- indicadores climáticos --------------------------------------------------------------------------------------

INDICES_CLIMA = {
    "nino34_rel": {"preditor": "nino34_rel", "peso": "cenario", "pesos_t7": ["N", "N·|N|", "ΔN"]},
    "roni": {"preditor": None, "peso": "referencia"},
    "oni": {"preditor": None, "peso": "referencia"},
    "nino12": {"preditor": "nino12", "peso": "contexto"},
    "soi": {"preditor": "soi", "peso": "contexto"},
    "tna": {"preditor": "tna", "peso": "contexto"},
    "tsa": {"preditor": "tsa", "peso": "contexto"},
    "grad_atl": {"preditor": "grad_atl", "peso": "teste", "pesos_t7": ["grad_atl"]},
    "atl_sul_se": {"preditor": "atl_sul_se", "peso": "contexto", "pesos_t7": ["atl_sul_se"]},
    "dmi": {"preditor": "dmi", "peso": "contexto", "pesos_t7": ["dmi"]},
    "aao": {"preditor": "aao", "peso": "contexto"},
    "pdo": {"preditor": "pdo", "peso": "contexto", "pesos_t7": ["pdo"]},
    "amo_rel": {"preditor": "amo_rel", "peso": "contexto"},
    "amo_ncei": {"preditor": None, "peso": "referencia"},
}
# Tabela histórica de cada índice (pesquisa D024): "cpc" (ONI, RONI: ±0,5 °C por 5 trimestres seguidos), "icen"
# (Niño 1+2: critério do ICEN do ENFEN aplicado à nossa série, não é o ICEN oficial) e "intensidade" (cor pelo
# tamanho do desvio, sem episódio; "sinal" = −1 inverte a cor: SOI negativo = El Niño).
TRIMESTRES = ["DJF", "JFM", "FMA", "MAM", "AMJ", "MJJ", "JJA", "JAS", "ASO", "SON", "OND", "NDJ"]
MESES_TAB = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
TABELAS_CLIMA = {
    "roni": {"criterio": "cpc"},
    "oni": {"criterio": "cpc"},
    "nino12": {"criterio": "icen"},
    "nino34_rel": {"criterio": "intensidade", "limiares": [0.5, 1.0, 1.5, 2.0]},
    "soi": {"criterio": "intensidade", "sinal": -1, "casas": 1},
    "dmi": {"criterio": "intensidade"},
    "tna": {"criterio": "intensidade"},
    "tsa": {"criterio": "intensidade"},
    "grad_atl": {"criterio": "intensidade"},
    "pdo": {"criterio": "intensidade"},
    "aao": {"criterio": "intensidade"},
}
CPC_FAIXAS = [0.5, 1.0, 1.5, 2.0]  # fraco, moderado, forte, muito forte
ICEN_QUENTE, ICEN_FRIO = (
    [0.4, 1.0, 1.7, 3.0],
    [-1.0, -1.2, -1.4],
)  # débil, moderado, forte, extraordinário


def _legenda(frio: str, faixas_frio, quente: str, faixas_quente) -> list:
    """[classe, rótulo curto da legenda, rótulo completo do tooltip], do mais frio ao mais quente."""

    def rot(lado, r, nomeia):
        return (f"{lado} {r}" if nomeia else r).strip(), f"{lado} {r}".strip()

    fr = [[-(i + 1), *rot(frio, r, i == len(faixas_frio) - 1)] for i, r in enumerate(faixas_frio)][
        ::-1
    ]
    return fr + [[i + 1, *rot(quente, r, i == 0)] for i, r in enumerate(faixas_quente)]


def _nivel(v: float, limiares) -> int:
    return sum(abs(v) >= abs(lim) for lim in limiares)


def _episodios(valores: np.ndarray, quente, frio, minimo: int) -> np.ndarray:
    """Classe de cada mês, só dentro de sequências de `minimo` meses seguidos além do primeiro limiar."""
    classe = np.zeros(len(valores), dtype=int)
    for sinal, lims in ((1, quente), (-1, frio)):
        dentro = np.array([not np.isnan(v) and sinal * v >= abs(lims[0]) for v in valores])
        i = 0
        while i < len(dentro):
            if not dentro[i]:
                i += 1
                continue
            j = i
            while j < len(dentro) and dentro[j]:
                j += 1
            if j - i >= minimo:
                classe[i:j] = [sinal * _nivel(v, lims) for v in valores[i:j]]
            i = j
    return classe


def tabela_indice(
    serie: pd.Series, criterio: str, limiares=None, sinal: int = 1, casas: int = 2
) -> dict:
    """Ano × 12 colunas (ano mais recente primeiro), com valor e classe de cor por célula."""
    if criterio == "icen":
        serie = serie.rolling(3, center=True).mean()
    serie = serie.dropna()
    serie = serie[serie.index >= "1950-01-01"]
    meses = pd.date_range(
        f"{serie.index.min().year}-01-01", f"{serie.index.max().year}-12-01", freq="MS"
    )
    v = serie.reindex(meses).to_numpy(dtype=float)
    if criterio == "cpc":
        casas = 1
        # o CPC publica e classifica com 1 casa, arredondando o meio para cima (0,65 → 0,7)
        v = np.floor(v * 10 + 0.5 + 1e-9) / 10
        classe = _episodios(v, CPC_FAIXAS, [-x for x in CPC_FAIXAS[:3]], 5)
        legenda = _legenda(
            "La Niña",
            ["fraca (−0,5 a −0,9)", "moderada (−1,0 a −1,4)", "forte (≤ −1,5)"],
            "El Niño",
            [
                "fraco (0,5 a 0,9)",
                "moderado (1,0 a 1,4)",
                "forte (1,5 a 1,9)",
                "muito forte (≥ 2,0)",
            ],
        )
    elif criterio == "icen":
        v = np.round(v, 2)  # o ENFEN publica e classifica o ICEN com 2 casas
        classe = _episodios(v, ICEN_QUENTE, ICEN_FRIO, 3)
        legenda = _legenda(
            "La Niña costeira",
            ["fraca (−1,0 a −1,2)", "moderada (−1,2 a −1,4)", "forte (≤ −1,4)"],
            "El Niño costeiro",
            [
                "fraco (0,4 a 1,0)",
                "moderado (1,0 a 1,7)",
                "forte (1,7 a 3,0)",
                "extraordinário (≥ 3,0)",
            ],
        )
    else:
        if limiares is None:
            dp = float(np.nanstd(v))
            limiares = [
                round(k * dp, casas) for k in (0.5, 1.0, 1.5, 2.0)
            ]  # a cor segue o limiar mostrado
        classe = np.array(
            [
                0
                if np.isnan(q)
                else int(np.sign(q) * sinal * min(_nivel(q, limiares), 3 if q * sinal < 0 else 4))
                for q in v
            ]
        )

        def fmt(
            q, s
        ):  # limiar com sinal, do lado frio (s = −1) ou quente (s = +1) da escala de cor
            return f"{'≥ +' if s * sinal > 0 else '≤ −'}{q:.{casas}f}".replace(".", ",")

        legenda = _legenda(
            "", [fmt(q, -1) for q in limiares[:3]], "", [fmt(q, 1) for q in limiares]
        )
    anos = sorted({d.year for d in meses}, reverse=True)
    pos = {d: i for i, d in enumerate(meses)}
    linhas = [
        [
            [_r(v[pos[pd.Timestamp(a, m, 1)]], casas), int(classe[pos[pd.Timestamp(a, m, 1)]])]
            for m in range(1, 13)
        ]
        for a in anos
    ]
    return {
        "criterio": criterio,
        "colunas": TRIMESTRES if criterio in ("cpc", "icen") else MESES_TAB,
        "anos": anos,
        "linhas": linhas,
        "legenda": legenda,
        "casas": casas,
    }


def previsao_cpc(arm: Armazenamento) -> tuple[dict, dict]:
    """Probabilidades por fase e por força da emissão mais recente guardada."""
    emissoes = sorted({c.split("emissao=")[1].split("/")[0] for c in arm.listar(chaves.RAW_CPC)})
    ultima = emissoes[-1]
    return tuple(
        noaa.ler_probabilidades_enso(arm.caminho_local(chaves.raw_cpc(ultima, f)))
        for f in ("probabilidades.html", "forca.html")
    )


def dados_clima(arm: Armazenamento, ena, indices, anos_similares=()) -> dict:
    """Indicadores climáticos: estado atual, histórico, o que medimos e previsão oficial do ENSO (CPC)."""
    corr = _estatico("correlacoes_subsistema.parquet")
    corr = corr[corr.h <= 6]
    pesos = _estatico("coeficientes_t7.csv").set_index("nome")
    umido = (
        ena_umido(ena)
        .query("nivel == 'subsistema'")
        .pivot(index="ano", columns="nome", values="pct_mlt")
    )
    meses_abrev = MESES_TAB
    saida = {}
    for chave, meta in INDICES_CLIMA.items():
        serie = indices[chave].dropna()
        serie = serie[serie.index >= "1950-01-01"]
        ult = serie.index.max()
        tres = serie.rolling(3).mean()
        atual = float(serie.iloc[-1])
        percentil = float((serie < atual).mean() * 100)
        anterior = serie.get(ult - pd.DateOffset(months=3))
        medido = {}
        if meta["preditor"]:
            c = corr[corr.preditor == meta["preditor"]]
            for nome, g in c.groupby("nome"):
                sig = g[g.q < 0.10]
                melhor = (sig if len(sig) else g).loc[lambda d: d.r.abs().idxmax()]
                medido[nome] = {
                    "r": _r(melhor.r, 2),
                    "mes_indice": meses_abrev[int(melhor.mes_emissao) - 1],
                    "mes_alvo": meses_abrev[int(melhor.mes_alvo) - 1],
                    "h": int(melhor.h),
                    "significativo": bool(len(sig)),
                    "n_sig": len(sig),
                }
        pesos_t7 = (
            {nome: {v: _r(pesos.loc[nome, v], 3) for v in meta["pesos_t7"]} for nome in pesos.index}
            if meta.get("pesos_t7")
            else None
        )
        mesmo_mes = tres[(tres.index.month == ult.month) & (tres.index.year < ult.year)].dropna()
        proximos = (
            (mesmo_mes - tres.loc[ult]).abs().nsmallest(5).index
            if not np.isnan(tres.loc[ult])
            else []
        )
        parecidos = [
            {
                "ano": int(d.year),
                "valor": _r(mesmo_mes.loc[d], 2),
                "umido": {
                    k: _r(umido.loc[d.year, k]) if d.year in umido.index else None for k in SUBS
                },
            }
            for d in proximos
        ]
        saida[chave] = {
            "ultimo_mes": f"{ult:%Y-%m}",
            "valor": _r(atual, 2),
            "tres_meses": _r(tres.loc[ult], 2),
            "variacao_3m": _r(atual - anterior, 2) if anterior is not None else None,
            "percentil": _r(percentil, 0),
            "minimo": _r(serie.min(), 2),
            "maximo": _r(serie.max(), 2),
            "peso": meta["peso"],
            "serie": {
                "inicio": f"{serie.index.min():%Y-%m}",
                "valores": [
                    _r(v, 2)
                    for v in serie.reindex(pd.date_range(serie.index.min(), ult, freq="MS"))
                ],
            },
            "medido": medido,
            "pesos_t7": pesos_t7,
            "parecidos": parecidos,
        }
        if chave in TABELAS_CLIMA:
            saida[chave]["tabela"] = tabela_indice(indices[chave], **TABELAS_CLIMA[chave])
    fases, forca = previsao_cpc(arm)
    return {
        "indices": saida,
        "anos_similares": [int(a) for a in anos_similares],
        "cpc_fases": fases,
        "cpc_forca": forca,
        "gerado_em": _agora(),
    }


# --- publicar ---------------------------------------------------------------------------------------------------


def publicar(arm: Armazenamento) -> dict:
    """Registra a rodada do mês, se pendente, e regrava os quatro JSON das páginas."""
    nova = rodadas.rodada_do_mes(arm)
    ena = ler_parquet(arm, chaves.PROC_ENA)
    indices = ler_parquet(arm, chaves.PROC_INDICES)
    res = ler_parquet(arm, chaves.PROC_BACKTEST)
    produto = dados_produto(arm, ena, indices, res)
    gravar_json(arm, produto, chaves.serving("produto"))
    gravar_json(arm, dados_fundamentos(ena, indices), chaves.serving("fundamentos"))
    gravar_json(arm, dados_metodologia(arm, ena, indices, res), chaves.serving("metodologia"))
    anos = [a["ano"] for a in produto["similares"].get("anos", [])]
    gravar_json(arm, dados_clima(arm, ena, indices, anos), chaves.serving("clima"))
    return {
        "rodada": None if nova is None else nova["id"],
        "ultima_rodada": produto["rodada"]["id"],
        "atualizacao": produto["atualizacao"]
        and f"{produto['atualizacao']['mes']} com {produto['atualizacao']['dias']} dias",
    }
