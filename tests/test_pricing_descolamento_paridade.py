"""Paridade com a pesquisa (opt-in): app × pacote de promoção do pricing-descolamento-analytics.

Conferência única da migração (docs/promocao_descolamento.md da pesquisa, seção 9). Só roda com
QE_PARIDADE_PRICING_DESCOLAMENTO=<pasta reports/promocao/AAAA-MM da pesquisa> e com o app tendo ingerido os mesmos
arquivos brutos (hashes no manifesto da pasta). Bloco 1: leitores (R1 a R3) e tabelas-base (R4, R5); bloco 2:
modelo treinado (R6), cenários, insumos, faixas e o exemplo do T1/2027 (R7).
"""

import datetime as dt
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from qe_core.armazenamento import ArmazenamentoLocal, ler_parquet
from qe_core.leitores import dessem, newave
from qe_pricing_descolamento import chaves, tratamento

PASTA = os.environ.get("QE_PARIDADE_PRICING_DESCOLAMENTO")
DADOS = Path(__file__).resolve().parents[1] / "data"
DIAS = ["2023-03-15", "2025-03-15", "2026-09-15"]
# nomes do leitor do qe_core → nomes da pesquisa
NOMES_SIST = {
    "periodo": "iper",
    "submercado": "sub",
    "grenova": "renovavel",
    "somat_gh": "hidraulica",
    "somat_gt": "termica",
    "cons_eleva": "conseleva",
    "corte_carga": "cortecarga",
    "soma_gt_min": "gtmin",
    "somat_gt_max": "gtmax",
}

pytestmark = pytest.mark.skipif(not PASTA, reason="paridade com a pesquisa é opt-in")


@pytest.fixture(scope="module")
def arm():
    return ArmazenamentoLocal(DADOS)


def _r(nome: str) -> pd.DataFrame:
    return pd.read_parquet(Path(PASTA) / f"{nome}.parquet")


def _igual(app: pd.DataFrame, ref: pd.DataFrame, atol: float = 0.0) -> None:
    pd.testing.assert_frame_equal(
        app, ref, check_dtype=False, check_index_type=False, check_names=False, atol=atol, rtol=0
    )


@pytest.mark.parametrize("dia", DIAS)
def test_R1_ler_pdo_sist(arm, dia):
    d = dt.date.fromisoformat(dia)
    a = dessem.ler_pdo_sist(arm.caminho_local(chaves.raw_dessem(d, "PDO_SIST.DAT.gz")), d)
    a = a.rename(columns=NOMES_SIST)
    r = _r("R1_ler_pdo_sist")
    r = r[r["dia"] == dia].reset_index(drop=True)
    cols = [c for c in r.columns if c not in ("data_hora", "dia")]
    _igual(a[cols], r[cols])


@pytest.mark.parametrize("dia", DIAS)
def test_R2_ler_re_inte(arm, dia):
    d = dt.date.fromisoformat(dia)
    a = dessem.ler_re_inte(arm.caminho_local(chaves.raw_dessem(d, "PDO_RESTOPER.DAT.gz")), d)
    r = _r("R2_ler_re_inte")
    r = r[r["dia"] == dia].reset_index(drop=True)
    cols = ["iper", "num", "valor", "linf", "lsup", "mult", "composicao"]
    _igual(a.rename(columns={"periodo": "iper"})[cols], r[cols])


@pytest.mark.parametrize("deck", ["202401", "202610"])
def test_R3_sistema_e_agrint(arm, deck):
    pasta = tratamento.decks_sistema_agrint(arm)[deck]
    s = newave.ler_sistema(arm.caminho_local(f"{pasta}/sistema.dat"))
    _igual(s["mercado"], _r(f"R3_sistema_mercado_{deck}"))
    _igual(s["nao_simuladas"], _r(f"R3_sistema_nao_simuladas_{deck}"))
    _igual(newave.ler_agrint(arm.caminho_local(f"{pasta}/agrint.dat")), _r(f"R3_agrint_{deck}"))


