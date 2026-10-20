"""Modelo do descolamento NE e N, condicionado à curva do SE informada (pesquisa: pricing-descolamento-analytics,
estrutural.py, caminho da v2.2: `treinar` + `ajustes_v2_2` + `prever`; D015, D022, D025).

Para um deck D e cada mês-alvo m, com dados só até o fim de D−2:
1. P(trava) por regime (1S, 2S) e submercado (NE, N): regressão logística nas features padronizadas (sobra N+NE sem
   térmica e margem de exportação do NE), horas desde `inicio_treino`;
2. k (intensidade): o do mesmo ano climático e semestre do cenário (desde 2021, semestres completos, folga média
   ≥ `folga_min_k`); sem ele, o k de reserva do regime (média nas horas descoladas desde `inicio_treino`);
3. cenários: um por ano histórico com o mesmo mês do calendário (≥ `min_dias_cenario` dias), com renovável do NE no
   nível do deck D (sem correção de viés, D015), carga do NE e do N no nível do deck × viés da carga, hidráulica do
   NE do ano mais recente e renovável e hidráulica do N do próprio ano; limite de exportação do NE do AGRINT do deck;
4. d_sub = média_h(−p_h · k · max(SE · perfil_h − piso, 0)), com o perfil horário do SE por mês do calendário e
   hora (até D−2) e o piso do ano min(m.ano, D.ano).

Coeficientes por cenário (para a página): c_sub[h] = Σ p·k nas horas h ÷ horas do mês, e perfil_h; para qualquer SE,
d = −Σ_h c_h · max(SE · perfil_h − piso, 0), exato.

Mudar um parâmetro ou definição = versão nova do modelo (decisão na pesquisa, `congelar`, tag
`pricing_descolamento-modelo-<versão>`), como nas outras funcionalidades.
"""

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from qe_core.armazenamento import Armazenamento, ler_parquet
from qe_pricing_descolamento import chaves


@dataclass(frozen=True)
class Modelo:
    versao: str
    # definições da base horária (T5)
    limiar_desc: float  # R$/MWh: hora descolada = sub − SE < −limiar_desc
    limiar_mult: float  # R$/MWh: restrição travada = multiplicador > limiar_mult
    # treino (D−2)
    features: tuple[str, ...]
    inicio_treino: str  # horas da logística e do k de reserva
    c_logistica: float  # regularização da regressão logística (C)
    min_horas_classe: int  # horas mínimas de cada classe para treinar P(trava); senão P = 0
    min_horas_k: int  # horas descoladas mínimas para o k de reserva; senão k = 0
    min_horas_k_ano: int  # horas descoladas mínimas para o k de um (ano, semestre)
    folga_min_k: (
        float  # R$/MWh: folga média mínima para usar o k pareado com o ano climático (D022)
    )
    meses_vies: int  # meses (até D−2) do viés da carga: realizado ÷ projetado no próprio deck
    min_dias_cenario: int  # dias mínimos de um ano histórico no mês para virar cenário

    def como_dict(self) -> dict:
        return asdict(self)


V2_2 = Modelo(
    versao="v2.2",
    limiar_desc=1.0,
    limiar_mult=1.0,
    features=("sobra_NNE_st", "margem_exp_NE"),
    inicio_treino="2024-01-01",
    c_logistica=1.0,
    min_horas_classe=20,
    min_horas_k=20,
    min_horas_k_ano=50,
    folga_min_k=50.0,
    meses_vies=12,
    min_dias_cenario=20,
)

MODELO = V2_2
SUBS = ["NE", "N"]
REGIMES = ("1S", "2S")
TIPOS_RENOVAVEL = ["EOL", "UFV", "EOL MMGD", "UFV MMGD"]
COLS_CENARIO = [
    "renovavel_NE",
    "demanda_NE",
    "renovavel_N",
    "hidraulica_N",
    "demanda_N",
    "hidraulica_NE",
]


def regime(m: pd.Period) -> str:
    return "1S" if m.month <= 6 else "2S"


# --- dados de base (lidos uma vez) ----------------------------------------------------------------------


