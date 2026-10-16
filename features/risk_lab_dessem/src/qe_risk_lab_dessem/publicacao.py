"""Publicação: processed/risk_lab_dessem/ → serving/risk_lab_dessem/<chave>.json (o que a página lê).

O acompanhamento (blocos 1 a 6) é descritivo e se atualiza a cada deck: `publicar` regrava os
dados da página, sem registro de rodada (o registro fica para o simulador, bloco 7). Toda conta que
não depende de entrada do usuário é feita aqui; a página só desenha.

Chaves e formatos são os da página de referência da pesquisa (window.DADOS de
risk-lab-dessem-analytics, pagina.py), um arquivo por chave.
"""

import json
import math
from datetime import datetime

import pandas as pd

from qe_core.armazenamento import Armazenamento, ler_parquet
from qe_risk_lab_dessem import chaves, tratamento
from qe_risk_lab_dessem.modelo import MODELO, SUBMERCADOS, TIPOS_DIA


def _r(x, c=1):
    return None if x is None or math.isnan(float(x)) else round(float(x), c)


def _d(t) -> str:
    return pd.Timestamp(t).strftime("%Y-%m-%d")


def _tipos(arm: Armazenamento) -> pd.Series:
    t = ler_parquet(arm, chaves.PROC_TIPOS)
    return pd.Series(t["tipo"].to_numpy(), index=pd.to_datetime(t["data"]))


def _horario(arm: Armazenamento) -> pd.DataFrame:
    """T2 nas horas com DECOMP vigente, só os quatro submercados."""
    h = ler_parquet(arm, chaves.PROC_HORARIO).dropna(subset=["decomp_pld"])
    return h[h["submercado"].isin(SUBMERCADOS)].copy()


# --- bloco 1: PLD médio do dia, DESSEM e DECOMP vigente ---------------------------------------------


def dias_nivel(h: pd.DataFrame, tipos: pd.Series) -> dict:
    """PLD médio diário do DESSEM, DECOMP vigente e piso, por submercado, todo o histórico (D044).

    {sub: [[data, dessem, decomp, piso, horas do vale no piso, tipo, mín. horário, máx. horário]]}
    """
    h = h.assign(
        no_piso=h["hora"].isin(MODELO.vale) & (h["pld_dessem"] <= h["piso"] + MODELO.tol_piso)
    )
    g = h.groupby(["submercado", "data"]).agg(
        dessem=("pld_dessem", "mean"),
        decomp=("decomp_pld", "mean"),
        piso=("piso", "first"),
        hp=("no_piso", "sum"),
        mn=("pld_dessem", "min"),
        mx=("pld_dessem", "max"),
    )
    out = {}
    for (sub, dia), r in g.iterrows():
        t = pd.Timestamp(dia)
        out.setdefault(sub, []).append(
            [
                _d(t),
                _r(r.dessem, 1),
                _r(r.decomp, 1),
                _r(r.piso, 2),
                int(r.hp),
                tipos.get(t, ""),
                _r(r.mn, 1),
                _r(r.mx, 1),
            ]
        )
    return out


def dias_perfil(t1: pd.DataFrame, tipos: pd.Series) -> dict:
    """PLD de cada hora nos últimos 4 meses civis (cobre "últimos 3 meses" do gráfico horário;
    D036, D046): {sub: {mes: [{data, tipo, pld[24]}]}}."""
    p = t1[t1["submercado"].isin(SUBMERCADOS)].copy()
    p["mes"] = p["data"].dt.strftime("%Y-%m")
    ult = pd.Period(p["mes"].max(), "M")
    p = p[p["mes"] >= str(ult - 3)]
    out = {}
    for (sub, mes, dia), x in p.groupby(["submercado", "mes", "data"]):
        v = x.set_index("hora")["pld"].reindex(range(24))
        out.setdefault(sub, {}).setdefault(mes, []).append(
            {"data": _d(dia), "tipo": tipos.get(dia, ""), "pld": [_r(z, 2) for z in v]}
        )
    return out


def semanas_perfil(h: pd.DataFrame, tipos: pd.Series) -> dict:
    """Perfil horário do PLD por semana operativa nos dois últimos meses civis (D035); cada semana
    entra só com os dias que caem no mês: {sub: {mes: [{rv, inicio, dias, dias_uteis, pld[24],
    pld_util[24], decomp_media}]}}."""
    ult = pd.Period(h["mes"].max(), "M")
    h = h[h["mes"].isin([str(ult - 1), str(ult)])].copy()
    h["tipo"] = tipos.reindex(pd.to_datetime(h["data"])).to_numpy()
    h["semana"] = pd.to_datetime(h["semana"]).dt.strftime("%Y-%m-%d")
    out = {}
    for (sub, mes, sem), x in h.groupby(["submercado", "mes", "semana"]):
        u = x[x["tipo"] == "útil"]
        perfil = x.groupby("hora")["pld_dessem"].mean().reindex(range(24))
        perfil_u = u.groupby("hora")["pld_dessem"].mean().reindex(range(24))
        out.setdefault(sub, {}).setdefault(mes, []).append(
            {
                "rv": int(x["rv"].iloc[0]),
                "inicio": sem,
                "dias": int(x["data"].nunique()),
                "dias_uteis": int(u["data"].nunique()),
                "pld": [_r(v) for v in perfil],
                "pld_util": [_r(v) for v in perfil_u],
                "decomp_media": _r(x["decomp_pld"].mean(), 2),
            }
        )
    for por_mes in out.values():
        for semanas in por_mes.values():
            semanas.sort(key=lambda s: s["inicio"])
    return out


