"""Definições e parâmetros do método do PLD horário, num único ponto (pesquisa: risk-lab-dessem-analytics).

Mudar uma definição ou parâmetro = versão nova do modelo (decisão registrada na pesquisa,
`qe risk_lab_dessem congelar`, tag `risk_lab_dessem-modelo-<versão>`), como nas bandeiras.
"""

from dataclasses import asdict, dataclass, replace


@dataclass(frozen=True)
class Modelo:
    versao: str
    # definições do acompanhamento (blocos 1 a 6)
    vale: tuple[int, ...]  # horas do vale (D054: 8h–15h)
    ponta: tuple[int, ...]  # horas da ponta (18h–21h)
    tol_piso: float  # hora no piso: PLD <= piso + tol_piso
    limiar_desvio: float  # hora abaixo/acima do DECOMP: desvio < −limiar ou > +limiar (D067)
    # simulador do PLD médio do mês, v1 simplificada (bloco 7; D057, D058, D061–D063, D073)
    janela: int  # dias da janela das horas no piso e do prêmio da ponta (D057, dentro da amostra)
    meses_ref_fora: int  # meses civis encerrados para o desconto das outras horas (D061)
    # desconto das outras horas: True = um número só para os três tipos de dia, medido em todas as horas fora da
    # ponta e do piso (D087); False = um por tipo de dia (D061)
    desconto_unico: bool
    espaco_min: float  # R$/MWh: piso do espaço DECOMP − piso nas frações e meses aceitos (D061)
    limiar_direcao: float  # R$/MWh: desconto < −limiar < neutro < +limiar < prêmio
    janelas_pagina: tuple[int, ...]  # janelas mostradas no quadro de premissas
    estresse_meses: int  # meses encerrados para os níveis de estresse da ponta (D056)
    q_estresse: tuple[float, float]  # quantis do prêmio mensal: (com estresse, sem estresse)
    q_sensibilidade: float  # preço padrão da sensibilidade: quantil da ponta no mês (D073)
    pct_sensibilidade: int  # % padrão dos dias úteis no preço da sensibilidade (D073, D076)
    backtest_inicio: str  # primeiro mês-alvo do backtest
    horizontes: int  # antecedências de 1 a `horizontes` meses
    regime_desde: str  # meses usados na confiança e na faixa 10–90% (regime atual)
    meses_a_frente: int  # meses no calendário do simulador

    def como_dict(self) -> dict:
        return asdict(self)


V1 = Modelo(
    versao="v1",
    vale=tuple(range(8, 16)),
    ponta=tuple(range(18, 22)),
    tol_piso=0.005,
    limiar_desvio=0.5,
    janela=14,
    meses_ref_fora=12,
    desconto_unico=False,
    espaco_min=20.0,
    limiar_direcao=5.0,
    janelas_pagina=(7, 14, 30, 60, 90),
    estresse_meses=12,
    q_estresse=(0.8, 0.2),
    q_sensibilidade=0.9,
    pct_sensibilidade=5,
    backtest_inicio="2024-07",
    horizontes=6,
    regime_desde="2025-03",
    meses_a_frente=6,
)

# v2 (pesquisa: D087, tag promocao-quant-v3): desconto das outras horas num número só para os três tipos de dia
V2 = replace(V1, versao="v2", desconto_unico=True)

MODELO = V2
SUBMERCADOS = ["SE", "S", "NE", "N"]
TIPOS_DIA = ["útil", "sábado", "domingo/feriado"]

# Feriados nacionais dos meses ainda sem deck (pesquisa: simulador.FERIADOS_FUTUROS). Lacuna L3: a
# recomendação é usar o AAC001 da CCEE depois de conferir a equivalência com "sem patamar pesado".
# Não é parâmetro do método: é calendário; ampliar quando o horizonte do simulador passar de mar/2027.
FERIADOS_FUTUROS = [
    "2026-10-12",
    "2026-11-02",
    "2026-11-15",
    "2026-11-20",
    "2026-12-25",
    "2027-01-01",
    "2027-02-08",
    "2027-02-09",
    "2027-03-26",
]
