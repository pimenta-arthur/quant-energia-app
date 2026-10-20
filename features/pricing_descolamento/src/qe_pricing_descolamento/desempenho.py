"""Desempenho do modelo para a página de metodologia (pesquisa: web.desempenho, estrutural.resumo_backtest_periodos,
comparacao.py; D025, D031–D035).

Sobre o backtest da página (SE realizado como insumo): por trimestre e semestre que começam depois do deck, o preço
justo e a faixa entre cenários contra o realizado (erro médio absoluto, viés, cobertura da faixa, largura e CRPS), nos
recortes "todos" e "treinada" (P(trava) prevista > 0,5% das horas). Comparação, nos mesmos casos, com alternativas de
referência:
- assumir zero: não há descolamento;
- repetir: fração do mesmo mês no último ano realizado até D−2 × folga do SE;
- climatologia: um cenário por ano (desde 2021) com a fração do mês; faixa = média por horas do menor e do maior valor
  de cada mês.
Fração = descolamento ÷ (SE − piso), limitada a [−1, 0]; meses com SE a menos de R$ 20 do piso ficam de fora.
"""

import numpy as np
import pandas as pd

from qe_pricing_descolamento import modelo as M

FOLGA_MIN = 20.0
LIMIAR_TREINADA = 0.5  # % das horas: abaixo disso, o modelo praticamente não prevê trava no período


def _r(v, c=4):
    if v is None or not np.isfinite(v):
        return None
    return round(float(v), c)


ROTULO = {
    "trimestre": lambda m: f"{m.year}-T{m.quarter}",
    "semestre": lambda m: f"{m.year}-S{1 if m.month <= 6 else 2}",
}


def inicio(p: str) -> pd.Period:
    """Primeiro mês do período ('2025-T3' → 2025-07; '2025-S2' → 2025-07)."""
    if "-T" in p:
        return pd.Period(f"{p[:4]}-{3 * int(p[-1]) - 2:02d}", "M")
    return pd.Period(f"{p[:4]}-{'01' if p.endswith('1') else '07'}", "M")


def crps_ponderado(x, w, y: float) -> float:
    """CRPS de uma amostra com pesos: E|X−y| − ½·E|X−X'| (pesos normalizados)."""
    w = np.asarray(w, float) / np.sum(w)
    x = np.asarray(x, float)
    return float(
        np.sum(w * np.abs(x - y))
        - 0.5 * np.sum(w[:, None] * w[None, :] * np.abs(x[:, None] - x[None, :]))
    )


