"""Acompanhamento do nível da hidráulica do NE (D039): o nível que o modelo usa para um mês-alvo só depende de horas até
D−2 (o realizado, por definição, é posterior), e o acompanhamento não altera o modelo. Pulado sem os dados tratados."""

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


@pytest.fixture  # uma Base nova por teste: o teste altera as horas futuras
def base():
    return M.Base(ArmazenamentoLocal(DADOS))


def test_nivel_usado_nao_depende_do_futuro(base):
    m, d = pd.Period("2026-03", "M"), pd.Period("2026-02", "M")
    mod = M.treinar(base, d)
    ins = M.insumos_mes(base, d, m, mod)
    antes = M.cenarios(base, d, m, ins)[0][0]
    futuro = base.h.index >= (d - 1).to_timestamp()  # a partir do início de D−1: depois de D−2
    base.h.loc[futuro, "hidraulica_NE"] = 1e5
    depois = M.cenarios(base, d, m, ins)[0][0]
    assert antes["hidraulica_NE"] == depois["hidraulica_NE"]
    assert antes["ano_hidr_ne"] == depois["ano_hidr_ne"]


def test_cenarios_iguais_em_todos_os_cenarios_e_resumo_coerente(base):
    d = pd.Period("2026-10", "M")
    mod = M.treinar(base, d)
    m = pd.Period("2026-12", "M")
    cen = M.prever(base, d, m, 200.0, mod)
    # mesmo perfil em todos os cenários (o nível pode diferir na última casa: cenários com menos dias somam em outra ordem)
    assert cen["hidraulica_NE"].max() - cen["hidraulica_NE"].min() < 1e-6
    assert cen["ano_hidr_ne"].nunique() == 1
    a = publicacao.acompanhamento_hidr_ne(base)
    assert a["resumo"]["n"] == len(a["linhas"]) > 0
    assert (
        a["gatilho_pct"] == publicacao.GATILHO_HIDR_NE and a["janela"] == publicacao.JANELA_HIDR_NE
    )
    assert all(
        x["deck"] == str(pd.Period(x["mes"], "M") - 1) for x in a["linhas"]
    )  # deck do mês anterior
