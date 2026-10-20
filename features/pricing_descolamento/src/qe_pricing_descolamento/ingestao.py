"""Ingestão do descolamento: da caixa de entrada (data/entrada/<fonte>/) para raw/.

Todas as fontes são comuns a outras funcionalidades e são ingeridas por qe_core.fontes, que grava em raw/ o que
qualquer funcionalidade usa (aqui: o conjunto sistema_agrint do deck do NEWAVE, o PDO_SIST e o PDO_RESTOPER do
DESSEM, o PLD publicado e os limites). Formato de cada fonte: docs/entrada.md.
"""

from pathlib import Path

from qe_core import fontes
from qe_core.armazenamento import Armazenamento
from qe_core.entrada import Resultado, gravar_relatorio, itens

FONTES = {
    f: fontes.COMUNS[f] for f in ("ccee_newave", "ccee_dessem", "ccee_pld", "ccee_limites_pld")
}
PREFIXO_RELATORIO = "pricing_descolamento_"


def preparar_entrada(entrada: Path) -> None:
    for fonte in FONTES:
        (entrada / fonte).mkdir(parents=True, exist_ok=True)
    (entrada / "relatorios").mkdir(parents=True, exist_ok=True)


def ingerir_entrada(
    arm: Armazenamento, entrada: Path, sobrescrever: bool = False, aviso=None
) -> list[Resultado]:
    """Ingere tudo o que estiver em entrada/<fonte>/ das fontes desta funcionalidade e grava um relatório."""
    preparar_entrada(entrada)
    resultados = []
    for fonte in FONTES:
        for item in itens(entrada / fonte):
            r = fontes.ingerir_pacote(arm, fonte, item, sobrescrever)
            resultados.append(r)
            if aviso:
                aviso(f"{r.fonte}/{r.origem}: {r.mensagem}")
    gravar_relatorio(entrada, resultados, PREFIXO_RELATORIO)
    return resultados