def resumo_periodos(x: pd.DataFrame, periodo: str) -> pd.DataFrame:
    """Por (deck, período): preço justo (média dos cenários em cada mês, depois por horas) e faixa, CRPS e cobertura
    (cada cenário agregado no período, só os presentes em todos os meses), mais as variáveis do período."""
    x = x.assign(periodo=x["mes"].map(ROTULO[periodo]))
    alvo = ("NE_prev", "N_prev", "trav_prev_%")
    por_mes = x.groupby(["deck", "periodo", "mes"]).apply(
        lambda g: pd.Series(
            {"horas": g["horas"].iloc[0], **{c: np.average(g[c], weights=g["peso"]) for c in alvo}}
        ),
        include_groups=False,
    )
    prev = por_mes.groupby(["deck", "periodo"]).apply(
        lambda g: pd.Series({c: np.average(g[c], weights=g["horas"]) for c in alvo}),
        include_groups=False,
    )
    prev = prev.rename(columns={"trav_prev_%": "trav_prev"})
    w = lambda g, c: np.average(g[c], weights=g["horas"])
    cen = (
        x.groupby(["deck", "periodo", "cenario"])
        .apply(
            lambda g: pd.Series(
                {
                    "meses": g["mes"].nunique(),
                    "NE_prev": w(g, "NE_prev"),
                    "N_prev": w(g, "N_prev"),
                    "peso": g["peso"].iloc[0],
                }
            ),
            include_groups=False,
        )
        .reset_index()
    )
    n_mes = x.groupby(["deck", "periodo"])["mes"].nunique().rename("n_mes")
    cen = cen.join(n_mes, on=["deck", "periodo"])
    cen = cen[cen["meses"] == cen["n_mes"]]
    reais = (
        x.drop_duplicates(["deck", "mes"])
        .groupby(["deck", "periodo"])
        .apply(lambda g: np.average(g["NE_real"], weights=g["horas"]), include_groups=False)
    )
    dist = {}
    for (dk, per), g in cen.groupby(["deck", "periodo"]):
        y = reais.loc[(dk, per)]
        dist[(dk, per)] = {
            "NE_min": g["NE_prev"].min(),
            "NE_max": g["NE_prev"].max(),
            "N_min": g["N_prev"].min(),
            "N_max": g["N_prev"].max(),
            "crps_NE": crps_ponderado(g["NE_prev"].to_numpy(), g["peso"].to_numpy(), y),
            "cobre_NE": float(g["NE_prev"].min() - 1 <= y <= g["NE_prev"].max() + 1),
            "largura_NE": g["NE_prev"].max() - g["NE_prev"].min(),
            "n_cenarios": len(g),
        }
    prev = prev.join(pd.DataFrame(dist).T.rename_axis(["deck", "periodo"]))
    # k previsto: média ponderada pelas horas travadas esperadas, por cenário e depois entre cenários
    xx = x.assign(
        wk=x["trav_prev_%"] * x["horas"], kw=x["k_prev"].fillna(0) * x["trav_prev_%"] * x["horas"]
    )
    kp = xx.groupby(["deck", "periodo"])[["kw", "wk"]].sum()
    prev["k_prev"] = kp["kw"] / kp["wk"].replace(0, np.nan)
    mes = x.drop_duplicates(["deck", "mes"])
    fora = (
        "deck",
        "mes",
        "horas",
        "cenario",
        "NE_prev",
        "N_prev",
        "trav_prev_%",
        "periodo",
        "k_prev",
        "peso",
    )
    cols = [c for c in mes.columns if c not in fora]
    var = mes.groupby(["deck", "periodo"]).apply(
        lambda g: pd.Series(
            {c: np.nansum(g[c] * g["horas"]) / g.loc[g[c].notna(), "horas"].sum() for c in cols}
        ),
        include_groups=False,
    )
    k = mes.groupby(["deck", "periodo"])[["k_soma", "k_horas"]].sum()
    var["k_real"] = k["k_soma"] / k["k_horas"].replace(0, np.nan)
    var = var.drop(columns=["k_soma", "k_horas"])
    out = prev.join(var)
    out["NE_erro"] = out["NE_prev"] - out["NE_real"]
    out["N_erro"] = out["N_prev"] - out["N_real"]
    return out


def _fracoes(b: M.Base) -> tuple[pd.DataFrame, pd.DataFrame]:
    mensal = b.mensal.set_index(pd.PeriodIndex(b.mensal.index, freq="M"))
    f = pd.DataFrame(index=mensal.index)
    piso = mensal.index.year.map(b.limites["piso"]).to_numpy()
    folga = mensal["SE"].to_numpy() - piso
    for s in M.SUBS:
        fr = np.clip(mensal[f"d_{s}"].to_numpy() / np.maximum(folga, 1), -1, 0)
        f[s] = np.where(folga >= FOLGA_MIN, fr, np.nan)
    return mensal, f


