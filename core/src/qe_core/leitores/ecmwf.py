"""Leitor dos arquivos de ENA da previsão sazonal do ECMWF (SEAS5) por subsistema.

Cada arquivo ENA_MLT_SUBSISTEMA_MENSAL_<produto>_..._<AAAAMMDD>.txt traz, para uma rodada
(mês de emissão) e um produto (média, percentil ou membro), a ENA e a MLT por mês-alvo.
"""

import re
from pathlib import Path

import pandas as pd

SUBSISTEMAS = {"Sudeste": "SE", "Sul": "S", "Nordeste": "NE", "Norte": "N"}


def ler_arquivo(caminho: Path) -> pd.DataFrame:
    """Colunas: alvo (AAAA-MM), subsistema, ena (MWmed), mlt, pct_mlt."""
    df = pd.read_csv(caminho, sep=r"\s{2,}", engine="python")
    df.columns = ["alvo", "subsistema", "ena", "mlt", "pct_mlt"]
    df["alvo"] = df.alvo.str.strip().str[:7]
    df["subsistema"] = df.subsistema.str.strip().map(SUBSISTEMAS)
    return df


def emissao(caminho: Path) -> str:
    """Mês de emissão (AAAA-MM) a partir da data no fim do nome do arquivo."""
    data = Path(caminho).stem.rsplit("_", 1)[1]
    return f"{data[:4]}-{data[4:6]}"


def produto(caminho: Path) -> dict:
    """Produto do arquivo: {'tipo': 'estatistica', 'estatistica': 'av', 'abordagem': 'precip'}
    ou {'tipo': 'membro', 'membro': 7}."""
    nome = Path(caminho).name
    m = re.search(r"ECENSLTm(\d+)_", nome)
    if m:
        return {"tipo": "membro", "membro": int(m.group(1))}
    m = re.search(r"ECENSLT([a-z0-9]+)_(precip|vaz)_", nome)
    if m:
        return {"tipo": "estatistica", "estatistica": m.group(1), "abordagem": m.group(2)}
    raise ValueError(f"produto do ECMWF não reconhecido: {nome}")
