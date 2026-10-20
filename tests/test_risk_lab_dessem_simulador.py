"""Simulador do PLD médio do mês (bloco 7): paridade Python × JS da conta e exemplo de referência.

A conta do dia típico roda no navegador (o usuário digita o DECOMP), em
web/risk_lab_dessem/simulador_conta.js, e no Python (qe_risk_lab_dessem.simulador). O teste de paridade
roda o mesmo arquivo da página com node em cenários aleatórios e, para o resumo para a mesa (D091) e os dias do
mês (D095), sobre as chaves publicadas em data/serving/; é pulado sem node. O exemplo da origem 25/09/2026 (RV0 de
out/2026) é o conferido à mão no pacote de promoção da pesquisa (seção 9, leva promocao-quant-v3).
"""

import json
import random
import shutil
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from qe_core.armazenamento import ArmazenamentoLocal
from qe_risk_lab_dessem import simulador as S
from qe_risk_lab_dessem.modelo import TIPOS_DIA

RAIZ = Path(__file__).resolve().parents[1]
CONTA_JS = RAIZ / "web" / "risk_lab_dessem" / "simulador_conta.js"
DADOS = RAIZ / "data"
SERVING = DADOS / "serving" / "risk_lab_dessem"
sem_node = pytest.mark.skipif(shutil.which("node") is None, reason="sem node")
com_dados = pytest.mark.skipif(
    not (DADOS / "processed" / "risk_lab_dessem").exists(), reason="sem dados tratados localmente"
)


def _cenarios(n: int = 2000) -> list[dict]:
    rnd = random.Random(20261014)
    out = []
    for _ in range(n):
        partes = [rnd.random() for _ in range(3)]
        if rnd.random() < 0.1:
            partes[rnd.randrange(3)] = 0.0  # mês sem um dos tipos de dia
        tot = sum(partes) or 1.0
        out.append(
            {
                "D": rnd.choice([rnd.uniform(0, 80), rnd.uniform(50, 800)]),
                "c": {
                    "piso": rnd.choice([57.31, 58.6, 61.07]),
                    "parte_util": partes[0] / tot,
                    "parte_sabado": partes[1] / tot,
                    "parte_domingo": partes[2] / tot,
                },
                "prem": {
                    t: {
                        "horas_piso": rnd.uniform(-1, 9),
                        "frac_fora": rnd.uniform(-1.2, 0.5),
                        "premio_ponta": rnd.uniform(-100, 900),
                    }
                    for t in TIPOS_DIA
                },
            }
        )
    return out


def _python(cen: dict) -> dict:
    partes = {"útil": "parte_util", "sábado": "parte_sabado", "domingo/feriado": "parte_domingo"}
    c, D = cen["c"], cen["D"]
    tipos = {t: S.dia_s(cen["prem"][t], D, c["piso"]) for t, col in partes.items() if c[col]}
    return {
        "pld": S.prever_mes(cen["prem"], c, D),
        "tipos": {t: [v["pld"], v["vale_piso"], v["fora"], v["ponta"]] for t, v in tipos.items()},
    }


@sem_node
def test_conta_do_navegador_igual_a_do_python(tmp_path):
    cen = _cenarios()
    (tmp_path / "cenarios.json").write_text(json.dumps(cen, ensure_ascii=False), encoding="utf-8")
    script = f"""
      const {{ criar }} = require({json.dumps(str(CONTA_JS))});
      const fs = require("fs");
      const C = criar({len(S.MODELO.vale)}, {len(S.MODELO.ponta)});
      const cen = JSON.parse(fs.readFileSync({json.dumps(str(tmp_path / "cenarios.json"))}, "utf8"));
      const out = cen.map(x => {{
        const r = C.somar(x.c, x.D, t => x.prem[t], t => x.prem[t].premio_ponta);
        const tipos = {{}};
        for (const [t, d] of Object.entries(r.porTipo)) tipos[t] = [d.pld, d.vpiso, d.fora, d.ponta];
        return {{ pld: r.pld, tipos }};
      }});
      process.stdout.write(JSON.stringify(out));
    """
    js = json.loads(subprocess.run(["node", "-e", script], capture_output=True, check=True).stdout)
    for c, j in zip(cen, js):
        p = _python(c)
        assert abs(p["pld"] - j["pld"]) < 1e-9
        assert set(p["tipos"]) == set(j["tipos"])
        for t in p["tipos"]:
            assert all(abs(a - b) < 1e-9 for a, b in zip(p["tipos"][t], j["tipos"][t]))


