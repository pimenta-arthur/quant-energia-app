"""Peças comuns da caixa de entrada (data/entrada/<fonte>/ → raw/), usadas pela ingestão de cada
funcionalidade.

Regras (docs/entrada.md): grava em raw/ só o que é usado, relê e confere o hash, e só então apaga o
original da entrada. raw/ é imutável: arquivo já gravado e diferente do novo não é substituído sem
`sobrescrever`. O que não for reconhecido fica na entrada, com o motivo.
"""

import gzip
import hashlib
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

from qe_core.armazenamento import Armazenamento


class NaoReconhecido(Exception):
    """O pacote fica na entrada; a mensagem diz o que faltou."""


@dataclass
class Resultado:
    fonte: str
    origem: str
    removido: bool
    mensagem: str
    gravados: dict[str, str] = field(default_factory=dict)  # chave → novo | igual | sobrescrito
    meses: set[pd.Period] = field(default_factory=set)  # meses cujo tratamento muda

    @property
    def novo(self) -> bool:
        return any(s in ("novo", "sobrescrito") for s in self.gravados.values())


def sha(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def gravar_conferido(arm: Armazenamento, chave: str, dados: bytes, sobrescrever: bool) -> str:
    """Grava em raw/ e confere a releitura: novo | igual | sobrescrito | divergente (não gravado)."""
    if arm.existe(chave):
        if sha(arm.ler_bytes(chave)) == sha(dados):
            return "igual"
        if not sobrescrever:
            return "divergente"
        situacao = "sobrescrito"
    else:
        situacao = "novo"
    arm.gravar_bytes(dados, chave)
    if sha(arm.ler_bytes(chave)) != sha(dados):
        raise OSError(f"conferência falhou ao gravar {chave}")
    return situacao


def gravar_comprimido(arm: Armazenamento, chave: str, dados: bytes, sobrescrever: bool) -> str:
    """Como `gravar_conferido`, para arquivos guardados em .gz (`chave` termina em .gz).

    O que se compara e confere é o conteúdo original (descomprimido). O gzip sai sem data no
    cabeçalho, então o mesmo conteúdo dá sempre os mesmos bytes.
    """
    if arm.existe(chave):
        if sha(gzip.decompress(arm.ler_bytes(chave))) == sha(dados):
            return "igual"
        if not sobrescrever:
            return "divergente"
        situacao = "sobrescrito"
    else:
        situacao = "novo"
    arm.gravar_bytes(gzip.compress(dados, compresslevel=6, mtime=0), chave)
    if sha(gzip.decompress(arm.ler_bytes(chave))) != sha(dados):
        raise OSError(f"conferência falhou ao gravar {chave}")
    return situacao


def remover(item: Path) -> None:
    shutil.rmtree(item) if item.is_dir() else item.unlink()


def itens(pasta: Path) -> list[Path]:
    """O que foi solto na pasta da fonte (arquivos e pastas), sem os ocultos."""
    return sorted(p for p in pasta.iterdir() if not p.name.startswith("."))


def gravar_relatorio(entrada: Path, resultados: list[Resultado], prefixo: str = "") -> None:
    """Relatório da execução em entrada/relatorios/<prefixo><data e hora>.txt."""
    if not resultados:
        return
    linhas = []
    for r in resultados:
        linhas.append(f"{r.fonte}/{r.origem}: {r.mensagem}")
        linhas += [f"    {s}: {c}" for c, s in r.gravados.items() if s != "igual"]
    pasta = entrada / "relatorios"
    pasta.mkdir(parents=True, exist_ok=True)
    nome = prefixo + datetime.now().strftime("%Y-%m-%dT%H-%M-%S") + ".txt"
    (pasta / nome).write_text("\n".join(linhas) + "\n", encoding="utf-8")
