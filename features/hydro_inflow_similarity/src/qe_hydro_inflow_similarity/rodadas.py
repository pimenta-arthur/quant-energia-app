"""Rodadas mensais (pesquisa: rodadas.py, D019; pacote, seção 5, bloco 6; decisões 2, 3 e 5 da promoção).

Uma rodada por mês M, depois que a ENA de M está completa e a ERSST de M publicada: previsão do modelo-v1, camada de
El Niño forte e anos similares, com a versão de cada arquivo bruto usado. Registro em
serving/hydro_inflow_similarity/historico_rodadas.json: só acrescenta, nunca recalcula. Registrar a mesma emissão e
versão de novo é erro. A atualização diária não é rodada. Os modelos-sombra (T2, T3, T7) ficam na pesquisa
(decisão 5): a rodada 2026-09, vinda da pesquisa (legado), é a única com sombra.
"""

import datetime as dt
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from qe_core.armazenamento import Armazenamento, gravar_json, ler_json, ler_parquet
from qe_core.entrada import sha
from qe_hydro_inflow_similarity import backtest as B
from qe_hydro_inflow_similarity import chaves
from qe_hydro_inflow_similarity import modelo as M
from qe_hydro_inflow_similarity import similares as S


class RodadaRepetida(Exception):
    pass


def regime(n: float) -> str:
    m = M.MODELO
    if abs(n) >= m.limiar_regime:
        return "El Niño forte" if n > 0 else "La Niña forte"
    if abs(n) >= 1.0:
        return "El Niño moderado" if n > 0 else "La Niña moderada"
    return "fraco ou neutro"


def _a(v):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), 3)


def versoes_brutas(arm: Armazenamento) -> dict:
    """Hash de cada arquivo bruto vigente usado pela rodada (planilhas, ENA diária, ERSST, índices)."""
    from qe_hydro_inflow_similarity.tratamento import arquivos_diaria

    saida = {}
    for arq in chaves.PLANILHAS.values():
        c = f"{chaves.RAW_HISTORICA}/{arq}"
        saida[c] = sha(arm.ler_bytes(c))[:16]
    for nivel in chaves.PLANILHAS:
        for p in arquivos_diaria(arm, nivel):
            saida[str(p).split("raw/", 1)[1]] = sha(p.read_bytes())[:16]
    pub = ler_json(arm, chaves.RAW_ERSST_PUBLICACOES)[-1]
    saida[chaves.RAW_ERSST.split("raw/", 1)[1]] = pub["sha256"][:16]
    return saida


def montar_rodada(
    ena, indices, res_backtest: pd.DataFrame, emissao: str, versoes: dict, tipo: str = "publicada"
) -> dict:
    """Rodada da emissão `emissao` ('AAAA-MM'), só com dados até o fim desse mês."""
    data = pd.Timestamp(f"{emissao}-01")
    se = ena[(ena.nivel == "subsistema") & (ena.nome == "SE") & (ena.data == data)]
    if se.empty or not se.completo.all():
        raise ValueError(f"ENA de {emissao} ainda não está completa")
    if data not in indices.index or pd.isna(indices.loc[data, "nino34_rel"]):
        raise ValueError(f"ERSST de {emissao} ainda não publicada")
    ena_ate, ind_ate = ena[ena.data <= data], indices[indices.index <= data]
    series = M.montar_series(ena_ate, ind_ate)
    blocos, mlts = M.montar_blocos(ena_ate, ind_ate)
    t = M.posicao(data)
    n = float(series["SE"].enso3[t])
    n_mes = float(ind_ate.loc[data, "nino34_rel"])
    lim = M.MODELO.limiar_regime

    oficial = M.prever_v1(ena_ate, ind_ate, data)
    previsoes = [
        {
            "nome": r.nome,
            "alvo": f"{r.alvo:%Y-%m}",
            "h": int(r.h),
            "media": _a(r.media),
            "p10": _a(r.p10),
            "p50": _a(r.p50),
            "p90": _a(r.p90),
            "anomalia_gw": _a(r.anomalia_gw),
        }
        for r in oficial.itertuples()
    ]
    # camada de El Niño forte: só eventos que começaram antes do ano da emissão
    tabela = B.tabela_vies(res_backtest, series["SE"].enso3)
    resumo = B.resumo_el_nino(tabela[tabela.index.str[:4].astype(int) < data.year])
    vies = {
        "ativa_3m": abs(n) >= lim and n > 0,
        "ativa_mes": abs(n_mes) >= lim and n_mes > 0,
        "por_nome": {
            nome: {
                "direcao": B.direcao(r),
                "media": _a(r.media),
                "minimo": _a(r.minimo),
                "maximo": _a(r.maximo),
                "positivos": int(r.positivos),
                "eventos": int(r.eventos),
            }
            for nome, r in resumo.iterrows()
        },
    }
    return {
        "id": f"{emissao}_{M.MODELO.versao}",
        "emissao": emissao,
        "tipo": tipo,
        "versao": M.MODELO.versao,
        "registrada_em": dt.datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat(
            timespec="seconds"
        ),
        "insumos": {
            "ultimo_mes_ena": f"{ena_ate[ena_ate.completo].data.max():%Y-%m}",
            "ultimo_mes_ersst": f"{ind_ate.nino34_rel.dropna().index.max():%Y-%m}",
            "nino34_rel_3m": round(n, 3),
            "nino34_rel_mes": round(n_mes, 3),
            "regime_enso": regime(n),
            "versoes": versoes,
        },
        "previsoes": previsoes,
        "vies_el_nino_forte": vies,
        "similares": S.recompor(series, blocos, mlts, t),
    }


def ler_historico(arm: Armazenamento) -> list[dict]:
    return ler_json(arm, chaves.SERVING_REGISTRO) if arm.existe(chaves.SERVING_REGISTRO) else []


def registrar(arm: Armazenamento, rodada: dict) -> None:
    historico = ler_historico(arm)
    if any(r["id"] == rodada["id"] for r in historico):
        raise RodadaRepetida(f"rodada {rodada['id']} já registrada; rodadas não são recalculadas")
    gravar_json(arm, [*historico, rodada], chaves.SERVING_REGISTRO)


def emissao_pendente(arm: Armazenamento, ena: pd.DataFrame, indices: pd.DataFrame) -> str | None:
    """Último mês com ENA completa e ERSST publicada, se ainda não tiver rodada registrada."""
    sub = ena[(ena.nivel == "subsistema") & ena.completo]
    ultimo = min(sub.data.max(), indices.nino34_rel.dropna().index.max())
    emissao = f"{ultimo:%Y-%m}"
    feitas = {r["emissao"] for r in ler_historico(arm)}
    return None if emissao in feitas or emissao < max(feitas, default="") else emissao


def rodada_do_mes(arm: Armazenamento, forcar_emissao: str | None = None) -> dict | None:
    """Registra a rodada pendente (ou a de `forcar_emissao`); None se não houver."""
    ena = ler_parquet(arm, chaves.PROC_ENA)
    indices = ler_parquet(arm, chaves.PROC_INDICES)
    emissao = forcar_emissao or emissao_pendente(arm, ena, indices)
    if emissao is None:
        return None
    res = ler_parquet(arm, chaves.PROC_BACKTEST)
    rodada = montar_rodada(ena, indices, res, emissao, versoes_brutas(arm))
    registrar(arm, rodada)
    return rodada
