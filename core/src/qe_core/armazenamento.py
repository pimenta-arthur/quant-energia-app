"""Armazenamento de dados por chave, com o mesmo formato de chave no disco local e no S3.

Camadas (prefixo da chave):
- raw/<fonte>/...                 arquivo original, nunca alterado depois de gravado
- processed/<funcionalidade>/...  tabelas tratadas (Parquet)
- serving/<funcionalidade>/...    o que as páginas leem (JSON/JS)

As etapas nunca abrem caminhos diretamente: pedem ao armazenamento. Trocar local por S3 é
configuração (QE_ARMAZENAMENTO), não mudança de código.
"""

import io
import json
import shutil
from pathlib import Path
from typing import Protocol

import pandas as pd

from qe_core.config import Configuracao, configuracao


class Armazenamento(Protocol):
    def existe(self, chave: str) -> bool: ...
    def listar(self, prefixo: str) -> list[str]: ...
    def caminho_local(self, chave: str) -> Path:
        """Caminho de um arquivo legível localmente (no S3, baixa para o cache)."""
        ...

    def gravar_arquivo(self, origem: Path, chave: str) -> None: ...
    def gravar_bytes(self, dados: bytes, chave: str) -> None: ...
    def ler_bytes(self, chave: str) -> bytes: ...


class ArmazenamentoLocal:
    """Disco local; a raiz imita o bucket (data/raw, data/processed, data/serving)."""

    def __init__(self, raiz: Path):
        self.raiz = Path(raiz)

    def _caminho(self, chave: str) -> Path:
        return self.raiz / chave

    def existe(self, chave: str) -> bool:
        return self._caminho(chave).exists()

    def listar(self, prefixo: str) -> list[str]:
        base = self._caminho(prefixo)
        if not base.exists():
            return []
        return sorted(str(p.relative_to(self.raiz)) for p in base.rglob("*") if p.is_file())

    def caminho_local(self, chave: str) -> Path:
        caminho = self._caminho(chave)
        if not caminho.exists():
            raise FileNotFoundError(f"chave inexistente no armazenamento: {chave}")
        return caminho

    def gravar_arquivo(self, origem: Path, chave: str) -> None:
        destino = self._caminho(chave)
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origem, destino)

    def gravar_bytes(self, dados: bytes, chave: str) -> None:
        destino = self._caminho(chave)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(dados)

    def ler_bytes(self, chave: str) -> bytes:
        return self.caminho_local(chave).read_bytes()


class ArmazenamentoS3:
    """Bucket S3 (fase AWS). Mesmas chaves do armazenamento local."""

    def __init__(self, bucket: str, cache: Path):
        self.bucket, self.cache = bucket, Path(cache)

    def _nao_implementado(self, *_):
        raise NotImplementedError("armazenamento S3 entra na fase AWS (boto3)")

    existe = listar = caminho_local = gravar_arquivo = gravar_bytes = ler_bytes = _nao_implementado


def armazenamento(cfg: Configuracao | None = None) -> Armazenamento:
    cfg = cfg or configuracao()
    if cfg.armazenamento == "s3":
        if not cfg.bucket:
            raise ValueError("QE_BUCKET é obrigatório com QE_ARMAZENAMENTO=s3")
        return ArmazenamentoS3(cfg.bucket, cfg.cache)
    return ArmazenamentoLocal(cfg.dados)


# --- formatos usados pelas etapas -------------------------------------------------------------


def gravar_parquet(arm: Armazenamento, df: pd.DataFrame, chave: str) -> None:
    buffer = io.BytesIO()
    df.to_parquet(buffer)
    arm.gravar_bytes(buffer.getvalue(), chave)


def ler_parquet(arm: Armazenamento, chave: str) -> pd.DataFrame:
    return pd.read_parquet(io.BytesIO(arm.ler_bytes(chave)))


def gravar_json(arm: Armazenamento, obj, chave: str) -> None:
    arm.gravar_bytes(json.dumps(obj, ensure_ascii=False, indent=1).encode("utf-8"), chave)


def ler_json(arm: Armazenamento, chave: str):
    return json.loads(arm.ler_bytes(chave).decode("utf-8"))
