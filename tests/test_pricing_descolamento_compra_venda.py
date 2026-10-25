"""Compra e venda NE e N (leva promocao-quant-v5): a conta do navegador (web/pricing_descolamento/compra_venda_conta.js) é a
mesma do Python (qe_pricing_descolamento.compra_venda), a cotação de um produto reproduz a R16 da pesquisa e os dados
publicados (cv_backtest, cv_historico, cv_exemplo) reproduzem R13, R14 e R15.

Roda sobre as chaves publicadas em data/serving/pricing_descolamento/ (versionadas no git) e as referências congeladas
em tests/referencias/pricing_descolamento/compra_venda/. A paridade Python × JS precisa de node (pulada sem ele).
"""

import json
import random
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from qe_pricing_descolamento import compra_venda as cv
from qe_pricing_descolamento.conta import Conta

RAIZ = Path(__file__).resolve().parents[1]
CVC_JS = RAIZ / "web" / "pricing_descolamento" / "compra_venda_conta.js"
WEB = RAIZ / "web" / "pricing_descolamento"
SERVING = RAIZ / "data" / "serving" / "pricing_descolamento"
REFS = RAIZ / "tests" / "referencias" / "pricing_descolamento" / "compra_venda"
pytestmark = pytest.mark.skipif(
    not (SERVING / "cv_backtest.json").exists(), reason="sem serving publicado"
)
sem_node = pytest.mark.skipif(shutil.which("node") is None, reason="sem node")


def _json(arq: Path):
    return json.loads(arq.read_text(encoding="utf-8"))


def _ref(nome: str):
    return _json(REFS / nome)


def _node(expr: str):
    prog = f"const C = require(process.argv[1]); console.log(JSON.stringify({expr}));"
    out = subprocess.run(
        ["node", "-e", prog, str(CVC_JS)], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)


def _igual(a, b, tol=1e-3, cam=""):
    if isinstance(a, dict):
        assert set(a) == set(b), (cam, set(a) ^ set(b))
        for k in a:
            _igual(a[k], b[k], tol, f"{cam}/{k}")
    elif isinstance(a, list):
        assert len(a) == len(b), (cam, len(a), len(b))
        for i, (x, y) in enumerate(zip(a, b)):
            _igual(x, y, tol, f"{cam}[{i}]")
    elif isinstance(a, (int, float)) and not isinstance(a, bool):
        assert a == pytest.approx(b, abs=tol), (cam, a, b)
    else:
        assert a == b, (cam, a, b)


@pytest.fixture(scope="module")
def pagina():
    meses = _json(SERVING / "meses.json")
    saz = _json(SERVING / "sazonal_se.json")["fator"]
    meta = _json(SERVING / "meta.json")
    return meses, saz, meta


# --- conta do navegador × Python ---------------------------------------------------------------------------------------


@sem_node
def test_precificar_do_navegador_igual_ao_python():
    rnd = random.Random(20261025)
    for _ in range(80):
        x = [rnd.uniform(-150, 5) for _ in range(rnd.randint(3, 8))]
        par = {
            "p": rnd.choice([0.1, 0.2, 0.3, 0.4]),
            "alfa": rnd.choice([0.1, 0.2, 0.34]),
            "lam": rnd.choice([0.15, 0.3, 0.5, 1.0]),
        }
        js = _node(f"C.precificar({x}, {json.dumps(par)})")
        py = cv.precificar(x, **par)
        for k in ("justo", "compra", "venda"):
            assert js[k] == pytest.approx(py[k], abs=1e-9), (x, par, k)


@sem_node
def test_venda_do_produto_ancorada_do_navegador_igual_ao_python():
    rnd = random.Random(7)
    par = {"p": 0.3, "alfa": 0.1, "lam": 1.0}
    for _ in range(40):
        meses = [
            {
                "h": rnd.choice([672, 720, 744]),
                "anos": [rnd.uniform(-90, 0) for _ in range(rnd.randint(4, 7))],
                "hist": rnd.choice([None, rnd.uniform(-60, 0)]),
            }
            for _ in range(rnd.randint(1, 6))
        ]
        js = _node(f"C.vendaProduto({json.dumps(meses)}, {json.dumps(par)}, true)")
        H = sum(m["h"] for m in meses)
        py = sum(m["h"] * cv.venda_usada(m, par) for m in meses) / H
        assert js == pytest.approx(py, abs=1e-9)


@sem_node
def test_swap_com_se_desloca_a_cotacao_pela_diferenca_de_se():
    d = [-30, -20, -10, -5, -40, -15]
    par = '{"p": 0.3, "alfa": 0.1, "lam": 1}'
    r = _node(f"C.swapComSE(true, 270, C.precificar({d}, {par}), 250, 1)")
    p = _node(f"C.precificar({d}, {par})")
    assert r["compra"] == pytest.approx(270 + p["compra"] - 250)
    assert r["venda"] == pytest.approx(270 + p["venda"] - 250)
    v = _node(f"C.swapVetor({[270 + x for x in d]}, {[250] * 6}, 1, {par}, {par})")
    for k in ("compra", "justo", "venda"):
        assert v[k] == pytest.approx(r[k])