def revisoes(dec: pd.DataFrame) -> list:
    """Revisões do DECOMP de todo o histórico: [[início da semana operativa, RV, PMO]] (D045)."""
    d = dec[dec["estagio"] == 1].drop_duplicates("inicio_estudo").sort_values("inicio_estudo")
    return [[_d(r.inicio_estudo), int(r.rv), r.pmo] for r in d.itertuples()]


def referencia(h: pd.DataFrame, t1: pd.DataFrame) -> list:
    """Último dia com deck (e DECOMP), último dia publicado pela CCEE e DECOMP vigente (SE/CO)."""
    se = h[h["submercado"] == "SE"]
    ult = se["data"].max()
    pub = t1.loc[t1["origem"] == "publicado", "data"].max()
    return [
        {
            "ultimo_dia": _d(ult),
            "ultimo_publicado": _d(pub),
            "decomp_vigente": round(float(se.loc[se["data"] == ult, "decomp_pld"].mean()), 2),
        }
    ]


# --- blocos 2 e 5: desvio por bloco de horas; horas no piso, abaixo e acima do DECOMP --------------


def desvio_mensal(t5: pd.DataFrame) -> list:
    """T5 dos quatro submercados: meses completos e o mês corrente parcial (até o último deck;
    D041)."""
    corrente = t5["mes"].max()
    m = t5[t5["submercado"].isin(SUBMERCADOS) & (t5["completo"] | (t5["mes"] == corrente))]
    return [
        {
            "sub": r.submercado,
            "mes": r.mes,
            "parcial": bool(r.mes == corrente and not r.completo),
            "dias": int(r.dias),
            "decomp": _r(r.decomp, 2),
            "dessem": _r(r.dessem, 2),
            "delta": _r(r.delta, 2),
            "vale": _r(r.delta_vale, 2),
            "ponta": _r(r.delta_ponta, 2),
            "demais": _r(r.delta_resto, 2),
        }
        for r in m.itertuples()
    ]


def dias_blocos(h: pd.DataFrame) -> dict:
    """Desvio diário DESSEM − DECOMP vigente por bloco de horas, últimos 13 meses (D039, D040):
    contribuição de cada bloco = Σ desvio nas horas do bloco / horas do dia."""
    ult = pd.Period(h["mes"].max(), "M")
    h = h[h["mes"] >= str(ult - 12)].copy()
    h["desvio"] = h["pld_dessem"] - h["decomp_pld"]
    h["bloco"] = h["hora"].map(
        lambda x: "vale" if x in MODELO.vale else "ponta" if x in MODELO.ponta else "demais"
    )
    out = {}
    for (sub, dia), x in h.groupby(["submercado", "data"]):
        n = len(x)
        out.setdefault(sub, []).append(
            {
                "data": _d(dia),
                "dessem": _r(x["pld_dessem"].mean(), 2),
                "decomp": _r(x["decomp_pld"].mean(), 2),
                "delta": _r(x["desvio"].mean(), 2),
                **{
                    b: _r(x.loc[x["bloco"] == b, "desvio"].sum() / n, 2)
                    for b in ["vale", "ponta", "demais"]
                },
            }
        )
    return out


def horas(h: pd.DataFrame, tipos: pd.Series) -> dict:
    """Por submercado, mês, tipo de dia e hora: [n, no piso, abaixo, acima do DECOMP, soma do
    desvio]; e o mesmo por semana operativa dentro de cada mês civil (só os dias da semana que caem
    no mês), últimos 13 meses (D043, D067)."""
    h = h.copy()
    h["tipo"] = tipos.reindex(pd.to_datetime(h["data"])).to_numpy()
    h["desvio"] = h["pld_dessem"] - h["decomp_pld"]
    h["piso_"] = h["pld_dessem"] <= h["piso"] + MODELO.tol_piso
    h["abaixo"] = h["desvio"] < -MODELO.limiar_desvio
    h["acima"] = h["desvio"] > MODELO.limiar_desvio
    agg = {
        "n": ("desvio", "size"),
        "piso": ("piso_", "sum"),
        "abaixo": ("abaixo", "sum"),
        "acima": ("acima", "sum"),
        "soma": ("desvio", "sum"),
    }

    def linhas24(x: pd.DataFrame) -> list:
        x = x.set_index("hora").reindex(range(24))
        return [
            [
                int(r.n or 0),
                int(r.piso or 0),
                int(r.abaixo or 0),
                int(r.acima or 0),
                _r(r.soma or 0, 1),
            ]
            for r in x.itertuples()
        ]

    g = h.groupby(["submercado", "mes", "tipo", "hora"]).agg(**agg).reset_index()
    mensal = {}
    for (sub, mes, tipo), x in g.groupby(["submercado", "mes", "tipo"]):
        mensal.setdefault(sub, {}).setdefault(mes, {})[tipo] = linhas24(x)
    ult = pd.Period(h["mes"].max(), "M")
    rec = h[h["mes"] >= str(ult - 12)].copy()
    rec["semana"] = pd.to_datetime(rec["semana"]).dt.strftime("%Y-%m-%d")
    ndias = rec.groupby(["submercado", "mes", "semana"])["data"].nunique()
    gs = rec.groupby(["submercado", "mes", "semana", "rv", "tipo", "hora"]).agg(**agg).reset_index()
    semanal = {}
    for (sub, mes, sem, rv, tipo), x in gs.groupby(["submercado", "mes", "semana", "rv", "tipo"]):
        d = (
            semanal.setdefault(sub, {})
            .setdefault(mes, {})
            .setdefault(sem, {"rv": int(rv), "dias": int(ndias[(sub, mes, sem)])})
        )
        d[tipo] = linhas24(x)
    return {"mensal": mensal, "semanal": semanal}


