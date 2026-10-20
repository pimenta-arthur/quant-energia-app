"""Cálculo da bandeira a partir de relatos do DECOMP: referências oficiais e paridade Python × JS.

Os recortes de relato (tests/referencias/forecast_bandeiras/relato/, ~4 KB cada) trazem só os blocos que os
leitores usam; `parametros.json` guarda as horas por patamar, o GF_band e o PLD mín/máx de cada mês, mais o
resultado oficial do boletim. A conta da página (web/forecast_bandeiras/relato_conta.js) roda com node sobre
os mesmos arquivos; o teste é pulado sem node.

Meses (PLD gatilho oficial): out/2026 R$ 90,19; mai/2026 R$ 237,58 (submercados descolados); abr/2025
R$ 208,03 (1ª publicação do deck); mar/2025 R$ 264,69 (2ª publicação, a que o boletim usou).
"""

import json
import math
import shutil
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from qe_core.leitores.dessem import texto
from qe_forecast_bandeiras import regra, relato

RAIZ = Path(__file__).resolve().parents[1]
REF = RAIZ / "tests" / "referencias" / "forecast_bandeiras" / "relato"
CONTA_JS = RAIZ / "web" / "forecast_bandeiras" / "relato_conta.js"
PARAMS = json.loads((REF / "parametros.json").read_text())
MESES = list(PARAMS)
com_node = pytest.mark.skipif(shutil.which("node") is None, reason="sem node")


def _horas(ym: str) -> pd.DataFrame:
    return pd.DataFrame(
        PARAMS[ym]["horas"],
        index=["PESADO", "MEDIO", "LEVE"],
        columns=range(1, len(PARAMS[ym]["horas"][0]) + 1),
    )


def _calc(ym: str, ccee=True, ons=True, **alt):
    p = PARAMS[ym]
    arg = {"gf_band": p["gf_band"], "pld_min": p["pld_min"], "pld_max": p["pld_max"]}
    arg.update(alt)
    return relato.calcular_bandeira(
        pd.Period(ym, "M"),
        _horas(ym),
        relato_ccee=REF / f"ccee_{ym}.txt.gz" if ccee else None,
        relato_ons=REF / f"ons_{ym}.txt.gz" if ons else None,
        **arg,
    )


@pytest.mark.parametrize("ym", MESES)
def test_reproduz_o_boletim_com_os_dois_relatos(ym):
    r, oficial = _calc(ym), PARAMS[ym]["oficial"]
    assert round(r["pld_gatilho"], 2) == oficial["pld_gatilho"]
    assert r["gsf"] == oficial["gsf"]
    assert r["cor"] == oficial["cor"]
    assert r["fontes"] == {"gh": "ONS", "pld": "CCEE"}


@pytest.mark.parametrize("ym", MESES)
def test_so_relato_da_ccee_aproxima_o_gh(ym):
    completo, so_ccee = _calc(ym), _calc(ym, ons=False)
    assert so_ccee["pld_gatilho"] == pytest.approx(completo["pld_gatilho"])
    assert so_ccee["fontes"]["gh"] == "CCEE (aproximação)"
    assert abs(so_ccee["gh_band"] / completo["gh_band"] - 1) < 0.015  # até ~1% (D034)


def test_so_ons_exige_pld_manual_e_nunca_usa_o_cmo_do_ons():
    with pytest.raises(ValueError, match="CMO do ONS"):
        _calc("2026-10", ccee=False)
    r = _calc("2026-10", ccee=False, pld_gatilho_manual=200.0)
    assert r["fontes"]["pld"] == "manual" and r["pld_gatilho"] == 200.0 and r["cor"] == "Amarela"


def test_sem_relato_nenhum():
    with pytest.raises(ValueError, match="ao menos um relato"):
        _calc("2026-10", ccee=False, ons=False)


def test_folga_ate_a_cor_vizinha_out_2026():
    r = _calc("2026-10")
    assert r["cor"] == "Verde" and r["pld_cor_acima"] == pytest.approx(27.48 / 0.18)  # ~152,7


def test_probabilidade_das_cores():
    p = relato.probabilidade_cores(["Verde", "Verde", "Amarela"])
    assert p == pytest.approx({"Verde": 2 / 3, "Amarela": 1 / 3, "Vermelha 1": 0, "Vermelha 2": 0})


# --- paridade Python × JS ---------------------------------------------------------------------------