def alternativas(b: M.Base, x: pd.DataFrame, periodo: str) -> pd.DataFrame:
    """Para cada (deck, período) do backtest: realizado, modelo e as três alternativas (NE e N), com faixa e CRPS."""
    mensal, fr = _fracoes(b)
    mod = resumo_periodos(x, periodo)
    meses = x.drop_duplicates(["deck", "mes"])[["deck", "mes", "horas"]].copy()
    meses["periodo"] = meses["mes"].map(ROTULO[periodo])
    anos = sorted({p.year for p in fr.index if p.year >= 2021})
    lin = []
    for (dk, per), g in meses.groupby(["deck", "periodo"]):
        d = pd.Period(dk, "M")
        ms, h = list(g["mes"]), g["horas"].to_numpy(float)
        w = h / h.sum()
        se = mensal.loc[ms, "SE"].to_numpy()
        piso = np.array([b.limites.loc[min(m.year, d.year), "piso"] for m in ms])
        folga = np.maximum(se - piso, 0)
        r = {"deck": dk, "periodo": per, "SE": float(se @ w)}
        for s in M.SUBS:
            r[f"{s}_real"] = float(mensal.loc[ms, f"d_{s}"].to_numpy() @ w)
            r[f"{s}_zero"] = 0.0
            rep = []
            for m in ms:
                ult = [p for p in fr.index if p.month == m.month and p <= d - 2]
                rep.append(fr.loc[ult[-1], s] if ult and np.isfinite(fr.loc[ult[-1], s]) else 0.0)
            r[f"{s}_repetir"] = float((np.array(rep) * folga) @ w)
            por_mes, lo_m, hi_m, cen = [], [], [], {}
            for i, m in enumerate(ms):
                vals = {}
                for a in anos:
                    p = pd.Period(f"{a}-{m.month:02d}", "M")
                    if p <= d - 2 and p in fr.index and np.isfinite(fr.loc[p, s]):
                        vals[a] = fr.loc[p, s] * folga[i]
                por_mes.append(np.mean(list(vals.values())) if vals else 0.0)
                lo_m.append(min(vals.values()) if vals else 0.0)
                hi_m.append(max(vals.values()) if vals else 0.0)
                for a, v in vals.items():
                    cen.setdefault(a, {})[i] = v
            r[f"{s}_clim"] = float(np.array(por_mes) @ w)
            completos = [
                np.array([c[i] for i in range(len(ms))]) @ w
                for c in cen.values()
                if len(c) == len(ms)
            ]
            # faixa: média por horas do menor e do maior valor de cada mês (o justo fica sempre dentro dela);
            # igual ou mais larga que a faixa por cenário completo: favorece a alternativa na cobertura
            r[f"{s}_clim_min"] = float(np.array(lo_m) @ w)
            r[f"{s}_clim_max"] = float(np.array(hi_m) @ w)
            if completos and s == "NE":
                r["crps_clim"] = crps_ponderado(
                    np.array(completos), np.ones(len(completos)), r["NE_real"]
                )
        if (dk, per) in mod.index:
            m_ = mod.loc[(dk, per)]
            r.update(
                {
                    "NE_mod": m_["NE_prev"],
                    "N_mod": m_["N_prev"],
                    "NE_mod_min": m_["NE_min"],
                    "NE_mod_max": m_["NE_max"],
                    "N_mod_min": m_["N_min"],
                    "N_mod_max": m_["N_max"],
                    "crps_mod": m_["crps_NE"],
                    "treinada": bool(m_["trav_prev"] > LIMIAR_TREINADA),
                }
            )
        lin.append(r)
    out = pd.DataFrame(lin)
    return out[
        [inicio(p) >= pd.Period(dk, "M") for dk, p in zip(out["deck"], out["periodo"])]
    ].reset_index(drop=True)


def resumo_alternativas(alt: pd.DataFrame) -> pd.DataFrame:
    """Erro médio, viés, cobertura, largura média da faixa e CRPS de cada abordagem por alvo e recorte."""
    lin = []
    for alvo in ("2025", "2026"):
        for rec in ("todos", "treinada"):
            a = alt[
                alt["periodo"].str.startswith(alvo)
                & (alt["treinada"] if rec == "treinada" else True)
            ]
            if not len(a):
                continue
            for nome, col in (
                (f"modelo {M.MODELO.versao}", "mod"),
                ("climatologia", "clim"),
                ("repetir ano anterior", "repetir"),
                ("assumir zero", "zero"),
            ):
                e = a[f"NE_{col}"] - a["NE_real"]
                row = {
                    "alvo": alvo,
                    "recorte": rec,
                    "abordagem": nome,
                    "n": len(a),
                    "eam_NE": e.abs().mean(),
                    "vies_NE": e.mean(),
                    "eam_N": (a[f"N_{col}"] - a["N_real"]).abs().mean(),
                }
                if col in ("mod", "clim"):
                    lo, hi = a[f"NE_{col}_min"], a[f"NE_{col}_max"]
                    row["cobertura"] = ((lo - 1 <= a["NE_real"]) & (a["NE_real"] <= hi + 1)).mean()
                    row["crps_NE"] = a[f"crps_{col}"].mean()
                    row["largura_NE"] = (hi - lo).mean()
                lin.append(row)
    return pd.DataFrame(lin)