def _faixas() -> list[tuple[str, list[int]]]:
    v, p = list(MODELO.vale), list(MODELO.ponta)
    return [
        (f"Vale {v[0]}–{v[-1]}h", v),
        (f"Ponta {p[0]}–{p[-1]}h", p),
        ("Demais horas", [x for x in range(24) if x not in v and x not in p]),
    ]


def periodos_contribuicao(meses: list[str], anos: list[int]) -> dict[str, list[str]]:
    """Meses de cada período do detalhe por tipo de dia (mês corrente = último mês da base)."""
    i = len(meses) - 1
    per = {
        "corrente": meses[-1:],
        "ultimo": meses[-2:-1],
        "3m": meses[max(0, i - 3) : i],
        "12m": meses[max(0, i - 12) : i],
    }
    for a in anos[-3:]:
        per[f"a{a}"] = [m for m in meses if m.startswith(f"{a}-")]
    return per


def contribuicao(hr: dict, anos: list[int]) -> dict:
    """Detalhe do bloco 2 (D067), por submercado e período: por tipo de dia × faixa horária,
    contribuição ao desvio médio do período (desvio médio da célula × peso das suas horas; a soma das
    células dá o desvio médio) e horas por dia no piso, abaixo e acima do DECOMP.

    {sub: {periodo: {meses, total, linhas: [{tipo, faixa, nh, contrib, medio, dias, piso, abaixo,
    acima}]}}}. Antes era calculado no navegador (pesquisa, app.js desenharContrib).
    """
    out = {}
    for sub, por_mes in hr["mensal"].items():
        meses = sorted(por_mes)
        out[sub] = {}
        for nome, ms in periodos_contribuicao(meses, anos).items():
            cel, n_tot = {}, 0
            for m in ms:
                for t in TIPOS_DIA:
                    a = por_mes.get(m, {}).get(t)
                    if not a:
                        continue
                    for f, hs in _faixas():
                        c = cel.setdefault((t, f), [0, 0, 0, 0, 0.0])
                        for hh in hs:
                            for k in range(5):
                                c[k] += a[hh][k]
                            n_tot += a[hh][0]
            linhas = []
            for t in TIPOS_DIA:
                for f, hs in _faixas():
                    n, piso, abaixo, acima, soma = cel.get((t, f), [0, 0, 0, 0, 0.0])
                    dias = n / len(hs)
                    linhas.append(
                        {
                            "tipo": t,
                            "faixa": f,
                            "nh": len(hs),
                            "contrib": soma / n_tot if n_tot else 0,
                            "medio": soma / n if n else None,
                            "dias": dias,
                            "piso": piso / dias if dias else 0,
                            "abaixo": abaixo / dias if dias else 0,
                            "acima": acima / dias if dias else 0,
                        }
                    )
            out[sub][nome] = {
                "meses": ms,
                "total": sum(r["contrib"] for r in linhas),
                "linhas": linhas,
            }
    return out


# --- blocos 3 e 4: perfil horário do mês dia a dia, mapa de calor, perfis por mês do ano ------------

VARIAVEIS_PRECO = ("pld", "decomp")  # em R$/MWh, 1 casa; as demais em MW, sem casas


def perfis(series: dict) -> dict:
    """Média por variável, submercado, mês e hora: {var: {sub: {mes: [24 valores]}}}."""
    out = {}
    for k, x in series.items():
        x = x[x["submercado"].isin([*SUBMERCADOS, "SIN"])].copy()  # SIN só nas variáveis em MW
        x["mes"] = x["data"].dt.strftime("%Y-%m")
        x = x[x["mes"] >= "2021-01"]
        g = (
            x.groupby(["submercado", "mes", "hora"])["v"]
            .mean()
            .unstack("hora")
            .reindex(columns=range(24))
        )
        c = 1 if k in VARIAVEIS_PRECO else 0
        out[k] = {
            sub: {mes: [_r(v, c) for v in row] for mes, row in gs.droplevel(0).iterrows()}
            for sub, gs in g.groupby(level=0)
        }
    return out


