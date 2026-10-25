"""Projeção de ENA e anos similares: o estado atual de raw/ e processed/ reproduz as referências congeladas (só
períodos que não mudam com dados novos). Pulado sem os dados tratados locais."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from qe_core.armazenamento import ArmazenamentoLocal, ler_parquet
from qe_hydro_inflow_similarity import chaves, referencias
from qe_hydro_inflow_similarity import modelo as M

RAIZ = Path(__file__).resolve().parents[1]
DADOS = RAIZ / "data"
REFS = RAIZ / "tests" / "referencias"
com_dados = pytest.mark.skipif(
    not (DADOS / chaves.PROC_BACKTEST).exists(), reason="sem dados tratados localmente"
)


@com_dados
def test_iguais_as_referencias_congeladas():
    ref = referencias.ler_congeladas(REFS)
    app = referencias.calcular(ArmazenamentoLocal(DADOS))
    assert set(app) == set(ref)
    for nome, r in ref.items():
        pd.testing.assert_frame_equal(
            app[nome].reset_index(drop=True),
            r.reset_index(drop=True),
            check_dtype=False,
            check_names=False,
            obj=nome,
        )


@com_dados
def test_se_e_a_soma_dos_blocos():
    """A anomalia do SE em GWmed é a soma das dos blocos (SPLIT, membro a membro pelo mesmo ano)."""
    arm = ArmazenamentoLocal(DADOS)
    ena, ind = ler_parquet(arm, chaves.PROC_ENA), ler_parquet(arm, chaves.PROC_INDICES)
    p = M.prever_v1(ena, ind, "2025-09-01", h_max=6).set_index(["nome", "h"]).anomalia_gw.unstack(0)
    np.testing.assert_allclose(p["SE"], p["SE-sul"] + p["SE-resto"], atol=1e-9)


def test_sem_vazamento():
    """O modelo-v1 emitido em t não muda se tudo depois de t for apagado."""
    rng = np.random.default_rng(0)
    n = 95 * 12
    pct = 100 * np.exp(rng.normal(0, 0.3, n))
    s = M.Serie("X", pct, np.zeros(n))
    t = 80 * 12 + 8
    corte = M.Serie("X", np.where(np.arange(n) <= t, pct, np.nan), np.zeros(n))
    for h in (1, 6, 18):
        np.testing.assert_allclose(M.membros_per(s, t, h), M.membros_per(corte, t, h))
