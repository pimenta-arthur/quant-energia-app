"""Simulador do PLD médio do mês, SE/CO: v1 simplificada (bloco 7; pesquisa: simulador.py, D057, D058,
D061–D065, D073).

Entrada do usuário: DECOMP médio do mês D e o mês-alvo. Piso P do ano (ano sem limite publicado: o do
último ano conhecido, sinalizado). Três premissas por tipo de dia (útil, sábado, domingo/feriado),
medidas antes da data da previsão:
1. horas do vale no piso por dia (janela de `MODELO.janela` dias);
2. desconto das outras horas fora da ponta, em fração do espaço D − P: média dos 12 meses civis
   encerrados antes da origem, só meses com espaço médio ≥ R$ 20 (D061);
3. prêmio da ponta sobre o DECOMP vigente (janela de `MODELO.janela` dias).

Dia típico: PLD = [n × P + (20 − n) × max(D + f × max(D − P, 0), P) + 4 × max(D + prêmio, P)] / 24;
PLD do mês = max(Σ parte do tipo × PLD do dia típico, P). A mesma conta roda no navegador
(web/risk_lab_dessem/simulador_conta.js), conferida por teste de paridade.

Rótulos obrigatórios: janela escolhida dentro da amostra (D057); backtest condicional ao DECOMP
(entra o realizado); premissas fora da amostra (só dias e meses anteriores à origem).
"""

import numpy as np
import pandas as pd

from qe_core.armazenamento import Armazenamento, ler_parquet
from qe_risk_lab_dessem import chaves, tratamento
from qe_risk_lab_dessem.modelo import FERIADOS_FUTUROS, MODELO, TIPOS_DIA

NV, NP = len(MODELO.vale), len(MODELO.ponta)
NF = 24 - NP  # horas fora da ponta


# --- base hora a hora ----------------------------------------------------------------------------------


class Base:
    """Dados do simulador lidos uma vez: horas do SE com DECOMP, meses completos, tipos de dia,
    rodadas da RV0 e limites."""

    def __init__(self, arm: Armazenamento, submercado: str = "SE"):
        h = ler_parquet(arm, chaves.PROC_HORARIO)
        h = h[h["submercado"] == submercado].dropna(subset=["decomp_pld"])
        self.h = h.assign(
            desvio=h["pld_dessem"] - h["decomp_pld"], espaco=h["decomp_pld"] - h["piso"]
        )
        m = ler_parquet(arm, chaves.PROC_DELTA)
        self.m = m[(m["submercado"] == submercado) & m["completo"]].set_index("mes")
        t = ler_parquet(arm, chaves.PROC_TIPOS)
        self.tipos = pd.Series(t["tipo"].to_numpy(), index=pd.to_datetime(t["data"]))
        self.rod = rodadas_rv0(ler_parquet(arm, chaves.PROC_DECOMP))
        self.limites = tratamento.limites(arm)
        self.t1 = ler_parquet(arm, chaves.PROC_PLD)
        self._hs = None

    @property
    def hs(self) -> pd.DataFrame:
        """Horas com tipo de dia, os grupos da v3 e os três grupos da v1 simplificada."""
        if self._hs is None:
            h = self.h.assign(tipo=self.tipos.reindex(self.h["data"]).to_numpy())
            h["no_piso"] = h["pld_dessem"] <= h["piso"] + MODELO.tol_piso
            h["grupo"] = np.where(
                h["hora"].isin(MODELO.vale),
                np.where(h["no_piso"], "vale_piso", "vale_fora"),
                np.where(h["hora"].isin(MODELO.ponta), "ponta", "demais"),
            )
            self._hs = h.assign(
                grupo_s=np.where(h["grupo"].isin(["vale_piso", "ponta"]), h["grupo"], "fora")
            )
        return self._hs


def rodadas_rv0(dec: pd.DataFrame) -> pd.Series:
    """Data da rodada da RV0 de cada mês operativo (origem do backtest de 1 mês)."""
    return pd.to_datetime(dec[dec["rv"] == 0].groupby("pmo")["rodada"].first())


def classe(delta: pd.Series, z: float = MODELO.limiar_direcao) -> pd.Series:
    return pd.Series(
        np.select([delta < -z, delta > z], ["desconto", "prêmio"], "neutro"), index=delta.index
    )


# --- premissas e dia típico -----------------------------------------------------------------------------


