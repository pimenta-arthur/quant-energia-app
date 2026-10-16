"""Tratamento do PLD horário: regra do PLD e resultados iguais às referências congeladas.

As referências (tests/referencias/risk_lab_dessem/) foram geradas pelo app e, na migração
(2026-10-14), conferidas contra o pacote de promoção da pesquisa (test_risk_lab_dessem_paridade.py).
Só cobrem períodos fechados, então decks novos não as mudam. Os testes com dados reais são
pulados quando não há data/processed local.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from qe_core.armazenamento import ArmazenamentoLocal
from qe_risk_lab_dessem import referencias, tratamento

RAIZ = Path(__file__).resolve().parent / "referencias"
DADOS = Path(__file__).resolve().parents[1] / "data"

com_dados = pytest.mark.skipif(
    not (DADOS / "processed" / "risk_lab_dessem").exists()
    or not (RAIZ / referencias.PASTA).exists(),
    reason="sem dados tratados localmente ou sem referências",
)

# tolerâncias do pacote de promoção (seção 9)
TOLERANCIA = {
    "leitor_renovaveis": 0.001,
    "pld_horario": 0.01,
    "mensal_horario": 1e-4,
    "mensal_delta": 0.01,
    "bloco7_backtest": 0.01,
}
CHAVES = {
    "leitor_pdo_sist": ["data", "periodo", "submercado"],
    "leitor_renovaveis": ["data", "periodo", "submercado", "tipo"],
    "decomp_cmo": ["pmo", "sem", "estagio", "submercado", "patamar"],
    "pld_horario": ["data", "hora", "submercado"],
    "mensal_horario": ["data", "hora", "submercado"],
    "tipos_de_dia": ["data"],
    "mensal_delta": ["mes", "submercado"],
    "bloco1_dias_nivel": ["sub", "data"],
    "bloco2_desvio_mensal": ["sub", "mes"],
    "bloco5_horas": ["sub", "mes", "tipo", "hora"],
    "bloco4_perfis": ["var", "sub", "mes", "hora"],
    "bloco4_indicadores": ["sub", "periodo", "ano"],
    "bloco6_mecanismos": ["mes"],
    "bloco7_backtest": ["mes", "h"],
}


# --- regra do PLD (sintético) -----------------------------------------------------------------------


def _dia(cmos: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {"data": pd.Timestamp("2026-10-01"), "hora": range(24), "submercado": "SE", "cmo": cmos}
    )


def test_piso_e_teto_horario():
    pld = tratamento.pld_a_partir_do_cmo(_dia([10.0] * 12 + [2000.0] * 12), 57.31, 1611.04, 1000)
    assert pld.iloc[0] == 57.31 and pld.iloc[-1] == 1611.04


def test_teto_estrutural_iterativo_mantem_media_no_teto_e_piso():
    cmos = [57.31] * 8 + [1500.0] * 16
    pld = tratamento.pld_a_partir_do_cmo(_dia(cmos), 57.31, 1611.04, 785.27)
    assert abs(pld.mean() - 785.27) < 1e-6
    assert (pld >= 57.31 - 1e-9).all() and pld.iloc[0] == 57.31


def test_soma_dos_blocos_e_o_desvio_do_mes():
    h = pd.DataFrame(
        {
            "data": pd.date_range("2026-10-01", periods=48, freq="h").normalize(),
            "hora": list(range(24)) * 2,
            "submercado": "SE",
            "pld_dessem": np.linspace(57.31, 300, 48),
            "decomp_pld": 100.0,
            "decomp_cmo": 100.0,
            "piso": 57.31,
            "mes": "2026-10",
        }
    )
    h["bloco"] = tratamento._bloco(h["hora"])
    t = tratamento.delta_mes_civil(h).iloc[0]
    assert abs(t.delta_vale + t.delta_ponta + t.delta_resto - t.delta) < 1e-9
    assert not t.completo  # 2 de 31 dias


# --- dados reais ------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def arm():
    return ArmazenamentoLocal(DADOS)


@com_dados
def test_iguais_as_referencias_congeladas(arm):
    atual = referencias.calcular(arm)
    congelado = referencias.ler_congeladas(RAIZ)
    assert set(atual) == set(congelado)
    for nome, ref in congelado.items():
        a = atual[nome][ref.columns].sort_values(CHAVES[nome]).reset_index(drop=True)
        r = ref.sort_values(CHAVES[nome]).reset_index(drop=True)
        pd.testing.assert_frame_equal(
            a, r, check_dtype=False, atol=TOLERANCIA.get(nome, 0.0), rtol=0, obj=nome
        )


@com_dados
def test_pld_calculado_do_deck_confere_com_o_publicado(arm):
    """Lacuna L4 da pesquisa: o recálculo foi conferido lá só em 10 dias; aqui, nos últimos 30."""
    sist = tratamento.ler_dessem(arm, "sist", ["data", "periodo", "submercado", "cmo"])
    dif, datas = tratamento.conferir_calculo(
        tratamento.pld_publicado(arm), sist, tratamento.limites(arm), dias=30
    )
    assert len(datas) == 30 and len(dif) == 30 * 24 * 4
    assert dif.max() <= 0.0100001


@com_dados
def test_contribuicao_soma_o_desvio_medio_do_periodo(arm):
    """D067: a soma das células (tipo de dia × faixa) dá o desvio médio do período."""
    from qe_risk_lab_dessem import publicacao

    h = publicacao._horario(arm)
    hr = publicacao.horas(h, publicacao._tipos(arm))
    c = publicacao.contribuicao(hr, [2024, 2025, 2026])
    for sub in ("SE", "NE"):
        for per in ("ultimo", "3m", "a2025"):
            x = h[(h["submercado"] == sub) & h["mes"].isin(c[sub][per]["meses"])]
            esperado = (x["pld_dessem"] - x["decomp_pld"]).mean()
            # a soma do desvio por hora sai arredondada a 1 casa no `horas` (como na pesquisa)
            assert abs(c[sub][per]["total"] - esperado) < 0.05


def test_calor_percentis_como_no_navegador():
    """Percentil por índice arredondado (Math.round do JS): com 101 valores, p5 = 5º e p95 = 95º."""
    from qe_risk_lab_dessem import publicacao

    pdia = {"pld": {"SE": {"2026-10": {"dias": [], "tipos": [], "v": [list(range(101))]}}}}
    c = publicacao.calor(pdia)["pld"]["SE"]["2026-10"]
    assert (c["lo"], c["hi"], c["mes"]) == (5, 95, 50)
    # 0,5 arredonda para cima, como Math.round (o round do Python arredondaria para o par)
    assert publicacao._percentil_js([1.0, 2.0, 3.0, 4.0], 0.5) == 3.0


@com_dados
def test_sin_soma_os_quatro_submercados_so_nas_horas_com_os_quatro(arm):
    """D084: SIN = soma dos quatro submercados hora a hora, só nas variáveis em MW e só nas horas em que
    os quatro existem. Exemplo do pacote: carga líquida em 01/10/2026 às 19h = 75.583,4 MW."""
    s = tratamento.series_horarias(arm)
    assert "SIN" not in set(s["pld"]["submercado"]) | set(s["decomp"]["submercado"])
    cl = s["carga_liquida"]
    x = cl[(cl["data"] == "2026-10-01") & (cl["hora"] == 19)].set_index("submercado")["v"]
    assert x["SIN"] == pytest.approx(x[["SE", "S", "NE", "N"]].sum())
    assert x["SIN"] == pytest.approx(75583.4, abs=0.05)
    for v in tratamento.VARIAVEIS_MW:
        y = s[v]
        n = y[y["submercado"] != "SIN"].groupby(["data", "hora"]).size()
        assert len(y[y["submercado"] == "SIN"]) == int((n == 4).sum())