@sem_node
def test_painel_do_passado_da_politica_conservador():
    """Valores esperados do pacote (seção 11, v5): perda de cada lado, ganho médio e largura, com cada período pesando igual."""
    cvb = _json(SERVING / "cv_backtest.json")
    esperado = {
        ("tri", "NE"): (36, 5, 0.033, 0.0, 16.94, 11.98, 28.92),
        ("tri", "N"): (36, 5, 0.583, 0.0, 6.79, 7.18, 13.97),
        ("sem", "NE"): (23, 3, 0.0, 0.0, 15.52, 10.11, 25.63),
        ("sem", "N"): (23, 3, 0.583, 0.0, 5.81, 6.06, 11.88),
    }
    par = {"p": 0.3, "alfa": 0.1, "lam": 1.0}
    for (tipo, sub), (nc, np_, pc, pv, gc, gv, lg) in esperado.items():
        por = {}
        for c in [c for c in cvb["casos"] if c["tipo"] == tipo]:
            meses = [
                {"h": m["h"], "anos": m["anos"][sub], "hist": m["hist"][sub]} for m in c["meses"]
            ]
            comp = cv.precificar(c["anos"][sub], **par)["compra"]
            ven = sum(m["h"] * cv.venda_usada(m, par) for m in meses) / sum(m["h"] for m in meses)
            r = c["real"][sub]
            por.setdefault(c["periodo"], []).append(
                (r < comp, r > ven, r - comp, ven - r, ven - comp)
            )
        assert sum(len(v) for v in por.values()) == nc and len(por) == np_
        med = lambda i, por=por: np.mean([np.mean([x[i] for x in v]) for v in por.values()])
        assert med(0) == pytest.approx(pc, abs=0.001)
        assert med(1) == pytest.approx(pv, abs=0.001)
        assert med(2) == pytest.approx(gc, abs=0.01)
        assert med(3) == pytest.approx(gv, abs=0.01)
        assert med(4) == pytest.approx(lg, abs=0.01)


# --- cotação de um produto: R16 da pesquisa ----------------------------------------------------------------------------


def test_cotacao_por_produto_reproduz_a_r16(pagina):
    """Com o SE plano de R$ 270 em todos os anos, o produto sozinho (compra, justo, venda) e a contribuição para o ano de
    cada ano, semestre, trimestre e mês, do NE e do N, são os da página da pesquisa (R16), dentro de R$ 0,001."""
    meses, saz, meta = pagina
    if meta["deck"] != "2026-10":
        pytest.skip("serving de outro deck: a referência congelada é do deck de out/2026")
    r16 = _ref("R16_cv_cotacoes_se270.json")
    cvh = _json(SERVING / "cv_historico.json")
    conta = Conta(meses, saz)
    res = conta.calcular(conta.resolver({a["k"]: r16["se"] for a in conta.per})["se"])
    n = 0
    for sub, por_tipo in r16["produtos"].items():
        for tipo, lista in por_tipo.items():
            for p in lista:
                ms = p["meses"]
                ano = next(a for a in conta.per if ms[0] in a["meses"])
                c = cv.cotar_produto(conta, res, ms, sub, cvh)
                ct = cv.contribuicao_para_o_ano(conta, res, ano["meses"], ms, sub, cvh)
                for k in ("se", "compra", "justo", "venda"):
                    assert c[k] == pytest.approx(p[k], abs=1e-3), (sub, tipo, p["rot"], k)
                assert ct["compra"] == pytest.approx(p["contrib"]["compra"], abs=1e-3), (
                    sub,
                    tipo,
                    p["rot"],
                )
                assert ct["venda"] == pytest.approx(p["contrib"]["venda"], abs=1e-3), (
                    sub,
                    tipo,
                    p["rot"],
                )
                n += 1
    assert n == 162


def test_semestres_e_trimestres_fecham_o_ano(pagina):
    """Modo "Fechar o ano": a média por horas das contribuições dos semestres (e a dos trimestres) reproduz a cotação do ano."""
    meses, saz, _ = pagina
    cvh = _json(SERVING / "cv_historico.json")
    conta = Conta(meses, saz)
    res = conta.calcular(conta.resolver({a["k"]: 270.0 for a in conta.per})["se"])
    for sub in ("NE", "N"):
        for a in conta.per:
            if len(a["meses"]) < 12:
                continue
            ano = cv.cotar_produto(conta, res, a["meses"], sub, cvh)
            for grupo in (a["S"], a["T"]):
                partes = [
                    (
                        conta.horas(g["meses"]),
                        cv.contribuicao_para_o_ano(conta, res, a["meses"], g["meses"], sub, cvh),
                    )
                    for g in grupo
                ]
                H = sum(h for h, _ in partes)
                for lado in ("compra", "venda"):
                    assert sum(h * c[lado] for h, c in partes) / H == pytest.approx(
                        ano[lado], abs=1e-6
                    ), (sub, a["y"], lado)