NODE = """
const C = require(process.argv[1]);
const casos = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const saida = casos.map((c) => { try { return C.calcular(c); } catch (e) { return { erro: String(e.message) }; } });
process.stdout.write(JSON.stringify(saida, (k, v) => (typeof v === 'number' && !Number.isFinite(v) ? String(v) : v)));
"""


def _casos_js() -> tuple[list[dict], list[dict]]:
    """Entradas do JS e as saídas do Python para os mesmos cenários (reais e com premissas variadas)."""
    js, py = [], []
    variacoes = [{}, {"gf_band": 51000.0}, {"gf_band": 56000.0, "pld_min": 80.0, "pld_max": 300.0}]
    for ym in MESES:
        p = PARAMS[ym]
        for v in variacoes:
            for ccee, ons, manual in [
                (True, True, None),
                (True, False, None),
                (False, True, 120.0),
            ]:
                premissas = {
                    "gf_band": p["gf_band"],
                    "pld_min": p["pld_min"],
                    "pld_max": p["pld_max"],
                    **v,
                }
                entrada = {
                    "periodo": ym,
                    "horas": p["horas"],
                    "fatores": regra.FATORES,
                    "limites_x": regra.LIMITES_X,
                    "ccee": texto(REF / f"ccee_{ym}.txt.gz") if ccee else None,
                    "ons": texto(REF / f"ons_{ym}.txt.gz") if ons else None,
                    "pld_gatilho_manual": manual,
                    **premissas,
                }
                js.append(entrada)
                py.append(
                    relato.calcular_bandeira(
                        pd.Period(ym, "M"),
                        _horas(ym),
                        relato_ccee=REF / f"ccee_{ym}.txt.gz" if ccee else None,
                        relato_ons=REF / f"ons_{ym}.txt.gz" if ons else None,
                        pld_gatilho_manual=manual,
                        **premissas,
                    )
                )
    return js, py


def _igual(a, b, caminho=""):
    if isinstance(b, dict):
        assert set(a) == set(b), (caminho, set(a) ^ set(b))
        for k in b:
            _igual(a[k], b[k], f"{caminho}.{k}")
    elif isinstance(b, float):
        if not math.isfinite(b):  # nan/inf voltam como texto do JS
            assert str(a).lower() in {str(b).lower(), "nan", "infinity", "inf"}, (caminho, a, b)
        else:
            assert a == pytest.approx(b, rel=1e-9, abs=1e-9), (caminho, a, b)
    else:
        assert a == b, (caminho, a, b)


@com_node
def test_paridade_python_js():
    js, py = _casos_js()
    out = subprocess.run(
        ["node", "-e", NODE, str(CONTA_JS)],
        input=json.dumps(js),
        capture_output=True,
        text=True,
        check=True,
    )
    resultados = json.loads(out.stdout)
    assert len(resultados) == len(py) == 36
    for entrada, js_res, py_res in zip(js, resultados, py):
        assert "erro" not in js_res, (entrada["periodo"], js_res)
        py_res = {k: v for k, v in py_res.items() if k != "mes"}
        py_res["mes"] = entrada["periodo"]
        py_res["avisos"] = []
        _igual(js_res, json.loads(json.dumps(py_res, default=float)))


@com_node
def test_js_recusa_o_que_o_python_recusa():
    base = {
        "periodo": "2026-10",
        "horas": PARAMS["2026-10"]["horas"],
        "fatores": regra.FATORES,
        "limites_x": regra.LIMITES_X,
        "gf_band": 52929.0,
        "pld_min": 57.31,
        "pld_max": 758.27,
        "ons": texto(REF / "ons_2026-10.txt.gz"),
        "ccee": None,
    }
    out = subprocess.run(
        ["node", "-e", NODE, str(CONTA_JS)],
        input=json.dumps([base, {**base, "ons": None}]),
        capture_output=True,
        text=True,
        check=True,
    )
    erros = [r.get("erro", "") for r in json.loads(out.stdout)]
    assert "CMO do ONS" in erros[0] and "ao menos um relato" in erros[1]


@pytest.mark.parametrize("ym", MESES)
def test_mes_do_relato(ym):
    esperado = int(ym[5:])
    assert relato.mes_do_relato(REF / f"ccee_{ym}.txt.gz") == esperado
    assert relato.mes_do_relato(REF / f"ons_{ym}.txt.gz") == esperado


