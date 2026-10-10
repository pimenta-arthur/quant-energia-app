"""Resultados do modelo em uso iguais às referências congeladas (tests/referencias/<versão>/).

Falhou? Se a mudança foi sem querer, corrija o código. Se foi intencional (dados novos no histórico
ou versão nova do modelo), rode `uv run qe bandeiras congelar`, revise a diferença no git e
registre a decisão no analytics.
"""

import math
from pathlib import Path

import pytest

from qe_bandeiras import modelo, referencias
from qe_core.armazenamento import ArmazenamentoLocal

RAIZ = Path(__file__).resolve().parent / "referencias"
DADOS = Path(__file__).resolve().parents[1] / "data"

pytestmark = pytest.mark.skipif(
    not (DADOS / "processed").exists() or not referencias.pasta(RAIZ).exists(),
    reason="sem dados tratados localmente ou sem referências da versão em uso",
)


@pytest.fixture(scope="module")
def atual():
    return referencias.calcular(ArmazenamentoLocal(DADOS))


@pytest.fixture(scope="module")
def congelado():
    return referencias.carregar(RAIZ)


def _igual(a, b, caminho):
    if isinstance(a, dict):
        assert set(a) == set(b), f"{caminho}: chaves {set(a) ^ set(b)}"
        for k in a:
            _igual(a[k], b[k], f"{caminho}.{k}")
    elif isinstance(a, list):
        assert len(a) == len(b), f"{caminho}: {len(a)} × {len(b)} linhas"
        for i, (x, y) in enumerate(zip(a, b)):
            _igual(x, y, f"{caminho}[{i}]")
    elif isinstance(a, float) and isinstance(b, float):
        assert math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9), f"{caminho}: {a} × {b}"
    else:
        assert a == b, f"{caminho}: {a!r} × {b!r}"


@pytest.mark.parametrize(
    "parte", ["modelo", "backtest", "oraculo", "rodadas", "projecao_referencia"]
)
def test_igual_a_referencia(atual, congelado, parte):
    assert congelado["modelo"]["versao"] == modelo.MODELO.versao
    _igual(atual[parte], congelado[parte], parte)