# --- dados publicados × referências ------------------------------------------------------------------------------------


def test_cv_backtest_publicado_reproduz_r14():
    pub, ref = _json(SERVING / "cv_backtest.json"), _ref("R14_cv_backtest.json")
    assert len(pub["casos"]) == 59
    _igual(pub, ref)


def test_cv_historico_publicado_so_acrescenta_a_r15():
    """O histórico cresce com os decks: o que a R15 tem (meses até D−2 do deck de out/2026) continua igual."""
    pub, ref = _json(SERVING / "cv_historico.json"), _ref("R15_cv_historico.json")
    for sub in ("NE", "N"):
        for mes, lista in ref[sub].items():
            assert pub[sub][mes][: len(lista)] == lista, (sub, mes)
    for mes, v in ref["real"].items():
        assert pub["real"][mes] == v, mes
    assert pub["real"]["2026-02"] == [382.4, -2.3, -2.3]


def test_cv_exemplo_publicado_reproduz_r13(pagina):
    meses, saz, meta = pagina
    pub = _json(SERVING / "cv_exemplo.json")
    assert cv.exemplo(meses, saz, meta["deck"], _json(SERVING / "cv_historico.json")) == pub
    if meta["deck"] != "2026-10":
        pytest.skip("serving de outro deck: a referência congelada é do deck de out/2026")
    _igual(pub, _ref("R13_cv_exemplo.json"), tol=0.011)


# --- páginas: menu, tabs e arquivos ------------------------------------------------------------------------------------


def _menu(arq: str) -> list[tuple[str, str]]:
    s = (WEB / arq).read_text(encoding="utf-8")
    nav = re.search(r'<nav class="nav".*?</nav>', s, re.DOTALL).group(0)
    return re.findall(r'<a (?!class="marca")href="([^"]+)"[^>]*>([^<]+)</a>', nav)


def test_menu_igual_nas_paginas_com_compra_e_venda_primeiro():
    esperado = [
        ("compra_venda.html", "Compra e venda NE e N"),
        ("./", "Descolamento NE e N"),
        ("fundamentos.html", "Fundamentos"),
        ("compra_venda_metodologia.html", "Metodologia"),
    ]
    for arq in (
        "index.html",
        "fundamentos.html",
        "metodologia.html",
        "compra_venda.html",
        "compra_venda_metodologia.html",
    ):
        assert _menu(arq) == esperado, arq


def test_tabs_da_metodologia_com_compra_e_venda_como_padrao():
    d = (WEB / "metodologia.html").read_text(encoding="utf-8")
    c = (WEB / "compra_venda_metodologia.html").read_text(encoding="utf-8")
    assert re.search(r'href="metodologia.html" role="tab" aria-selected="true"', d)
    assert re.search(r'href="compra_venda_metodologia.html" role="tab" aria-selected="false"', d)
    assert re.search(r'href="compra_venda_metodologia.html" role="tab" aria-selected="true"', c)
    assert re.search(r'href="metodologia.html" role="tab" aria-selected="false"', c)


def test_pagina_de_compra_e_venda_carrega_os_arquivos_e_os_dados_que_existem():
    s = (WEB / "compra_venda.html").read_text(encoding="utf-8")
    for src in re.findall(r'<script src="([^"]+)"', s):
        assert (WEB / src).resolve().exists(), src
    js = (WEB / "compra_venda.js").read_text(encoding="utf-8")
    chaves = re.search(r"const CHAVES = \[(.*?)\]", js).group(1)
    for k in re.findall(r'"(\w+)"', chaves):
        assert (SERVING / f"{k}.json").exists(), k
    met = (WEB / "compra_venda_metodologia.html").read_text(encoding="utf-8")
    assert "/dados/pricing_descolamento/${k}.json" in met and '["cv_exemplo", "cv_backtest"]' in met


def test_paginas_com_dica_tem_o_elemento_do_tooltip():
    """`dicaEm` (graficos.js) escreve em #dica; sem o elemento, o tooltip do histórico e do gráfico quebra."""
    for arq in WEB.glob("*.html"):
        s = arq.read_text(encoding="utf-8")
        js = arq.with_suffix(".js")
        usa = "dicaEm(" in s or (js.exists() and "dicaEm(" in js.read_text(encoding="utf-8"))
        if "graficos.js" in s and usa:
            assert 'id="dica"' in s, arq.name