def test_dia_tipico_limites():
    p = {"horas_piso": 12.0, "frac_fora": -3.0, "premio_ponta": -500.0}
    d = S.dia_s(p, 100.0, 57.31)
    assert d["pld"] == pytest.approx(57.31)  # tudo no piso: horas no piso ≤ 8, preços ≥ piso
    assert d["vale_piso"] + d["fora"] + d["ponta"] == pytest.approx(d["pld"] - 100.0)


@com_dados
def test_exemplo_da_pesquisa_rv0_de_outubro():
    """Origem 25/09/2026, DECOMP digitado R$ 88,31: PLD de out/2026 = R$ 102,93 com o desconto único do modelo
    v2 (D087; no v1, um desconto por tipo de dia, 102,77). Pacote, seção 9."""
    b = S.Base(ArmazenamentoLocal(DADOS))
    o = pd.Timestamp("2026-09-25")
    pr = S.premissas_na_origem(b, o)
    assert (pr["útil"]["horas_piso"], pr["sábado"]["horas_piso"]) == (7.9, 8.0)
    for t in TIPOS_DIA:  # um número só para os três tipos (média de set/2025 a ago/2026)
        assert pr[t]["frac_fora"] == pytest.approx(-0.06123, abs=1e-5)
    assert pr["útil"]["premio_ponta"] == pytest.approx(206.23, abs=0.005)
    c = next(x for x in S.calendario(b, o) if x["mes"] == "2026-10")
    assert (c["h"], c["piso"]) == (1, 57.31)
    assert c["dias"].count("u") == 21 and c["dias"][11] == "f"  # 12/10 feriado
    dias = {t: S.dia_s(pr[t], 88.31, 57.31)["pld"] for t in TIPOS_DIA}
    assert [round(v, 2) for v in dias.values()] == [111.52, 88.42, 81.36]
    assert S.prever_mes(pr, c, 88.31) == pytest.approx(102.93, abs=0.005)


# --- resumo para a mesa (D091) e dias do mês (D095): Python × JS sobre as chaves publicadas -------------------


def _casos_resumo(d: dict) -> list[dict]:
    """Meses do calendário × DECOMP (no piso, perto, longe) × % da régua, com e sem edições."""
    rnd = random.Random(20261019)
    casos = []
    for c in d["calendario"]:
        for D in (c["piso"] - 1, c["piso"] + 3, c["piso"] + 15, 150.0, 420.0):
            for pct in (0, 5, 50, 100):
                _, prem, premio, ps = S.estado_padrao(d, c["mes"], D)
                casos.append(
                    {"mes": c["mes"], "D": D, "pct": pct, "prem": prem, "premio": premio, "ps": ps}
                )
        _, prem, premio, ps = S.estado_padrao(d, c["mes"], 120.0)
        prem = {
            t: {**p, "horas_piso": rnd.uniform(0, 8), "frac_fora": rnd.uniform(-0.5, 0.2)}
            for t, p in prem.items()
        }
        premio = {t: rnd.uniform(-50, 400) for t in premio}
        ps = {**premio, "útil": rnd.uniform(0, 1500) - 120.0}
        casos.append(
            {"mes": c["mes"], "D": 120.0, "pct": 25, "prem": prem, "premio": premio, "ps": ps}
        )
    return casos


