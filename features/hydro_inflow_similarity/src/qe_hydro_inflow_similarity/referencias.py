"""Referências congeladas da projeção de ENA (tests/referencias/hydro_inflow_similarity/).

Na migração (2026-10-24), as saídas do app foram conferidas contra o pacote de promoção da pesquisa
(hydro-inflow-similarity-analytics, tag promocao-quant-v1, reports/promocao/2026-09/; teste opt-in
tests/test_hydro_inflow_similarity_paridade.py): leitores, tabelas-base, modelo-v1, atualização, similares, rodada e os
quatro JSON das páginas, sem diferença. Aqui só entram períodos que não mudam com dados novos nem com a revisão da
ENA diária de 2025–2026 pelo ONS: a ENA e os índices até dez/2024, a MLT, e o modelo-v1, os membros e os anos
similares emitidos em set/2024 (dados até ela), o CRPS médio do backtest com emissões até 2023 e alvos até jun/2024 e
a camada de El Niño forte dos eventos até 2016. Regerar só quando a mudança for intencional:
`uv run qe hydro_inflow_similarity congelar` e revisar a diferença no git.
"""

import json
from pathlib import Path

import pandas as pd

from qe_core.armazenamento import Armazenamento, ler_parquet
from qe_hydro_inflow_similarity import backtest as B
from qe_hydro_inflow_similarity import chaves
from qe_hydro_inflow_similarity import modelo as M
from qe_hydro_inflow_similarity import similares as S

PASTA = "hydro_inflow_similarity"
FIM = pd.Timestamp("2024-12-01")  # último mês da planilha (não muda)
EMISSAO = pd.Timestamp("2024-09-01")  # emissão de referência do modelo


def calcular(arm: Armazenamento) -> dict[str, pd.DataFrame]:
    ena = ler_parquet(arm, chaves.PROC_ENA)
    ind = ler_parquet(arm, chaves.PROC_INDICES)
    e, i = ena[ena.data <= EMISSAO], ind[ind.index <= EMISSAO]
    series, (blocos, mlts) = M.montar_series(e, i), M.montar_blocos(e, i)
    t = M.posicao(EMISSAO)
    membros = pd.DataFrame(
        [
            (n, h, k, float(v))
            for n in M.NOMES
            for h in range(1, 7)
            for k, v in enumerate(M.membros_v1(series, blocos, mlts, n, t, h))
        ],
        columns=["nome", "h", "membro", "valor"],
    )
    sim = S.recompor(series, blocos, mlts, t)
    similares = pd.DataFrame(
        [
            (n, x["h"], ano, v)
            for n, lista in sim["por_nome"].items()
            for x in lista
            for ano, v in x["anos"].items()
        ],
        columns=["nome", "h", "ano", "valor"],
    )
    res = ler_parquet(arm, chaves.PROC_BACKTEST)
    res = res[(res.t <= M.posicao("2023-12-01")) & (res.alvo <= "2024-06-01")]
    crps = res.groupby(["metodo", "nome", "h"]).crps.mean().reset_index()
    vies = B.tabela_vies(res, M.montar_series(ena, ind)["SE"].enso3)
    vies = vies[vies.index.str[:4].astype(int) <= 2016].reset_index()
    return {
        "ena_mensal": ena[ena.data <= FIM].reset_index(drop=True),
        "mlt": ler_parquet(arm, chaves.PROC_MLT),
        "indices_mensais": ind[ind.index <= FIM],
        "modelo_v1": M.prever_v1(e, i, EMISSAO),
        "membros_v1": membros,
        "similares": similares,
        "backtest_crps": crps,
        "vies_el_nino_forte": vies,
    }


def congelar(arm: Armazenamento, destino: Path) -> Path:
    pasta = Path(destino) / PASTA
    pasta.mkdir(parents=True, exist_ok=True)
    for nome, df in calcular(arm).items():
        df.to_parquet(pasta / f"{nome}.parquet")
    (pasta / "manifesto.json").write_text(
        json.dumps(
            {"fim": f"{FIM:%Y-%m}", "emissao": f"{EMISSAO:%Y-%m}", "versao": M.MODELO.versao},
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    return pasta


def ler_congeladas(destino: Path) -> dict[str, pd.DataFrame]:
    return {p.stem: pd.read_parquet(p) for p in sorted((Path(destino) / PASTA).glob("*.parquet"))}
