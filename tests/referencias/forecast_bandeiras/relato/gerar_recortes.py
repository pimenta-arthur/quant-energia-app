"""Gera os recortes de relato.rv0 usados nos testes do cálculo a partir do relato.

Mantém só o que os leitores usam (balanço por semana/subsistema/patamar, pequenas usinas, eco de Itaipu
e custo marginal), na ordem original, e comprime em .gz. Uso (a partir da raiz do app):

    uv run python tests/referencias/forecast_bandeiras/relato/gerar_recortes.py <pasta com os relatos>

Os relatos de origem não vão para o git (5 MB cada); os recortes sim.
"""

import gzip
import re
import sys
from pathlib import Path

MANTER = re.compile(
    r"SEMANA \d - ESTAGIO|^\s+Subsistema \w+\s*$|^\s*Mercado\b|^\s+Pat_\d|^\s+Med_\w+"
)
BLOCOS = (
    "Relatorio dos Dados de Pequenas Usinas",
    "Relatorio de eco  das informacoes de ITAIPU",
    "CUSTO MARGINAL DE OPERACAO",
)
# nome do recorte -> (origem relativa à pasta informada, descrição)
CASOS = {
    "ccee_2026-10": "ccee/2026_10_relato.rv0.gz",
    "ccee_2026-05": "ccee/2026_05_relato.rv0.gz",
    "ccee_2025-04": "ccee/2025_04_relato_1aPublicacao.rv0.gz",
    "ccee_2025-03": "ccee/2025_03_relato_2aPublicacao.rv0.gz",
    "ons_2026-10": "ons/2026-10/relato.rv0",
    "ons_2026-05": "ons/2026-05/relato.rv0",
    "ons_2025-04": "ons/2025-04/relato.rv0",
    "ons_2025-03": "ons/2025-03/relato.rv0",
}


def ler(caminho: Path) -> list[str]:
    dados = caminho.read_bytes()
    if caminho.suffix == ".gz":
        dados = gzip.decompress(dados)
    return dados.decode("latin-1").splitlines()


def recortar(linhas: list[str]) -> list[str]:
    saida, i = [], 0
    while i < len(linhas):
        ln = linhas[i]
        if any(b in ln for b in BLOCOS):
            fim = i + 1
            bordas = 0
            while fim < len(linhas) and bordas < 3:  # 2 bordas do cabeçalho + 1 de fechamento
                bordas += linhas[fim].strip().startswith("X-")
                fim += 1
            saida.extend(linhas[i:fim])
            i = fim
            continue
        if MANTER.search(ln):
            saida.append(ln)
        i += 1
    return saida


if __name__ == "__main__":
    origem = Path(sys.argv[1])
    destino = Path(__file__).parent
    for nome, rel in CASOS.items():
        linhas = recortar(ler(origem / rel))
        (destino / f"{nome}.txt.gz").write_bytes(
            gzip.compress("\n".join(linhas).encode("latin-1"), 9)
        )
        print(nome, len(linhas), "linhas")
