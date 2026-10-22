"""D040: o histórico de rodadas tem um degrau no deck em que o 1º semestre passa a ser treinado (regra do mínimo de 20 horas
por classe). A função só descreve; o modelo e as rodadas não mudam. Pulado sem os dados tratados."""

from pathlib import Path

import pandas as pd
import pytest

from qe_core.armazenamento import ArmazenamentoLocal
from qe_pricing_descolamento import chaves, publicacao
from qe_pricing_descolamento import modelo as M

DADOS = Path(__file__).resolve().parents[1] / "data"
pytestmark = pytest.mark.skipif(
    not (DADOS / chaves.PROC_BASE).exists(), reason="sem dados tratados localmente"
)


@pytest.fixture(scope="module")
def base():
    return M.Base(ArmazenamentoLocal(DADOS))


def test_marco_do_primeiro_semestre_em_abr25(base):
    historico = publicacao.carregar_registro(ArmazenamentoLocal(DADOS))
    marcos = publicacao.marcos_historico(base, historico)
    m = next(x for x in marcos if x["regime"] == "1S")
    assert (m["deck"], m["deck_antes"]) == ("2025-04", "2025-03")
    assert m["horas_antes"] < m["minimo"] <= m["horas"]  # 8 horas antes, 467 depois; mínimo 20
    assert m["minimo"] == M.MODELO.min_horas_classe and m["dados_ate"] == "2025-02"
    # o degrau é o do modelo: antes do marco o modelo do regime é vazio; no marco passa a existir
    antes = M.treinar(base, pd.Period(m["deck_antes"], "M"))
    depois = M.treinar(base, pd.Period(m["deck"], "M"))
    assert antes[("p", "1S", "NE")] is None and depois[("p", "1S", "NE")] is not None


def test_sem_historico_nao_ha_marco(base):
    assert publicacao.marcos_historico(base, []) == []
