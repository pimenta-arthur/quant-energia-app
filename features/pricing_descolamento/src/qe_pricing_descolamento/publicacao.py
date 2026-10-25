"""Publicação do descolamento: serving/pricing_descolamento/<chave>.json (o que a página lê) e o registro das rodadas
(pesquisa: web.exportar, web.resumo_rodada, web.registrar_rodada).

O modelo roda uma vez por deck. Para cada mês e cenário climático saem os coeficientes horários e o perfil do SE; a
página recalcula, no navegador, o descolamento exato do modelo para a curva do SE digitada (web/pricing_descolamento/
descolamento_conta.js, com teste de paridade contra `qe_pricing_descolamento.conta`). O que não depende da curva vem
pronto daqui: o histórico realizado por período, com a comparação com os mesmos períodos dos outros anos, e os
fundamentos do deck por produto (pacote de promoção, seção 7).

Rodada = publicação com o deck do NEWAVE vigente e a versão do modelo: DESSEM e PLD novos não geram rodada sozinhos (o
modelo só usa dados até D−2). Cada rodada guarda o descolamento com o SE plano de referência (R$ 200) por ano e
semestre completos, para comparar decks sem a curva digitada no meio. As rodadas de jan/2025 a set/2026 vêm da
pesquisa, reconstruídas (`reconstruida: true`: como a v2.2 teria visto cada deck, não o que foi publicado).
"""

import datetime as dt
import json

import numpy as np
import pandas as pd

from qe_core.armazenamento import Armazenamento, ler_parquet
from qe_pricing_descolamento import chaves, tratamento
from qe_pricing_descolamento import modelo as M

SE_REFERENCIA = 200.0  # curva fixa das rodadas: a diferença entre rodadas vem do deck e dos dados
ANOS_HORIZONTE = 4  # horizonte: do mês seguinte ao deck até dezembro de D.ano + 4
MES_ABR = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def _r(v, c=4):
    """Arredonda para reduzir o arquivo (None para valores inválidos)."""
    if v is None or not np.isfinite(v):
        return None
    return round(float(v), c)


def rot(p: str) -> str:
    return f"{MES_ABR[int(p[5:7]) - 1]}/{p[2:4]}"


def deck_vigente(arm: Armazenamento) -> pd.Period:
    """O deck do NEWAVE mais recente com o conjunto sistema_agrint em raw/."""
    return pd.Period(max(tratamento.decks_sistema_agrint(arm)), "M")


def horizonte(d: pd.Period) -> list[pd.Period]:
    return list(pd.period_range(d + 1, pd.Period(f"{d.year + ANOS_HORIZONTE}-12", "M"), freq="M"))


def dados_ate(d: pd.Period) -> str:
    return str(((d - 1).to_timestamp() - pd.Timedelta(hours=1)).date())


# --- dados por mês (pesquisa: web.exportar) ----------------------------------------------------------------


def sazonal_se(b: M.Base) -> dict:
    """SE do mês ÷ média do ano (ponderada por horas), média dos anos completos com dados."""
    x = b.mensal.copy()
    x.index = pd.PeriodIndex(x.index, freq="M")
    x["horas"] = [p.days_in_month * 24 for p in x.index]
    anos = [int(a) for a, g in x.groupby(x.index.year) if len(g) == 12 and a >= 2021]
    fat = []
    for a in anos:
        g = x[x.index.year == a]
        fat.append((g["SE"] / np.average(g["SE"], weights=g["horas"])).to_numpy())
    return {"anos": anos, "fator": [_r(v) for v in np.mean(fat, axis=0)]}


def _k_real(b: M.Base, y: pd.DataFrame) -> float | None:
    """k realizado do NE no mês: média de (SE − NE)/(SE − piso) nas horas descoladas (≥ 20 h), como no modelo."""
    tr = y[y["desc_NE"].astype(bool)]
    if len(tr) < 20:
        return None
    piso = tr.index.year.map(b.limites["piso"]).to_numpy()
    return _r(((tr["SE"] - tr["NE"]) / (tr["SE"] - piso).clip(lower=1)).clip(0, 1).mean(), 3)