class Base:
    """Base horária, limites, PLD mensal e as projeções dos decks."""

    def __init__(self, arm: Armazenamento):
        from qe_pricing_descolamento import tratamento

        self.h = ler_parquet(arm, chaves.PROC_BASE)
        self.h["mes"] = self.h.index.to_period("M")
        self.limites = tratamento.limites(arm)
        self.mensal = ler_parquet(arm, chaves.PROC_PLD_MENSAL)
        ns = ler_parquet(arm, chaves.PROC_DECK["nao_simuladas"])
        merc = ler_parquet(arm, chaves.PROC_DECK["mercado"])
        ag = ler_parquet(arm, chaves.PROC_DECK["agrint"])
        self.exp_ne = ag[ag["nome"].str.replace(" ", "").str.contains("EXPORTACAONE")]
        ren = ns[ns["tipo"].isin(TIPOS_RENOVAVEL) & (ns["sub"] == "NE")]
        self.ren_proj = ren.groupby(["deck", "ano", "mes"])["mw"].sum()
        self.car_proj = merc[merc["sub"] == "NE"].set_index(["deck", "ano", "mes"])["mw"]
        self.car_proj_n = merc[merc["sub"] == "N"].set_index(["deck", "ano", "mes"])["mw"]
        self.real_mes = self.h.groupby("mes")[["renovavel_NE", "demanda_NE", "demanda_N"]].mean()

    def piso(self, ano) -> pd.Series | float:
        return self.limites["piso"].loc[ano]


def _chave(deck: pd.Period, m: pd.Period) -> tuple[str, int, int]:
    return (deck.strftime("%Y%m"), m.year, m.month)


def _fator_vies(b: Base, deck: pd.Period, serie_proj: pd.Series, col: str) -> float:
    """Média de realizado ÷ projetado no próprio deck (h = 0) nos meses de D−1−n a D−2."""
    r = []
    for m in pd.period_range(deck - 1 - MODELO.meses_vies, deck - 2, freq="M"):
        if _chave(m, m) in serie_proj.index and m in b.real_mes.index:
            r.append(b.real_mes.loc[m, col] / serie_proj.loc[_chave(m, m)])
    return float(np.mean(r)) if r else 1.0


# --- treino na data do deck --------------------------------------------------------------------------------


def treinar(b: Base, deck: pd.Period) -> dict:
    """Padronização, logísticas de P(trava), k de reserva, k por (ano, semestre), perfil do SE e viés da carga,
    com dados até o fim de D−2."""
    feats = list(MODELO.features)
    fim = (deck - 1).to_timestamp()
    ini = pd.Timestamp(MODELO.inicio_treino)
    t = b.h[(b.h.index >= ini) & (b.h.index < fim)].dropna(subset=feats)
    out = {"mu": t[feats].mean(), "sd": t[feats].std()}
    for reg in REGIMES:
        y = t[t["regime"] == reg]
        z = ((y[feats] - out["mu"]) / out["sd"]).to_numpy()
        piso = y.index.year.map(b.limites["piso"]).to_numpy()
        for s in SUBS:
            alvo = y[f"desc_{s}"].to_numpy(dtype=bool)
            if alvo.sum() < MODELO.min_horas_classe or (~alvo).sum() < MODELO.min_horas_classe:
                out[("p", reg, s)] = None
            else:
                out[("p", reg, s)] = LogisticRegression(C=MODELO.c_logistica).fit(
                    z, alvo, sample_weight=np.ones(len(y))
                )
            dd = y[alvo]
            if len(dd) >= MODELO.min_horas_k:
                folga = (dd["SE"] - piso[alvo]).clip(lower=1)
                out[("k", reg, s)] = float(np.mean(((dd["SE"] - dd[s]) / folga).clip(0, 1)))
            else:
                out[("k", reg, s)] = 0.0
    # k e folga média por (ano, semestre) desde o início da base, semestres completos até D−2
    hh = b.h[b.h.index < fim]
    for s in SUBS:
        kano = {}
        for (ano, reg), y in hh.groupby([hh.index.year, hh["regime"]]):
            fim_sem = (
                pd.Timestamp(f"{ano}-07-01") if reg == "1S" else pd.Timestamp(f"{ano + 1}-01-01")
            )
            if fim_sem > fim:
                continue
            dd = y[y[f"desc_{s}"].astype(bool)]
            if len(dd) >= MODELO.min_horas_k_ano:
                folga_y = dd["SE"] - dd.index.year.map(b.limites["piso"]).to_numpy()
                kano[(ano, reg)] = {
                    "k": float(((dd["SE"] - dd[s]) / folga_y.clip(lower=1)).clip(0, 1).mean()),
                    "folga_media": float(folga_y.mean()),
                    "horas": len(dd),
                }
        out[("kano", s)] = kano
    # perfil horário do SE: SE_h ÷ SE médio do mês, média por (mês do calendário, hora)
    se = b.h[b.h.index < fim]["SE"]
    rel = se / se.groupby(se.index.to_period("M")).transform("mean")
    out["perfil_se"] = rel.groupby([rel.index.month, rel.index.hour]).mean()
    out["vies_car"] = _fator_vies(b, deck, b.car_proj, "demanda_NE")
    out["vies_car_n"] = _fator_vies(b, deck, b.car_proj_n, "demanda_N")
    return out


