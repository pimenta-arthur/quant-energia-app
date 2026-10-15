"""Referências congeladas de uma versão do modelo: os resultados esperados para os dados atuais.

Servem de rede de segurança nos testes: se uma mudança de código altera algum resultado sem
querer, o teste falha. Quando a mudança é intencional (dados novos no histórico ou versão nova do
modelo), regera-se com `qe forecast_bandeiras congelar` e a diferença aparece no commit para revisão.

Conteúdo (um JSON por parte), só no período fechado (decks e meses-alvo até `ATE`): backtest
(previsões com bandeira oficial), oráculo, rodadas reconstruídas e a projeção da rodada de referência (deck de set/2026 com a emissão de 01/09/2026,
a mesma publicada pelo forecast-bandeiras-analytics).
"""

import json
from pathlib import Path

import pandas as pd

from qe_core.armazenamento import Armazenamento
from qe_forecast_bandeiras import backtest, insumos, modelo, projecao

RODADA_REFERENCIA = ("2026-09", "2026-09-01")  # (deck, emissão do ECMWF)
# período fechado: decks e meses-alvo até aqui não mudam com dados novos (o backtest só usa o que
# existia na data de cada deck), então um deck ou uma bandeira oficial nova não quebra os testes
ATE = "2026-09"
CASAS = 6


def _registros(df: pd.DataFrame, colunas: list[str]) -> list[dict]:
    saida = []
    for r in df[colunas].itertuples(index=False):
        linha = {}
        for c, v in zip(colunas, r):
            if isinstance(v, pd.Period):
                v = str(v)
            elif isinstance(v, float):
                v = None if pd.isna(v) else round(v, CASAS)
            elif hasattr(v, "item"):
                v = v.item()
            linha[c] = v
        saida.append(linha)
    return saida


def calcular(arm: Armazenamento) -> dict[str, list | dict]:
    """Recalcula tudo com o código atual, sem gravar nada no armazenamento."""
    bt = backtest.rodar(arm, gravar=False)
    deck, emissao = RODADA_REFERENCIA
    ins = insumos.Insumos(deck, insumos.versao_atual(arm, pd.Period(deck, "M")), emissao)
    cen = projecao.projetar(arm, ins, bt["referencia"], gravar=False)
    cen = cen.rename(columns=lambda c: c.replace(" ", "_"))
    cenarios = [f"{k}_{n}" for n in ("esp", "li", "ls") for k in ("gsf", "pld", "cor")]
    base = ["deck", "alvo", "h", "gsf_medio", "pld_medio", "cor_media"]
    fechado = lambda rs: [r for r in rs if r["deck"] <= ATE and r["alvo"] <= ATE]
    return {
        "modelo": modelo.MODELO.como_dict(),
        "backtest": fechado(_registros(bt["referencia"], base + ["cor_oficial"])),
        "oraculo": fechado(_registros(bt["oraculo"], base)),
        "rodadas": [
            r
            for r in _registros(
                bt["rodadas"], ["deck", "alvo", "h", "cor_esp", "cor_li", "cor_ls", "prob"]
            )
            if r["deck"] <= ATE
        ],
        "projecao_referencia": _registros(
            cen, ["alvo", "h", *cenarios, "p_Verde", "p_Amarela", "p_Vermelha_1", "p_Vermelha_2"]
        ),
    }


def pasta(raiz: Path, versao: str | None = None) -> Path:
    return Path(raiz) / (versao or modelo.MODELO.versao)


def congelar(arm: Armazenamento, raiz: Path) -> Path:
    destino = pasta(raiz)
    destino.mkdir(parents=True, exist_ok=True)
    for nome, conteudo in calcular(arm).items():
        (destino / f"{nome}.json").write_text(
            json.dumps(conteudo, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
    return destino


def carregar(raiz: Path, versao: str | None = None) -> dict:
    p = pasta(raiz, versao)
    return {a.stem: json.loads(a.read_text(encoding="utf-8")) for a in sorted(p.glob("*.json"))}


# --- tratamento (não depende da versão do modelo) --------------------------------------------------

COLUNAS_MENSAL = [
    "gh_ons", "ande", "gh_band", "carga_bruta", "mmgd", "termica", "pch", "ena_sin", "ena_mlt_sin",
    "ear_ini_sin", "gf_band_boletim", "gsf_band_boletim", "pld_gatilho_boletim", "pld_min_boletim",
    "pld_max_boletim", "gsf_calc", "cor_regra",
]  # fmt: skip
DECK_REFERENCIA, ALVO_DECK_REFERENCIA = "2026-09", "2026-10"


def calcular_tratamento(arm: Armazenamento) -> dict[str, list | dict]:
    """Base mensal (PMO + boletim) e a ENA do SIN por série do deck de referência no primeiro mês-alvo."""
    from qe_core.armazenamento import ler_parquet
    from qe_forecast_bandeiras import chaves, tratamento

    base = tratamento.base_mensal(arm)
    mensal = _registros(base.reset_index(names="mes"), ["mes", *COLUNAS_MENSAL])
    m = pd.Period(DECK_REFERENCIA, "M")
    ena = ler_parquet(arm, chaves.proc_newave(m, insumos.versao_atual(arm, m), "ena"))
    sin = ena[ena.periodo == ALVO_DECK_REFERENCIA].groupby("serie").valor.sum()
    return {
        "base_mensal": mensal,
        "deck_ena_sin": {
            "deck": DECK_REFERENCIA,
            "alvo": ALVO_DECK_REFERENCIA,
            "por_serie": [round(float(v), CASAS) for v in sin.sort_index()],
        },
    }


def congelar_tratamento(arm: Armazenamento, raiz: Path) -> Path:
    destino = Path(raiz) / "tratamento"
    destino.mkdir(parents=True, exist_ok=True)
    for nome, conteudo in calcular_tratamento(arm).items():
        (destino / f"{nome}.json").write_text(
            json.dumps(conteudo, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
    return destino
