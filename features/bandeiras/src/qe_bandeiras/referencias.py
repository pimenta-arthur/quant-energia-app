"""Referências congeladas de uma versão do modelo: os resultados esperados para os dados atuais.

Servem de rede de segurança nos testes: se uma mudança de código altera algum resultado sem
querer, o teste falha. Quando a mudança é intencional (dados novos no histórico ou versão nova do
modelo), regera-se com `qe bandeiras congelar` e a diferença aparece no commit para revisão.

Conteúdo (um JSON por parte): backtest (previsões com bandeira oficial), oráculo, rodadas
reconstruídas e a projeção da rodada de referência (deck de set/2026 com a emissão de 01/09/2026,
a mesma publicada pelo forecast-bandeiras-analytics).
"""

import json
from pathlib import Path

import pandas as pd

from qe_bandeiras import backtest, insumos, modelo, projecao
from qe_core.armazenamento import Armazenamento

RODADA_REFERENCIA = ("2026-09", "2026-09-01")  # (deck, emissão do ECMWF)
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
    return {
        "modelo": modelo.MODELO.como_dict(),
        "backtest": _registros(bt["referencia"], base + ["cor_oficial"]),
        "oraculo": _registros(bt["oraculo"], base),
        "rodadas": _registros(
            bt["rodadas"], ["deck", "alvo", "h", "cor_esp", "cor_li", "cor_ls", "prob"]
        ),
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
