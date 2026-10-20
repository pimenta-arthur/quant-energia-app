"""A conta da página que depende da curva do SE digitada, em Python: a mesma de
web/pricing_descolamento/descolamento_conta.js (roda no navegador). Mudar uma exige mudar a outra; o teste de paridade
compara as duas (tests/test_pricing_descolamento_pagina.py, com node).

- `resolver`: a curva do SE do ano ao mês. Cada nó (ano, semestre, trimestre, mês) vale o digitado ou o derivado do
  pai; filhos não digitados dividem o que falta para fechar a média do pai (ponderada por horas), na proporção da
  sazonalidade escolhida (plana = iguais; histórica = SE do mês ÷ média do ano);
- `calcular`: descolamento exato do modelo por mês e cenário, d = −Σ_h c_h · max(SE · perfil_h − piso, 0);
- `agregar`: preço justo (média por mês, ponderada por horas, da média dos cenários) e faixa (mín–máx dos cenários
  agregados no período, só os presentes em todos os meses).
"""

import math


def _desc(coef: list[float], folga: list[float]) -> float:
    """d = −Σ_h c_h · folga_h (soma na mesma ordem do JS)."""
    a = 0
    for v, f in zip(coef, folga):
        a += v * f
    return -a


def _media(cen: list[dict], campo: str) -> float:
    """Média dos cenários ponderada pelo peso (soma na mesma ordem do JS)."""
    a = 0
    for c in cen:
        a += c["peso"] * c[campo]
    return a / sum(c["peso"] for c in cen)


