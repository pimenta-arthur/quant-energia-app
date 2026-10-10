"""Ingestão: leva os arquivos brutos de uma pasta de origem para raw/ do armazenamento.

Fase local: a origem é uma pasta com os arquivos baixados manualmente, no layout do
forecast-bandeiras-analytics (data/raw). Fase AWS: um worker baixa das fontes e grava nas mesmas
chaves. raw/ é imutável: arquivo já gravado e diferente do novo não é sobrescrito sem pedido
explícito (exceto o histórico da ANEEL, que é um conjunto atualizado pela fonte).

Versões: o deck do NEWAVE é guardado por mês e versão (hash do conteúdo), e o ECMWF por data de
emissão. Uma republicação do deck ou uma emissão extra do ECMWF entram como versões novas, ao lado
das anteriores.
"""

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from qe_bandeiras import chaves
from qe_core.armazenamento import Armazenamento, gravar_json


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


def versao_deck(pasta: Path) -> str:
    """Versão do deck = 8 primeiros caracteres do hash do conteúdo dos arquivos usados."""
    h = hashlib.sha256()
    for arq in chaves.ARQUIVOS_NEWAVE:
        caminho = Path(pasta) / arq
        h.update(arq.encode())
        h.update(_hash(caminho).encode() if caminho.exists() else b"-")
    return h.hexdigest()[:8]


def ingerir_deck(arm: Armazenamento, pasta: Path, deck: pd.Period) -> list[Item]:
    """Um deck do NEWAVE como nova versão (ou 'igual', se o conteúdo já foi ingerido)."""
    versao = versao_deck(pasta)
    itens = [
        _copiar(arm, Path(pasta) / arq, chaves.raw_newave(deck, versao, arq), "ccee_newave", False)
        for arq in chaves.ARQUIVOS_NEWAVE
    ]
    marca = chaves.raw_newave(deck, versao, "_ingestao.json")
    if not arm.existe(marca):
        gravar_json(
            arm,
            {"ingerido_em": datetime.now().isoformat(timespec="seconds"), "origem": str(pasta)},
            marca,
        )
    return itens


def emissao_do_arquivo(caminho: Path) -> str:
    """Data de emissão do ECMWF (AAAA-MM-DD) a partir do fim do nome do arquivo (…_AAAAMMDD.txt)."""
    data = re.search(r"_(\d{8})\.txt$", Path(caminho).name).group(1)
    return f"{data[:4]}-{data[4:6]}-{data[6:]}"


def ingerir_mes(
    arm: Armazenamento, origem: Path, m: pd.Period, sobrescrever: bool = False
) -> list[Item]:
    """Arquivos de um mês: PMO, boletim, deck do NEWAVE, emissões do ECMWF do mês e patamares do ano."""
    origem = Path(origem)
    a, mm = m.year, f"{m.month:02d}"
    itens = []
    pmo = origem / "ons_decomp" / str(a) / f"{a}_{mm}"
    for arq in chaves.ARQUIVOS_PMO:
        itens.append(_copiar(arm, pmo / arq, chaves.raw_pmo(m, arq), "ons_pmo", sobrescrever))
    boletim = _primeiro(f"*_{a}_{mm}.pdf", origem / "ccee_calculo_bandeira" / str(a))
    itens.append(_copiar(arm, boletim, chaves.raw_boletim(m), "ccee_boletim", sobrescrever))
    deck = origem / "ccee_newave" / str(a) / f"{a}_{mm}"
    if (deck / "ghtotsin.out").exists():  # há pastas de mês vazias na origem
        itens += ingerir_deck(arm, deck, m)
    else:
        itens.append(Item("ccee_newave", f"{chaves.RAW_NEWAVE}/deck={m}", "ausente na origem"))
    # todas as emissões com data dentro do mês (a habitual, no dia 1, e eventuais extras)
    ecmwf = sorted((origem / "ecmwf_ena" / "ECENSLT_estat").glob(f"ECENSLT*_*/*_{a}{mm}??.txt"))
    ecmwf += sorted((origem / "ecmwf_ena" / "ECENSLTm" / f"{a}-{mm}").glob("*.txt"))
    for arq in ecmwf:
        chave = chaves.raw_ecmwf(emissao_do_arquivo(arq), arq.name)
        itens.append(_copiar(arm, arq, chave, "ecmwf", sobrescrever))
    if not ecmwf:
        itens.append(Item("ecmwf", f"{chaves.RAW_ECMWF}/{m}", "ausente na origem"))
    if not arm.existe(chaves.raw_patamares(a)):
        pat = _primeiro("AAC001*.xlsx", origem / "patamar" / str(a))
        itens.append(_copiar(arm, pat, chaves.raw_patamares(a), "ccee_patamares", sobrescrever))
    return itens


def ingerir_historico(arm: Armazenamento, origem: Path) -> Item:
    """Histórico oficial de bandeiras (ANEEL): sempre atualiza, é um conjunto mantido pela fonte."""
    return _copiar(
        arm, Path(origem) / "bandeiras" / "historico.csv", chaves.RAW_HISTORICO, "aneel", True
    )
