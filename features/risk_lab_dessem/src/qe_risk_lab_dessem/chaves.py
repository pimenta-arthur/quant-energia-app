"""Chaves de armazenamento da funcionalidade do PLD horário.

raw/ é por fonte (compartilhado: o descolamento entre submercados vai usar os mesmos decks);
processed/ e serving/ são desta funcionalidade. As mesmas chaves valem no disco local e no S3.

- PLD publicado: um csv por ano, substituído a cada republicação da CCEE (conjunto da fonte);
- DESSEM: um deck por dia (dia=AAAA-MM-DD), só os arquivos usados, em .gz;
- DECOMP: um deck por semana operativa e publicação (pmo=AAAA-MM/sem=N/pub=K), em .gz. Uma
  republicação da semana entra ao lado da anterior; o tratamento usa a mais recente.
"""

import datetime as dt

RAW_PLD = "raw/ccee_pld"
RAW_LIMITES = "raw/ccee_limites_pld/dados_pld.csv"
RAW_DESSEM = "raw/ccee_dessem"
RAW_DECOMP = "raw/ccee_decomp"


def raw_pld(ano: int) -> str:
    return f"{RAW_PLD}/pld_horario_{ano}.csv"


def raw_dessem(dia: dt.date, arquivo: str = "") -> str:
    return f"{RAW_DESSEM}/dia={dia:%Y-%m-%d}/{arquivo}"


def raw_decomp(pmo: str, sem: int, pub: int, arquivo: str = "") -> str:
    return f"{RAW_DECOMP}/pmo={pmo}/sem={sem}/pub={pub}/{arquivo}"


# arquivos usados de cada metade do deck diário do DESSEM (nome no zip → guardado como <nome>.gz);
# PDO_OPER_USIH.DAT é opcional (ausente ou truncado em alguns decks: o dia fica sem esse dado)
ARQUIVOS_DESSEM = {
    "entrada": ["entdados.dat", "renovaveis.dat"],
    "resultado": ["PDO_SIST.DAT", "PDO_OPER_USIH.DAT"],
}
OPCIONAIS_DESSEM = {"PDO_OPER_USIH.DAT"}
# marca de cada metade ingerida: nome do zip, PMO, revisão e hash dos originais
MARCA_DESSEM = {"entrada": "_entrada.json", "resultado": "_resultado.json"}
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

SERVING = "serving/risk_lab_dessem"


def serving(nome: str) -> str:
    """Dados da página: um JSON por chave, lido em /dados/risk_lab_dessem/<nome>.json."""
    return f"{SERVING}/{nome}.json"