def premissas_s(w: pd.DataFrame) -> dict:
    """Três premissas de um conjunto de dias (com `grupo_s`), mais leituras da ponta (R$)."""
    dias = w["data"].nunique()
    fora, pt = w[w["grupo_s"] == "fora"], w[w["grupo_s"] == "ponta"]
    f = fora["desvio"].mean() / max(fora["espaco"].mean(), MODELO.espaco_min) if len(fora) else 0.0
    pdia = pt.groupby("data")["pld_dessem"].mean()
    return {
        "dias": int(dias),
        "horas_piso": float((w["grupo_s"] == "vale_piso").sum() / dias) if dias else 0.0,
        "frac_fora": float(max(f, -1.0)),
        "premio_ponta": float(pt["desvio"].mean()) if len(pt) else 0.0,
        "ponta_media": float(pt["pld_dessem"].mean()) if len(pt) else np.nan,
        "ponta_min_dia": float(pdia.min()) if len(pdia) else np.nan,
        "ponta_max_dia": float(pdia.max()) if len(pdia) else np.nan,
        "ponta_max_hora": float(pt["pld_dessem"].max()) if len(pt) else np.nan,
    }


def premissas_s_por_tipo(w: pd.DataFrame) -> dict:
    todos = premissas_s(w)
    out = {
        t: premissas_s(w[w["tipo"] == t]) if (w["tipo"] == t).any() else todos for t in TIPOS_DIA
    }
    out["todos"] = todos
    return out


def dia_s(p: dict, D: float, P: float) -> dict:
    """Dia típico: PLD e contribuição de cada grupo ao desvio (R$/MWh, antes de ponderar pelo
    calendário)."""
    n = min(max(p["horas_piso"], 0.0), NV)
    pf = max(D + p["frac_fora"] * max(D - P, 0.0), P)
    pp = max(D + p["premio_ponta"], P)
    return {
        "pld": (n * P + (NF - n) * pf + NP * pp) / 24,
        "vale_piso": n * (P - D) / 24,
        "fora": (NF - n) * (pf - D) / 24,
        "ponta": NP * (pp - D) / 24,
    }


def janela(hs: pd.DataFrame, origem: pd.Timestamp, dias: int = MODELO.janela) -> pd.DataFrame:
    return hs[(hs["data"] < origem) & (hs["data"] >= origem - pd.Timedelta(days=dias))]


# --- realizado por mês e referência de 12 meses (D060, D061) ----------------------------------------------


def mensal_realizado_s(hs: pd.DataFrame) -> pd.DataFrame:
    """Por mês civil e tipo de dia: as três premissas realizadas no mês, DECOMP e espaço médios."""
    h = hs.assign(mes=hs["data"].dt.to_period("M").astype(str))
    linhas = []
    for mes, x in h.groupby("mes"):
        for t in TIPOS_DIA + ["todos"]:
            xt = x if t == "todos" else x[x["tipo"] == t]
            if xt.empty:
                continue
            real = premissas_s(xt)
            linhas.append(
                {
                    "mes": mes,
                    "tipo": t,
                    "dias": real["dias"],
                    "decomp": float(xt["decomp_pld"].mean()),
                    "espaco": float(xt["espaco"].mean()),
                    "horas_piso": real["horas_piso"],
                    "frac_fora": real["frac_fora"],
                    "premio_ponta": real["premio_ponta"],
                    "ponta_media": real["ponta_media"],
                    "ponta_max_dia": real["ponta_max_dia"],
                }
            )
    mr = pd.DataFrame(linhas)
    mr["fim"] = pd.PeriodIndex(mr["mes"], freq="M").end_time.normalize()
    return mr


def ref_fora_em(mr: pd.DataFrame, origem: pd.Timestamp, tipo: str) -> dict:
    """Desconto das outras horas (D061): média do realizado nos 12 meses civis encerrados antes da
    origem, do tipo de dia, só meses com espaço médio ≥ R$ 20."""
    x = mr[(mr["tipo"] == tipo) & (mr["fim"] < origem) & (mr["espaco"] >= MODELO.espaco_min)]
    x = x.tail(MODELO.meses_ref_fora)
    return {
        "valor": float(x["frac_fora"].mean()) if len(x) else np.nan,
        "meses": len(x),
        "de": x["mes"].min() if len(x) else None,
        "ate": x["mes"].max() if len(x) else None,
    }


