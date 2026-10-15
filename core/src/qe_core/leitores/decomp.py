"""Leitores dos decks do DECOMP da CCEE (um deck por semana operativa, com republicações).

Funções puras sobre o caminho do arquivo (texto ou .gz, como fica guardado em raw/).

- `ler_dadger_dp` (dadger.rvN): início do estudo (DT), revisão (TE) e carga e horas por estágio,
  submercado e patamar (DP);
- `ler_sumario_cmo` (sumario.rvN): CMO por estágio semanal, submercado e patamar.
"""

import datetime as dt
import re
from pathlib import Path

import pandas as pd

from qe_core.leitores.dessem import texto

SUBSISTEMA = {"1": "SE", "2": "S", "3": "NE", "4": "N", "11": "FC"}

# Zips semanais da CCEE: deck e relatório (com o sumário). `_kaPublicacao` = republicação k da semana.
PADRAO_DECK = re.compile(r"^DC(\d{4})(\d{2})-sem(\d)(?:_(\d)aPublicacao)?\.+zip$")
PADRAO_RELATORIO = re.compile(
    r"^Relatorio_Sumario-(\d{4})(\d{2})-sem(\d)(?:_(\d)aPublicacao)?\.+zip$"
)


def semana_do_zip(nome: str) -> tuple[str, str, int, int] | None:
    """Nome do zip semanal -> (tipo 'deck' | 'relatorio', PMO 'AAAA-MM', semana, publicação)."""
    for tipo, padrao in (("deck", PADRAO_DECK), ("relatorio", PADRAO_RELATORIO)):
        m = padrao.match(nome)
        if m:
            return tipo, f"{m[1]}-{m[2]}", int(m[3]), int(m[4] or 1)
    return None


def ler_dadger_dp(caminho: Path) -> tuple[dt.date, int, pd.DataFrame]:
    """Data de início do estudo (DT), revisão (TE) e registros DP (carga e horas por patamar)."""
    linhas = texto(caminho).splitlines()
    dtl = next(ln for ln in linhas if ln.startswith("DT")).split()
    inicio = dt.date(int(dtl[3]), int(dtl[2]), int(dtl[1]))
    rv = int(re.search(r"REV\s+(\d+)", next(ln for ln in linhas if ln.startswith("TE"))).group(1))
    reg = []
    for ln in linhas:
        if ln.startswith("DP"):
            p = ln.split()
            est, sub, npat = int(p[1]), SUBSISTEMA.get(p[2]), int(p[3])
            v = p[4:]
            if sub is None or len(v) < 2 * npat:
                continue  # FC não tem carga (só horas)
            for k in range(npat):
                reg.append((est, sub, k + 1, float(v[2 * k]), float(v[2 * k + 1])))
    dp = pd.DataFrame(reg, columns=["estagio", "submercado", "patamar", "carga_mw", "horas"])
    return inicio, rv, dp


def ler_sumario_cmo(caminho: Path) -> tuple[dt.date, pd.DataFrame]:
    """Data da rodada e CMO ($/MWh) por estágio semanal, submercado e patamar (1 pesada, 2 média,
    3 leve)."""
    linhas = texto(caminho).splitlines()
    datas = (re.search(r"(\d\d/\d\d/\d{4})", ln) for ln in linhas[:6])
    rodada = dt.datetime.strptime(next(m for m in datas if m).group(1), "%d/%m/%Y").date()
    i = next(k for k, ln in enumerate(linhas) if "CUSTO MARGINAL DE OPERACAO" in ln)
    reg, pendentes = [], []
    for ln in linhas[i + 4 :]:
        p = ln.split()
        if not p or p[0].startswith("X"):
            if reg or pendentes:
                break
            continue
        if p[0].startswith("Pat_"):
            pendentes.append((int(p[0][4:]), [float(v) for v in p[1:]]))
        elif p[0].startswith("Med_"):
            sub = p[0][4:]
            for pat, vals in pendentes:
                reg += [(k + 1, sub, pat, v) for k, v in enumerate(vals)]
            pendentes = []
    return rodada, pd.DataFrame(reg, columns=["estagio", "submercado", "patamar", "cmo"])