def perfis_dia(series: dict, tipos: pd.Series, meses: int = 6) -> dict:
    """Perfil horário de cada dia nos últimos `meses` meses civis (D068): {var: {sub: {mes: {dias,
    tipos, v: [[24 valores] por dia]}}}}."""
    fim = pd.Period(series["pld"]["data"].max(), "M")
    ini = str(fim - (meses - 1))
    out = {}
    for k, x in series.items():
        x = x[x["submercado"].isin([*SUBMERCADOS, "SIN"])].copy()  # SIN só nas variáveis em MW
        x["mes"] = x["data"].dt.strftime("%Y-%m")
        x = x[x["mes"] >= ini]
        g = x.groupby(["submercado", "mes", "data", "hora"])["v"].mean().unstack("hora")
        g = g.reindex(columns=range(24))
        c = 1 if k in VARIAVEIS_PRECO else 0
        d = {}
        for (sub, mes), gm in g.groupby(level=[0, 1]):
            datas = gm.index.get_level_values(2)
            d.setdefault(sub, {})[mes] = {
                "dias": [t.strftime("%Y-%m-%d") for t in datas],
                "tipos": [tipos.get(t, "") for t in datas],
                "v": [[_r(v, c) for v in row] for row in gm.to_numpy()],
            }
        out[k] = d
    return out


# As contas abaixo eram feitas no navegador (pesquisa, app.js); aqui seguem a mesma ordem de soma e o
# mesmo arredondamento do JS sobre os valores já arredondados de `perfis` e `perfis_dia`.


def _media(vs) -> float | None:
    vs = [v for v in vs if v is not None]
    return sum(vs) / len(vs) if vs else None


def _arred(v, c=4):
    return None if v is None else round(v, c)


def _percentil_js(ordenados: list[float], p: float) -> float:
    """Percentil por índice arredondado (Math.round do JS), sobre a lista já ordenada."""
    n = len(ordenados)
    return ordenados[min(n - 1, max(0, math.floor((n - 1) * p + 0.5)))]


def calor(pdia: dict) -> dict:
    """Mapa de calor do mês (D078, D080) e média do perfil dia a dia: escala cortada nos percentis 5
    e 95 do mês (índice arredondado, como no JS), média de cada dia (e horas com dado), de cada hora e
    do mês. {var: {sub: {mes: {lo, hi, dia, nh, hora, mes}}}}."""
    out = {}
    for var, por_sub in pdia.items():
        for sub, por_mes in por_sub.items():
            for mes, m in por_mes.items():
                todos = sorted(v for r in m["v"] for v in r if v is not None)
                if not todos:
                    continue
                out.setdefault(var, {}).setdefault(sub, {})[mes] = {
                    "lo": _percentil_js(todos, 0.05),
                    "hi": _percentil_js(todos, 0.95),
                    "dia": [_arred(_media(r)) for r in m["v"]],
                    "nh": [sum(v is not None for v in r) for r in m["v"]],
                    "hora": [_arred(_media([r[h] for r in m["v"]])) for h in range(24)],
                    "mes": _arred(_media([v for r in m["v"] for v in r])),
                }
    return out


def media_mes(pf: dict) -> dict:
    """Média do mês (todas as horas) por variável, submercado e mês (D077, "média do mês por ano")."""
    return {
        var: {sub: {mes: _arred(_media(v)) for mes, v in pm.items()} for sub, pm in ps.items()}
        for var, ps in pf.items()
    }


