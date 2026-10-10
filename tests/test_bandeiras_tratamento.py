"""Aceitação do tratamento de bandeiras: os dados tratados pela aplicação têm de bater com os do
forecast-bandeiras-analytics (repositório de pesquisa, onde o método foi validado).

Precisam dos dados já ingeridos e tratados em ./data e do analytics em QE_ANALYTICS
(padrão: ../forecast-bandeiras). Sem eles, os testes são pulados.
"""

import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from qe_bandeiras import chaves, insumos, tratamento
from qe_core.armazenamento import ArmazenamentoLocal, ler_parquet

ANALYTICS = Path(
    os.environ.get("QE_ANALYTICS", Path(__file__).resolve().parents[2] / "forecast-bandeiras")
)
DADOS = Path(__file__).resolve().parents[1] / "data"

pytestmark = pytest.mark.skipif(
    not (ANALYTICS / "data/processed/base_mensal.parquet").exists()
    or not (DADOS / "processed").exists(),
    reason="sem analytics ou sem dados tratados localmente",
)


@pytest.fixture(scope="module")
def arm():
    return ArmazenamentoLocal(DADOS)


@pytest.fixture(scope="module")
def ref():
    base = pd.read_parquet(ANALYTICS / "data/processed/base_mensal.parquet")
    base.index = base.index.to_period("M")
    return base


def test_base_mensal_igual_ao_analytics(arm, ref):
    app = tratamento.base_mensal(arm)
    comum = app.index.intersection(ref.index)
    assert len(comum) == len(ref) == 46
    numericas = [
        "gh_ons",
        "ande",
        "gh_band",
        "carga_bruta",
        "mmgd",
        "termica",
        "pch",
        "ena_sin",
        "ena_mlt_sin",
        "ear_ini_sin",
        "gf_band_boletim",
        "gsf_band_boletim",
        "pld_gatilho_boletim",
        "pld_min_boletim",
        "pld_max_boletim",
        "gsf_calc",
    ]
    for c in numericas:
        np.testing.assert_allclose(
            app.loc[comum, c].astype(float),
            ref.loc[comum, c].astype(float),
            rtol=1e-9,
            atol=1e-9,
            err_msg=c,
        )
    assert (app.loc[comum, "cor_regra"] == ref.loc[comum, "cor_regra"]).all()


def test_gsf_reproduz_boletim(arm):
    app = tratamento.base_mensal(arm)
    assert (app.gsf_calc.round(2) == app.gsf_band_boletim.round(2)).all()


def test_newave_deck_set26(arm):
    m = pd.Period("2026-09", "M")
    ena = ler_parquet(arm, chaves.proc_newave(m, insumos.versao_atual(arm, m), "ena"))
    assert ena.serie.nunique() == 2000
    sin = ena[ena.periodo == "2026-10"].groupby("serie").valor.sum()
    # mesma leitura do analytics: ENA do SIN por série no primeiro mês após o deck
    import sys

    sys.path.insert(0, str(ANALYTICS / "src"))
    from forecast_bandeiras import newave as nw_ref

    pasta = ANALYTICS / "data/raw/ccee_newave/2026/2026_09"
    ref = sum(
        nw_ref.ler_nwlistop(pasta / f"eafbm00{i}.out")
        .query("ano == 2026 and mes == 10")
        .set_index("serie")
        .valor
        for i in range(1, 5)
    )
    np.testing.assert_allclose(sin.sort_index(), ref.sort_index())


def test_ecmwf_rodada_set26(arm):
    m = pd.Period("2026-09", "M")
    est = ler_parquet(arm, chaves.proc_ecmwf(f"{m}-01", "estatisticas"))
    mem = ler_parquet(arm, chaves.proc_ecmwf(f"{m}-01", "membros"))
    assert mem.membro.nunique() == 51
    av = est.query("estatistica == 'av' and abordagem == 'precip'")
    assert set(av.subsistema) == {"SE", "S", "NE", "N"}
    assert av.alvo.min() == "2026-09" and av.alvo.max() == "2027-03"


def test_historico_aneel(arm):
    h = ler_parquet(arm, chaves.PROC_HISTORICO)
    assert h.mes.min() == "2015-01"
    assert "Escassez hídrica" in set(h.cor)
