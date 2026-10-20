"""Página do descolamento: a conta do navegador (web/pricing_descolamento/descolamento_conta.js) é a mesma do Python
(qe_pricing_descolamento.conta) e reproduz o modelo.

Roda sobre as chaves publicadas em data/serving/pricing_descolamento/ (versionadas no git). A paridade Python × JS
precisa de node (pulada sem ele).
"""

import json
import random
import shutil
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from qe_pricing_descolamento.conta import Conta

RAIZ = Path(__file__).resolve().parents[1]
CONTA_JS = RAIZ / "web" / "pricing_descolamento" / "descolamento_conta.js"
SERVING = RAIZ / "data" / "serving" / "pricing_descolamento"
REFS = RAIZ / "tests" / "referencias" / "pricing_descolamento"
pytestmark = pytest.mark.skipif(
    not (SERVING / "meses.json").exists(), reason="sem serving publicado"
)


@pytest.fixture(scope="module")
def pagina():
    meses = json.loads((SERVING / "meses.json").read_text(encoding="utf-8"))
    saz = json.loads((SERVING / "sazonal_se.json").read_text(encoding="utf-8"))["fator"]
    return meses, saz


def _curvas(conta: Conta, n: int = 60) -> list[dict]:
    """Curvas digitadas: só anos, anos + semestres/trimestres/meses, períodos que não fecham a média do pai e SE
    abaixo do piso, nas duas sazonalidades."""
    rnd = random.Random(20261019)
    chaves = []
    for a in conta.per:
        chaves.append(a["k"])
        chaves += [s["k"] for s in a["S"] if s["meses"]] + [t["k"] for t in a["T"] if t["meses"]]
        chaves += [f"M{p}" for p in a["meses"]]
    out = [{"ent": {a["k"]: 200.0 for a in conta.per}, "saz": "plana"}]
    for i in range(n):
        ent = {a["k"]: rnd.uniform(40, 450) for a in conta.per if rnd.random() < 0.8}
        for k in rnd.sample(chaves, rnd.randint(0, 12)):
            ent[k] = rnd.uniform(20, 600)
        out.append({"ent": ent, "saz": "hist" if i % 2 else "plana"})
    return out


def _produtos(conta: Conta) -> list[list[str]]:
    ps = []
    for a in conta.per:
        ps.append(a["meses"])
        ps += [s["meses"] for s in a["S"] if s["meses"]] + [
            t["meses"] for t in a["T"] if t["meses"]
        ]
        ps += [[p] for p in a["meses"]]
    return ps


def _python(conta: Conta, caso: dict) -> dict:
    r = conta.resolver(caso["ent"], caso["saz"])
    out = {"resolvido": r}
    for nome, aj in (("base", lambda x: x), ("rs", lambda x: x + 10), ("pct", lambda x: x * 1.1)):
        res = conta.calcular(r["se"], aj)
        out[nome] = {"meses": res, "produtos": [conta.agregar(res, ms) for ms in _produtos(conta)]}
    return out


def _igual(a, b, cam=""):
    if isinstance(a, dict):
        assert set(a) == set(b), (cam, set(a) ^ set(b))
        for k in a:
            _igual(a[k], b[k], f"{cam}.{k}")
    elif isinstance(a, list):
        assert len(a) == len(b), cam
        for i, (x, y) in enumerate(zip(a, b)):
            _igual(x, y, f"{cam}[{i}]")
    elif isinstance(a, float) or isinstance(b, float):
        assert a == pytest.approx(b, abs=1e-9), cam
    else:
        assert a == b, cam


@pytest.mark.skipif(shutil.which("node") is None, reason="sem node")
def test_conta_do_navegador_igual_a_do_python(pagina, tmp_path):
    meses, saz = pagina
    conta = Conta(meses, saz)
    casos = _curvas(conta)
    (tmp_path / "casos.json").write_text(json.dumps(casos), encoding="utf-8")
    (tmp_path / "produtos.json").write_text(json.dumps(_produtos(conta)), encoding="utf-8")
    script = f"""
      const {{ criar }} = require({json.dumps(str(CONTA_JS))});
      const fs = require("fs"), ler = f => JSON.parse(fs.readFileSync(f, "utf8"));
      const C = criar(ler({json.dumps(str(SERVING / "meses.json"))}), ler({json.dumps(str(SERVING / "sazonal_se.json"))}).fator);
      const casos = ler({json.dumps(str(tmp_path / "casos.json"))}), produtos = ler({json.dumps(str(tmp_path / "produtos.json"))});
      const out = casos.map(c => {{
        const r = C.resolver(c.ent, c.saz), o = {{ resolvido: r }};
        for (const [nome, aj] of [["base", x => x], ["rs", x => x + 10], ["pct", x => x * 1.1]]) {{
          const res = C.calcular(r.se, aj);
          o[nome] = {{ meses: res, produtos: produtos.map(ms => C.agregar(res, ms)) }};
        }}
        return o;
      }});
      process.stdout.write(JSON.stringify(out));
    """
    js = json.loads(subprocess.run(["node", "-e", script], capture_output=True, check=True).stdout)
    for caso, j in zip(casos, js):
        _igual(_python(conta, caso), j)


def test_com_se_plano_reproduz_as_faixas_do_modelo(pagina):
    """Com o SE plano de R$ 200, a conta da página (coeficientes publicados, arredondados) dá o preço justo e a faixa
    do modelo por trimestre, semestre e ano (referência congelada do deck de out/2026), dentro de R$ 0,01."""
    meses, saz = pagina
    meta = json.loads((SERVING / "meta.json").read_text(encoding="utf-8"))
    if meta["deck"] != "2026-10":
        pytest.skip("serving de outro deck: a referência congelada é do deck de out/2026")
    conta = Conta(meses, saz)
    res = conta.calcular(conta.resolver({a["k"]: 200.0 for a in conta.per})["se"])
    ref = pd.read_parquet(REFS / "modelo_faixas.parquet").set_index("periodo")
    rotulo = {}
    for a in conta.per:
        rotulo[str(a["y"])] = a["meses"]
        for i, s in enumerate(a["S"]):
            rotulo[f"{a['y']}-S{i + 1}"] = s["meses"]
        for i, t in enumerate(a["T"]):
            rotulo[f"{a['y']}-T{i + 1}"] = t["meses"]
    for per, r in ref.iterrows():
        g = conta.agregar(res, rotulo[per])
        for s in ("NE", "N"):
            assert g[s] == pytest.approx(r[f"{s}_justo"], abs=0.01), (per, s)
            assert g[f"{s}min"] == pytest.approx(r[f"{s}_min"], abs=0.01), (per, s)
            assert g[f"{s}max"] == pytest.approx(r[f"{s}_max"], abs=0.01), (per, s)
