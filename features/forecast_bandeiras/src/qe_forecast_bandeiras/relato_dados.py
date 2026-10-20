"""Dados embutidos na página de cálculo pelo relato (web/forecast_bandeiras/relato.html).

O navegador não lê os arquivos do app, então tudo o que a conta precisa vai junto num `.js`:
fatores da CCEE, limites do ábaco, horas por patamar e semana de cada mês e o boletim publicado
(GF_band, PLD mín/máx e o resultado oficial, para conferir). Regravado a cada publicação.
"""

import json
import warnings

import pandas as pd

from qe_core.armazenamento import Armazenamento, ler_parquet
from qe_core.periodo import rotulo
from qe_forecast_bandeiras import chaves, regra, tratamento

PRIMEIRO_MES = pd.Period("2023-01", "M")
COLUNAS_BOLETIM = {
    "gf_band_boletim": "gf_band",
    "pld_min_boletim": "pld_min",
    "pld_max_boletim": "pld_max",
    "pld_gatilho_boletim": "pld_gatilho",
    "gsf_band_boletim": "gsf",
    "gh_band_boletim": "gh_band",
    "cor_boletim": "cor",
}


def _ultimo_mes_tratado(arm: Armazenamento) -> pd.Period:
    m = ultimo = PRIMEIRO_MES
    while m.year <= PRIMEIRO_MES.year + 10:
        if arm.existe(chaves.proc_mensal(m)):
            ultimo = m
        m += 1
    return ultimo


def montar(arm: Armazenamento) -> dict:
    """Dados da página: do primeiro mês tratado até dezembro do ano seguinte ao último tratado."""
    ultimo = _ultimo_mes_tratado(arm)
    fim = pd.Period(f"{ultimo.year + 1}-12", "M")
    horas, estimadas, boletim = {}, [], {}
    for m in pd.period_range(PRIMEIRO_MES, fim, freq="M"):
        if arm.existe(chaves.proc_mensal(m)):
            linha = ler_parquet(arm, chaves.proc_mensal(m)).iloc[0]
            b = {
                nome: (None if pd.isna(linha.get(col)) else linha[col])
                for col, nome in COLUNAS_BOLETIM.items()
            }
            if b["gf_band"] is not None:
                boletim[rotulo(m)] = {
                    k: (v if isinstance(v, str) or v is None else float(v)) for k, v in b.items()
                }
        publicado = arm.existe(chaves.proc_patamares(m)) or arm.existe(chaves.raw_patamares(m.year))
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                h = tratamento.horas_mes(arm, m)
        except FileNotFoundError:
            continue
        horas[rotulo(m)] = h.to_numpy().tolist()
        if not publicado:
            estimadas.append(rotulo(m))  # patamares do ano ainda não publicados (D032)
    return {
        "fatores": regra.FATORES,
        "limites_x": regra.LIMITES_X,
        "cores": regra.CORES,
        "horas": horas,
        "horas_estimadas": estimadas,
        "boletim": boletim,
    }


def gravar(arm: Armazenamento) -> None:
    dados = montar(arm)
    arm.gravar_bytes(
        ("window.RELATO_DADOS = " + json.dumps(dados, ensure_ascii=False) + ";\n").encode("utf-8"),
        chaves.SERVING_RELATO_DADOS,
    )
