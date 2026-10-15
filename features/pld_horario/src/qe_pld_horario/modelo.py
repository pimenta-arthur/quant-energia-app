"""Definições do método do PLD horário, num único ponto (pesquisa: risk-lab-dessem-analytics).

Mudar uma definição ou parâmetro = versão nova do modelo (decisão registrada na pesquisa,
`qe pld_horario congelar`, tag `modelo-pld-<versão>`), como nas bandeiras.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Modelo:
    versao: str
    vale: tuple[int, ...]  # horas do vale (D054: 8h–15h)
    ponta: tuple[int, ...]  # horas da ponta (18h–21h)
    tol_piso: float  # hora no piso: PLD <= piso + tol_piso
    limiar_desvio: float  # hora abaixo/acima do DECOMP: desvio < −limiar ou > +limiar (D067)


V1 = Modelo(
    versao="v1",
    vale=tuple(range(8, 16)),
    ponta=tuple(range(18, 22)),
    tol_piso=0.005,
    limiar_desvio=0.5,
)

MODELO = V1
SUBMERCADOS = ["SE", "S", "NE", "N"]
TIPOS_DIA = ["útil", "sábado", "domingo/feriado"]
