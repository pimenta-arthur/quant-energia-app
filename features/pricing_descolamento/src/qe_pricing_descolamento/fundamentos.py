"""Dados da página de fundamentos: por que o NE e o N descolam, a partir da base horária e do PLD (pesquisa:
web.exportar_fundamentos e fisica.travas_por_regime, poder_explicativo). Descreve o que aconteceu; o modelo está na
metodologia.

1. série mensal: SE, piso e descolamento de Sul, NE e N;
2. mapa mês × hora para S, NE e N (% das horas descoladas e R$/MWh médio) nas janelas desde 2021, 2024 e 2025;
3. que restrição está no limite quando o NE descola, por ano e semestre;
4. poder explicativo (AUC) de cada variável física por regime, desde 2024, e curvas de resposta por decil;
5. k mensal do 1º semestre × sobra N+NE.
"""

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from qe_pricing_descolamento import modelo as M

NOMES_VAR = {
    "sobra_NNE": "Sobra N+NE",
    "margem_exp_NE": "Margem até o limite de exportação do NE",
    "sobra_NE": "Sobra do NE",
    "renovavel_NE": "Renovável do NE",
    "sobra_ren_NE": "Renovável − carga do NE",
    "hidraulica_N": "Hidráulica do N",
    "sobra_N": "Sobra do N",
    "demanda_NE": "Carga do NE",
}
VARIAVEIS = [
    "renovavel_NE",
    "demanda_NE",
    "sobra_ren_NE",
    "margem_exp_NE",
    "sobra_NE",
    "hidraulica_N",
    "sobra_N",
    "sobra_NNE",
]
DESDE_FISICA = "2024-01-01"  # restrições do DESSEM confiáveis (AUC e curvas de resposta)
MINIMO_TRAVA = (
    10.0  # % das horas descoladas: restrições abaixo disso em todos os períodos não aparecem
)


def _r(v, c=4):
    if v is None or not np.isfinite(v):
        return None
    return round(float(v), c)


def _travas(h: pd.DataFrame) -> pd.DataFrame:
    """Colunas trava_* como número (1 travada, 0 não, NaN sem dado da restrição na hora)."""
    cols = [c for c in h.columns if c.startswith("trava_")]
    return h[cols].apply(lambda s: pd.to_numeric(s.map({True: 1.0, False: 0.0}), errors="coerce"))


def travas_por_regime(h: pd.DataFrame, sub: str = "NE") -> pd.DataFrame:
    """% das horas descoladas em que cada restrição trava, por ano e semestre; "nenhuma" = nenhuma restrição
    travada (hora sem dado de uma restrição conta como travada nela, como na pesquisa)."""
    y = h[h[f"desc_{sub}"].astype(bool)]
    tv = _travas(y)
    reg = y.index.year.astype(str) + "-" + y["regime"]
    t = tv.groupby(reg).mean() * 100
    t.columns = [c.replace("trava_", "") for c in t.columns]
    t = t.loc[:, t.max() >= MINIMO_TRAVA]
    t.insert(0, "horas descoladas", y.groupby(reg).size())
    t["nenhuma"] = 100 * (~(tv.fillna(1) != 0).any(axis=1)).groupby(reg).mean()
    t.index.name = "ano-regime"
    return t


def poder_explicativo(h: pd.DataFrame, sub: str = "NE") -> pd.DataFrame:
    """AUC de cada variável para separar horas descoladas, por regime (0,5 = nenhum poder; sinal = direção)."""
    lin = {}
    for reg in M.REGIMES:
        y = h[(h["regime"] == reg) & (h.index >= DESDE_FISICA)].dropna(subset=VARIAVEIS)
        for c in VARIAVEIS:
            a = roc_auc_score(y[f"desc_{sub}"].astype(bool), y[c])
            lin[(c, reg)] = max(a, 1 - a) * (1 if a >= 0.5 else -1)
    return pd.Series(lin).unstack()