def historico_mensal(b: M.Base) -> list:
    """Realizado por mês desde 2021 (meses completos do PLD; física do DESSEM quando cobre ≥ 60% das horas)."""
    mensal = b.mensal.set_index(pd.PeriodIndex(b.mensal.index, freq="M"))
    out = []
    for m, y in b.h.groupby("mes"):
        if len(y) < m.days_in_month * 24 * 0.6 or m not in mensal.index:
            continue
        piso = float(b.limites.loc[m.year, "piso"])
        tr = y[y["desc_NE"].astype(bool)]
        k_soma = (
            float(((tr["SE"] - tr["NE"]) / (tr["SE"] - piso).clip(lower=1)).clip(0, 1).sum())
            if len(tr)
            else 0.0
        )
        out.append(
            {
                "mes": str(m),
                "horas": m.days_in_month * 24,
                "cobertura_dessem": _r(len(y) / (m.days_in_month * 24), 2),
                "piso": _r(piso, 2),
                "SE": _r(mensal.loc[m, "SE"], 2),
                "d_NE": _r(mensal.loc[m, "d_NE"], 2),
                "d_N": _r(mensal.loc[m, "d_N"], 2),
                "trava": _r(y["desc_NE"].astype(bool).mean(), 3),
                "k_soma": _r(k_soma, 2),
                "k_horas": len(tr),
                "renov_NE": _r(y["renovavel_NE"].mean() / 1e3, 2),
                "carga_NE": _r(y["demanda_NE"].mean() / 1e3, 2),
                "carga_N": _r(y["demanda_N"].mean() / 1e3, 2),
                "hidr_N": _r(y["hidraulica_N"].mean() / 1e3, 2),
                "hidr_NE": _r(y["hidraulica_NE"].mean() / 1e3, 2),
                "sobra_NNE": _r(y["sobra_NNE_st"].mean() / 1e3, 2),
                "exp_NE": _r(y["valor_EXP_NE"].mean() / 1e3, 2),
                "lim_NE": _r(y["lsup_EXP_NE"].mean() / 1e3, 2),
            }
        )
    return out


