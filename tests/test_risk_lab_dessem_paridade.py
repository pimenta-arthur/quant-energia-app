"""Paridade com a pesquisa (opt-in): app × pacote de promoção do risk-lab-dessem-analytics.

Conferência única da migração (docs/promocao_pld_horario.md da pesquisa, seção 9). Só roda com
QE_PARIDADE_RISK_LAB_DESSEM=<pasta reports/promocao/AAAA-MM-DD da pesquisa> e com o app tendo ingerido
os mesmos arquivos brutos (decks até a data da pasta, PLD publicado até a data do manifesto): com
mais dias, as chaves de "últimos N meses" e o mês corrente mudam. Os períodos fechados (R1 a R7)
não mudam e são os que ficam congelados em tests/referencias/risk_lab_dessem/. Desde a leva promocao-quant-v3
(pasta 2026-10-15_v3), também o exemplo do simulador (R9), o resumo para a mesa (R10) e os dias do mês (R11), com
tolerância de R$ 0,01.
"""

import json
import os
from pathlib import Path

import pandas as pd
import pytest

from qe_core.armazenamento import ArmazenamentoLocal, ler_parquet
from qe_risk_lab_dessem import chaves, publicacao, referencias

PASTA = os.environ.get("QE_PARIDADE_RISK_LAB_DESSEM")
DADOS = Path(__file__).resolve().parents[1] / "data"

pytestmark = pytest.mark.skipif(not PASTA, reason="paridade com a pesquisa é opt-in")


@pytest.fixture(scope="module")
def arm():
    return ArmazenamentoLocal(DADOS)


@pytest.fixture(scope="module")
def app(arm):
    return referencias.calcular(arm)


def _r(nome: str) -> pd.DataFrame:
    return pd.read_parquet(Path(PASTA) / f"{nome}.parquet")


def _norm(df: pd.DataFrame, chave: list[str]) -> pd.DataFrame:
    df = df.copy()
    for c in df.columns:
        if df[c].dtype == object and len(df) and hasattr(df[c].iloc[0], "isoformat"):
            df[c] = pd.to_datetime(df[c])
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = df[c].astype("datetime64[ns]")
        elif pd.api.types.is_string_dtype(df[c]):
            df[c] = df[c].astype(object)
    return df.sort_values(chave).reset_index(drop=True)


def _igual(app: pd.DataFrame, ref: pd.DataFrame, chave: list[str], atol: float = 0.0):
    assert sorted(app.columns) == sorted(ref.columns)
    a, r = _norm(app[ref.columns], chave), _norm(ref, chave)
    pd.testing.assert_frame_equal(a, r, check_dtype=False, atol=atol, rtol=0)


def test_R1_ler_pdo_sist(app):
    _igual(app["leitor_pdo_sist"], _r("R1_ler_pdo_sist"), ["data", "periodo", "submercado"])


def test_R2_decomp_cmo(app):
    _igual(
        app["decomp_cmo"], _r("R2_decomp_cmo"), ["pmo", "sem", "estagio", "submercado", "patamar"]
    )


def test_R3_ler_renovaveis(app):
    k = ["data", "periodo", "submercado", "tipo"]
    _igual(app["leitor_renovaveis"], _r("R3_ler_renovaveis"), k, atol=0.001)


def test_R4_pld_horario(arm):
    t1 = ler_parquet(arm, chaves.PROC_PLD)
    a = pd.concat([referencias._no_periodo(t1), t1[t1["origem"] != "publicado"]])
    _igual(a, _r("R4_pld_horario"), ["data", "hora", "submercado"], atol=0.01)


def test_R5_mensal_horario(app):
    _igual(app["mensal_horario"], _r("R5_mensal_horario"), ["data", "hora", "submercado"], 1e-4)


def test_R6_tipos_de_dia(arm):
    _igual(ler_parquet(arm, chaves.PROC_TIPOS), _r("R6_tipos_de_dia"), ["data"])


def test_R7_mensal_delta(app):
    _igual(app["mensal_delta"], _r("R7_mensal_delta"), ["mes", "submercado"], atol=0.01)


def test_R8_bloco1(arm):
    ref = json.loads((Path(PASTA) / "R8_bloco1_nivel.json").read_text(encoding="utf-8"))
    d = publicacao.dados(arm)
    for k in ref:
        assert d[k] == ref[k], k


def test_R8_blocos_2_e_5(arm):
    d = publicacao.dados(arm)
    for nome in ("R8_bloco2_desvio.json", "R8_bloco2_5_horas.json"):
        ref = json.loads((Path(PASTA) / nome).read_text(encoding="utf-8"))
        for k in ref:
            assert d[k] == ref[k], k


