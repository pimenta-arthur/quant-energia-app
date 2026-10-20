"""Descolamento NE e N, bloco 1 (tabelas-base): o estado atual de raw/ e processed/ reproduz as referências
congeladas (períodos fechados). Pulado sem os dados tratados locais."""

from pathlib import Path

import pandas as pd
import pytest

from qe_core.armazenamento import ArmazenamentoLocal
from qe_pricing_descolamento import chaves, referencias

RAIZ = Path(__file__).resolve().parents[1]
DADOS = RAIZ / "data"
REFS = RAIZ / "tests" / "referencias"
com_dados = pytest.mark.skipif(
    not (DADOS / chaves.PROC_BASE).exists(), reason="sem dados tratados localmente"
)


@com_dados
def test_iguais_as_referencias_congeladas():
    ref = referencias.ler_congeladas(REFS)
    app = referencias.calcular(ArmazenamentoLocal(DADOS))
    assert set(app) == set(ref)
    for nome, r in ref.items():
        pd.testing.assert_frame_equal(app[nome], r, check_dtype=False, check_names=False, obj=nome)