def premissas_na_origem(b: Base, origem: pd.Timestamp, mr: pd.DataFrame | None = None) -> dict:
    """Premissas que o simulador usa numa origem: janela padrão e desconto pela média de 12 meses."""
    mr = mensal_realizado_s(b.hs) if mr is None else mr
    pr = premissas_s_por_tipo(janela(b.hs, origem))
    for t in pr:
        v = ref_fora_em(mr, origem, t)["valor"]
        if np.isfinite(v):
            pr[t]["frac_fora"] = v
    return pr


# --- backtest (fora da amostra, condicional ao DECOMP) -----------------------------------------------------


def backtest(b: Base) -> pd.DataFrame:
    """v1 simplificada nos meses completos desde `MODELO.backtest_inicio`, antecedências de 1 a 6:
    origem = rodada da RV0 do mês M − (h − 1); DECOMP realizado (D017); erro = previsto − PLD médio
    oficial do mês."""
    hs, mr = b.hs, mensal_realizado_s(b.hs)
    linhas = []
    for mes, r in b.m[b.m.index >= MODELO.backtest_inicio].iterrows():
        per = pd.Period(mes, "M")
        cal = b.tipos[(b.tipos.index >= per.start_time) & (b.tipos.index <= per.end_time)]
        partes = cal.value_counts(normalize=True)
        Dm, P = r["decomp"], r["piso"]
        for hz in range(1, MODELO.horizontes + 1):
            mo = str(per - (hz - 1))
            if mo not in b.rod.index:
                continue
            o = b.rod[mo]
            if janela(hs, o).empty:
                continue
            pr = premissas_na_origem(b, o, mr)
            prev = max(sum(s * dia_s(pr[t], Dm, P)["pld"] for t, s in partes.items()), P)
            linhas.append(
                {
                    "mes": mes,
                    "h": hz,
                    "decomp": Dm,
                    "real": r["dessem"],
                    "prev": prev,
                    "delta_real": r["delta"],
                    "delta_prev": prev - Dm,
                }
            )
    bt = pd.DataFrame(linhas)
    bt["erro"] = bt["prev"] - bt["real"]
    return bt


def estatisticas(bt: pd.DataFrame) -> dict:
    """Por antecedência, no regime atual: matriz direção prevista → realizada e erros."""
    x = bt[bt["mes"] >= MODELO.regime_desde].copy()
    x["prev_cl"], x["real_cl"] = classe(x["delta_prev"]), classe(x["delta_real"])
    out = {}
    for hz, g in x.groupby("h"):
        out[hz] = {
            "acerto": (g["prev_cl"] == g["real_cl"]).mean(),
            "matriz": pd.crosstab(g["prev_cl"], g["real_cl"], normalize="index"),
            "n": pd.crosstab(g["prev_cl"], g["real_cl"]).sum(axis=1),
            "erro_p10": g["erro"].quantile(0.1),
            "erro_p90": g["erro"].quantile(0.9),
            "erro_abs": g["erro"].abs().mean(),
            "meses": len(g),
        }
    return out


# --- ponta (D056, D064, D065, D072) ------------------------------------------------------------------------


def ponta_diaria(hs: pd.DataFrame) -> pd.DataFrame:
    """Por dia: média das horas da ponta, prêmio sobre o DECOMP vigente, hora mais cara."""
    p = hs[hs["grupo"] == "ponta"]
    return p.groupby("data").agg(
        tipo=("tipo", "first"),
        decomp=("decomp_pld", "first"),
        ponta=("pld_dessem", "mean"),
        premio=("desvio", "mean"),
        hora_max=("pld_dessem", "max"),
    )


def ponta_mensal(hs: pd.DataFrame) -> pd.DataFrame:
    """Por mês civil e tipo de dia: ponta média, prêmio, menor e maior dia, hora mais cara, DECOMP,
    dias e dias com prêmio acima de R$ 100."""
    p = ponta_diaria(hs)
    p = pd.concat([p, p.assign(tipo="todos")])
    p["mes"] = p.index.to_period("M").astype(str)
    return (
        p.groupby(["mes", "tipo"])
        .agg(
            ponta=("ponta", "mean"),
            premio=("premio", "mean"),
            ponta_min_dia=("ponta", "min"),
            ponta_max_dia=("ponta", "max"),
            ponta_max_hora=("hora_max", "max"),
            decomp=("decomp", "mean"),
            dias=("ponta", "size"),
            dias_premio_100=("premio", lambda s: int((s > 100).sum())),
        )
        .reset_index()
    )