# --- insumos e cenários do mês-alvo ----------------------------------------------------------------------


def _lim_exp(b: Base, deck: pd.Period, m: pd.Period) -> float:
    """Limite de exportação do NE (AGRINT do deck, patamar 1) no mês m; sem o mês, o último definido."""
    x = b.exp_ne[b.exp_ne["deck"] == deck.strftime("%Y%m")]
    xm = x[(x["ano"] == m.year) & (x["mes"] == m.month)]
    if len(xm):
        return float(xm["lim_p1"].iloc[0])
    return float(x.sort_values(["ano", "mes"])["lim_p1"].iloc[-1])


def insumos_mes(b: Base, deck: pd.Period, m: pd.Period, modelo: dict) -> dict:
    """Renovável do NE do deck (sem viés), carga do NE e do N (deck × viés) e limite de exportação do NE. Vazio
    se o mês não tem o mesmo mês do calendário realizado até D−2 ou a projeção do deck D para m (o mês não entra)."""
    ult = [p for p in b.real_mes.index if p.month == m.month and p <= deck - 2]
    if not ult or _chave(deck, m) not in b.ren_proj.index:
        return {}
    return {
        "renovavel_deck_NE": float(b.ren_proj.loc[_chave(deck, m)]),
        "carga_NE": float(b.car_proj.loc[_chave(deck, m)] * modelo["vies_car"]),
        "carga_N": float(b.car_proj_n.get(_chave(deck, m), np.nan) * modelo["vies_car_n"]),
        "limite_exp_NE": _lim_exp(b, deck, m),
    }


def cenarios(b: Base, deck: pd.Period, m: pd.Period, ins: dict) -> list[tuple[dict, pd.DataFrame]]:
    """Um cenário por ano histórico com o mesmo mês do calendário até D−2: (informações, features por hora)."""
    hist = b.h[b.h.index < (deck - 1).to_timestamp()]
    do_mes = hist[hist.index.month == m.month].dropna(subset=COLS_CENARIO)
    if do_mes.empty:
        return []
    recente = do_mes[do_mes.index.year == do_mes.index.year.max()]
    hidr_ne = recente.groupby(recente.index.hour)["hidraulica_NE"].mean()
    out = []
    for ano, x in do_mes.groupby(do_mes.index.year):
        if len(x) < 24 * MODELO.min_dias_cenario:
            continue
        ren = x["renovavel_NE"] / x["renovavel_NE"].mean() * ins["renovavel_deck_NE"]
        car = x["demanda_NE"] * ins["carga_NE"] / x["demanda_NE"].mean()
        car_n = x["demanda_N"] * (
            ins["carga_N"] / x["demanda_N"].mean() if np.isfinite(ins["carga_N"]) else 1.0
        )
        hne = hidr_ne.reindex(x.index.hour).fillna(hidr_ne.mean()).to_numpy()
        sobra_ren = ren - car
        f = pd.DataFrame(
            {
                "sobra_NNE_st": sobra_ren + hne + (x["renovavel_N"] + x["hidraulica_N"] - car_n),
                "margem_exp_NE": sobra_ren - ins["limite_exp_NE"],
            },
            index=x.index,
        )
        info = {
            "ano_hidro": int(ano),
            "renovavel_efetiva_NE": float(ren.mean()),
            "hidraulica_N": float(x["hidraulica_N"].mean()),
            "peso": 1.0,
        }
        out.append((info, f))
    return out


# --- previsão --------------------------------------------------------------------------------------------


def _k(modelo: dict, s: str, reg: str, ano: int) -> float:
    """k pareado com o ano climático (D022); sem k elegível do (ano, semestre), o k de reserva do regime."""
    ent = modelo[("kano", s)].get((ano, reg))
    ok = ent is not None and ent["folga_media"] >= MODELO.folga_min_k
    return float(np.clip(ent["k"] if ok else modelo[("k", reg, s)], 0, 1))


def piso_previsao(b: Base, deck: pd.Period, m: pd.Period) -> float:
    """Piso do ano min(m.ano, D.ano): o piso futuro é desconhecido na data do deck."""
    return float(b.limites.loc[min(m.year, deck.year, b.limites.index.max()), "piso"])


