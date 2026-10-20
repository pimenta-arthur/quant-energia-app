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


@com_dados
def test_coeficientes_reproduzem_o_modelo():
    """d = −Σ_h c_h · max(SE · perfil_h − piso, 0) é a média horária do modelo para qualquer SE (a página usa só os
    coeficientes)."""
    from qe_pricing_descolamento import modelo as M

    b = M.Base(ArmazenamentoLocal(DADOS))
    d = pd.Period("2026-10", "M")
    mod = M.treinar(b, d)
    for m in (pd.Period("2026-12", "M"), pd.Period("2027-03", "M"), pd.Period("2027-08", "M")):
        for se in (40.0, 150.0, 420.0):
            for r in M.prever(b, d, m, se, mod).itertuples():
                folga = [max(se * ph - r.piso, 0.0) for ph in r.perfil_h]
                for s in M.SUBS:
                    c = getattr(r, f"c_{s}")
                    assert -sum(ci * fi for ci, fi in zip(c, folga)) == pytest.approx(
                        getattr(r, f"d_{s}"), abs=1e-9
                    )
