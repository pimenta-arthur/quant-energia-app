"""Publicação: processed/pld_horario/ → serving/pld_horario/<chave>.json (o que a página lê).

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
from qe_pld_horario import chaves
from qe_pld_horario.modelo import MODELO, SUBMERCADOS


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
    from qe_pld_horario.modelo import TIPOS_DIA

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


# --- montagem e gravação -----------------------------------------------------------------------------


def dados(arm: Armazenamento) -> dict:
    """Todas as chaves da página, prontas para gravar."""
    t1 = ler_parquet(arm, chaves.PROC_PLD)
    h, tipos = _horario(arm), _tipos(arm)
    dec = ler_parquet(arm, chaves.PROC_DECOMP)
    hr = horas(h, tipos)
    anos = sorted(t1["data"].dt.year.unique().tolist())
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


def publicar(arm: Armazenamento) -> dict:
    """Regrava serving/pld_horario/ com os dados atuais. Devolve o estado publicado."""
    d = dados(arm)
    e = estado(arm, d)
    for nome, valor in {**d, "estado": e}.items():
        arm.gravar_bytes(
            json.dumps(valor, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            chaves.serving(nome),
        )
    return e