def niveis_estresse(hs: pd.DataFrame, origem: pd.Timestamp) -> pd.DataFrame:
    """Prêmio médio mensal da ponta, por tipo de dia, nos meses encerrados antes da origem: com
    estresse = quantil 0,8; sem estresse = quantil 0,2 (D056)."""
    pm = ponta_mensal(hs)
    fim = pd.Period(origem, "M") - 1
    ini = fim - (MODELO.estresse_meses - 1)
    x = pm[(pm["mes"] >= str(ini)) & (pm["mes"] <= str(fim))]
    q_com, q_sem = MODELO.q_estresse
    return pd.DataFrame(
        [
            {
                "tipo": t,
                "com_estresse": float(x[x["tipo"] == t]["premio"].quantile(q_com)),
                "sem_estresse": float(x[x["tipo"] == t]["premio"].quantile(q_sem)),
                "meses": int((x["tipo"] == t).sum()),
                "de": str(ini),
                "ate": str(fim),
            }
            for t in TIPOS_DIA + ["todos"]
        ]
    )


# --- histórico das premissas ----------------------------------------------------------------------------


def trajetoria_diaria(hs: pd.DataFrame, dias: int) -> pd.DataFrame:
    """Por dia (últimos `dias`): tipo, horas do vale no piso, desconto das outras horas, prêmio e
    preço médio da ponta, hora mais cara, DECOMP vigente e espaço."""
    h = hs[hs["data"] > hs["data"].max() - pd.Timedelta(days=dias)]
    fora = h[h["grupo_s"] == "fora"].groupby("data")
    pt = h[h["grupo_s"] == "ponta"].groupby("data")
    d = h.groupby("data").agg(
        tipo=("tipo", "first"), decomp=("decomp_pld", "first"), espaco=("espaco", "first")
    )
    d["horas_piso"] = h[h["grupo_s"] == "vale_piso"].groupby("data").size()
    d["horas_piso"] = d["horas_piso"].fillna(0)
    d["frac_fora"] = (
        fora["desvio"].mean() / fora["espaco"].mean().clip(lower=MODELO.espaco_min)
    ).clip(lower=-1)
    d["premio_ponta"], d["ponta_media"], d["ponta_max_hora"] = (
        pt["desvio"].mean(),
        pt["pld_dessem"].mean(),
        pt["pld_dessem"].max(),
    )
    return d.reset_index()


def historico_premissas_s(hs: pd.DataFrame, X: int, desde: str = "2024-07-01") -> pd.DataFrame:
    """As três premissas que um usuário teria em cada data t (janela de X dias antes de t), por tipo
    de dia; mesma conta de `premissas_s`, em janela móvel."""
    datas = pd.date_range(pd.Timestamp(desde), hs["data"].max() + pd.Timedelta(days=1))
    out = []
    for t in TIPOS_DIA + ["todos"]:
        x = hs if t == "todos" else hs[hs["tipo"] == t]
        d = pd.DataFrame(index=pd.DatetimeIndex(sorted(x["data"].unique())))
        d["dias"] = 1.0
        d["n_piso"] = x[x["grupo_s"] == "vale_piso"].groupby("data").size()
        for g in ("fora", "ponta"):
            xg = x[x["grupo_s"] == g].groupby("data")
            d[f"d_{g}"], d[f"e_{g}"], d[f"n_{g}"] = (
                xg["desvio"].sum(),
                xg["espaco"].sum(),
                xg.size(),
            )
        d["esp_soma"], d["esp_n"] = x.groupby("data")["espaco"].sum(), x.groupby("data").size()
        d["p_soma"] = x[x["grupo_s"] == "ponta"].groupby("data")["pld_dessem"].sum()
        d["dec_soma"] = x.groupby("data")["decomp_pld"].sum()
        d = d.fillna(0.0).reindex(pd.date_range(d.index.min(), datas.max())).fillna(0.0)
        r = d.rolling(f"{X}D", closed="left").sum().reindex(datas)
        esp = (r["e_fora"] / r["n_fora"]).clip(lower=MODELO.espaco_min)
        out.append(
            pd.DataFrame(
                {
                    "data": datas,
                    "tipo": t,
                    "dias": r["dias"].values,
                    "horas_piso": (r["n_piso"] / r["dias"]).values,
                    "frac_fora": ((r["d_fora"] / r["n_fora"]) / esp).clip(lower=-1).values,
                    "premio_ponta": (r["d_ponta"] / r["n_ponta"]).values,
                    "ponta_media": (r["p_soma"] / r["n_ponta"]).values,
                    "decomp": (r["dec_soma"] / r["esp_n"]).values,
                    "espaco": (r["esp_soma"] / r["esp_n"]).values,
                }
            )
        )
    return pd.concat(out, ignore_index=True)


