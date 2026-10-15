"""Simulador do PLD médio do mês (bloco 7): paridade Python × JS da conta e exemplo de referência.

A conta do dia típico roda no navegador (o usuário digita o DECOMP), em
web/risk_lab_dessem/simulador_conta.js, e no Python (qe_risk_lab_dessem.simulador). O teste de paridade
roda o mesmo arquivo da página com node em cenários aleatórios; é pulado sem node. O exemplo da origem
25/09/2026 (RV0 de out/2026) é o conferido à mão no pacote de promoção da pesquisa (seção 9).
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


@pytest.mark.skipif(shutil.which("node") is None, reason="sem node")
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
    """Origem 25/09/2026, DECOMP digitado R$ 88,31: PLD de out/2026 = R$ 102,77 (pacote, seção 9)."""
    b = S.Base(ArmazenamentoLocal(DADOS))
    o = pd.Timestamp("2026-09-25")
    pr = S.premissas_na_origem(b, o)
    assert (pr["útil"]["horas_piso"], pr["sábado"]["horas_piso"]) == (7.9, 8.0)
    assert pr["útil"]["frac_fora"] == pytest.approx(-0.01833, abs=1e-5)
    assert pr["útil"]["premio_ponta"] == pytest.approx(206.23, abs=0.005)
    c = next(x for x in S.calendario(b, o) if x["mes"] == "2026-10")
    assert (c["h"], c["piso"]) == (1, 57.31)
    assert S.prever_mes(pr, c, 88.31) == pytest.approx(102.77, abs=0.005)
