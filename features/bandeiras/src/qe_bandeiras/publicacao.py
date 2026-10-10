"""Publicação: monta os dados da página de Projeções e registra a rodada publicada.

Saídas em serving/bandeiras/:
- produto_dados.js: `window.DADOS = {...}` lido pela página (mesmo formato do analytics);
- historico_projecoes.json: registro acumulado das rodadas publicadas, como foram publicadas.
  Publicar de novo no mesmo mês substitui só a rodada desse mês; as outras nunca são recalculadas.
"""

import json
from datetime import date

import pandas as pd

from qe_bandeiras import backtest, chaves, ecmwf, modelo, regra, series
from qe_bandeiras.backtest import AB, br
from qe_core.armazenamento import Armazenamento, gravar_json, ler_json, ler_parquet

ORD = regra.CORES
NIV = {c: i for i, c in enumerate(ORD)}


def historico_oficial(arm: Armazenamento, base: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Histórico da ANEEL + meses já anunciados (boletim da CCEE) e o adicional vigente de cada cor."""
    hist = ler_parquet(arm, chaves.PROC_HISTORICO)
    hist.index = pd.PeriodIndex(hist.pop("mes"), freq="M")
    vigente = {c: float(hist[hist.cor == c].adicional.iloc[-1]) for c in ORD}
    vigente["Verde"] = 0.0
    for m in base.index[(base.index > hist.index.max()) & base.cor_oficial.notna()]:
        hist.loc[m] = {
            "cor": base.loc[m, "cor_oficial"],
            "adicional": vigente[base.loc[m, "cor_oficial"]],
        }
    return hist.sort_index(), vigente


def _projecoes(cen: pd.DataFrame, hist: pd.DataFrame, vigente: dict) -> list[dict]:
    saida = []
    for r in cen.itertuples():
        anunciada = hist.cor.get(r.alvo)
        saida.append(
            {
                "alvo": str(r.alvo),
                "h": int(r.h),
                "anunciada": anunciada if isinstance(anunciada, str) else None,
                "prob": {c: round(float(getattr(r, f"p_{c}".replace(" ", "_"))), 4) for c in ORD},
                "adicional": vigente[
                    r.cor_esp
                ],  # adicional da bandeira esperada (não há proporcional)
                **{
                    f"{k}_{n}": (
                        round(float(getattr(r, f"{k}_{n}")), 3)
                        if k != "cor"
                        else getattr(r, f"{k}_{n}")
                    )
                    for n in ("esp", "li", "ls")
                    for k in ("gsf", "pld", "x", "cor")
                },
            }
        )
    return saida


def _selecao(prep: dict, refs: dict, dk: pd.Period, alvos: list) -> dict:
    periodos = [dk + i for i in range(7)]
    ena_todas = prep["ena"][periodos]
    sel = {
        "periodos": [str(p) for p in periodos],
        "faixa": {
            q: [round(float(v)) for v in ena_todas.quantile(qq)]
            for q, qq in (("p10", 0.1), ("p50", 0.5), ("p90", 0.9))
        },
        "referencias": {n: [round(float(refs[n][p])) for p in periodos] for n in refs},
        "alvos": {},
    }
    for alvo in alvos:
        traj = [dk + i for i in range((alvo - dk).n + 1)]
        sel["alvos"][str(alvo)] = {}
        for n, ref in refs.items():
            idx = modelo.escolher(prep, ref, alvo)
            sel["alvos"][str(alvo)][n] = {
                "series": [int(s) for s in idx],
                "ena": [[round(float(v)) for v in prep["ena"].loc[s, traj]] for s in idx],
                "gsf": [round(float(v), 3) for v in prep["gsf"].loc[idx, alvo]],
                "pld": [round(float(v), 1) for v in prep["pld"].loc[idx, alvo]],
            }
    return sel


def _passos_gsf(prep: dict, sel: dict, alvo: pd.Period, cenario: str) -> dict:
    f, gf_band = prep["fatores"], float(prep["gf_band"])
    idx = sel["alvos"][str(alvo)][cenario]["series"]
    gh_ons = float(prep["gh"].loc[idx, alvo].mean())
    ande, pch = float(prep["ande"][alvo]), float(prep["pch"].loc[alvo].sum())
    gh_cg = (gh_ons - ande) * (1 - f["perda_bruta_conexao"]) * (1 - f["perda_conexao_cg"])
    pch_cg = pch * f["part_pch_mre"] * (1 - f["perda_pch_cg"])
    return {
        "alvo": str(alvo),
        "gh_ons": round(gh_ons),
        "ande": round(ande),
        "perdas": round(gh_ons - ande - gh_cg),
        "pch": round(pch),
        "pch_mre": round(pch_cg),
        "gh_band": round(gh_cg + pch_cg),
        "gf_band": round(gf_band),
        "gsf": round((gh_cg + pch_cg) / gf_band, 3),
    }


def _desempenho(bt: dict, hist: pd.DataFrame) -> dict:
    A = bt["referencia"].copy()
    A["pers"] = A.deck.map(hist.cor)
    A["saz"] = [hist.cor.get(a - 12) for a in A.alvo]
    acerto = {
        n: [round(float((g[c] == g.cor_oficial).mean()), 3) for _, g in A.groupby("h")]
        for n, c in (("modelo", "cor_media"), ("persistencia", "pers"), ("ano_anterior", "saz"))
    }
    acerto["oraculo"] = [
        round(float((g.cor_media == g.cor_oficial).mean()), 3)
        for _, g in bt["oraculo"].groupby("h")
    ]
    pares = []
    for r in A.itertuples():
        p = modelo.probabilidade_por_grupo(A, r.deck, r.h, r.x_medio, r.gsf_medio)
        if not p.isna().all():
            pares += [(float(p[c]), float(c == r.cor_oficial)) for c in ORD]
    pares = pd.DataFrame(pares, columns=["p", "ocorreu"])
    pares["faixa"] = pd.cut(pares.p, [-0.001, 0.1, 0.3, 0.5, 0.7, 0.9, 1.0])
    conf = pares.groupby("faixa", observed=True).agg(
        prevista=("p", "mean"), observada=("ocorreu", "mean"), n=("p", "size")
    )
    R = bt["rodadas"][bt["rodadas"].real.notna()]
    cobertura = sum(NIV[r.cor_ls] <= NIV[r.real] <= NIV[r.cor_li] for r in R.itertuples()) / len(R)
    previstas = {}
    for r in A[A.h.isin([1, 3])].itertuples():
        previstas.setdefault(str(r.alvo), {})[f"h{r.h}"] = r.cor_media
    return {
        "acerto_por_h": acerto,
        "n_previsoes": len(A),
        "n_decks": int(A.deck.nunique()),
        "periodo": [str(A.deck.min()), str(A.deck.max())],
        "cobertura_li_ls": round(cobertura, 3),
        "confiabilidade": [
            {
                "prevista": round(float(r.prevista), 3),
                "observada": round(float(r.observada), 3),
                "n": int(r.n),
            }
            for r in conf.itertuples()
        ],
        "previstas": previstas,
    }


def _registrar(arm: Armazenamento, dk: pd.Period, projecoes: list[dict]) -> dict:
    publicadas = (
        ler_json(arm, chaves.SERVING_REGISTRO) if arm.existe(chaves.SERVING_REGISTRO) else {}
    )
    publicadas[str(dk)] = [
        {
            "deck": str(dk),
            "alvo": p["alvo"],
            "h": p["h"],
            "esp": p["cor_esp"],
            "li": p["cor_li"],
            "ls": p["cor_ls"],
            "prob": " ".join(f"{AB[c]} {v:.0%}" for c, v in p["prob"].items() if v >= 0.05),
            "gp": f"GSF {br(p['gsf_esp'], 2)} · R$ {br(p['pld_esp'])}",
            "publicada_em": date.today().isoformat(),
        }
        for p in projecoes
    ]
    publicadas = dict(sorted(publicadas.items()))
    gravar_json(arm, publicadas, chaves.SERVING_REGISTRO)
    return publicadas


def publicar(arm: Armazenamento, dk: pd.Period, cen: pd.DataFrame, bt: dict) -> dict:
    """Monta e grava os dados da página para a rodada `dk`; devolve o dicionário publicado."""
    base = backtest.base_oficial(arm)
    hist, vigente = historico_oficial(arm, base)
    prep = series.series_do_deck(arm, dk, base)
    refs = backtest.referencias(arm, dk, base)
    cen = cen.rename(columns=lambda c: c.replace(" ", "_"))
    projecoes = _projecoes(cen, hist, vigente)

    meses_hist = [
        m for m in base.index if dk - 17 <= m <= dk and pd.notna(base.loc[m, "gsf_band_boletim"])
    ]
    mlt_hist = base.ena_sin / (base.ena_mlt_sin / 100)
    mlt_proj = ecmwf.referencia_climatologia(arm, dk)
    insumos = {
        "realizado": [
            {
                "mes": str(m),
                "ena": round(float(base.loc[m, "ena_sin"])),
                "mlt": round(float(mlt_hist[m])),
                "gsf": float(base.loc[m, "gsf_band_boletim"]),
                "pld": round(float(base.loc[m, "pld_gatilho_boletim"]), 2),
            }
            for m in meses_hist
        ],
        "projetado": [
            {
                "mes": str(a),
                "mlt": round(float(mlt_proj[a])),
                **{f"ena_{n}": round(float(refs[n][a])) for n in refs},
                **{f"{k}_{n}": p[f"{k}_{n}"] for n in ("esp", "li", "ls") for k in ("gsf", "pld")},
            }
            for a, p in zip(cen.alvo, projecoes)
        ],
    }
    sel = _selecao(prep, refs, dk, list(cen.alvo))
    calculo = {n: [_passos_gsf(prep, sel, a, n) for a in cen.alvo] for n in refs}

    publicadas = _registrar(arm, dk, projecoes)

    def oficial(alvo):
        c = hist.cor.get(pd.Period(alvo, "M"))
        return c if isinstance(c, str) else None

    rec = bt["rodadas"]
    rodadas = [
        {
            "deck": str(r.deck),
            "alvo": str(r.alvo),
            "h": int(r.h),
            "real": r.real if isinstance(r.real, str) else None,
            "esp": r.cor_esp,
            "li": r.cor_li,
            "ls": r.cor_ls,
            "prob": r.prob,
            "gp": r.gp,
        }
        for r in rec[~rec.deck.astype(str).isin(publicadas)].itertuples()
    ]
    for lista in publicadas.values():
        rodadas += [{**x, "real": oficial(x["alvo"]), "publicada": True} for x in lista]

    dados = {
        "gerado_em": date.today().isoformat(),
        "deck": str(dk),
        "rodada_ecmwf": str(dk),
        "adicional_vigente": vigente,
        "limites_x": regra.LIMITES_X,
        "fatores": {k: round(v * 100, 3) for k, v in prep["fatores"].items()},
        "pld_min": float(base.loc[dk, "pld_min_boletim"]),
        "pld_max": float(base.loc[dk, "pld_max_boletim"]),
        "projecoes": projecoes,
        "historico": [
            {
                "mes": str(m),
                "cor": r.cor,
                "adicional": float(r.adicional),
                **(
                    {
                        "gsf": float(base.loc[m, "gsf_band_boletim"]),
                        "pld": round(float(base.loc[m, "pld_gatilho_boletim"]), 2),
                    }
                    if m in base.index and pd.notna(base.loc[m, "gsf_band_boletim"])
                    else {}
                ),
            }
            for m, r in hist.iterrows()
        ],
        "insumos": insumos,
        "selecao": sel,
        "calculo_gsf": calculo["esp"],
        "calculo_gsf_cenarios": calculo,
        "desempenho": _desempenho(bt, hist),
        "rodadas": rodadas,
    }
    arm.gravar_bytes(
        ("window.DADOS = " + json.dumps(dados, ensure_ascii=False) + ";\n").encode("utf-8"),
        chaves.SERVING_DADOS,
    )
    return dados
