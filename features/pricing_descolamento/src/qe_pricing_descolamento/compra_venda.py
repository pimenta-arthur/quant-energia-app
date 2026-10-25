"""Compra e venda do descolamento NE e N (pesquisa: compra_venda.py, compra_venda_backtest.py e compra_venda_ancora.py;
leva promocao-quant-v5, D041 a D055).

Instrumento: o produto paga o descolamento d = PLD_sub − PLD_SE (R$/MWh, média do período ponderada por horas). Comprar a
P recebe d e paga P (ganho = d − P); vender a P paga d e recebe P (ganho = P − d). Cada lado é calculado sozinho, com a
curva de SE da página e uma política de risco (p, α, λ).

Política Conservador (padrão): p = 0,30, α = 10% e λ = 1, método "combinado" (o mais conservador entre o quantil de p e a
cauda de α, λ). Venda ancorada no realizado: mês a mês, o máximo entre a venda do modelo e o maior descolamento já
realizado naquele mês do calendário (fração da folga × folga do SE informado).

O que a página lê (publicação, serving/pricing_descolamento/):
- `cv_backtest`: casos treinados do backtest (trimestres e semestres) com os meses de cada caso, para o painel "Como essa
  cotação se saiu no passado" recalcular qualquer política no navegador;
- `cv_historico`: fração da folga já realizada por mês do calendário (até D−2) e a série mensal realizada, para a venda
  ancorada e para a coluna "realizado" dos descritivos;
- `cv_exemplo`: exemplo trabalhado da metodologia (T1 do ano seguinte, SE plano de R$ 200).

A conta da cotação que depende da curva digitada roda no navegador (web/pricing_descolamento/compra_venda_conta.js); aqui
fica `precificar`, com o teste de paridade (tests/test_pricing_descolamento_compra_venda.py, com node).
"""

import numpy as np
import pandas as pd

from qe_pricing_descolamento import desempenho as D
from qe_pricing_descolamento import modelo as M
from qe_pricing_descolamento.backtest import MESES as ALVOS
from qe_pricing_descolamento.conta import Conta

POL = {"p": 0.30, "alfa": 0.10, "lam": 1.0}  # Conservador
POLITICA_EXEMPLO = {
    "p": 0.30,
    "alfa": 0.10,
    "lam": 0.30,
}  # política da v1: ponto de partida dos exemplos da metodologia
PERIODOS = {"trimestre": "tri", "semestre": "sem"}
FOLGA_MIN = D.FOLGA_MIN


def precificar(
    amostra, metodo: str = "combinado", p: float = 0.30, alfa: float = 0.10, lam: float = 0.30
) -> dict:
    """Preço justo, compra e venda de uma amostra de cenários (um valor por ano climático). Porta de `curvas.precificar`."""
    x = np.sort(np.asarray(amostra, dtype=float))
    x = x[~np.isnan(x)]
    e = float(x.mean())
    if metodo == "cauda":
        n = max(1, int(np.ceil(alfa * len(x))))
        compra = e - lam * (e - x[:n].mean())
        venda = e + lam * (x[-n:].mean() - e)
    elif metodo == "quantil":
        compra = min(float(np.quantile(x, p)), e)
        venda = max(float(np.quantile(x, 1 - p)), e)
    elif metodo == "combinado":
        q = precificar(x, "quantil", p, alfa, lam)
        c = precificar(x, "cauda", p, alfa, lam)
        compra, venda = min(q["compra"], c["compra"]), max(q["venda"], c["venda"])
    else:
        raise ValueError(f"método desconhecido: {metodo}")
    return {"justo": e, "compra": float(compra), "venda": float(venda)}


# --- backtest: casos treinados com os meses de cada um ---------------------------------------------------------------


