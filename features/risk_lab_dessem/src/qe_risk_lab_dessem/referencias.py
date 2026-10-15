"""Referências congeladas do PLD horário (tests/referencias/risk_lab_dessem/).

Na migração (2026-10-14) as saídas do app foram conferidas uma vez contra o pacote de promoção da
pesquisa (risk-lab-dessem-analytics, reports/promocao/2026-10-13/; teste opt-in
tests/test_risk_lab_dessem_paridade.py) e congeladas aqui. Só entram períodos fechados, que não mudam
com os decks novos: leitores em três dias, tabelas-base de jul a set/2026, tipos de dia até
30/09/2026 e os blocos 1, 2 e 5 nesses meses. Regerar só quando a mudança for intencional:
`uv run qe risk_lab_dessem congelar` e revisar a diferença no git.
"""

import datetime as dt
import json
from pathlib import Path

import pandas as pd

from qe_core.armazenamento import Armazenamento, ler_parquet
from qe_core.leitores import dessem
from qe_risk_lab_dessem import chaves, publicacao, tratamento

PERIODO = (pd.Timestamp("2026-07-01"), pd.Timestamp("2026-09-30"))  # três meses fechados
# útil cujos intervalos do renovaveis.dat atravessam a virada do mês; sábado; feriado (7 de setembro)
DIAS_LEITORES = [dt.date(2026, 9, 30), dt.date(2026, 7, 18), dt.date(2026, 9, 7)]
PASTA = "risk_lab_dessem"


def _no_periodo(x: pd.DataFrame, col: str = "data") -> pd.DataFrame:
    d = pd.to_datetime(x[col])
    return x[(d >= PERIODO[0]) & (d <= PERIODO[1])].reset_index(drop=True)


def calcular(arm: Armazenamento) -> dict[str, pd.DataFrame]:
    """Tabelas de referência a partir do estado atual de raw/ e processed/."""
    sist, ren = [], []
    for dia in DIAS_LEITORES:
        caminho = lambda a, d=dia: arm.caminho_local(chaves.raw_dessem(d, a + ".gz"))
        dessem.conferir_tm(caminho("entdados.dat"), dia)
        sist.append(dessem.ler_pdo_sist(caminho("PDO_SIST.DAT"), dia))
        ren.append(dessem.ler_renovaveis(caminho("renovaveis.dat"), dia))
    dec = ler_parquet(arm, chaves.PROC_DECOMP)
    ini = dec["inicio_estudo"]
    t1 = ler_parquet(arm, chaves.PROC_PLD)
    t3 = ler_parquet(arm, chaves.PROC_TIPOS)
    t5 = ler_parquet(arm, chaves.PROC_DELTA)
    meses = [str(m) for m in pd.period_range(PERIODO[0], PERIODO[1], freq="M")]
    tipos = pd.Series(t3["tipo"].to_numpy(), index=pd.to_datetime(t3["data"]))
    h = publicacao._horario(arm)
    nivel = publicacao.dias_nivel(_no_periodo(h), tipos)
    hr = publicacao.horas(_no_periodo(h), tipos)["mensal"]
    return {
        "leitor_pdo_sist": pd.concat(sist, ignore_index=True),
        "leitor_renovaveis": pd.concat(ren, ignore_index=True),
        "decomp_cmo": dec[
            (ini >= PERIODO[0] - pd.Timedelta(days=6)) & (ini <= PERIODO[1])
        ].reset_index(drop=True),
        "pld_horario": _no_periodo(t1[t1["origem"] == "publicado"]),
        "mensal_horario": _no_periodo(ler_parquet(arm, chaves.PROC_HORARIO)),
        "tipos_de_dia": t3[pd.to_datetime(t3["data"]) <= PERIODO[1]].reset_index(drop=True),
        "mensal_delta": t5[t5["mes"].isin(meses)].reset_index(drop=True),
        "bloco1_dias_nivel": pd.DataFrame(
            [[s, *r] for s, rs in nivel.items() for r in rs],
            columns=["sub", "data", "dessem", "decomp", "piso", "horas_piso", "tipo", "min", "max"],
        ),
        "bloco2_desvio_mensal": pd.DataFrame(
            [r for r in publicacao.desvio_mensal(t5) if r["mes"] in meses]
        ),
        "bloco5_horas": pd.DataFrame(
            [
                [s, m, t, hh, *v]
                for s, pm in hr.items()
                for m, pt in pm.items()
                for t, vs in pt.items()
                for hh, v in enumerate(vs)
            ],
            columns=["sub", "mes", "tipo", "hora", "n", "piso", "abaixo", "acima", "soma"],
        ),
    }


def congelar(arm: Armazenamento, destino: Path) -> Path:
    pasta = Path(destino) / PASTA
    pasta.mkdir(parents=True, exist_ok=True)
    for nome, df in calcular(arm).items():
        df.to_parquet(pasta / f"{nome}.parquet", index=False)
    (pasta / "manifesto.json").write_text(
        json.dumps(
            {
                "periodo": [str(PERIODO[0].date()), str(PERIODO[1].date())],
                "dias_leitores": [str(d) for d in DIAS_LEITORES],
                "tratado_ate": str(ler_parquet(arm, chaves.PROC_PLD)["data"].max().date()),
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    return pasta


def ler_congeladas(destino: Path) -> dict[str, pd.DataFrame]:
    pasta = Path(destino) / PASTA
    return {p.stem: pd.read_parquet(p) for p in sorted(pasta.glob("*.parquet"))}


def tratamento_disponivel(arm: Armazenamento) -> bool:
    return all(
        arm.existe(c)
        for c in (chaves.PROC_PLD, chaves.PROC_HORARIO, chaves.PROC_TIPOS, chaves.PROC_DELTA)
    ) and bool(tratamento.inventario_dessem(arm).completos)
