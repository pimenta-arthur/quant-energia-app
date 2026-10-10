"""Configuração da aplicação, lida de variáveis de ambiente (prefixo QE_) ou do arquivo .env.

Local (padrão): os dados ficam em ./data, que imita o bucket S3.
Na AWS: QE_ARMAZENAMENTO=s3 e QE_BUCKET=<nome do bucket>; o código das etapas não muda.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Configuracao(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="QE_", env_file=".env", extra="ignore")

    armazenamento: Literal["local", "s3"] = "local"
    dados: Path = Path("data")  # raiz local (imita o bucket)
    bucket: str | None = None  # só para armazenamento s3
    cache: Path = Path(".cache")  # cópias locais de arquivos do S3 para os leitores


@lru_cache(maxsize=1)
def configuracao() -> Configuracao:
    return Configuracao()