def prever(b: Base, deck: pd.Period, m: pd.Period, se: float, modelo: dict) -> pd.DataFrame:
    """Cenários do mês-alvo m com o SE informado: d_NE e d_N, coeficientes c_NE e c_N (24 valores), perfil_h,
    piso, P(trava) média e k efetivo. Vazio se o mês não tem insumos."""
    ins = insumos_mes(b, deck, m, modelo)
    if not ins:
        return pd.DataFrame()
    feats = list(MODELO.features)
    reg, piso = regime(m), piso_previsao(b, deck, m)
    lin = []
    for info, f in cenarios(b, deck, m, ins):
        z = ((f[feats] - modelo["mu"]) / modelo["sd"]).to_numpy()
        perfil = (
            modelo["perfil_se"]
            .reindex(list(zip(f.index.month, f.index.hour)))
            .fillna(1.0)
            .to_numpy()
        )
        folga = np.clip(se * perfil - piso, 0, None)
        hs = f.index.hour.to_numpy()
        r = {"mes_alvo": str(m), "h": (m - deck).n, "SE": se, **info}
        r["perfil_h"] = (
            np.bincount(hs, weights=perfil, minlength=24)
            / np.maximum(np.bincount(hs, minlength=24), 1)
        ).tolist()
        r["piso"] = piso
        for s in SUBS:
            clf = modelo[("p", reg, s)]
            p = clf.predict_proba(z)[:, 1] if clf is not None else np.zeros(len(f))
            k = np.full(len(f), _k(modelo, s, reg, info["ano_hidro"]))
            r[f"d_{s}"] = float(np.mean(-p * k * folga))
            r[f"c_{s}"] = (np.bincount(hs, weights=p * k, minlength=24) / len(f)).tolist()
            r[f"p_trava_{s}"] = float(p.mean())
            r[f"k_prev_{s}"] = float((p * k).sum() / p.sum()) if p.sum() > 0 else np.nan
        lin.append(r)
    return pd.DataFrame(lin)


# --- agregação por produto (D025) ------------------------------------------------------------------------

ROTULO_PERIODO = {
    "trimestre": lambda m: f"{m.year}-T{m.quarter}",
    "semestre": lambda m: f"{m.year}-S{1 if m.month <= 6 else 2}",
    "ano": lambda m: str(m.year),
}


def projecao(b: Base, deck: pd.Period, se_mensal: pd.Series, modelo: dict) -> pd.DataFrame:
    """Mês a mês e por cenário (id = ano climático): mes, horas, cenario, peso, NE, N."""
    lin = []
    for m, se in se_mensal.items():
        p = prever(b, deck, m, float(se), modelo)
        for c in p.itertuples():
            lin.append(
                {
                    "mes": m,
                    "horas": m.days_in_month * 24,
                    "cenario": str(c.ano_hidro),
                    "peso": c.peso,
                    "NE": c.d_NE,
                    "N": c.d_N,
                }
            )
    return pd.DataFrame(lin)


def faixa_periodos(x: pd.DataFrame, periodo: str) -> pd.DataFrame:
    """Preço justo e faixa entre cenários por período. Justo = média ponderada dos cenários (peso) em cada mês,
    depois média por horas. Faixa = mín–máx de cada cenário agregado no período por horas; só entram cenários
    presentes em todos os meses do período (o ano climático mais recente pode cobrir só parte deles)."""
    x = x.assign(periodo=x["mes"].map(ROTULO_PERIODO[periodo]))
    mes = x.groupby(["periodo", "mes"]).apply(
        lambda g: pd.Series(
            {
                "horas": g["horas"].iloc[0],
                "NE": np.average(g["NE"], weights=g["peso"]),
                "N": np.average(g["N"], weights=g["peso"]),
            }
        ),
        include_groups=False,
    )
    justo = mes.groupby("periodo").apply(
        lambda g: pd.Series({f"{s}_justo": np.average(g[s], weights=g["horas"]) for s in SUBS}),
        include_groups=False,
    )
    n_mes = x.groupby("periodo")["mes"].nunique()
    cen = x.groupby(["periodo", "cenario"]).apply(
        lambda g: pd.Series(
            {
                "meses": g["mes"].nunique(),
                "NE": np.average(g["NE"], weights=g["horas"]),
                "N": np.average(g["N"], weights=g["horas"]),
            }
        ),
        include_groups=False,
    )
    cen = cen[cen["meses"] == n_mes.reindex(cen.index.get_level_values("periodo")).values]
    faixa = cen.groupby("periodo").agg(
        NE_min=("NE", "min"),
        NE_max=("NE", "max"),
        N_min=("N", "min"),
        N_max=("N", "max"),
        n_cenarios=("NE", "size"),
    )
    out = justo.join(faixa)
    out.index.name = periodo
    return out[["NE_justo", "NE_min", "NE_max", "N_justo", "N_min", "N_max", "n_cenarios"]]
