"""Chaves de armazenamento do descolamento NE e N.

raw/ é por fonte e todas as fontes daqui são comuns (qe_core.fontes): deck do NEWAVE (conjunto sistema_agrint),
DESSEM (PDO_SIST e PDO_RESTOPER do dia), PLD publicado e limites. processed/ e serving/ são desta funcionalidade.
"""

from qe_core.fontes import (  # noqa: F401 — raw/ das fontes comuns: definido em qe_core.fontes
    RAW_DESSEM,
    RAW_LIMITES,
    RAW_NEWAVE,
    RAW_PLD,
    raw_dessem,
    raw_pld,
)

PROC = "processed/pricing_descolamento"
# T1: PLD publicado, horário (uma coluna por submercado) e mensal (só meses completos)
PROC_PLD_HORARIO = f"{PROC}/pld_horario.parquet"
PROC_PLD_MENSAL = f"{PROC}/pld_mensal.parquet"
# T2: projeções de cada deck do NEWAVE (última publicação)
PROC_DECK = {t: f"{PROC}/deck_{t}.parquet" for t in ("mercado", "nao_simuladas", "agrint")}
# T5: base horária
PROC_BASE = f"{PROC}/base_horaria.parquet"
# backtest da página (metodologia): modelo vigente em 16 decks, SE realizado como insumo
PROC_BACKTEST = f"{PROC}/backtest.parquet"


def proc_dessem(tabela: str, mes: str) -> str:
    """T3 (`sist`: balanço horário) e T4 (`re`: restrições de intercâmbio horárias), uma partição por mês."""
    return f"{PROC}/dessem/{tabela}/mes={mes}.parquet"


SERVING = "serving/pricing_descolamento"
# registro das rodadas publicadas (uma linha por rodada, com o descolamento no SE de referência): não apagar nem
# recalcular; as linhas de jan/2025 a out/2026 vêm da pesquisa (legado, reconstruídas até set/2026)
SERVING_REGISTRO = f"{SERVING}/historico_rodadas.json"


def serving(nome: str) -> str:
    return f"{SERVING}/{nome}.json"
