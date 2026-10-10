"""Ingestão: leva os arquivos brutos de uma pasta de origem para raw/ do armazenamento.

Fase local: a origem é uma pasta com os arquivos baixados manualmente, no layout do
forecast-bandeiras-analytics (data/raw). Fase AWS: um worker baixa das fontes e grava nas mesmas
chaves. raw/ é imutável: arquivo já gravado e diferente do novo não é sobrescrito sem pedido
explícito (exceto o histórico da ANEEL, que é um conjunto atualizado pela fonte).
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from qe_bandeiras import chaves
from qe_core.armazenamento import Armazenamento


@dataclass
class Item:
    fonte: str
    chave: str
    situacao: str  # novo | igual | divergente (mantido) | sobrescrito | ausente na origem


def _hash(caminho: Path) -> str:
    return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()


def _copiar(
    arm: Armazenamento, origem: Path | None, chave: str, fonte: str, sobrescrever: bool
) -> Item:
    if origem is None or not Path(origem).exists():
        return Item(fonte, chave, "ausente na origem")
    if arm.existe(chave):
        if _hash(arm.caminho_local(chave)) == _hash(origem):
            return Item(fonte, chave, "igual")
        if not sobrescrever:
            return Item(fonte, chave, "divergente (mantido)")
        arm.gravar_arquivo(Path(origem), chave)
        return Item(fonte, chave, "sobrescrito")
    arm.gravar_arquivo(Path(origem), chave)
    return Item(fonte, chave, "novo")


def _primeiro(padrao: str, pasta: Path) -> Path | None:
    return next(iter(sorted(pasta.glob(padrao))), None) if pasta.exists() else None


def ingerir_mes(
    arm: Armazenamento, origem: Path, m: pd.Period, sobrescrever: bool = False
) -> list[Item]:
    """Todos os arquivos de um mês: PMO, boletim, deck do NEWAVE, rodada do ECMWF e patamares do ano."""
    origem = Path(origem)
    a, mm = m.year, f"{m.month:02d}"
    itens = []
    pmo = origem / "ons_decomp" / str(a) / f"{a}_{mm}"
    for arq in chaves.ARQUIVOS_PMO:
        itens.append(_copiar(arm, pmo / arq, chaves.raw_pmo(m, arq), "ons_pmo", sobrescrever))
    boletim = _primeiro(f"*_{a}_{mm}.pdf", origem / "ccee_calculo_bandeira" / str(a))
    itens.append(_copiar(arm, boletim, chaves.raw_boletim(m), "ccee_boletim", sobrescrever))
    deck = origem / "ccee_newave" / str(a) / f"{a}_{mm}"
    if deck.exists():
        for arq in chaves.ARQUIVOS_NEWAVE:
            itens.append(
                _copiar(arm, deck / arq, chaves.raw_newave(m, arq), "ccee_newave", sobrescrever)
            )
    else:
        itens.append(Item("ccee_newave", chaves.raw_newave(m), "ausente na origem"))
    ecmwf = sorted((origem / "ecmwf_ena" / "ECENSLT_estat").glob(f"ECENSLT*_*/*_{a}{mm}01.txt"))
    ecmwf += sorted((origem / "ecmwf_ena" / "ECENSLTm" / f"{a}-{mm}").glob("*.txt"))
    if ecmwf:
        for arq in ecmwf:
            itens.append(_copiar(arm, arq, chaves.raw_ecmwf(m, arq.name), "ecmwf", sobrescrever))
    else:
        itens.append(Item("ecmwf", chaves.raw_ecmwf(m), "ausente na origem"))
    if not arm.existe(chaves.raw_patamares(a)):
        pat = _primeiro("AAC001*.xlsx", origem / "patamar" / str(a))
        itens.append(_copiar(arm, pat, chaves.raw_patamares(a), "ccee_patamares", sobrescrever))
    return itens


def ingerir_historico(arm: Armazenamento, origem: Path) -> Item:
    """Histórico oficial de bandeiras (ANEEL): sempre atualiza, é um conjunto mantido pela fonte."""
    return _copiar(
        arm, Path(origem) / "bandeiras" / "historico.csv", chaves.RAW_HISTORICO, "aneel", True
    )