def meses_pagina(b: M.Base, d: pd.Period, mod: dict) -> list:
    """Por mês do horizonte: piso, perfil do SE, coeficientes de cada cenário, fundamentos do deck e o último
    realizado do mesmo mês do calendário."""
    mensal = b.mensal.set_index(pd.PeriodIndex(b.mensal.index, freq="M"))
    saida = []
    for m in horizonte(d):
        p = M.prever(b, d, m, SE_REFERENCIA, mod)
        if p.empty:
            continue
        ins = M.insumos_mes(b, d, m, mod)
        w = p["peso"].to_numpy()
        cen = [
            {
                "id": str(c.ano_hidro),
                "ano": int(c.ano_hidro),
                "peso": _r(c.peso),
                "cNE": [_r(v, 6) for v in c.c_NE],
                "cN": [_r(v, 6) for v in c.c_N],
                "trava": _r(c.p_trava_NE),
                "k": _r(c.k_prev_NE),
            }
            for c in p.itertuples()
        ]
        ult = [q for q in b.real_mes.index if q.month == m.month and q <= d - 2]
        real = None
        if ult:
            y = b.h[b.h["mes"] == ult[-1]]
            tem = ult[-1] in mensal.index
            real = {
                "mes": str(ult[-1]),
                "renov_NE": _r(y["renovavel_NE"].mean() / 1e3, 2),
                "carga_NE": _r(y["demanda_NE"].mean() / 1e3, 2),
                "carga_N": _r(y["demanda_N"].mean() / 1e3, 2),
                "lim_NE": _r(y["lsup_EXP_NE"].mean() / 1e3, 2),
                "hidr_N": _r(y["hidraulica_N"].mean() / 1e3, 2),
                "hidr_NE": _r(y["hidraulica_NE"].mean() / 1e3, 2),
                "trava": _r(y["desc_NE"].astype(bool).mean(), 3),
                "k": _k_real(b, y),
                "se": _r(mensal.loc[ult[-1], "SE"], 2) if tem else None,
                "d_NE": _r(mensal.loc[ult[-1], "d_NE"], 2) if tem else None,
                "d_N": _r(mensal.loc[ult[-1], "d_N"], 2) if tem else None,
            }
        saida.append(
            {
                "mes": str(m),
                "horas": m.days_in_month * 24,
                "piso": _r(p["piso"].iloc[0], 2),
                "perfil": [_r(v) for v in p["perfil_h"].iloc[0]],
                "cen": cen,
                "fund": {
                    "renov_NE": _r(np.average(p["renovavel_efetiva_NE"], weights=w) / 1e3, 2),
                    "carga_NE": _r(ins["carga_NE"] / 1e3, 2),
                    "carga_N": _r(ins["carga_N"] / 1e3, 2),
                    "lim_NE": _r(ins["limite_exp_NE"] / 1e3, 2),
                    "hidr_N": _r(np.average(p["hidraulica_N"], weights=w) / 1e3, 2),
                    "hidr_NE": _r(np.average(p["hidraulica_NE"], weights=w) / 1e3, 2),
                    "trava": _r(np.average(p["p_trava_NE"], weights=w), 3),
                    "k": _r(
                        np.nansum(p["k_prev_NE"] * p["p_trava_NE"] * w)
                        / max(np.sum(p["p_trava_NE"] * w), 1e-9),
                        3,
                    ),
                },
                "real": real,
            }
        )
    return saida


# --- produtos do horizonte (mês, trimestre, semestre, ano) -----------------------------------------------