def test_R4_pld(arm):
    _igual(ler_parquet(arm, chaves.PROC_PLD_HORARIO), _r("R4_pld_horario"), 1e-4)
    r = _r("R4_pld_mensal")
    _igual(ler_parquet(arm, chaves.PROC_PLD_MENSAL)[r.columns], r, 1e-4)


def test_R4_decks(arm):
    for k, c in chaves.PROC_DECK.items():
        r = _r(f"R4_deck_{k}")
        _igual(ler_parquet(arm, c)[r.columns], r)


def test_R5_base_horaria(arm):
    r = _r("R5_base_horaria")
    a = ler_parquet(arm, chaves.PROC_BASE)
    a = a[a.index <= r.index.max()]
    _igual(a[r.columns], r, 1e-3)


# --- bloco 2: modelo v2.2 (R6, R7) -----------------------------------------------------------------------


@pytest.fixture(scope="module")
def rodada(arm):
    from qe_pricing_descolamento import modelo as M

    b, d = M.Base(arm), pd.Period("2026-10", "M")
    mod = M.treinar(b, d)
    meses = list(pd.period_range(d + 1, pd.Period("2030-12", "M"), freq="M"))
    return M, b, d, mod, meses


def _perto(a, r, tol):
    a, r = np.asarray(a, float), np.asarray(r, float)
    assert a.shape == r.shape and np.nanmax(np.abs(a - r)) <= tol


def test_R6_modelo(rodada):
    M, _b, _d, mod, _ = rodada
    r6 = json.loads((Path(PASTA) / "R6_modelo.json").read_text(encoding="utf-8"))
    f = r6["features"]
    _perto(mod["mu"][f], [r6["mu"][x] for x in f], 1e-6)
    _perto(mod["sd"][f], [r6["sd"][x] for x in f], 1e-6)
    _perto([mod["vies_car"], mod["vies_car_n"]], [r6["vies_car_NE"], r6["vies_car_N"]], 1e-6)
    perfil = [[mod["perfil_se"].get((m, h), np.nan) for h in range(24)] for m in range(1, 13)]
    _perto(perfil, r6["perfil_se"], 1e-6)
    for reg in M.REGIMES:
        for s in M.SUBS:
            c, r = mod[("p", reg, s)], r6["p_trava"][f"{reg}_{s}"]
            _perto([*c.coef_[0], c.intercept_[0]], [*r["coef"], r["intercepto"]], 1e-6)
            _perto([mod[("k", reg, s)]], [r6["k_reserva"][f"{reg}_{s}"]], 1e-6)
    for s in M.SUBS:
        a = sorted(mod[("kano", s)].items())
        r = r6["k_ano_semestre"][s]
        assert [k for k, _ in a] == [(x["ano"], x["semestre"]) for x in r]
        _perto(
            [[v["k"], v["folga_media"], v["horas"]] for _, v in a],
            [[x["k"], x["folga_media"], x["horas"]] for x in r],
            1e-6,
        )


def test_R7_cenarios_insumos_e_faixas(rodada):
    M, b, d, mod, meses = rodada
    cen = pd.concat([M.prever(b, d, m, 200.0, mod) for m in meses], ignore_index=True)
    r7 = _r("R7_cenarios")
    assert (
        cen[["mes_alvo", "ano_hidro"]].values.tolist()
        == r7[["mes_alvo", "ano_hidro"]].values.tolist()
    )
    for c in ["h", "SE", "renovavel_efetiva_NE", "hidraulica_N", "peso", "d_NE", "d_N", "piso"]:
        _perto(cen[c], r7[c], 1e-9)
    for c in ["p_trava_NE", "p_trava_N", "k_prev_NE", "k_prev_N"]:
        _perto(cen[c], r7[c], 1e-9)
    for c in ["c_NE", "c_N", "perfil_h"]:
        _perto(np.vstack(cen[c]), np.vstack(r7[c]), 1e-9)
    ri = _r("R7_insumos")
    ins = pd.DataFrame([M.insumos_mes(b, d, pd.Period(m, "M"), mod) for m in ri["mes"]])
    _perto(ins[ri.columns[1:]], ri[ri.columns[1:]], 1e-3)
    x = M.projecao(b, d, pd.Series(200.0, index=meses), mod)
    fx = json.loads((Path(PASTA) / "R7_faixas_se200.json").read_text(encoding="utf-8"))
    for per in ("trimestre", "semestre", "ano"):
        a, r = M.faixa_periodos(x, per).reset_index(), pd.DataFrame(fx[per])
        assert a[per].tolist() == r[per].tolist()
        _perto(a.iloc[:, 1:], r.iloc[:, 1:], 0.01)
    ex = json.loads((Path(PASTA) / "R7_exemplo.json").read_text(encoding="utf-8"))
    t = M.faixa_periodos(x, "trimestre").loc[ex["periodo"]]
    assert [round(t.NE_justo, 2), round(t.NE_min, 2), round(t.NE_max, 2)] == [
        ex["NE_justo"],
        ex["NE_min"],
        ex["NE_max"],
    ]


