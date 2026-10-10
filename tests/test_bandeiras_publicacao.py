"""Aceitação da projeção e da publicação: os dados da página gerados pela aplicação para a rodada de
set/2026 têm de ser iguais aos publicados pelo forecast-bandeiras-analytics
(reports/pagina/produto_dados.js), exceto datas de geração.

Precisa de `qe bandeiras backtest`, `projetar --mes 2026-09` e `publicar --mes 2026-09` já rodados.
"""

import json
import math
import os
from pathlib import Path

import pytest

ANALYTICS = Path(
    os.environ.get("QE_ANALYTICS", Path(__file__).resolve().parents[2] / "forecast-bandeiras")
)
APP = Path(__file__).resolve().parents[1] / "data/serving/bandeiras/produto_dados.js"
REF = ANALYTICS / "reports/pagina/produto_dados.js"

pytestmark = pytest.mark.skipif(
    not (APP.exists() and REF.exists()), reason="sem dados publicados da aplicação ou do analytics"
)
IGNORAR = {"gerado_em", "publicada_em"}


def _ler(caminho: Path) -> dict:
    texto = caminho.read_text(encoding="utf-8")
    return json.loads(texto[texto.index("=") + 1 : texto.rstrip().rindex(";")])


def _comparar(a, b, caminho="dados"):
    if isinstance(a, dict):
        assert isinstance(b, dict), caminho
        chaves_a, chaves_b = set(a) - IGNORAR, set(b) - IGNORAR
        assert chaves_a == chaves_b, f"{caminho}: chaves {chaves_a ^ chaves_b}"
        for k in chaves_a:
            _comparar(a[k], b[k], f"{caminho}.{k}")
    elif isinstance(a, list):
        assert isinstance(b, list) and len(a) == len(b), f"{caminho}: tamanhos {len(a)} × {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            _comparar(x, y, f"{caminho}[{i}]")
    elif isinstance(a, float) or isinstance(b, float):
        assert math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-6), f"{caminho}: {a} × {b}"
    else:
        assert a == b, f"{caminho}: {a!r} × {b!r}"


@pytest.fixture(scope="module")
def dados():
    return _ler(APP), _ler(REF)


@pytest.mark.parametrize(
    "parte",
    [
        "projecoes",
        "insumos",
        "selecao",
        "calculo_gsf_cenarios",
        "historico",
        "desempenho",
        "rodadas",
        "adicional_vigente",
        "fatores",
        "pld_min",
        "pld_max",
        "limites_x",
        "deck",
    ],
)
def test_parte_igual_ao_analytics(dados, parte):
    app, ref = dados
    _comparar(app[parte], ref[parte], parte)