def historico_mensal_s(b: Base, desde: str = "2024-07") -> pd.DataFrame:
    """Por mês civil e tipo de dia: premissas realizadas e as que o simulador usaria na rodada da RV0
    do mês (previsão de 1 mês). Ponta "na RV0" = DECOMP realizado do mês + prêmio da janela."""
    hs = b.hs
    mr = mensal_realizado_s(hs)
    linhas = []
    for r in mr[mr["mes"] >= desde].to_dict("records"):
        o = b.rod.get(r["mes"])
        lin = {k: v for k, v in r.items() if k != "fim"}
        if o is not None:
            w = janela(hs, o)
            if len(w):
                p = premissas_s_por_tipo(w)[r["tipo"]]
                lin.update(
                    rv0=str(pd.Timestamp(o).date()),
                    rv0_horas_piso=p["horas_piso"],
                    rv0_frac_fora=ref_fora_em(mr, o, r["tipo"])["valor"],
                    rv0_premio=p["premio_ponta"],
                    rv0_ponta=r["decomp"] + p["premio_ponta"],
                )
        linhas.append(lin)
    return pd.DataFrame(linhas)


# --- calendário dos meses a simular ------------------------------------------------------------------------


def rv0_estimada(per: pd.Period) -> pd.Timestamp:
    """Data provável da rodada da RV0: sexta antes do sábado que abre a semana do dia 1º."""
    d1 = per.start_time.normalize()
    return d1 - pd.Timedelta(days=(d1.dayofweek - 5) % 7) - pd.Timedelta(days=1)


def calendario(b: Base, origem: pd.Timestamp) -> list[dict]:
    """Meses a simular a partir da origem: antecedência, RV0 (publicada ou estimada), piso e partes
    do mês de cada tipo de dia (tipos dos decks já lidos e, depois deles, dia da semana + feriados
    conhecidos)."""
    lim = b.limites.set_index("ano")["piso"].dropna()
    cal, nao_publicadas = [], 0
    inicio = pd.Period(origem, "M")
    for k in range(MODELO.meses_a_frente):
        per = inicio + k
        # antecedência (D057): 1 se a RV0 do mês já saiu; senão 1 + RV0 ainda não publicadas até a do mês
        publicada = str(per) in b.rod.index
        nao_publicadas += 0 if publicada else 1
        rv0 = b.rod[str(per)] if publicada else rv0_estimada(per)
        dias = pd.date_range(per.start_time, per.end_time.normalize())
        dow = pd.Series(dias.dayofweek, index=dias)
        base = pd.Series(
            np.select([dow == 5, dow == 6], ["sábado", "domingo/feriado"], "útil"), index=dias
        )
        base[base.index.isin(pd.to_datetime(FERIADOS_FUTUROS))] = "domingo/feriado"
        p = b.tipos.reindex(dias).fillna(base).value_counts(normalize=True)
        cal.append(
            {
                "mes": str(per),
                "h": min(1 + nao_publicadas, MODELO.horizontes),
                "rv0": str(pd.Timestamp(rv0).date()),
                "rv0_publicada": publicada,
                "piso": float(lim.get(per.year, lim.iloc[-1])),
                "piso_estimado": bool(per.year not in lim.index),
                **{
                    f"parte_{n}": float(p.get(tp, 0.0))
                    for tp, n in zip(TIPOS_DIA, ["util", "sabado", "domingo"])
                },
            }
        )
    return cal


def prever_mes(pr: dict, c: dict, D: float) -> float:
    """PLD médio do mês com as premissas `pr`, o calendário `c` e o DECOMP D (mesma conta da página)."""
    partes = {
        "útil": c["parte_util"],
        "sábado": c["parte_sabado"],
        "domingo/feriado": c["parte_domingo"],
    }
    return max(
        sum(s * dia_s(pr[t], D, c["piso"])["pld"] for t, s in partes.items() if s), c["piso"]
    )