def trimestres_realizados(b: M.Base) -> list:
    """Descolamento do NE e SE realizados por trimestre (média ponderada por horas), desde 2021."""
    m = b.mensal.set_index(pd.PeriodIndex(b.mensal.index, freq="M"))
    m = m[m.index >= pd.Period("2021-01", "M")]
    m = m.assign(h=[p.days_in_month * 24 for p in m.index])
    out = []
    for (a, q), g in m.groupby([m.index.year, m.index.quarter]):
        if len(g) < 3:
            continue
        out.append(
            {
                "ano": int(a),
                "tri": int(q),
                "NE": _r(np.average(g["d_NE"], weights=g["h"]), 1),
                "SE": _r(np.average(g["SE"], weights=g["h"]), 0),
            }
        )
    return out


def desempenho(b: M.Base, x: pd.DataFrame) -> dict:
    """Resumo do backtest da página por trimestre e semestre, acerto por trimestre, comparação com as alternativas e
    o realizado por trimestre (dados da página de metodologia)."""
    resumo, periodos = [], []
    for per in ("trimestre", "semestre"):
        t = resumo_periodos(x, per)
        t = t[[inicio(p) >= pd.Period(d, "M") for d, p in t.index]]
        treinada = t["trav_prev"] > LIMIAR_TREINADA
        for alvo in ("2025", "2026"):
            for rec in ("todos", "treinada"):
                sel = t.index.get_level_values(1).str.startswith(alvo)
                tt = t[sel & (treinada.to_numpy() if rec == "treinada" else True)]
                if not len(tt):
                    continue
                resumo.append(
                    {
                        "agregacao": per,
                        "alvo": alvo,
                        "recorte": rec,
                        "n": len(tt),
                        "eam_NE": _r(tt["NE_erro"].abs().mean(), 2),
                        "vies_NE": _r(tt["NE_erro"].mean(), 2),
                        "eam_N": _r(tt["N_erro"].abs().mean(), 2),
                        "crps_NE": _r(tt["crps_NE"].mean(), 2),
                        "cobertura": _r(tt["cobre_NE"].mean(), 3),
                    }
                )
        if per == "trimestre":
            for p in sorted(set(t.index.get_level_values(1))):
                tp = t[t.index.get_level_values(1) == p]
                ultimo = tp.index.get_level_values(0).max()  # deck mais recente antes do início
                r = tp.loc[(ultimo, p)]
                periodos.append(
                    {
                        "periodo": p,
                        "deck": ultimo,
                        "real": _r(r["NE_real"], 2),
                        "prev": _r(r["NE_prev"], 2),
                        "min": _r(r["NE_min"], 2),
                        "max": _r(r["NE_max"], 2),
                        "erro": _r(r["NE_erro"], 2),
                        "treinada": bool(r["trav_prev"] > LIMIAR_TREINADA),
                    }
                )
    comp, casos, escala = {}, {}, None
    for per in ("trimestre", "semestre"):
        alt = alternativas(b, x, per)
        comp[per] = [
            {k: (_r(v, 3) if isinstance(v, float) else v) for k, v in row.items()}
            for row in resumo_alternativas(alt).to_dict("records")
        ]
        if per == "trimestre":
            reais = alt.drop_duplicates("periodo")
            escala = [_r(reais["NE_real"].max(), 1), _r(reais["NE_real"].min(), 1)]
        sel = alt[alt["treinada"].fillna(False).astype(bool)]
        casos[per] = [
            {
                k: (_r(v, 2) if isinstance(v, float) else v)
                for k, v in r.items()
                if not (isinstance(v, float) and not np.isfinite(v))
            }
            for r in sel.to_dict("records")
        ]
    return {
        "decks": sorted(x["deck"].unique().tolist()),
        "resumo": resumo,
        "periodos": periodos,
        "comparacao": comp,
        "casos": casos,
        "escala": escala,
        "trimestres": trimestres_realizados(b),
    }