def _fim(periodo: str) -> pd.Period:
    """Último mês do período ('2025-T3' → 2025-09; '2025-S1' → 2025-06)."""
    a = int(periodo[:4])
    if "-T" in periodo:
        return pd.Period(f"{a}-{3 * int(periodo[-1]):02d}", "M")
    return pd.Period(f"{a}-{'06' if periodo.endswith('1') else '12'}", "M")


def casos(b: M.Base, x: pd.DataFrame, periodo: str = "trimestre") -> pd.DataFrame:
    """Um caso por (deck, período) treinado: realizado e valores por ano climático (NE e N) do período todo."""
    alt = D.alternativas(b, x, periodo)
    alt = alt[alt["treinada"].fillna(False).astype(bool)].copy()
    z = x.assign(periodo=x["mes"].map(D.ROTULO[periodo]))
    z["ano"] = z["cenario"].astype(str).str.split("|").str[0].astype(int)
    anos = {}
    for (dk, per), g in z.groupby(["deck", "periodo"]):
        n_mes = g["mes"].nunique()
        v = g.groupby("ano").apply(
            lambda h: pd.Series(
                {
                    "meses": h["mes"].nunique(),
                    "NE": np.average(h["NE_prev"], weights=h["horas"]),
                    "N": np.average(h["N_prev"], weights=h["horas"]),
                }
            ),
            include_groups=False,
        )
        v = v[v["meses"] == n_mes]
        anos[(dk, per)] = (v["NE"].to_numpy(), v["N"].to_numpy())
    alt["fim"] = alt["periodo"].map(_fim)
    alt["grupo"] = alt["periodo"].map(lambda p: p[-2:])
    alt["anos_NE"] = [anos[(d, p)][0] for d, p in zip(alt["deck"], alt["periodo"])]
    alt["anos_N"] = [anos[(d, p)][1] for d, p in zip(alt["deck"], alt["periodo"])]
    return alt.reset_index(drop=True)