def dados_fundamentos(b: M.Base) -> dict:
    h = b.h
    m = b.mensal.set_index(pd.PeriodIndex(b.mensal.index, freq="M"))
    m = m[(m.index >= pd.Period("2021-01", "M")) & (m.index <= h["mes"].max())]
    serie = [
        {
            "mes": str(p),
            "SE": _r(r["SE"], 1),
            "piso": _r(b.limites.loc[p.year, "piso"], 2),
            **{s: _r(r[f"d_{s}"], 1) for s in ("NE", "N", "S")},
        }
        for p, r in m.iterrows()
    ]
    # mapa mês × hora: % das horas descoladas e descolamento médio, por submercado e janela
    mapa = {}
    h = h.assign(d_S=h["S"] - h["SE"])
    h = h.assign(desc_S=h["d_S"] > 1)  # o Sul descola para cima (acima do SE)
    for ini in ("2021", "2024", "2025"):
        y = h[h.index >= f"{ini}-01-01"]
        for s in ("S", "NE", "N"):
            g = y.groupby([y.index.month, y.index.hour])
            pct = g[f"desc_{s}"].mean().unstack().reindex(index=range(1, 13), columns=range(24))
            rs = g[f"d_{s}"].mean().unstack().reindex(index=range(1, 13), columns=range(24))
            mapa[f"{s}_{ini}"] = {
                "pct": [[_r(v, 3) for v in linha] for linha in pct.to_numpy(dtype=float)],
                "rs": [[_r(v, 1) for v in linha] for linha in rs.to_numpy(dtype=float)],
            }
    travas = [
        {
            "periodo": i,
            **{k: (int(v) if k == "horas descoladas" else _r(v, 0)) for k, v in r.items()},
        }
        for i, r in travas_por_regime(h, "NE").iterrows()
    ]
    auc = {
        s: [
            {"var": NOMES_VAR.get(i, i), "1S": _r(r["1S"], 3), "2S": _r(r["2S"], 3)}
            for i, r in poder_explicativo(h, s).iterrows()
        ]
        for s in M.SUBS
    }
    resposta = {}
    for var, reg in (("sobra_NNE", "1S"), ("margem_exp_NE", "2S")):
        y = h[(h["regime"] == reg) & (h.index >= DESDE_FISICA)].dropna(subset=[var])
        q = pd.qcut(y[var], 10, duplicates="drop")
        t = (
            y.assign(desc_NE=y["desc_NE"].astype(bool))
            .groupby(q, observed=True)
            .agg(horas=("desc_NE", "size"), p=("desc_NE", "mean"), x=(var, "mean"))
        )
        resposta[reg] = {
            "var": NOMES_VAR[var],
            "pontos": [
                {
                    "lo": _r(iv.left / 1e3, 1),
                    "hi": _r(iv.right / 1e3, 1),
                    "x": _r(r["x"] / 1e3, 2),
                    "p": _r(r["p"], 3),
                    "horas": int(r["horas"]),
                }
                for iv, r in t.iterrows()
            ],
        }
    # intensidade: k mensal do 1º semestre × sobra N+NE (meses com ≥ 20 h descoladas, desde 2021)
    kpts = []
    for mm, y in h[h["regime"] == "1S"].groupby("mes"):
        tr = y[y["desc_NE"].astype(bool)]
        if len(tr) < 20:
            continue
        piso = b.limites.loc[mm.year, "piso"]
        kpts.append(
            {
                "mes": str(mm),
                "k": _r(
                    ((tr["SE"] - tr["NE"]) / (tr["SE"] - piso).clip(lower=1)).clip(0, 1).mean(), 3
                ),
                "sobra": _r(y["sobra_NNE_st"].mean() / 1e3, 2),
                "horas": len(tr),
                "folga": _r((tr["SE"] - piso).mean(), 1),
            }
        )
    return {
        "serie": serie,
        "mapa": mapa,
        "travas": travas,
        "auc": auc,
        "resposta": resposta,
        "k": kpts,
        "dados_ate": str(h.index.max().date()),
    }