@com_node
def test_mes_do_relato_js():
    script = (
        "const C = require(process.argv[1]);"
        "const t = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
        "process.stdout.write(JSON.stringify(t.map((x) => C.mesDoRelato(x))));"
    )
    textos = [texto(REF / f"{o}_{ym}.txt.gz") for ym in MESES for o in ("ccee", "ons")]
    out = subprocess.run(
        ["node", "-e", script, str(CONTA_JS)],
        input=json.dumps(textos + ["sem rótulo"]),
        capture_output=True,
        text=True,
        check=True,
    )
    esperado = [int(ym[5:]) for ym in MESES for _ in range(2)] + [None]
    assert json.loads(out.stdout) == esperado


def test_mes_diferente_nao_impede_o_calculo():
    """Relato de outro mês só gera aviso na página: a conta roda (estudos customizados)."""
    p = PARAMS["2026-05"]
    r = relato.calcular_bandeira(
        pd.Period("2026-11", "M"),
        _horas("2026-05"),
        p["gf_band"],
        p["pld_min"],
        p["pld_max"],
        relato_ccee=REF / "ccee_2026-05.txt.gz",
    )
    assert r["pld_gatilho"] > 0 and r["cor"] in regra.CORES


NODE_MEMORIA = """
const C = require(process.argv[1]);
const casos = JSON.parse(require('fs').readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(casos.map((c) => ({ calc: C.calcular(c), mem: C.memoria(c), csv: C.memoriaCsv(C.memoria(c)) }))));
"""


@com_node
def test_memoria_de_calculo_fecha_com_o_resultado_e_com_o_python():
    js, py = _casos_js()
    out = subprocess.run(
        ["node", "-e", NODE_MEMORIA, str(CONTA_JS)],
        input=json.dumps(js),
        capture_output=True,
        text=True,
        check=True,
    )
    resultados = json.loads(out.stdout)
    for entrada, res, py_res in zip(js, resultados, py):
        calc, mem = res["calc"], res["mem"]
        # a memória fecha com o resultado da própria conta e com o Python
        assert mem["gh"]["gh_band"] == pytest.approx(calc["gh_band"], rel=1e-12)
        assert mem["gh"]["gsf"] == calc["gsf"] == py_res["gsf"]
        assert mem["pld"]["pld_gatilho"] == pytest.approx(calc["pld_gatilho"], rel=1e-12)
        assert mem["bandeira"]["x"] == pytest.approx(calc["x"], rel=1e-12)
        assert mem["bandeira"]["cor"] == calc["cor"]
        # identidades que o usuário confere à mão
        g = mem["gh"]
        f = g["fatores"]
        gh_cg = (
            (g["gh_ons"] - g["ande"]) * (1 - f["perda_bruta_conexao"]) * (1 - f["perda_conexao_cg"])
        )
        pch_cg = g["pch"] * f["part_pch_mre"] * (1 - f["perda_pch_cg"])
        assert g["gh_band"] == pytest.approx(gh_cg + pch_cg, rel=1e-12)
        assert g["gsf"] == round(g["gh_band"] / g["gf_band"], 2)
        horas = mem["horas"]["tab"]
        assert mem["horas"]["total"] == sum(map(sum, horas))
        assert sum(sum(a * b for a, b in zip(l, h)) for l, h in zip(g["tab_gh_ons"], horas)) / mem[
            "horas"
        ]["total"] == pytest.approx(g["gh_ons"], rel=1e-12)
        if mem["pld"].get("submercados"):
            subs = mem["pld"]["submercados"]
            assert sum(d["contribuicao"] for d in subs.values()) == pytest.approx(
                mem["pld"]["pld_gatilho"], rel=1e-12
            )
            assert sum(d["peso"] for d in subs.values()) == pytest.approx(1.0)
            for d in subs.values():
                assert all(
                    entrada["pld_min"] <= v <= entrada["pld_max"] for l in d["limitado"] for v in l
                )
        # números intermediários iguais aos do Python (GH ONS, ANDE e PCH da fonte do GH)
        ym = entrada["periodo"]
        fonte = REF / (f"ons_{ym}.txt.gz" if entrada["ons"] else f"ccee_{ym}.txt.gz")
        gh_py = relato.gh_band(fonte, pd.Period(ym, "M"), _horas(ym))
        for chave in ("gh_ons", "ande", "gh_cg", "pch_cg", "gh_band"):
            assert g[chave] == pytest.approx(gh_py[chave], rel=1e-9), chave
        assert g["pch"] == pytest.approx(gh_py["pch_total"], rel=1e-9)
        assert res["csv"].startswith("﻿secao;item;patamar;semana;valor")