class Conta:
    def __init__(self, meses: list[dict], saz: list[float]):
        self.M = meses
        self.SAZ = saz
        self.idx = {m["mes"]: i for i, m in enumerate(meses)}
        self.anos = list(dict.fromkeys(int(m["mes"][:4]) for m in meses))
        self.per = [self._periodos_do_ano(y) for y in self.anos]

    def horas(self, ms: list[str]) -> float:
        return sum(self.M[self.idx[p]]["horas"] for p in ms)

    def _periodos_do_ano(self, y: int) -> dict:
        ms = [m["mes"] for m in self.M if int(m["mes"][:4]) == y]
        mes = lambda p: int(p[5:7])
        S = [
            {"k": f"S{y}-{s}", "meses": [p for p in ms if (mes(p) <= 6) == (s == 1)]}
            for s in (1, 2)
        ]
        T = [
            {
                "k": f"T{y}-{t}",
                "sem": 1 if t <= 2 else 2,
                "meses": [p for p in ms if math.ceil(mes(p) / 3) == t],
            }
            for t in (1, 2, 3, 4)
        ]
        return {"y": y, "k": f"A{y}", "meses": ms, "S": S, "T": T}

    def resolver(self, ent: dict, saz_modo: str = "plana") -> dict:
        def fator_saz(ms):
            if saz_modo != "hist":
                return 1
            a = h = 0
            for p in ms:
                hh = self.M[self.idx[p]]["horas"]
                a += self.SAZ[int(p[5:7]) - 1] * hh
                h += hh
            return a / h

        se, info, avisos = {}, {}, []

        def no(chave, ms, herdado, filhos):
            dig = ent.get(chave)
            v = dig if dig is not None else herdado
            info[chave] = {"v": v, "digitado": dig is not None}
            if filhos is None:
                if v is not None:
                    for p in ms:
                        se[p] = v
                return
            vivos = [f for f in filhos if f["meses"]]
            fixos = [f for f in vivos if ent.get(f["chave"]) is not None]
            livres = [f for f in vivos if ent.get(f["chave"]) is None]
            herd = {}
            if v is not None:
                H = self.horas(ms)
                Hf = 0
                for f in fixos:
                    Hf += self.horas(f["meses"]) * ent[f["chave"]]
                Hl = 0
                for f in livres:
                    Hl += self.horas(f["meses"])
                if livres:
                    alvo = (v * H - Hf) / Hl
                    norm = 0
                    for f in livres:
                        norm += fator_saz(f["meses"]) * self.horas(f["meses"])
                    norm /= Hl
                    for f in livres:
                        herd[f["chave"]] = alvo * fator_saz(f["meses"]) / norm
                elif abs(Hf / H - v) > 0.05:
                    avisos.append({"tipo": "media", "chave": chave, "media": Hf / H, "v": v})
            for f in vivos:
                no(f["chave"], f["meses"], herd.get(f["chave"]), f.get("filhos"))

        for a in self.per:
            tri = [
                {
                    "chave": t["k"],
                    "meses": t["meses"],
                    "filhos": [{"chave": f"M{p}", "meses": [p]} for p in t["meses"]],
                }
                for t in a["T"]
            ]
            sem = [
                {
                    "chave": s["k"],
                    "meses": s["meses"],
                    "filhos": [tri[j] for j, t in enumerate(a["T"]) if t["sem"] == i + 1],
                }
                for i, s in enumerate(a["S"])
            ]
            no(a["k"], a["meses"], None, sem)
        for a in self.per:
            for p in [{"k": a["k"], "meses": a["meses"]}, *a["S"], *a["T"]]:
                if not p["meses"]:
                    continue
                if (
                    p["k"] in info
                    and info[p["k"]]["v"] is None
                    and all(se.get(q) is not None for q in p["meses"])
                ):
                    s = 0
                    for q in p["meses"]:
                        s += se[q] * self.M[self.idx[q]]["horas"]
                    info[p["k"]] = {
                        "v": s / self.horas(p["meses"]),
                        "digitado": False,
                        "media": True,
                    }
        for p in sorted(se):
            if se[p] < self.M[self.idx[p]]["piso"]:
                avisos.append(
                    {"tipo": "piso", "mes": p, "v": se[p], "piso": self.M[self.idx[p]]["piso"]}
                )
        return {"se": se, "info": info, "avisos": avisos}

    def calcular(self, se: dict, ajuste=lambda x: x) -> dict:
        res = {}
        for m in self.M:
            s = se.get(m["mes"])
            if s is None:
                continue
            S = ajuste(s)
            fol = [max(S * r - m["piso"], 0) for r in m["perfil"]]

            cen = [
                {
                    "id": c["id"],
                    "peso": c["peso"],
                    "NE": _desc(c["cNE"], fol),
                    "N": _desc(c["cN"], fol),
                    "trava": c["trava"],
                    "k": c["k"],
                }
                for c in m["cen"]
            ]
            res[m["mes"]] = {
                "se": S,
                "NE": _media(cen, "NE"),
                "N": _media(cen, "N"),
                "trava": _media(cen, "trava"),
                "cen": cen,
                "NEmin": min(c["NE"] for c in cen),
                "NEmax": max(c["NE"] for c in cen),
                "Nmin": min(c["N"] for c in cen),
                "Nmax": max(c["N"] for c in cen),
            }
        return res

    def agregar(self, res: dict, ms: list[str]) -> dict | None:
        if not ms or any(p not in res for p in ms):
            return None
        H = self.horas(ms)
        wm = {p: self.M[self.idx[p]]["horas"] / H for p in ms}
        out = {"se": 0, "NE": 0, "N": 0, "trava": 0}
        for p in ms:
            for f in ("se", "NE", "N", "trava"):
                out[f] += res[p][f] * wm[p]
        ids = [
            c["id"]
            for c in res[ms[0]]["cen"]
            if all(any(x["id"] == c["id"] for x in res[p]["cen"]) for p in ms)
        ]
        por_cen = []
        for i in ids:
            o = {"NE": 0, "N": 0}
            for p in ms:
                c = next(x for x in res[p]["cen"] if x["id"] == i)
                o["NE"] += c["NE"] * wm[p]
                o["N"] += c["N"] * wm[p]
            por_cen.append(o)
        if por_cen:
            for s in ("NE", "N"):
                out[f"{s}min"] = min(c[s] for c in por_cen)
                out[f"{s}max"] = max(c[s] for c in por_cen)
        return out
