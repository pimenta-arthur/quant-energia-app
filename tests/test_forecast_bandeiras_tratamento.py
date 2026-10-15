"""Tratamento: resultados iguais às referências congeladas em tests/referencias/forecast_bandeiras/tratamento/.

As referências foram geradas pelo app e, na migração (2026-10-09), conferidas contra o
forecast-bandeiras-analytics (base mensal idêntica nos 46 meses, ENA do deck de set/2026 idêntica
série a série). Mais meses no histórico mudam a base mensal de propósito: regere com
`uv run qe forecast_bandeiras congelar` e revise a diferença no git.
"""

import math
from pathlib import Path

import pytest

from qe_core.armazenamento import ArmazenamentoLocal, ler_parquet
from qe_forecast_bandeiras import chaves, referencias, tratamento

RAIZ = Path(__file__).resolve().parent / "referencias" / "forecast_bandeiras"
DADOS = Path(__file__).resolve().parents[1] / "data"

pytestmark = pytest.mark.skipif(
    not (DADOS / "processed").exists() or not (RAIZ / "tratamento").exists(),
    reason="sem dados tratados localmente ou sem referências do tratamento",
)


@pytest.fixture(scope="module")
def arm():
    return ArmazenamentoLocal(DADOS)


@pytest.fixture(scope="module")
def atual(arm):
    return referencias.calcular_tratamento(arm)


@pytest.fixture(scope="module")
def congelado():
    import json

    pasta = RAIZ / "tratamento"
    return {a.stem: json.loads(a.read_text(encoding="utf-8")) for a in pasta.glob("*.json")}


def _igual(a, b, caminho):
    if isinstance(a, dict):
        assert set(a) == set(b), f"{caminho}: chaves {set(a) ^ set(b)}"
        for k in a:
            _igual(a[k], b[k], f"{caminho}.{k}")
    elif isinstance(a, list):
        assert len(a) == len(b), f"{caminho}: {len(a)} × {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            _igual(x, y, f"{caminho}[{i}]")
    elif isinstance(a, float) and isinstance(b, float):
        assert math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9), f"{caminho}: {a} × {b}"
    else:
        assert a == b, f"{caminho}: {a!r} × {b!r}"


@pytest.mark.parametrize("parte", ["base_mensal", "deck_ena_sin"])
def test_igual_a_referencia(atual, congelado, parte):
    _igual(atual[parte], congelado[parte], parte)


def test_gsf_reproduz_boletim(arm):
    base = tratamento.base_mensal(arm)
    assert (base.gsf_calc.round(2) == base.gsf_band_boletim.round(2)).all()


def test_ecmwf_emissao_set26(arm):
    est = ler_parquet(arm, chaves.proc_ecmwf("2026-09-01", "estatisticas"))
    mem = ler_parquet(arm, chaves.proc_ecmwf("2026-09-01", "membros"))
    assert mem.membro.nunique() == 51
    av = est.query("estatistica == 'av' and abordagem == 'precip'")
    assert set(av.subsistema) == {"SE", "S", "NE", "N"}
    assert av.alvo.min() == "2026-09" and av.alvo.max() == "2027-03"


def test_historico_aneel(arm):
    h = ler_parquet(arm, chaves.PROC_HISTORICO)
    assert h.mes.min() == "2015-01"
    assert "Escassez hídrica" in set(h.cor)