PERIODOS_INDICADORES = {"ano": None, "Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}


def indicadores(pf: dict) -> dict:
    """Indicadores por ano (D069), por submercado e período (ano inteiro ou trimestre): média dos
    perfis mensais (cada mês pesa igual, não pelas horas), como na pesquisa. Carga líquida no vale e
    na ponta, rampa 12h→19h (carga líquida às 19h − às 12h), demanda sem MMGD (24 h), renovável com
    MMGD no vale, PLD médio, da ponta e do vale. MW e R$/MWh.

    {sub: {periodo: [{ano, meses, cl_vale, cl_ponta, rampa, demanda, renov_vale, pld, pld_ponta,
    pld_vale}]}}, com sub = SIN, SE, S, NE, N; no SIN, as colunas de PLD são do SE/CO (D084). O ano
    corrente é acumulado até o último deck.
    """
    anos = sorted({int(m[:4]) for m in pf["pld"]["SE"]})
    vale, ponta, todas = list(MODELO.vale), list(MODELO.ponta), list(range(24))

    def perfil_medio(sub, var, filtro):
        dd = pf[var].get(sub, {})
        ms = [m for m in dd if filtro(m)]
        if not ms:
            return None
        return len(ms), [_media([dd[m][h] for m in ms]) for h in range(24)]

    def media_h(p, hs):  # no JS, hora sem dado soma como 0
        return None if p is None else sum((p[1][h] or 0) for h in hs) / len(hs)

    out = {}
    for sub in ["SIN", *SUBMERCADOS]:
        for per, tri in PERIODOS_INDICADORES.items():
            linhas = []
            for a in anos:
                filtro = lambda m, a=a, tri=tri: (
                    m.startswith(f"{a}-") and (tri is None or math.ceil(int(m[5:7]) / 3) == tri)
                )
                cl = perfil_medio(sub, "carga_liquida", filtro)
                dm = perfil_medio(sub, "demanda_sem_mmgd", filtro)
                rv = perfil_medio(sub, "renov_com_mmgd", filtro)
                pl = perfil_medio("SE" if sub == "SIN" else sub, "pld", filtro)  # SIN não tem PLD
                if not cl and not pl:
                    continue
                linhas.append(
                    {
                        "ano": a,
                        "meses": (cl or pl)[0],
                        "cl_vale": _arred(media_h(cl, vale)),
                        "cl_ponta": _arred(media_h(cl, ponta)),
                        "rampa": _arred(cl[1][19] - cl[1][12]) if cl else None,
                        "demanda": _arred(media_h(dm, todas)),
                        "renov_vale": _arred(media_h(rv, vale)),
                        "pld": _arred(media_h(pl, todas)),
                        "pld_ponta": _arred(media_h(pl, ponta)),
                        "pld_vale": _arred(media_h(pl, vale)),
                    }
                )
            out.setdefault(sub, {})[per] = linhas
    return out


# --- bloco 6: mecanismos do vale (SE/CO) -------------------------------------------------------------


def mecanismos_se(arm: Armazenamento, tipos: pd.Series) -> list:
    """Por mês (diagnóstico com saídas do modelo; D082): horas do vale no piso do dia útil, folga
    hidráulica no vale do dia útil (SIN, GW: necessária, mínima revelada = mediana da hidráulica do
    modelo nos dias com o vale todo no piso, renovável cortada), % dos dias úteis com SE acoplado ao N
    e Belo Monte nos dias úteis (mediana do valor da água; geração e vertimento de Pimental)."""
    import numpy as np

    from qe_risk_lab_dessem import vale

    d = vale.dias_vale(vale.horas_vale(arm), tipos).join(vale.insumos_vale_diarios(arm))
    cm = vale.cmo_vale_diario(arm)
    d = d.join(((cm["SE"] - cm["N"]).abs() < vale.LIMIAR_ACOPLAMENTO).rename("acopl"))
    u = d[d["tipo"] == "útil"]
    gh_min = d[d["n_piso"] == len(MODELO.vale)].groupby("mes")["gh_modelo_sin"].median()
    fol = u.groupby("mes").agg(
        hid=("hid_nec_sin", "mean"), corte=("corte_sin", "mean"), acopl=("acopl", "mean")
    )
    fol["gh_min"] = gh_min
    tipo = d.groupby(["mes", "tipo"])["n_piso"].mean().unstack()
    bmu = vale.belo_monte_diario(arm).join(d[["mes", "tipo"]], how="inner")
    bmm = (
        bmu[bmu["tipo"] == "útil"]
        .groupby("mes")
        .agg(
            bm_vagua=("bm_vagua", "median"),
            bm_ger=("bm_ghid", "mean"),
            pim_ver=("pim_qver", "mean"),
        )
    )
    linhas = []
    for mes in sorted(fol.index):
        f = fol.loc[mes]
        b = bmm.loc[mes] if mes in bmm.index else None
        linhas.append(
            {
                "mes": mes,
                "piso_util": _r(tipo.loc[mes].get("útil", np.nan), 2)
                if mes in tipo.index
                else None,
                "hid_nec": _r(f.hid / 1000, 1),
                "gh_min": _r(f.gh_min / 1000, 1),
                "corte": _r(f.corte / 1000, 1),
                "acopl": _r(f.acopl, 3),
                "bm_vagua": _r(b.bm_vagua, 1) if b is not None else None,
                "bm_ger": _r(b.bm_ger / 1000, 1) if b is not None else None,
                "pim_ver": _r(b.pim_ver, 0) if b is not None else None,
            }
        )
    return linhas


# --- bloco 7: simulador do PLD médio do mês (SE/CO) ------------------------------------------------


def _registros(df: pd.DataFrame) -> list:
    """Como a pesquisa grava as tabelas do simulador: `to_json` (10 algarismos significativos)."""
    return json.loads(df.to_json(orient="records", force_ascii=False))


def _backtest_pagina(bt: pd.DataFrame) -> list:
    from qe_risk_lab_dessem import simulador as S

    bt = bt.assign(
        direcao_prevista=S.classe(bt["delta_prev"]).to_numpy(),
        direcao_real=S.classe(bt["delta_real"]).to_numpy(),
    )
    cols = ["mes", "h", "decomp", "real", "prev", "erro", "delta_real", "delta_prev"]
    return _registros(bt[[*cols, "direcao_prevista", "direcao_real"]].round(2))


def _confianca(bt: pd.DataFrame) -> list:
    from qe_risk_lab_dessem import simulador as S

    conf = []
    for hz, e in S.estatisticas(bt).items():
        for dp, linha in e["matriz"].iterrows():
            conf.append(
                {
                    "h": int(hz),
                    "direcao_prevista": dp,
                    "meses": int(e["n"].get(dp, 0)),
                    "acerto": float(linha.get(dp, 0.0)),
                    "desconto": float(linha.get("desconto", 0.0)),
                    "neutro": float(linha.get("neutro", 0.0)),
                    "premio": float(linha.get("prêmio", 0.0)),
                    "erro_p10": float(e["erro_p10"]),
                    "erro_p90": float(e["erro_p90"]),
                    "erro_abs": float(e["erro_abs"]),
                    "acerto_geral": float(e["acerto"]),
                    "meses_total": int(e["meses"]),
                }
            )
    return _registros(pd.DataFrame(conf).round(4))


def simulador(b, bt: pd.DataFrame) -> dict:
    """Chaves da página do simulador (pesquisa: pagina._premissas e simulador.exportar_pagina)."""
    from qe_risk_lab_dessem import simulador as S

    h = b.hs
    origem = h["data"].max() + pd.Timedelta(days=1)
    janelas = {}
    for X in MODELO.janelas_pagina:
        pr = S.premissas_s_por_tipo(S.janela(h, origem, X))
        janelas[X] = {t: {k: _r(v, 4) for k, v in p.items()} for t, p in pr.items()}
        janelas[X]["inicio"] = str((origem - pd.Timedelta(days=X)).date())
        janelas[X]["fim"] = str((origem - pd.Timedelta(days=1)).date())
    tr = S.trajetoria_diaria(h, max(MODELO.janelas_pagina))
    cols_tr = [
        "horas_piso",
        "frac_fora",
        "premio_ponta",
        "ponta_media",
        "ponta_max_hora",
        "decomp",
        "espaco",
    ]
    trajetoria = [
        [r.data.strftime("%Y-%m-%d"), r.tipo, *(_r(getattr(r, c), 3) for c in cols_tr)]
        for r in tr.itertuples()
    ]
    cols = ["horas_piso", "frac_fora", "premio_ponta", "ponta_media", "decomp", "espaco"]
    hp = S.historico_premissas_s(h, MODELO.janela)
    hist = {
        t: [
            [r.data.strftime("%Y-%m-%d"), *(_r(getattr(r, c), 3) for c in cols)]
            for r in x.itertuples()
        ]
        for t, x in hp.groupby("tipo")
    }
    pm = S.ponta_mensal(h)
    pm = pm[pm["mes"] >= "2024-07"]
    cols_pm = ["ponta", "premio", "ponta_min_dia", "ponta_max_dia", "ponta_max_hora", "decomp"]
    ponta = {
        t: [
            {
                "mes": r.mes,
                **{c: _r(getattr(r, c), 1) for c in cols_pm},
                "dias": int(r.dias),
                "dias_premio_100": int(r.dias_premio_100),
            }
            for r in x.itertuples()
        ]
        for t, x in pm.groupby("tipo")
    }
    hm = S.historico_mensal_s(b)
    cols_hm = [c for c in hm.columns if c not in ("mes", "tipo", "dias", "rv0")]
    mensal = {
        t: [
            {
                "mes": r["mes"],
                "dias": int(r["dias"]),
                "rv0": r.get("rv0") if isinstance(r.get("rv0"), str) else None,
                **{c: _r(r[c], 4 if c.endswith("frac_fora") else 2) for c in cols_hm},
            }
            for r in x.to_dict("records")
        ]
        for t, x in hm.groupby("tipo")
    }
    mr = S.mensal_realizado_s(h)
    est = S.niveis_estresse(h, origem)
    pdia = S.ponta_diaria(h)
    return {
        "janela_padrao": MODELO.janela,
        "calendario": _registros(pd.DataFrame(S.calendario(b, origem))),
        "backtest": _backtest_pagina(bt),
        "confianca": _confianca(bt),
        "premissas_mensal": mensal,
        "ponta_janelas": _ponta_janelas(h, mr),
        "ponta_horas": _ponta_horas(h),
        "ponta_dias": {
            t: [_r(v, 1) for v in x["ponta"].tolist()]
            for t, x in pdia.loc[pdia.index > pdia.index.max() - pd.Timedelta(days=365)].groupby(
                "tipo"
            )
        },
        "ref_fora": {
            t: {**v, "valor": _r(v["valor"], 4)}
            for t, v in {t: S.ref_fora_em(mr, origem, t) for t in [*S.TIPOS_DIA, "todos"]}.items()
        },
        "premissas_janelas": janelas,
        "trajetoria": {"colunas": ["data", "tipo", *cols_tr], "dias": trajetoria},
        "premissas_hist": {"janela": MODELO.janela, "colunas": ["data", *cols], "tipos": hist},
        "ponta_mensal": ponta,
        "estresse": {
            r.tipo: {
                "com": _r(r.com_estresse, 1),
                "sem": _r(r.sem_estresse, 1),
                "meses": int(r.meses),
                "de": r.de,
                "ate": r.ate,
            }
            for r in est.itertuples()
        },
    }


def _ponta_horas(h: pd.DataFrame, desde: str = "2024-07") -> dict:
    """Preço de cada hora de 18h a 21h, por mês civil e tipo de dia (D072)."""
    p = h[h["grupo_s"] == "ponta"].copy()
    p["mes"] = p["data"].dt.strftime("%Y-%m")
    p = p[p["mes"] >= desde]
    out = {}
    for (mes, t), x in p.groupby(["mes", "tipo"]):
        out.setdefault(mes, {})[t] = [round(v) for v in x["pld_dessem"].tolist()]
    return out


def _ponta_janelas(h: pd.DataFrame, mr: pd.DataFrame) -> dict:
    """Por tipo de dia (D064, D065): preço médio da ponta, prêmio e DECOMP médio nas janelas móveis de
    7/14/30/60 dias (cada data usa só os dias anteriores) e a média dos 12 meses encerrados."""
    from qe_risk_lab_dessem import simulador as S

    hps = {X: S.historico_premissas_s(h, X, desde="2025-01-01") for X in (7, 14, 30, 60)}
    out = {}
    for t in S.TIPOS_DIA:
        base = hps[14][hps[14]["tipo"] == t].set_index("data")
        d = {"datas": [x.strftime("%Y-%m-%d") for x in base.index]}
        for X, hp in hps.items():
            x = hp[hp["tipo"] == t].set_index("data")
            d[str(X)] = [_r(v, 1) for v in x["ponta_media"].tolist()]
            d[f"{X}p"] = [_r(v, 1) for v in x["premio_ponta"].tolist()]
            d[f"{X}d"] = [_r(v, 1) for v in x["decomp"].tolist()]
        x = mr[(mr["tipo"] == t) & (mr["fim"] < base.index.max())].tail(MODELO.meses_ref_fora)
        d["ref12"] = {
            "valor": _r(x["ponta_media"].mean(), 1),
            "premio": _r(x["premio_ponta"].mean(), 1),
            "decomp": _r(x["decomp"].mean(), 1),
            "de": x["mes"].min(),
            "ate": x["mes"].max(),
        }
        out[t] = d
    return out


# As contas abaixo eram feitas na página do simulador (pesquisa, app.js); aqui, sobre os mesmos valores
# já arredondados das chaves acima, na ordem de soma e com a interpolação do JS.


def _quantil_js(vs: list[float], p: float) -> float:
    """Quantil com interpolação linear (como `q` no JS e `np.quantile`), sobre a lista ordenada."""
    o = sorted(vs)
    k = (len(o) - 1) * p
    a, b = math.floor(k), math.ceil(k)
    return o[a] + (o[b] - o[a]) * (k - a)


def contas_simulador(d: dict, ultimo_dia: str) -> dict:
    """Desempenho por antecedência no regime atual, preço padrão da sensibilidade (p90 das horas de
    ponta dos dias úteis do mês corrente; D073), médias de 12 meses das premissas por tipo de dia e
    percentis 10/50/90 da ponta de cada mês (dispersão)."""
    regime = [r for r in d["backtest"] if r["mes"] >= MODELO.regime_desde]
    desempenho = []
    for hz in range(1, MODELO.horizontes + 1):
        rs = [r for r in regime if r["h"] == hz]
        if not rs:
            continue
        desempenho.append(
            {
                "h": hz,
                "erro": sum(abs(r["erro"]) for r in rs) / len(rs),
                "vies": sum(r["erro"] for r in rs) / len(rs),
                "dir": sum(r["direcao_prevista"] == r["direcao_real"] for r in rs) / len(rs),
                "dec": sum(abs(r["real"] - r["decomp"]) for r in rs) / len(rs),
                "meses": len(rs),
            }
        )
    ult_mes = max(d["ponta_horas"])
    horas_mes = d["ponta_horas"][ult_mes].get("útil", [])
    parcial = ultimo_dia[:7]
    R = {t: {r["mes"]: r for r in d["premissas_mensal"].get(t, [])} for t in TIPOS_DIA}
    fech = [m for m in sorted(R["útil"]) if m < parcial][-MODELO.meses_ref_fora :]

    def media12(t, k, filtrar_espaco=False):
        vs = [
            R[t][m][k]
            for m in fech
            if m in R[t]
            and (not filtrar_espaco or R[t][m]["espaco"] >= MODELO.espaco_min)
            and R[t][m][k] is not None
        ]
        return sum(vs) / len(vs) if vs else None

    return {
        "desempenho": desempenho,
        "sensibilidade": {
            "mes": ult_mes,
            "preco": _quantil_js(horas_mes, MODELO.q_sensibilidade) if horas_mes else None,
            "pct": MODELO.pct_sensibilidade,
        },
        "media12": {
            "de": fech[0] if fech else None,
            "ate": fech[-1] if fech else None,
            **{
                t: {
                    "horas_piso": media12(t, "horas_piso"),
                    "frac_fora": media12(t, "frac_fora", filtrar_espaco=True),
                    "ponta_media": media12(t, "ponta_media"),
                    "premio_ponta": media12(t, "premio_ponta"),
                }
                for t in TIPOS_DIA
            },
        },
        "ponta_quantis": {
            mes: {t: [_quantil_js(v, q) for q in (0.1, 0.5, 0.9)] for t, v in pt.items() if v}
            for mes, pt in d["ponta_horas"].items()
        },
    }


# --- montagem e gravação -----------------------------------------------------------------------------


def dados(arm: Armazenamento) -> dict:
    """Todas as chaves da página, prontas para gravar."""
    t1 = ler_parquet(arm, chaves.PROC_PLD)
    h, tipos = _horario(arm), _tipos(arm)
    dec = ler_parquet(arm, chaves.PROC_DECOMP)
    hr = horas(h, tipos)
    anos = sorted(t1["data"].dt.year.unique().tolist())
    series = tratamento.series_horarias(arm)
    pf, pd_ = perfis(series), perfis_dia(series, tipos)
    return {
        "dias_nivel": dias_nivel(h, tipos),
        "dias_perfil": dias_perfil(t1, tipos),
        "semanas_perfil": semanas_perfil(h, tipos),
        "revisoes": revisoes(dec),
        "referencia": referencia(h, t1),
        "desvio_mensal": desvio_mensal(ler_parquet(arm, chaves.PROC_DELTA)),
        "dias_blocos": dias_blocos(h),
        "horas": hr,
        "contribuicao": contribuicao(hr, anos),
        "perfis": pf,
        "perfis_dia": pd_,
        "calor": calor(pd_),
        "media_mes": media_mes(pf),
        "indicadores": indicadores(pf),
        "mecanismos_se": mecanismos_se(arm, tipos),
    }


def dados_simulador(arm: Armazenamento, ultimo_dia: str) -> dict:
    """Chaves do simulador (bloco 7), com o backtest gravado pelo tratamento."""
    from qe_risk_lab_dessem import simulador as S

    d = simulador(S.Base(arm), ler_parquet(arm, chaves.PROC_BACKTEST))
    return d | contas_simulador(d, ultimo_dia)


class RodadaRepetida(Exception):
    """Insumos e modelo iguais aos da última rodada: publicar de novo exige --forcar e --motivo."""


def carregar_registro(arm: Armazenamento) -> dict:
    if not arm.existe(chaves.SERVING_REGISTRO):
        return {"rodadas": {}}
    return json.loads(arm.ler_bytes(chaves.SERVING_REGISTRO).decode("utf-8"))


def insumos(arm: Armazenamento, ref: dict) -> dict:
    """O que define uma rodada do simulador: último deck do DESSEM, último dia de PLD publicado, último
    deck do DECOMP (PMO, semana e publicação) e a versão do modelo."""
    dec = ler_parquet(arm, chaves.PROC_DECOMP)
    u = dec.sort_values(["pmo", "sem", "publicacao"]).iloc[-1]
    return {
        "deck_dessem": ref["ultimo_dia"],
        "pld_publicado": ref["ultimo_publicado"],
        "decomp": f"{u['pmo']} sem{int(u['sem'])} pub{int(u['publicacao'])} (RV{int(u['rv'])})",
        "modelo": MODELO.versao,
    }


def rodada(arm: Armazenamento, d: dict, ins: dict, motivo: str) -> dict:
    """Rodada do simulador: premissas padrão por tipo de dia na origem (janela padrão; desconto das
    outras horas pela média de 12 meses) e o PLD de cada mês do calendário com o DECOMP vigente."""
    from qe_risk_lab_dessem import simulador as S

    b = S.Base(arm)
    origem = b.hs["data"].max() + pd.Timedelta(days=1)
    pr = S.premissas_na_origem(b, origem)
    dv = d["referencia"][0]["decomp_vigente"]
    return {
        "publicado_em": datetime.now().isoformat(timespec="seconds"),
        "motivo": motivo,
        "insumos": ins,
        "origem": str(origem.date()),
        "decomp_vigente": dv,
        "premissas": {
            t: {k: round(pr[t][k], 4) for k in ("dias", "horas_piso", "frac_fora", "premio_ponta")}
            for t in TIPOS_DIA
        },
        "previsao": [
            {
                "mes": c["mes"],
                "h": c["h"],
                "piso": c["piso"],
                "pld_com_decomp_vigente": round(S.prever_mes(pr, c, dv), 2),
            }
            for c in d["calendario"]
        ],
    }


def estado(arm: Armazenamento, d: dict) -> dict:
    """Premissas do topo da página: datas da base, dias com PLD calculado e versão do modelo."""
    t1 = ler_parquet(arm, chaves.PROC_PLD)
    calc = sorted(t1.loc[t1["origem"] != "publicado", "data"].unique())
    return {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "modelo": MODELO.versao,
        "ultimo_deck": d["referencia"][0]["ultimo_dia"],
        "ultimo_publicado": d["referencia"][0]["ultimo_publicado"],
        "calculados": [_d(calc[0]), _d(calc[-1])] if calc else None,
        "vale": [min(MODELO.vale), max(MODELO.vale)],
        "ponta": [min(MODELO.ponta), max(MODELO.ponta)],
        "chaves": sorted(d),
    }


def publicar(arm: Armazenamento, motivo: str | None = None, forcar: bool = False) -> dict:
    """Regrava serving/risk_lab_dessem/ (acompanhamento e simulador) com os dados atuais e registra uma
    rodada do simulador quando os insumos mudaram. Devolve o estado publicado (com `nova_rodada`)."""
    d = dados(arm)
    d |= dados_simulador(arm, d["referencia"][0]["ultimo_dia"])
    reg = carregar_registro(arm)
    ins = insumos(arm, d["referencia"][0])
    ultima = max(reg["rodadas"]) if reg["rodadas"] else None
    repetida = ultima is not None and reg["rodadas"][ultima]["insumos"] == ins
    if repetida and forcar and not motivo:
        raise RodadaRepetida("--forcar exige --motivo")
    nova = not repetida or forcar
    if nova:
        motivo = motivo or f"deck do DESSEM de {ins['deck_dessem']}"
        rid = datetime.now().isoformat(timespec="seconds")
        reg["rodadas"][rid] = rodada(arm, d, ins, motivo)
        arm.gravar_bytes(
            (json.dumps(reg, ensure_ascii=False, indent=1) + "\n").encode("utf-8"),
            chaves.SERVING_REGISTRO,
        )
        ultima = rid
    e = estado(arm, d) | {"rodada": ultima, "nova_rodada": nova}
    for nome, valor in {**d, "estado": e}.items():
        arm.gravar_bytes(
            json.dumps(valor, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            chaves.serving(nome),
        )
    return e
