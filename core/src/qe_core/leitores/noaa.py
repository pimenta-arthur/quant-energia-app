"""Leitores dos índices climáticos da NOAA (CPC e NCEI) e da previsão oficial do ENSO do CPC.

Funções puras sobre o caminho do arquivo. Séries mensais indexadas pelo 1º dia do mês, sem os valores ausentes.
Pesquisa: hydro-inflow-similarity-analytics, load.py (promocao-quant-v1).
"""

import html
import re
from pathlib import Path

import numpy as np
import pandas as pd

TRIMESTRES = ["DJF", "JFM", "FMA", "MAM", "AMJ", "MJJ", "JJA", "JAS", "ASO", "SON", "OND", "NDJ"]


def _serie_mensal(registros) -> pd.Series:
    """[(ano, mes, valor)] → Series indexada pelo 1º dia do mês, sem os valores ausentes."""
    df = pd.DataFrame(registros, columns=["ano", "mes", "valor"]).dropna()
    df.index = pd.to_datetime({"year": df.ano, "month": df.mes, "day": 1})
    return df["valor"].sort_index()


def ler_indice_trimestral_cpc(caminho: Path) -> pd.Series:
    """ONI/RONI do CPC ("SEAS YR [TOTAL] ANOM") → Series no mês central do trimestre (DJF de 1950 → jan/1950)."""
    df = pd.read_csv(caminho, sep=r"\s+")
    mes = df["SEAS"].map(TRIMESTRES.index) + 1
    return _serie_mensal(zip(df["YR"], mes, df["ANOM"], strict=True))


def ler_pdo_ncei(caminho: Path) -> pd.Series:
    """PDO do NCEI (ERSST v5): "Year Jan..Dec", ausente = 99.99."""
    registros = []
    for linha in Path(caminho).read_text().splitlines()[2:]:
        campos = linha.split()
        if len(campos) != 13:
            continue
        for mes, v in enumerate(campos[1:], start=1):
            valor = float(v)
            registros.append((int(campos[0]), mes, np.nan if valor >= 99 else valor))
    return _serie_mensal(registros)


def ler_amo_ncei(caminho: Path) -> pd.Series:
    """AMO do NCEI (ERSST v5): "Year month SSTA", anomalia do Atlântico Norte 0–60N, sem remover tendência."""
    df = pd.read_csv(caminho, sep=r"\s+", skiprows=2, names=["ano", "mes", "valor"])
    return _serie_mensal(zip(df.ano, df.mes, df.valor, strict=True))


def ler_aao_cpc(caminho: Path) -> pd.Series:
    """AAO mensal do CPC: "ano mês valor" por linha (1979–)."""
    df = pd.read_csv(caminho, sep=r"\s+", names=["ano", "mes", "valor"])
    return _serie_mensal(zip(df.ano, df.mes, df.valor, strict=True))


def ler_soi_cpc(caminho: Path) -> pd.Series:
    """SOI do CPC, tabela padronizada (a segunda do arquivo), largura fixa: ano (4) + 12 campos de 6;
    ausente = -999.9."""
    linhas = Path(caminho).read_text().splitlines()
    inicio = next(i for i, linha in enumerate(linhas) if "STANDARDIZED" in linha)
    registros = []
    for linha in linhas[inicio:]:
        if not linha[:4].isdigit():
            continue
        for mes in range(12):
            campo = linha[4 + 6 * mes : 10 + 6 * mes].strip()
            if campo:
                valor = float(campo)
                registros.append((int(linha[:4]), mes + 1, np.nan if valor <= -999 else valor))
    return _serie_mensal(registros)


def ler_probabilidades_enso(caminho: Path) -> dict:
    """Páginas do CPC com as probabilidades do ENSO (por fase: 3 valores por trimestre; por força: 9), com o mês
    de emissão ("Issued <mês> <ano>"; vale a última ocorrência, porque a de força cita também a da metodologia).

    {"emitida": "October 2026", "linhas": [{"trimestre": "OND", "valores": [...]}, ...]}
    """
    texto = re.sub(
        r"<style.*?</style>|<script.*?</script>", " ", Path(caminho).read_text(), flags=re.DOTALL
    )
    texto = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", texto)))
    emitida = re.findall(r"Issued (\w+ \d{4})", texto)
    linhas = [
        {"trimestre": m.group(1), "valores": [int(v) for v in m.group(3).split()]}
        for m in re.finditer(
            r"\b(" + "|".join(TRIMESTRES) + r") (\w{3} \w{3} \w{3}) ((?:\d+ ?)+)", texto
        )
    ]
    return {"emitida": emitida[-1] if emitida else None, "linhas": linhas}
