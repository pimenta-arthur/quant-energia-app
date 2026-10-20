"""Bandeira a partir de relatos do DECOMP (relato.rv0), sem passar pelo NEWAVE.

Portado do forecast-bandeiras-analytics (D034, `calculo_relato.py`), sem mudar o método:

- **PLD gatilho** vem do relato do DECOMP da **CCEE** (custo marginal por semana, patamar e submercado,
  limitado ao PLD mín/máx, média do mês pelas horas de cada patamar, 4 submercados pela carga);
- **GH_band / GSF** vêm do relato do **ONS** quando informado (fonte oficial do boletim); sem ele, do
  relato da CCEE, como aproximação (difere do GH do ONS em até ~1%, ~0,01 de GSF).

O CMO do relato do ONS nunca é usado como PLD. Não inclui GFOM. Esta é a referência do cálculo que a
página roda no navegador (web/forecast_bandeiras/relato_conta.js); o teste de paridade compara os dois.
"""

import re
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from qe_core.armazenamento import Armazenamento, ler_parquet
from qe_core.leitores import ons
from qe_core.leitores.dessem import texto
from qe_core.periodo import rotulo
from qe_forecast_bandeiras import chaves, regra, tratamento

SUBS = ("SE", "S", "NE", "N")  # ordem dos blocos do custo marginal; o 5º (FC) não entra


def ler_cmo(caminho: Path) -> dict[str, np.ndarray]:
    """Custo marginal (R$/MWh) por submercado: matriz patamar (3) × semana."""
    linhas = texto(caminho).splitlines()
    inicio = next((i for i, ln in enumerate(linhas) if "CUSTO MARGINAL DE OPERACAO" in ln), None)
    if inicio is None:
        raise ValueError("bloco 'CUSTO MARGINAL DE OPERACAO' não encontrado no relato")
    saida, atual = {}, []
    bordas = 0
    for ln in linhas[inicio:]:
        p = ln.split()
        if not p:
            continue
        if p[0].startswith("X-"):  # 2 bordas do cabeçalho + 1 de fechamento da tabela
            bordas += 1
            if bordas == 3:
                break
            continue
        if p[0].startswith("Pat_"):
            atual.append([float(x) for x in p[1:]])
        elif p[0].startswith("Med_"):
            saida[p[0][4:]] = np.array(atual)
            atual = []
    faltam = [s for s in SUBS if s not in saida]
    if faltam:
        raise ValueError(f"custo marginal sem os submercados {faltam}")
    return saida


MESES_RELATO = [
    "JANEIRO", "FEVEREIRO", "MARCO", "ABRIL", "MAIO", "JUNHO",
    "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO",
]  # fmt: skip


def mes_do_relato(caminho: Path) -> int | None:
    """Mês indicado no rótulo da semana 1 do relato (1 a 12); None se não achar.

    Só informativo: estudos customizados partem de um deck existente e o rótulo pode ficar igual.
    """
    m = re.search(r"^\s*([A-Za-z]+)\s*/\s*SEMANA 1 - ESTAGIO", texto(caminho), re.MULTILINE)
    nome = m.group(1).upper() if m else None
    return MESES_RELATO.index(nome) + 1 if nome in MESES_RELATO else None


def carga_submercados(caminho: Path, horas: pd.DataFrame) -> dict[str, float]:
    """Carga bruta média do mês (MWmed) de cada submercado, do balanço do relato."""
    bal = ons.ler_relato_balanco(caminho, horas.shape[1])
    if bal.empty:
        raise ValueError(f"{caminho}: sem o balanço energético (é o relato completo?)")
    return {s: regra.media_mensal_df(bal[bal.subsistema == s], "mercado", horas) for s in SUBS}


def pld_gatilho(
    relato_ccee: Path,
    horas: pd.DataFrame,
    pld_min: float,
    pld_max: float,
    relato_carga: Path | None = None,
) -> dict:
    """PLD gatilho do mês (R$/MWh) e o PLD médio de cada submercado (limitado a mín/máx)."""
    h = horas.to_numpy()
    n_sem = h.shape[1]
    cmo = ler_cmo(relato_ccee)
    try:
        carga = carga_submercados(relato_ccee, horas)
    except ValueError:
        if relato_carga is None:
            raise
        warnings.warn("relato da CCEE sem balanço: carga tirada do relato do ONS", stacklevel=2)
        carga = carga_submercados(relato_carga, horas)
    total = sum(carga.values())
    por_sub = {}
    for s in SUBS:
        if cmo[s].shape[1] < n_sem:
            raise ValueError(
                f"{s}: custo marginal com {cmo[s].shape[1]} semanas, o mês tem {n_sem}"
            )
        lim = np.clip(cmo[s][:, :n_sem], pld_min, pld_max)
        por_sub[s] = float((lim * h).sum() / h.sum())
    return {
        "pld_gatilho": sum(por_sub[s] * carga[s] / total for s in SUBS),
        "pld_submercado": por_sub,
    }