@sem_node
@pytest.mark.skipif(not (SERVING / "calendario.json").exists(), reason="sem serving publicado")
def test_resumo_e_dias_do_navegador_iguais_aos_do_python(tmp_path):
    chaves_ = ["calendario", "confianca", "backtest", "desempenho", "ponta_janelas", "piso_hist"]
    chaves_ += ["premissas_janelas", "janela_padrao", "ref_fora", "sensibilidade"]
    d = {k: json.loads((SERVING / f"{k}.json").read_text(encoding="utf-8")) for k in chaves_}
    casos = _casos_resumo(d)
    (tmp_path / "d.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "casos.json").write_text(json.dumps(casos, ensure_ascii=False), encoding="utf-8")
    m = S.MODELO
    script = f"""
      const {{ criar }} = require({json.dumps(str(CONTA_JS))});
      const fs = require("fs");
      const C = criar({len(m.vale)}, {len(m.ponta)}, {m.limiar_direcao}, {m.espaco_min}, {json.dumps(m.regime_desde)});
      const D = JSON.parse(fs.readFileSync({json.dumps(str(tmp_path / "d.json"))}, "utf8"));
      const casos = JSON.parse(fs.readFileSync({json.dumps(str(tmp_path / "casos.json"))}, "utf8"));
      const limpa = o => JSON.parse(JSON.stringify(o, (k, v) => (k.startsWith("_") ? undefined : v)));
      const out = casos.map(x => {{
        const c = D.calendario.find(y => y.mes === x.mes);
        return {{ resumo: limpa(C.resumo(D, c, x.D, x.prem, x.premio, x.ps, x.pct)),
                  dias: limpa(C.diasMes(c, x.D, x.prem, x.premio, x.ps, x.pct)) }};
      }});
      process.stdout.write(JSON.stringify(out));
    """
    js = json.loads(subprocess.run(["node", "-e", script], capture_output=True, check=True).stdout)

    def igual(a, b, cam):
        if isinstance(a, dict):
            assert set(a) == set(b), cam
            for k in a:
                igual(a[k], b[k], f"{cam}.{k}")
        elif isinstance(a, list):
            assert len(a) == len(b), cam
            for i, (x, y) in enumerate(zip(a, b)):
                igual(x, y, f"{cam}[{i}]")
        elif isinstance(a, float) or isinstance(b, float):
            assert a == pytest.approx(b, abs=1e-9), cam
        else:
            assert a == b, cam

    for x, j in zip(casos, js):
        c = next(y for y in d["calendario"] if y["mes"] == x["mes"])
        args = (x["D"], x["prem"], x["premio"], x["ps"], x["pct"])
        res = S.resumo_mesa(d, c, *args)
        dias = S.dias_mes(c, *args)
        igual(res, j["resumo"], f"{x['mes']} D={x['D']} resumo")
        igual(dias, j["dias"], f"{x['mes']} D={x['D']} dias")
        # a média dos dias é o PLD previsto e a da última coluna, o PLD com a sensibilidade (linearidade)
        n = len(dias)
        assert max(sum(r["pld_dia"] for r in dias) / n, c["piso"]) == pytest.approx(
            res["pld_previsto"], abs=0.05
        )


def test_metodologia_de_cada_versao_do_modelo():
    """Toda versão do modelo que já gerou rodada tem a sua metodologia: a atual em metodologia.html e cada
    anterior em metodologia-<versão>.html, com o aviso de versão anterior."""
    web = RAIZ / "web" / "risk_lab_dessem"
    assert f"modelo {S.MODELO.versao}" in (web / "metodologia.html").read_text(encoding="utf-8")
    reg = json.loads((SERVING / "historico_simulador.json").read_text(encoding="utf-8"))
    versoes = {r["insumos"]["modelo"] for r in reg["rodadas"].values()} - {S.MODELO.versao}
    for v in versoes:
        assert "Versão anterior" in (web / f"metodologia-{v}.html").read_text(encoding="utf-8"), v