def periodos_do_ano(meses: list[str], y: int) -> dict:
    """Ano, semestres e trimestres de um ano do horizonte (mesma organização da página)."""
    ms = [p for p in meses if int(p[:4]) == y]
    yy = str(y)[2:]
    S = [
        {"rot": f"{s}º sem/{yy}", "meses": [p for p in ms if (int(p[5:7]) <= 6) == (s == 1)]}
        for s in (1, 2)
    ]
    T = [
        {"rot": f"T{t}/{yy}", "meses": [p for p in ms if (int(p[5:7]) - 1) // 3 + 1 == t]}
        for t in (1, 2, 3, 4)
    ]
    rot_ano = str(y) if len(ms) == 12 else f"{rot(ms[0])[:3]}–{rot(ms[-1])}"
    return {"y": y, "rot": rot_ano, "meses": ms, "S": S, "T": T}


def produtos(meses: list[str], tipo: str) -> list[dict]:
    out = []
    for a in (periodos_do_ano(meses, y) for y in sorted({int(p[:4]) for p in meses})):
        if tipo == "ano":
            out.append({"rot": a["rot"], "meses": a["meses"], "parcial": len(a["meses"]) < 12})
        if tipo == "sem":
            out += [{**s, "parcial": len(s["meses"]) < 6} for s in a["S"] if s["meses"]]
        if tipo == "tri":
            out += [{**t, "parcial": len(t["meses"]) < 3} for t in a["T"] if t["meses"]]
        if tipo == "mes":
            out += [{"rot": rot(p), "meses": [p], "parcial": False} for p in a["meses"]]
    return out


# --- fundamentos por produto (antes no navegador: fundAgregado) ---------------------------------------------

CAMPOS_FUND = ["renov_NE", "carga_NE", "carga_N", "lim_NE", "hidr_N", "hidr_NE", "trava"]


def _derivar(o: dict | None) -> dict | None:
    """Sobra renovável do NE (renovável − carga) e folga até o limite de exportação (limite − sobra)."""
    if not o or o.get("renov_NE") is None or o.get("carga_NE") is None:
        return o
    sobra = o["renov_NE"] - o["carga_NE"]
    return {
        **o,
        "sobra": sobra,
        "folga": o["lim_NE"] - sobra if o.get("lim_NE") is not None else None,
    }


def fund_agregado(meses: list[dict], ms: list[str]) -> dict:
    """Fundamentos de um produto: média por horas (k ponderado pelas horas em que se espera trava); modelo e o
    último realizado dos mesmos meses do calendário."""
    por = {m["mes"]: m for m in meses}
    H = sum(por[p]["horas"] for p in ms)
    w = {p: por[p]["horas"] / H for p in ms}
    mod, rea = {}, {}
    for f in CAMPOS_FUND:
        mod[f] = sum(por[p]["fund"][f] * w[p] for p in ms)
        tem = all(por[p]["real"] and por[p]["real"].get(f) is not None for p in ms)
        rea[f] = sum(por[p]["real"][f] * w[p] for p in ms) if tem else None

    def kpond(fonte):
        a = b = 0.0
        for p in ms:
            x = fonte(p)
            if x and x.get("k") is not None and x.get("trava") is not None:
                a += x["k"] * x["trava"] * w[p]
                b += x["trava"] * w[p]
        return a / b if b > 0 else None

    mod["k"], rea["k"] = kpond(lambda p: por[p]["fund"]), kpond(lambda p: por[p]["real"])
    for o in (mod, rea):
        o["sobra"] = (
            o["renov_NE"] - o["carga_NE"]
            if o["renov_NE"] is not None and o["carga_NE"] is not None
            else None
        )
        o["folga"] = (
            o["lim_NE"] - o["sobra"] if o["lim_NE"] is not None and o["sobra"] is not None else None
        )
    refs = sorted({por[p]["real"]["mes"] for p in ms if por[p]["real"]})
    return {"mod": mod, "rea": rea, "refs": refs}


def fund_periodos(meses: list[dict]) -> dict:
    ms = [m["mes"] for m in meses]
    out = {}
    for tipo in ("mes", "tri", "sem", "ano"):
        out[tipo] = [
            {
                "rot": p["rot"],
                "parcial": p["parcial"],
                "meses": p["meses"],
                **fund_agregado(meses, p["meses"]),
            }
            for p in produtos(ms, tipo)
        ]
    # por mês, também a série do modelo e do realizado para os gráficos pequenos
    out["serie"] = [
        {"mes": m["mes"], "mod": _derivar(m["fund"]), "rea": _derivar(m["real"])} for m in meses
    ]
    return out


# --- histórico realizado por período (antes no navegador: agrH, comparaveis, dicaHist) ----------------------

CAMPOS_HIST = [
    "SE",
    "piso",
    "d_NE",
    "d_N",
    "trava",
    "renov_NE",
    "carga_NE",
    "carga_N",
    "hidr_N",
    "sobra_NNE",
]
CAMPOS_HIST += ["exp_NE", "lim_NE"]
# (nome na dica, campo, tipo, ordem da posição: "desc" = 1º é o mais descolado, "mais" = 1º é o maior)
LINHAS_HIST = [
    ("NE (R$/MWh)", "d_NE", "rs", "desc"),
    ("N (R$/MWh)", "d_N", "rs", "desc"),
    ("Renovável NE (GW)", "renov_NE", "gw", "mais"),
    ("Carga NE (GW)", "carga_NE", "gw", "mais"),
    ("Carga N (GW)", "carga_N", "gw", "mais"),
    ("Hidráulica N (GW)", "hidr_N", "gw", "mais"),
    ("Sobra N+NE (GW)", "sobra_NNE", "gw", "mais"),
    ("Exportação NE (GW)", "exp_NE", "gw", "mais"),
    ("Uso do limite de exp. NE", "uso", "pct", "mais"),
    None,
    ("NE (% da folga)", "fracao", "pct", "mais"),
    ("Horas travadas NE", "trava", "pct", "mais"),
    ("k NE", "k", "k", "mais"),
]


def agr_hist(hm: dict, ms: list[str]) -> dict:
    """Média por horas dos meses `ms` do histórico; k = Σ frações ÷ horas travadas (≥ 20 h); fração da folga só
    com SE ≥ piso + R$ 20."""
    H = sum(hm[p]["horas"] for p in ms)
    o = {f: sum(hm[p][f] * hm[p]["horas"] / H for p in ms) for f in CAMPOS_HIST}
    ks, kh = sum(hm[p]["k_soma"] for p in ms), sum(hm[p]["k_horas"] for p in ms)
    o["k"] = ks / kh if kh >= 20 else None
    folga = o["SE"] - o["piso"]
    o["fracao"] = min(max(-o["d_NE"] / folga, 0), 1) if folga >= 20 else None
    o["uso"] = o["exp_NE"] / o["lim_NE"] if o["lim_NE"] > 0 else None
    o["cob"] = min(
        hm[p]["cobertura_dessem"] if hm[p]["cobertura_dessem"] is not None else 1 for p in ms
    )
    return o


def historico_periodos(historico: list) -> list:
    """Cada célula da tabela do realizado (ano, semestres e trimestres completos, meses), do ano mais recente ao mais
    antigo: valores do período e a comparação com os mesmos meses do calendário nos outros anos (média, diferença,
    posição e a marca ▲/▼ de bem mais / menos descolado que a média)."""
    hm = {m["mes"]: m for m in historico}
    anos = sorted({int(p[:4]) for p in hm})
    de = lambda y, mm: [f"{y}-{k:02d}" for k in mm if f"{y}-{k:02d}" in hm]

    def comparaveis(ms):
        mm = [int(p[5:7]) for p in ms]
        return [(y, agr_hist(hm, de(y, mm))) for y in anos if len(de(y, mm)) == len(mm)]

    def celula(tipo, rotulo, ms):
        g, cmp = agr_hist(hm, ms), comparaveis(ms)
        linhas = []
        for linha in LINHAS_HIST:
            if linha is None:
                linhas.append(None)
                continue
            nome, f, t, ordem = linha
            v, vals = g[f], [c[f] for _, c in cmp if c[f] is not None]
            if v is None and not vals:
                continue
            med = sum(vals) / len(vals) if vals else None
            ordenado = sorted(vals, reverse=ordem != "desc")
            linhas.append(
                {
                    "nome": nome,
                    "tipo": t,
                    "v": v,
                    "med": med,
                    "pos": ordenado.index(v) + 1 if v is not None else None,
                    "n": len(vals),
                }
            )
        marca = {}
        for s in M.SUBS:
            vals = [c[f"d_{s}"] for _, c in cmp]
            med, v = sum(vals) / len(vals), g[f"d_{s}"]
            marca[s] = ("▲" if v < med else "▼") if abs(v - med) > max(2, 0.5 * abs(med)) else ""
        return {
            "tipo": tipo,
            "rot": rotulo,
            "meses": ms,
            "SE": g["SE"],
            "d_NE": g["d_NE"],
            "d_N": g["d_N"],
            "cob": g["cob"],
            "marca": marca,
            "anos": [y for y, _ in cmp],
            "linhas": linhas,
        }

    out = []
    for y in reversed(anos):
        yy = str(y)[2:]
        ano = de(y, range(1, 13))
        rot_a = str(y) if len(ano) == 12 else f"{rot(ano[0])[:3]}–{rot(ano[-1])}"
        cel = {"ano": y, "rot": rot_a, "parcial": len(ano) < 12, "A": celula("ano", rot_a, ano)}
        for s, mm in ((1, range(1, 7)), (2, range(7, 13))):
            ms = de(y, mm)
            cel[f"S{s}"] = celula("sem", f"{s}º sem/{yy}", ms) if len(ms) == 6 else None
        for q in (1, 2, 3, 4):
            ms = de(y, range(3 * q - 2, 3 * q + 1))
            cel[f"T{q}"] = celula("tri", f"T{q}/{yy}", ms) if len(ms) == 3 else None
        cel["M"] = {p: celula("mes", rot(p), [p]) for p in ano}
        out.append(cel)
    return out


# --- rodadas -----------------------------------------------------------------------------------------------


def resumo_rodada(b: M.Base, d: pd.Period, mod: dict, rodada: str) -> dict:
    """Uma linha do registro: descolamento com o SE plano de referência por ano e semestre completos, horas
    travadas do NE e insumos médios (pesquisa: web.resumo_rodada)."""
    lin = []
    for m in horizonte(d):
        p = M.prever(b, d, m, SE_REFERENCIA, mod)
        if p.empty:
            continue
        ins, w = M.insumos_mes(b, d, m, mod), p["peso"]
        lin.append(
            {
                "mes": m,
                "horas": m.days_in_month * 24,
                "NE": np.average(p["d_NE"], weights=w),
                "N": np.average(p["d_N"], weights=w),
                "trava": np.average(p["p_trava_NE"], weights=w),
                "renov_NE": np.average(p["renovavel_efetiva_NE"], weights=w) / 1000,
                "carga_NE": ins["carga_NE"] / 1000,
                "lim_NE": ins["limite_exp_NE"] / 1000,
            }
        )
    x = pd.DataFrame(lin)

    def agregar(chave):
        g = x.groupby(x["mes"].map(chave))
        return {
            k: {
                "n": len(y),
                **{
                    c: np.average(y[c], weights=y["horas"])
                    for c in x.columns
                    if c not in ("mes", "horas")
                },
            }
            for k, y in g
        }

    anos = agregar(lambda m: str(m.year))
    sem = agregar(lambda m: f"{m.year}-S{1 if m.month <= 6 else 2}")
    return {
        "deck": str(d),
        "versao": M.MODELO.versao,
        "rodada": rodada,
        "dados_ate": dados_ate(d),
        "reconstruida": False,
        "se_ref": SE_REFERENCIA,
        "anos": {
            a: {
                "NE": _r(r["NE"], 2),
                "N": _r(r["N"], 2),
                "trava": _r(r["trava"], 3),
                "renov_NE": _r(r["renov_NE"], 2),
                "carga_NE": _r(r["carga_NE"], 2),
                "lim_NE": _r(r["lim_NE"], 2),
            }
            for a, r in anos.items()
            if r["n"] == 12
        },
        "semestres": {
            k: {"NE": _r(r["NE"], 2), "N": _r(r["N"], 2)} for k, r in sem.items() if r["n"] == 6
        },
    }


# Acompanhamento do nível da hidráulica do NE (D039): gatilho para repetir os testes de hidráulica (itens 24 e 25),
# fixado antes de ver a série. Não é parâmetro do método: o modelo não usa estes valores.
GATILHO_HIDR_NE = 30.0  # % de erro absoluto médio do nível
JANELA_HIDR_NE = 6  # meses seguidos acima do gatilho


def acompanhamento_hidr_ne(b: M.Base, inicio: str = "2025-01", cobertura: float = 0.6) -> dict:
    """Nível da hidráulica do NE que o modelo usou × realizado, por mês-alvo (pesquisa: web.acompanhamento_hidr_ne).

    Para cada mês-alvo m, o deck é o do mês anterior (o último antes de o mês começar); o nível usado é a média do
    perfil horário do mesmo mês do calendário no ano mais recente com dados até D−2, igual em todos os cenários
    (`modelo.cenarios`). Só meses com ≥ 60% das horas do DESSEM. É uma reconstrução com a versão vigente, não o
    registro do que foi publicado em cada rodada."""
    modelos, linhas = {}, []
    for m in pd.period_range(inicio, b.h["mes"].max(), freq="M"):
        y = b.h[b.h["mes"] == m]
        if len(y) < m.days_in_month * 24 * cobertura:
            continue
        d = m - 1
        if d not in modelos:
            modelos[d] = M.treinar(b, d)
        ins = M.insumos_mes(b, d, m, modelos[d])
        cen = M.cenarios(b, d, m, ins) if ins else []
        if not cen:
            continue
        info = cen[0][0]
        real = float(y["hidraulica_NE"].mean())
        linhas.append(
            {
                "mes": str(m),
                "deck": str(d),
                "ano_usado": info["ano_hidr_ne"],
                "usado": _r(info["hidraulica_NE"] / 1e3, 2),
                "real": _r(real / 1e3, 2),
                "erro_pct": _r(100 * (info["hidraulica_NE"] - real) / real, 1),
            }
        )
    erros = [x["erro_pct"] for x in linhas]
    ult = erros[-JANELA_HIDR_NE:]
    return {
        "gatilho_pct": GATILHO_HIDR_NE,
        "janela": JANELA_HIDR_NE,
        "linhas": linhas,
        "resumo": {
            "n": len(erros),
            "vies_pct": _r(np.mean(erros), 1) if erros else None,
            "eam_pct": _r(np.mean(np.abs(erros)), 1) if erros else None,
            "eam_ultimos_pct": _r(float(np.mean(np.abs(ult))), 1) if ult else None,
            "vies_ultimos_pct": _r(np.mean(ult), 1) if ult else None,
            "mesmo_sinal_ultimos": int(sum(np.sign(e) == np.sign(ult[-1]) for e in ult))
            if ult
            else 0,
            "acima_gatilho": bool(
                len(ult) == JANELA_HIDR_NE and all(abs(e) > GATILHO_HIDR_NE for e in ult)
            ),
        },
    }


def marcos_historico(b: M.Base, historico: list) -> list:
    """Decks do registro de rodadas em que um regime (1S ou 2S) passa a ter modelo da chance de travar do NE (D040).

    Antes disso o modelo do regime fica vazio (menos de `min_horas_classe` horas de uma das classes no treino), a chance
    é zero e o descolamento previsto do semestre é zero: o histórico mostra um degrau no deck em que o regime ganha dado
    pela primeira vez. Só conta transição dentro do histórico (vazio no deck anterior, ajustado neste). `horas` e
    `horas_antes` são as horas de NE descolado do regime no treino (desde `inicio_treino` até o início do mês D−1)."""
    feats, ini = list(M.MODELO.features), pd.Timestamp(M.MODELO.inicio_treino)
    marcos, ant = [], {}
    for r in sorted(historico, key=lambda x: x["deck"]):
        d = pd.Period(r["deck"], "M")
        mod = M.treinar(b, d)
        t = b.h[(b.h.index >= ini) & (b.h.index < (d - 1).to_timestamp())].dropna(subset=feats)
        for regime in M.REGIMES:
            tem = mod[("p", regime, "NE")] is not None
            horas = int(t.loc[t["regime"] == regime, "desc_NE"].astype(bool).sum())
            if tem and ant.get(regime, (None,))[0] is False:
                marcos.append(
                    {
                        "deck": r["deck"],
                        "regime": regime,
                        "deck_antes": ant[regime][2],
                        "horas_antes": ant[regime][1],
                        "horas": horas,
                        "minimo": M.MODELO.min_horas_classe,
                        "dados_ate": str(d - 2),
                    }
                )
            ant[regime] = (tem, horas, r["deck"])
    return marcos


class RodadaRepetida(Exception):
    """Deck e modelo iguais aos da última rodada: publicar de novo exige --forcar e --motivo."""


def carregar_registro(arm: Armazenamento) -> list:
    if not arm.existe(chaves.SERVING_REGISTRO):
        return []
    return json.loads(arm.ler_bytes(chaves.SERVING_REGISTRO).decode("utf-8"))


def gravar_registro(arm: Armazenamento, registro: list) -> None:
    arm.gravar_bytes(
        (json.dumps(registro, ensure_ascii=False, indent=1) + "\n").encode("utf-8"),
        chaves.SERVING_REGISTRO,
    )


# --- montagem e gravação -----------------------------------------------------------------------------------


def dados(
    arm: Armazenamento, d: pd.Period, rodada: str, b: M.Base | None = None, mod: dict | None = None
) -> dict:
    """Todas as chaves da página para o deck d."""
    b = b or M.Base(arm)
    mod = mod or M.treinar(b, d)
    meses = meses_pagina(b, d, mod)
    hist = historico_mensal(b)
    lim = b.limites.loc[min(d.year, b.limites.index.max())]
    return {
        "meta": {
            "deck": str(d),
            "versao": M.MODELO.versao,
            "rodada": rodada,
            "dados_ate": dados_ate(d),
            "piso": _r(lim["piso"], 2),
            "teto": _r(lim["teto_estrutural"], 2),
            "horizonte": [meses[0]["mes"], meses[-1]["mes"]],
        },
        "sazonal_se": sazonal_se(b),
        "historico": hist,
        "meses": meses,
        "historico_periodos": historico_periodos(hist),
        "fund_periodos": fund_periodos(meses),
    }


def publicar(arm: Armazenamento, motivo: str | None = None, forcar: bool = False) -> dict:
    """Regrava serving/pricing_descolamento/ com o deck vigente e registra uma rodada quando o deck ou o modelo
    mudaram em relação à última rodada do registro. Devolve o meta publicado (com `nova_rodada`)."""
    d = deck_vigente(arm)
    reg = carregar_registro(arm)
    ultima = reg[-1] if reg else None
    repetida = ultima is not None and (ultima["deck"], ultima["versao"]) == (
        str(d),
        M.MODELO.versao,
    )
    if repetida and forcar and not motivo:
        raise RodadaRepetida("--forcar exige --motivo")
    nova = not repetida or forcar
    b = M.Base(arm)
    mod = M.treinar(b, d)
    rodada = dt.datetime.now().strftime("%Y-%m-%dT%H:%M") if nova else ultima["rodada"]
    if nova:
        linha = resumo_rodada(b, d, mod, rodada)
        linha["motivo"] = motivo or f"deck do NEWAVE de {rot(str(d))}"
        reg.append(linha)
        gravar_registro(arm, reg)
    pagina = dados(arm, d, rodada, b, mod)
    from qe_pricing_descolamento import compra_venda as cv

    if arm.existe(chaves.PROC_BACKTEST):  # metodologia: desempenho do backtest da página
        from qe_pricing_descolamento.desempenho import desempenho

        x = ler_parquet(arm, chaves.PROC_BACKTEST)
        pagina["desempenho"] = desempenho(b, x)
        pagina["cv_backtest"] = cv.dados_backtest(
            b, x
        )  # compra e venda: casos do painel do passado
    pagina["cv_historico"] = cv.dados_historico(
        b, str(d)
    )  # compra e venda: venda ancorada no realizado
    pagina["cv_exemplo"] = cv.exemplo(
        pagina["meses"], pagina["sazonal_se"]["fator"], str(d)
    )  # compra e venda: exemplo da metodologia
    pagina["hist_marcos"] = marcos_historico(
        b, reg
    )  # metodologia: degrau do histórico de rodadas (D040)
    pagina["hidr_ne"] = acompanhamento_hidr_ne(
        b
    )  # metodologia: nível da hidráulica do NE usado × realizado
    from qe_pricing_descolamento.fundamentos import dados_fundamentos

    pagina["fundamentos"] = dados_fundamentos(b)  # página de fundamentos: o realizado, sem o modelo
    for nome, valor in pagina.items():
        arm.gravar_bytes(
            json.dumps(valor, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            chaves.serving(nome),
        )
    return pagina["meta"] | {"nova_rodada": nova}