def _fracoes_contexto(b: M.Base) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(fração da folga já realizada por mês e submercado, limites do PLD)."""
    _, fr = D._fracoes(b)
    return fr, b.limites


def historico_mes(fr: pd.DataFrame, sub: str, mes: pd.Period, deck: pd.Period) -> float | None:
    """Maior fração da folga (a menos negativa) já realizada no mesmo mês do calendário, de 2021 até D−2."""
    v = [
        fr.loc[p, sub]
        for p in fr.index
        if p.month == mes.month and p.year >= 2021 and p <= deck - 2 and np.isfinite(fr.loc[p, sub])
    ]
    return float(max(v)) if v else None


def dados_backtest(b: M.Base, x: pd.DataFrame) -> dict:
    """`cv_backtest`: casos treinados (trimestres e semestres) com os meses de cada caso (valores por ano climático e venda
    do histórico), para o painel do passado recalcular qualquer política no navegador."""
    fr, lim = _fracoes_contexto(b)
    z = x.copy()
    z["ano"] = z["cenario"].astype(str).str.split("|").str[0].astype(int)
    saida = []
    for periodo, tipo in PERIODOS.items():
        c = casos(b, x, periodo)
        zz = z.assign(periodo=z["mes"].map(D.ROTULO[periodo]))
        por = {(dk, per): g for (dk, per), g in zz.groupby(["deck", "periodo"])}
        for i in c.index:
            d = pd.Period(c.loc[i, "deck"], "M")
            g = por[(c.loc[i, "deck"], c.loc[i, "periodo"])]
            ms = []
            for m in sorted(g["mes"].unique()):
                gm = g[g["mes"] == m]
                folga = max(
                    float(gm["SE_real"].iloc[0]) - float(lim.loc[min(m.year, d.year), "piso"]), 0.0
                )
                hist = {}
                for sub in ("NE", "N"):
                    f = historico_mes(fr, sub, m, d)
                    hist[sub] = round(f * folga, 4) if f is not None else None
                ms.append(
                    {
                        "h": int(gm["horas"].iloc[0]),
                        "anos": {
                            sub: [
                                round(float(v), 4)
                                for v in gm.groupby("ano")[f"{sub}_prev"].mean().to_numpy()
                            ]
                            for sub in ("NE", "N")
                        },
                        "hist": hist,
                    }
                )
            saida.append(
                {
                    "tipo": tipo,
                    "periodo": c.loc[i, "periodo"],
                    "deck": c.loc[i, "deck"],
                    "grupo": c.loc[i, "grupo"],
                    "real": {s: round(float(c.loc[i, f"{s}_real"]), 2) for s in ("NE", "N")},
                    "anos": {
                        s: [round(float(v), 4) for v in c.loc[i, f"anos_{s}"]] for s in ("NE", "N")
                    },
                    "meses": ms,
                }
            )
    meta = {
        "decks": sorted(x["deck"].unique().tolist()),
        "alvos": list(ALVOS),
        "versao": M.MODELO.versao,
        "rotulo": "casos treinados (v2.2 com mais de 0,5% de horas travadas previstas), SE realizado como insumo",
    }
    return {"meta": meta, "casos": saida}


def dados_historico(b: M.Base, deck: str) -> dict:
    """`cv_historico`: por mês do calendário, [ano, fração da folga, SE, descolamento] até D−2 (folga ≥ R$ 20), e a série
    mensal realizada "AAAA-MM": [SE, d_NE, d_N] (R$/MWh)."""
    mensal, fr = D._fracoes(b)
    dv = pd.Period(deck, "M")
    hist = {sub: {} for sub in ("NE", "N")}
    for sub in ("NE", "N"):
        for p in fr.index:
            if p.year >= 2021 and p <= dv - 2 and np.isfinite(fr.loc[p, sub]):
                hist[sub].setdefault(str(p.month), []).append(
                    [
                        p.year,
                        round(float(fr.loc[p, sub]), 4),
                        round(float(mensal.loc[p, "SE"]), 1),
                        round(float(mensal.loc[p, f"d_{sub}"]), 1),
                    ]
                )
    real = {
        str(p): [
            round(float(mensal.loc[p, "SE"]), 1),
            round(float(mensal.loc[p, "d_NE"]), 1),
            round(float(mensal.loc[p, "d_N"]), 1),
        ]
        for p in mensal.index
        if p.year >= 2021 and p <= dv - 2
    }
    return {"deck": deck, "ate": str(dv - 2), **hist, "real": real}


# --- exemplo trabalhado da metodologia --------------------------------------------------------------------------------


def _chave_periodo(m: str, tipo: str) -> str:
    y, mm = int(m[:4]), int(m[5:7])
    return {
        "mes": m,
        "tri": f"{y}-T{(mm - 1) // 3 + 1}",
        "sem": f"{y}-S{1 if mm <= 6 else 2}",
        "ano": str(y),
    }[tipo]


def _tipo(periodo: str) -> str:
    if "-T" in periodo:
        return "tri"
    if "-S" in periodo:
        return "sem"
    return "ano" if len(periodo) == 4 else "mes"


def valores_por_ano(conta: Conta, res: dict, periodo: str, sub: str) -> dict[int, float]:
    """Descolamento do período em cada ano climático (média por horas dos meses). sub: "NE", "N" ou "NE-N". Só entram anos
    presentes em todos os meses do período."""
    tipo = _tipo(periodo)
    ms = [m for m in res if _chave_periodo(m, tipo) == periodo]
    if not ms:
        return {}
    H = conta.horas(ms)
    por: dict[str, dict] = {}
    for m in ms:
        w = conta.M[conta.idx[m]]["horas"] / H
        for c in res[m]["cen"]:
            alvo = c["NE"] - c["N"] if sub == "NE-N" else c[sub]
            a = por.setdefault(str(c["id"]).split("|")[0], {"meses": 0, "v": 0.0})
            a["meses"] += 1
            a["v"] += alvo * w
    return {int(a): v["v"] for a, v in sorted(por.items()) if v["meses"] == len(ms)}


def exemplo(
    meses: list[dict], saz: list[float], deck: str, se: float = 200.0, periodo: str | None = None
) -> dict:
    """`cv_exemplo`: dados do exemplo trabalhado da metodologia (deck, SE plano, um produto, NE e swap NE × N)."""
    d = pd.Period(deck, "M")
    periodo = periodo or f"{d.year + 1}-T1"
    conta = Conta(meses, saz)
    res = conta.calcular({m["mes"]: se for m in meses})
    ne = valores_por_ano(conta, res, periodo, "NE")
    n = valores_por_ano(conta, res, periodo, "N")
    dif = valores_por_ano(conta, res, periodo, "NE-N")
    par = POLITICA_EXEMPLO
    cot = precificar(list(ne.values()), **par)
    por_metodo = {
        m: precificar(list(ne.values()), metodo=m, **par) for m in ("quantil", "cauda", "combinado")
    }
    sens = [
        {"p": pp, "lam": ll, **precificar(list(ne.values()), p=pp, alfa=par["alfa"], lam=ll)}
        for pp, ll in (
            (0.20, 0.30),
            (0.30, 0.30),
            (0.40, 0.30),
            (0.30, 0.15),
            (0.30, 0.30),
            (0.30, 0.50),
            (0.30, 1.00),
        )
    ]
    n_cen = {
        t: len(valores_por_ano(conta, res, t, "NE"))
        for t in (f"{d.year + 1}-T{q}" for q in (1, 2, 3, 4))
    }
    r2 = lambda v: round(float(v), 2)
    return {
        "meta": {
            "deck": deck,
            "se": se,
            "periodo": periodo,
            "versao": M.MODELO.versao,
            "politica": par,
            "n_cenarios": len(ne),
            "n_cenarios_trimestres": n_cen,
        },
        "cenarios": [
            {
                "ano": a,
                "NE": r2(ne[a]),
                "N": r2(n[a]) if a in n else None,
                "NE-N": r2(dif[a]) if a in dif else None,
            }
            for a in ne
        ],
        "cotacao": {k: r2(v) for k, v in cot.items()},
        "por_metodo": {m: {k: r2(v) for k, v in r.items()} for m, r in por_metodo.items()},
        "sensibilidade": [
            {k: (r2(v) if k not in ("p", "lam") else v) for k, v in r.items()} for r in sens
        ],
        "swap_ne_n": {
            "periodo": periodo,
            "cotacao": {k: r2(v) for k, v in precificar(list(dif.values()), **par).items()},
            "min": r2(min(dif.values())),
            "max": r2(max(dif.values())),
        },
    }


# --- cotação de um produto (referência em Python da lógica da página; conferida contra a R16 da pesquisa) ---------------


def _ids_comuns(res: dict, ms: list[str]) -> list[str]:
    return [
        c["id"]
        for c in res[ms[0]]["cen"]
        if all(any(x["id"] == c["id"] for x in res[p]["cen"]) for p in ms)
    ]


def valores_por_ano_produto(conta: Conta, res: dict, ms: list[str], sub: str) -> dict[str, float]:
    """Valor de cada ano climático no produto (média dos meses ponderada por horas); só anos presentes em todos os meses."""
    H = conta.horas(ms)
    out = {}
    for i in _ids_comuns(res, ms):
        v = 0.0
        for p in ms:
            c = next(x for x in res[p]["cen"] if x["id"] == i)
            v += c[sub] * conta.M[conta.idx[p]]["horas"] / H
        out[i] = v
    return out


def ano_referencia(cvh: dict, sub: str, mes: str) -> tuple[float, int] | None:
    """(fração da folga, ano) do ano que dá o maior (menos negativo) descolamento já realizado no mês do calendário."""
    arr = (cvh.get(sub) or {}).get(str(int(mes[5:7])))
    if not arr:
        return None
    b = arr[0]
    for x in arr:
        if x[1] > b[1]:
            b = x
    return b[1], b[0]


def _meses_do_produto(conta: Conta, res: dict, ms: list[str], sub: str, cvh: dict) -> list[dict]:
    out = []
    for p in ms:
        r = ano_referencia(cvh, sub, p)
        folga = max(res[p]["se"] - conta.M[conta.idx[p]]["piso"], 0)
        out.append(
            {
                "mes": p,
                "h": conta.M[conta.idx[p]]["horas"],
                "anos": [c[sub] for c in res[p]["cen"]],
                "hist": r[0] * folga if r else None,
            }
        )
    return out


def venda_usada(m: dict, par: dict, ancora: bool = True) -> float:
    base = precificar(m["anos"], **par)["venda"]
    return max(base, m["hist"]) if ancora and m["hist"] is not None else base


def cotar_produto(
    conta: Conta,
    res: dict,
    ms: list[str],
    sub: str,
    cvh: dict,
    politica: dict | None = None,
    ancora: bool = True,
) -> dict | None:
    """Compra, justo e venda de um produto (a cotação do produto sozinho): compra = política de compra sobre os anos
    climáticos do produto; venda = média por horas da venda usada de cada mês (modelo × histórico) quando ancorada;
    a compra nunca passa do justo e a venda nunca fica abaixo."""
    pol = politica or {"compra": POL, "venda": POL}
    g = conta.agregar(res, ms)
    if g is None:
        return None
    amostra = list(valores_por_ano_produto(conta, res, ms, sub).values())
    if not amostra:
        return None
    meses = _meses_do_produto(conta, res, ms, sub, cvh)
    compra = precificar(amostra, **pol["compra"])["compra"]
    if ancora:
        H = sum(m["h"] for m in meses)
        venda = sum(m["h"] * venda_usada(m, pol["venda"]) for m in meses) / H
    else:
        venda = precificar(amostra, **pol["venda"])["venda"]
    justo = g[sub]
    return {
        "se": g["se"],
        "justo": justo,
        "compra": min(compra, justo),
        "venda": max(venda, justo),
        "n": len(amostra),
    }


def contribuicao_para_o_ano(
    conta: Conta,
    res: dict,
    meses_ano: list[str],
    ms: list[str],
    sub: str,
    cvh: dict,
    politica: dict | None = None,
    ancora: bool = True,
) -> dict | None:
    """Contribuição de um pedaço (semestre, trimestre ou mês) para a cotação do ano: venda = média por horas da venda usada
    dos meses do pedaço; compra = valor do pedaço no ano climático que sustenta a compra do ano (o pior); a diferença para
    a cotação do ano (política, limite ao justo) entra como ajuste uniforme, de modo que os pedaços reproduzem o ano."""
    pol = politica or {"compra": POL, "venda": POL}
    c = cotar_produto(conta, res, meses_ano, sub, cvh, pol, ancora)
    if c is None:
        return None
    vano = valores_por_ano_produto(conta, res, meses_ano, sub)
    pior = min(vano, key=vano.get)
    melhor = max(vano, key=vano.get)
    por_mes = {
        m["mes"]: venda_usada(m, pol["venda"], ancora)
        for m in _meses_do_produto(conta, res, meses_ano, sub, cvh)
    }

    def do_ano(pedaco: list[str], ref: str) -> float:
        return valores_por_ano_produto(conta, res, pedaco, sub)[ref]

    def venda0(pedaco: list[str]) -> float:
        if not ancora:
            return do_ano(pedaco, melhor)
        return sum(por_mes[p] * conta.M[conta.idx[p]]["horas"] for p in pedaco) / conta.horas(
            pedaco
        )

    dC = c["compra"] - do_ano(meses_ano, pior)
    dV = c["venda"] - venda0(meses_ano)
    return {"compra": do_ano(ms, pior) + dC, "venda": venda0(ms) + dV}
