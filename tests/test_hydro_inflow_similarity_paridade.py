"""Paridade com a pesquisa (opt-in): app × pacote de promoção do hydro-inflow-similarity-analytics.

Conferência única da migração (docs/promocao_hydro_inflow_similarity.md da pesquisa, seção 9). Só roda com
QE_PARIDADE_HYDRO_INFLOW_SIMILARITY=<pasta reports/promocao/AAAA-MM da pesquisa> e com o app tendo ingerido os mesmos
arquivos brutos (hashes no manifesto da pasta). Conferidos em 2026-10-24 sem diferença: R1 (leitores), R3
(tabelas-base), R4 (modelo-v1, membros e ponto da PER), R5 (rodada, sem a sombra), R6 (atualização), R7 (similares e
desempenho), R8 (camada de El Niño forte) e R9 (dados das quatro páginas).
"""

import json
import os
from pathlib import Path

import pandas as pd
import pytest

from qe_core.armazenamento import ArmazenamentoLocal, ler_json, ler_parquet
from qe_hydro_inflow_similarity import chaves
from qe_hydro_inflow_similarity import modelo as M

PASTA = os.environ.get("QE_PARIDADE_HYDRO_INFLOW_SIMILARITY")
DADOS = Path(__file__).resolve().parents[1] / "data"
pytestmark = pytest.mark.skipif(not PASTA, reason="paridade com a pesquisa é opt-in")


@pytest.fixture(scope="module")
def arm():
    return ArmazenamentoLocal(DADOS)


@pytest.mark.parametrize("nome", ["ena_mensal", "mlt", "indices_mensais"])
def test_R3_tabelas_base(arm, nome):
    chave = {
        "ena_mensal": chaves.PROC_ENA,
        "mlt": chaves.PROC_MLT,
        "indices_mensais": chaves.PROC_INDICES,
    }[nome]
    pd.testing.assert_frame_equal(
        ler_parquet(arm, chave),
        pd.read_parquet(Path(PASTA) / f"R3_{nome}.parquet"),
        check_dtype=False,
        atol=1e-9,
    )


def test_R4_modelo_v1(arm):
    ena, ind = ler_parquet(arm, chaves.PROC_ENA), ler_parquet(arm, chaves.PROC_INDICES)
    emissao = json.loads((Path(PASTA) / "manifesto.json").read_text())["emissao"]
    d = pd.Timestamp(f"{emissao}-01")
    p = M.prever_v1(ena[ena.data <= d], ind[ind.index <= d], d)
    pd.testing.assert_frame_equal(
        p, pd.read_parquet(Path(PASTA) / "R4_modelo_v1.parquet"), check_dtype=False, atol=1e-9
    )


@pytest.mark.parametrize(
    ("app", "pesquisa"),
    [
        ("produto", "dados"),
        ("fundamentos", "dados_fundamentos"),
        ("metodologia", "dados_metodologia"),
        ("clima", "dados_clima"),
    ],
)
def test_R9_paginas(arm, app, pesquisa):
    a = ler_json(arm, chaves.serving(app))
    b = json.loads((Path(PASTA) / f"R9_{pesquisa}.json").read_text())
    for d in (a, b):
        d.pop("gerado_em", None)
        if d.get("atualizacao"):
            d["atualizacao"].pop("gerada_em", None)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