def test_R8_blocos_3_e_4(arm):
    d = publicacao.dados(arm)
    for nome in ("R8_bloco3_perfil_dia.json", "R8_bloco4_perfis.json"):
        ref = json.loads((Path(PASTA) / nome).read_text(encoding="utf-8"))
        for k in ref:
            assert d[k] == ref[k], k


def test_R8_bloco6(arm):
    ref = json.loads((Path(PASTA) / "R8_bloco6_mecanismos.json").read_text(encoding="utf-8"))
    assert publicacao.mecanismos_se(arm, publicacao._tipos(arm)) == ref["mecanismos_se"]


def test_R8_bloco7_e_R9_backtest(arm):
    from qe_risk_lab_dessem import chaves

    ref = json.loads((Path(PASTA) / "R8_bloco7_simulador.json").read_text(encoding="utf-8"))
    manifesto = json.loads((Path(PASTA) / "manifesto.json").read_text(encoding="utf-8"))
    d = json.loads(json.dumps(publicacao.dados_simulador(arm, manifesto["decks_dessem_ate"])))
    for k in ref:
        assert d[k] == ref[k], k
    bt = ler_parquet(arm, chaves.PROC_BACKTEST)
    r = pd.read_parquet(Path(PASTA) / "R9_backtest_v1s.parquet")
    _igual(bt, r.drop(columns="versao"), ["mes", "h"], atol=0.01)


def _perto(a, b, cam="", tol=0.01):
    if isinstance(b, dict):
        assert set(a) == set(b), (cam, set(a) ^ set(b))
        for k in b:
            _perto(a[k], b[k], f"{cam}.{k}", tol)
    elif isinstance(b, list):
        assert len(a) == len(b), cam
        for i, (x, y) in enumerate(zip(a, b)):
            _perto(x, y, f"{cam}[{i}]", tol)
    elif isinstance(a, float) or isinstance(b, float):
        assert abs(a - b) <= tol, (cam, a, b)
    else:
        assert a == b, (cam, a, b)


def test_R9_exemplo_do_simulador(arm):
    from qe_risk_lab_dessem import simulador as S

    ref = json.loads((Path(PASTA) / "R9_simulador_exemplo.json").read_text(encoding="utf-8"))
    b = S.Base(arm)
    o = pd.Timestamp(ref["origem"])
    pr = S.premissas_na_origem(b, o)
    c = next(x for x in S.calendario(b, o) if x["mes"] == ref["mes_alvo"])
    D, P = ref["decomp_digitado"], ref["piso"]
    assert c["piso"] == P
    for t, p in ref["premissas"].items():
        _perto({k: pr[t][k] for k in p}, p, t)
    for t, dt in ref["dia_tipico"].items():
        _perto(S.dia_s(pr[t], D, P), dt, t)
    assert abs(S.prever_mes(pr, c, D) - ref["pld_previsto"]) <= 0.01


@pytest.fixture(scope="module")
def pagina(arm):
    manifesto = json.loads((Path(PASTA) / "manifesto.json").read_text(encoding="utf-8"))
    d = publicacao.dados(arm) | publicacao.dados_simulador(arm, manifesto["decks_dessem_ate"])
    return json.loads(json.dumps(d))  # como a página lê (chaves em texto)


def test_R10_resumo_e_R11_dias_do_mes(pagina):
    from qe_risk_lab_dessem import simulador as S

    r10 = json.loads((Path(PASTA) / "R10_resumo_mesa.json").read_text(encoding="utf-8"))
    r11 = json.loads((Path(PASTA) / "R11_dias_mes.json").read_text(encoding="utf-8"))
    for ref, ref_dias in zip(r10, r11):
        c, prem, premio, ps = S.estado_padrao(pagina, ref["mes"], ref["decomp"])
        pct = ref["sensibilidade"]["pct_dias_uteis"]
        res = S.resumo_mesa(pagina, c, ref["decomp"], prem, premio, ps, pct)
        _perto(res, ref, f"R10 {ref['decomp']}")
        dias = S.dias_mes(c, ref["decomp"], prem, premio, ps, pct)
        _perto(dias, ref_dias["dias"], f"R11 {ref['decomp']}")
        n = len(dias)
        assert abs(sum(x["pld_dia"] for x in dias) / n - ref_dias["media_pld_dia"]) <= 0.01
        assert abs(ref_dias["media_pld_dia"] - ref_dias["pld_previsto"]) <= 0.01
