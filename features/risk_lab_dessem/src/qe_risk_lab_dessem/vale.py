"""Mecanismos do vale (bloco 6, só SE/CO): diagnóstico com saídas do modelo (D014: saída do modelo
nunca é variável de previsão). Pesquisa: risk-lab-dessem-analytics, vale.py (D018–D022, D082).

- dias do vale: horas do vale (8h–15h) no piso por dia, nos meses civis completos com espaço
  DECOMP − piso de pelo menos R$ 20;
- insumos do vale por dia (SIN): hidráulica necessária = demanda − renovável prevista − térmica
  mínima; hidráulica do modelo; renovável cortada = prevista − gerada;
- acoplamento SE–N: |CMO mediano do vale SE − N| < R$ 1;
- Belo Monte no vale (tabela do tratamento, a partir de 2025).
"""

import pandas as pd

from qe_core.armazenamento import Armazenamento, ler_parquet
from qe_risk_lab_dessem import chaves, tratamento
from qe_risk_lab_dessem.modelo import MODELO, SUBMERCADOS

ESPACO_MIN = 20.0
LIMIAR_ACOPLAMENTO = 1.0  # R$/MWh entre os CMOs medianos do vale do SE e do N


def horas_vale(arm: Armazenamento, submercado: str = "SE") -> pd.DataFrame:
    """Horas do vale dos meses civis completos, com o DECOMP médio do mês (D), o piso, o indicador de
    piso e o afastamento relativo g = (PLD − D) / max(D − piso, 20)."""
    h = ler_parquet(arm, chaves.PROC_HORARIO)
    h = h[(h["submercado"] == submercado) & h["hora"].isin(MODELO.vale)].copy()
    m = ler_parquet(arm, chaves.PROC_DELTA)
    m = m[(m["submercado"] == submercado) & m["completo"]].set_index("mes")
    h = h[h["mes"].isin(m.index)]
    h["D"] = h["mes"].map(m["decomp"])
    h["no_piso"] = h["pld_dessem"] <= h["piso"] + MODELO.tol_piso
    h["g"] = (h["pld_dessem"] - h["D"]) / (h["D"] - h["piso"]).clip(lower=ESPACO_MIN)
    return h


def dias_vale(h: pd.DataFrame, tipos: pd.Series) -> pd.DataFrame:
    """Por data: tipo, mês, D, piso, horas do vale no piso, soma e número de g fora do piso."""
    h = h[h["D"] - h["piso"] >= ESPACO_MIN]
    g = h.assign(g_fora=h["g"].where(~h["no_piso"])).groupby("data")
    d = pd.DataFrame(
        {
            "mes": g["mes"].first(),
            "D": g["D"].first(),
            "piso": g["piso"].first(),
            "n_piso": g["no_piso"].sum(),
            "n": g["no_piso"].size(),
            "soma_g": g["g_fora"].sum(),
            "n_g": g["g_fora"].count(),
        }
    )
    d["tipo"] = tipos.reindex(d.index).to_numpy()
    return d


def insumos_vale_diarios(arm: Armazenamento) -> pd.DataFrame:
    """Por data, médias no vale (SIN e SE+S): demanda, renovável prevista, solar, carga líquida,
    térmica mínima, hidráulica necessária, hidráulica do modelo (resultado) e renovável cortada."""
    s = tratamento.ler_dessem(
        arm,
        "sist",
        ["data", "periodo", "submercado", "demanda", "soma_gt_min", "somat_gh", "grenova"],
    )
    s = s[s["periodo"].isin(tratamento.PERIODOS_VALE) & s["submercado"].isin(SUBMERCADOS)]
    r = tratamento.ler_dessem(arm, "renovaveis")
    r = r[r["periodo"].isin(tratamento.PERIODOS_VALE)]
    rr = r.groupby(["data", "periodo", "submercado"])["mw"].sum().rename("renov_prev")
    sol = (
        r[r["tipo"].isin(["solar", "mmgd"])].groupby(["data", "periodo", "submercado"])["mw"].sum()
    )
    s = s.join(rr, on=["data", "periodo", "submercado"]).join(
        sol.rename("solar_prev"), on=["data", "periodo", "submercado"]
    )
    s = s.fillna({"solar_prev": 0.0})
    out = {}
    for nome, subs in {"sin": SUBMERCADOS, "ses": ["SE", "S"]}.items():
        x = s[s["submercado"].isin(subs)].groupby(["data", "periodo"]).sum(numeric_only=True)
        x = x.groupby("data").mean()
        out[f"demanda_{nome}"] = x["demanda"]
        out[f"renov_{nome}"] = x["renov_prev"]
        out[f"solar_{nome}"] = x["solar_prev"]
        out[f"cliq_{nome}"] = x["demanda"] - x["renov_prev"]
        out[f"gtmin_{nome}"] = x["soma_gt_min"]
        out[f"hid_nec_{nome}"] = x["demanda"] - x["renov_prev"] - x["soma_gt_min"]
        out[f"gh_modelo_{nome}"] = x["somat_gh"]
        out[f"corte_{nome}"] = x["renov_prev"] - x["grenova"]
    t = pd.DataFrame(out)
    t.index = pd.to_datetime(t.index)
    return t


def cmo_vale_diario(arm: Armazenamento) -> pd.DataFrame:
    """Mediana do CMO no vale por dia e submercado (DESSEM)."""
    s = tratamento.ler_dessem(arm, "sist", ["data", "periodo", "submercado", "cmo"])
    s = s[s["periodo"].isin(tratamento.PERIODOS_VALE)]
    return s.pivot_table(index="data", columns="submercado", values="cmo", aggfunc="median")


def belo_monte_diario(arm: Armazenamento) -> pd.DataFrame:
    bm = tratamento.ler_dessem(arm, "belo_monte").dropna(subset=["bm_vagua"])
    return bm.set_index("data").sort_index()