def gh_band(relato: Path, periodo: pd.Period, horas: pd.DataFrame) -> dict:
    """GH_band do mês a partir de um relato (mesma conta de `tratamento.linha_mensal`)."""
    n_sem = horas.shape[1]
    bal = ons.ler_relato_balanco(relato, n_sem)
    peq = ons.ler_relato_pequenas(relato, n_sem)
    ande_df = ons.ler_relato_ande(relato, n_sem)
    f = regra.fatores_vigentes(periodo)
    gh_ons = regra.media_mensal_df(bal, "ghid", horas) + regra.media_mensal_df(bal, "it60", horas)
    ande = regra.media_mensal_df(ande_df, "ande", horas)
    pch = regra.media_mensal_df(peq[peq.tipo == "PCH"], "mw", horas)
    gh_cg = (gh_ons - ande) * (1 - f["perda_bruta_conexao"]) * (1 - f["perda_conexao_cg"])
    pch_cg = pch * f["part_pch_mre"] * (1 - f["perda_pch_cg"])
    return {
        "gh_ons": gh_ons,
        "ande": ande,
        "pch_total": pch,
        "gh_cg": gh_cg,
        "pch_cg": pch_cg,
        "gh_band": gh_cg + pch_cg,
    }


def valores_publicados(arm: Armazenamento, periodo: pd.Period) -> dict:
    """GF_band e PLD mín/máx do último boletim publicado até o mês (premissa D013 do analytics)."""
    achados = []
    for m in pd.period_range(periodo - 36, periodo, freq="M"):
        if arm.existe(chaves.proc_mensal(m)):
            linha = ler_parquet(arm, chaves.proc_mensal(m)).iloc[0]
            if pd.notna(linha.get("gf_band_boletim")) and pd.notna(linha.get("pld_min_boletim")):
                achados.append((m, linha))
    if not achados:
        raise ValueError("sem boletim publicado até o mês; informe gf_band, pld_min e pld_max")
    m, linha = achados[-1]
    return {
        "gf_band": float(linha.gf_band_boletim),
        "pld_min": float(linha.pld_min_boletim),
        "pld_max": float(linha.pld_max_boletim),
        "origem": rotulo(m),
    }


def _folga(x: float, gsf: float, pld: float) -> dict:
    """Distância de X até os limites da cor e o PLD/GSF em que a cor muda para a de cima."""
    inferior, superior = 0.0, np.inf
    for limite in regra.LIMITES_X.values():
        if x <= limite:
            superior = limite
            break
        inferior = limite
    return {
        "x_limite_inferior": inferior,
        "x_limite_superior": superior,
        "folga_para_cor_acima_x": superior - x,
        "folga_para_cor_abaixo_x": x - inferior,
        "pld_cor_acima": superior / (1 - gsf) if gsf < 1 else np.nan,
        "gsf_cor_acima": 1 - superior / pld if np.isfinite(superior) and pld else np.nan,
    }


def calcular_bandeira(
    periodo: pd.Period,
    horas: pd.DataFrame,
    gf_band: float,
    pld_min: float,
    pld_max: float,
    relato_ccee: Path | None = None,
    relato_ons: Path | None = None,
    pld_gatilho_manual: float | None = None,
) -> dict:
    """Bandeira de um mês a partir dos relatos do DECOMP.

    `horas` é a tabela patamar × semana do mês (`tratamento.horas_mes`). Com os dois relatos, o GH_band
    vem do ONS e o PLD gatilho da CCEE; só com o da CCEE, o GH é aproximado; só com o do ONS, o PLD
    gatilho tem de ser informado (o CMO do ONS não é o PLD gatilho).
    """
    if relato_ccee is None and relato_ons is None:
        raise ValueError("informe ao menos um relato (CCEE e/ou ONS)")
    if relato_ccee is None and pld_gatilho_manual is None:
        raise ValueError(
            "só com o relato do ONS é preciso informar pld_gatilho_manual "
            "(o CMO do ONS não é o PLD gatilho)"
        )
    gh = gh_band(relato_ons or relato_ccee, periodo, horas)
    gsf = regra.gsf_band(gh["gh_band"], gf_band)
    if pld_gatilho_manual is not None:
        pld, por_sub, fonte_pld = pld_gatilho_manual, {}, "manual"
    else:
        r = pld_gatilho(relato_ccee, horas, pld_min, pld_max, relato_carga=relato_ons)
        pld, por_sub, fonte_pld = r["pld_gatilho"], r["pld_submercado"], "CCEE"
    x = pld * max(0.0, 1 - gsf)
    return {
        "mes": rotulo(periodo),
        "gh_band": gh["gh_band"],
        "gf_band": gf_band,
        "gsf": gsf,
        "pld_gatilho": pld,
        "pld_submercado": por_sub,
        "x": x,
        "cor": regra.cor_bandeira(gsf, pld),
        **_folga(x, gsf, pld),
        "fontes": {
            "gh": "ONS" if relato_ons is not None else "CCEE (aproximação)",
            "pld": fonte_pld,
        },
    }


def probabilidade_cores(cores: list[str]) -> dict[str, float]:
    """Fração das execuções em cada cor (peso igual)."""
    return {c: cores.count(c) / len(cores) for c in regra.CORES}


def horas_do_mes(arm: Armazenamento, periodo: pd.Period) -> pd.DataFrame:
    """Horas por patamar × semana do mês (com o fallback de ano sem patamares, D032)."""
    return tratamento.horas_mes(arm, periodo)