# --- bloco 5: backtest da página (R9) --------------------------------------------------------------------


def test_R9_backtest_pagina(arm):
    r = _r("R9_backtest_pagina")
    a = ler_parquet(arm, chaves.PROC_BACKTEST)
    r = r.assign(
        cenario=r["cenario"].str.split("|").str[0]
    )  # na v2.2, o cenário é só o ano climático
    chave = ["deck", "mes", "cenario"]
    assert a[chave].astype(str).values.tolist() == r[chave].astype(str).values.tolist()
    num = [c for c in r.columns if c not in chave]
    _igual(a[num], r[num], 1e-9)


# --- blocos 3 e 4: dados da página (R8_dados) e rodadas (R10) --------------------------------------------


def test_R8_dados_da_pagina(arm, rodada):
    from qe_pricing_descolamento import publicacao as P

    _M, b, d, mod, _ = rodada
    r8 = json.loads((Path(PASTA) / "R8_dados.json").read_text(encoding="utf-8"))
    a = json.loads(json.dumps(P.dados(arm, d, r8["meta"]["rodada"], b, mod)))
    for m in r8["meses"]:
        for c in m["cen"]:
            c["id"] = c["id"].split("|")[0]  # na v2.2, o cenário é só o ano climático
    for k in ("meta", "sazonal_se", "historico", "meses"):
        assert a[k] == r8[k], k


@pytest.mark.parametrize("deck", ["2025-01", "2025-06", "2026-01", "2026-10"])
def test_R10_resumo_das_rodadas(rodada, deck):
    from qe_pricing_descolamento import publicacao as P

    M, b, _d, _mod, _ = rodada
    linha = next(
        x
        for x in json.loads(
            (Path(PASTA) / "R10_historico_rodadas.json").read_text(encoding="utf-8")
        )
        if x["deck"] == deck
    )
    d = pd.Period(deck, "M")
    x = P.resumo_rodada(b, d, M.treinar(b, d), linha["rodada"])
    x["reconstruida"] = linha["reconstruida"]
    assert json.loads(json.dumps(x)) == linha


# --- blocos 5 e 6: páginas de metodologia (desempenho) e fundamentos ----------------------------------------


def test_R8_metodologia_desempenho(arm, rodada):
    from qe_pricing_descolamento.desempenho import desempenho

    _M, b, _d, _mod, _ = rodada
    r = json.loads((Path(PASTA) / "R8_metodologia.json").read_text(encoding="utf-8"))
    a = json.loads(json.dumps(desempenho(b, ler_parquet(arm, chaves.PROC_BACKTEST))))
    assert a == r["desempenho"]


def test_R8_fundamentos(rodada):
    from qe_pricing_descolamento.fundamentos import dados_fundamentos

    _M, b, _d, _mod, _ = rodada
    r = json.loads((Path(PASTA) / "R8_fundamentos.json").read_text(encoding="utf-8"))
    assert json.loads(json.dumps(dados_fundamentos(b))) == r
