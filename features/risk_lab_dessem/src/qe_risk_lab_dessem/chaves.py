"""Chaves de armazenamento da funcionalidade do PLD horário.

raw/ é por fonte (compartilhado: o descolamento entre submercados vai usar os mesmos decks);
processed/ e serving/ são desta funcionalidade. As mesmas chaves valem no disco local e no S3.

- PLD publicado: um csv por ano, substituído a cada republicação da CCEE (conjunto da fonte);
- DESSEM: um deck por dia (dia=AAAA-MM-DD), só os arquivos usados, em .gz;
- DECOMP: um deck por semana operativa e publicação (pmo=AAAA-MM/sem=N/pub=K), em .gz. Uma
  republicação da semana entra ao lado da anterior; o tratamento usa a mais recente.
"""

from qe_core.fontes import (  # noqa: F401 — raw/ das fontes comuns: definido em qe_core.fontes
    ARQUIVOS_DESSEM,
    MARCA_DESSEM,
    OPCIONAIS_DESSEM,
    RAW_DESSEM,
    RAW_LIMITES,
    RAW_PLD,
    raw_dessem,
    raw_pld,
)

RAW_DECOMP = "raw/ccee_decomp"


def raw_decomp(pmo: str, sem: int, pub: int, arquivo: str = "") -> str:
    return f"{RAW_DECOMP}/pmo={pmo}/sem={sem}/pub={pub}/{arquivo}"


# arquivos usados do DECOMP: prefixo do nome dentro do zip → nome guardado
ARQUIVOS_DECOMP = {"deck": ("dadger", "dadger.gz"), "relatorio": ("sumario", "sumario.gz")}

PROC = "processed/risk_lab_dessem"


def proc_dessem(tabela: str, mes: str) -> str:
    """Tabelas lidas dos decks do DESSEM, uma partição por mês civil do dia do caso."""
    return f"{PROC}/dessem/{tabela}/mes={mes}.parquet"


PROC_DECOMP = f"{PROC}/decomp_cmo.parquet"  # CMO, horas e carga por semana, estágio e patamar
PROC_PLD = f"{PROC}/pld_horario.parquet"  # T1: publicado + calculado do deck
PROC_HORARIO = f"{PROC}/mensal_horario.parquet"  # T2: hora a hora com o DECOMP vigente
PROC_TIPOS = f"{PROC}/tipos_de_dia.parquet"  # T3
PROC_DELTA = f"{PROC}/mensal_delta.parquet"  # T5: desvio do mês civil por bloco
PROC_BACKTEST = f"{PROC}/backtest_simulador.parquet"  # bloco 7: v1 simplificada, fora da amostra

SERVING = "serving/risk_lab_dessem"
# Registro das rodadas publicadas do simulador, como foram publicadas (não apagar nem recalcular);
# versionado no git até a fase AWS, como o das bandeiras.
SERVING_REGISTRO = f"{SERVING}/historico_simulador.json"


def serving(nome: str) -> str:
    """Dados da página: um JSON por chave, lido em /dados/risk_lab_dessem/<nome>.json."""
    return f"{SERVING}/{nome}.json"
