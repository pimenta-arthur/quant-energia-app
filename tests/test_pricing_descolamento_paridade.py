"""Paridade com a pesquisa (opt-in): app × pacote de promoção do pricing-descolamento-analytics.

Conferência única da migração (docs/promocao_descolamento.md da pesquisa, seção 9). Só roda com
QE_PARIDADE_PRICING_DESCOLAMENTO=<pasta reports/promocao/AAAA-MM da pesquisa> e com o app tendo ingerido os mesmos
arquivos brutos (hashes no manifesto da pasta). Bloco 1: leitores (R1 a R3) e tabelas-base (R4, R5).
"""

import datetime as dt
import os
from pathlib import Path

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
