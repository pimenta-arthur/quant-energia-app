"""Leitor do histórico oficial de bandeiras tarifárias da ANEEL (dados abertos)."""

from pathlib import Path

import pandas as pd

NOMES = {
    "Verde": "Verde",
    "Amarela": "Amarela",
    "Vermelha P1": "Vermelha 1",
    "Vermelha P2": "Vermelha 2",
}


def _nome(n: str) -> str:
    try:
        n = n.encode("latin-1").decode("utf-8")  # o arquivo vem com acentos em dupla codificação
    except UnicodeEncodeError, UnicodeDecodeError:
        pass
    return NOMES.get(n, "Escassez hídrica" if n.startswith("Escassez") else n)


def ler_historico_bandeiras(caminho: Path) -> pd.DataFrame:
    """Colunas: mes (AAAA-MM), cor, adicional (R$/MWh)."""
    h = pd.read_csv(caminho, sep=";", decimal=",")
    return pd.DataFrame(
        {
            "mes": h.DatCompetencia.str[:7],
            "cor": h.NomBandeiraAcionada.map(_nome),
            "adicional": h.VlrAdicionalBandeira.astype(float),
        }
    ).sort_values("mes", ignore_index=True)
