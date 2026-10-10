"""Tratamento: raw/ → processed/bandeiras/ (Parquet), um mês por vez.

Para o mês M:
- patamares/M: horas de cada patamar em cada semana operativa;
- mensal/M: uma linha com o balanço do PMO (GH_band etc.), ENA e EAR do PMO e os valores do
  boletim InfoBandeira (quando já publicado) — mesma base do forecast-bandeiras-analytics;
- newave/M: séries do deck da CCEE (geração hidráulica, ENA e custo marginal) e entradas do deck;
- ecmwf/M: médias, percentis e membros da rodada do ECMWF;
- historico_bandeiras: histórico oficial da ANEEL (sempre atualizado).
Cada parte só roda se o bruto correspondente existir; o relatório diz o que foi feito.
"""

import warnings

import numpy as np
import pandas as pd

from qe_bandeiras import chaves, regra
from qe_core.armazenamento import Armazenamento, gravar_parquet, ler_parquet
from qe_core.leitores import aneel, ccee, ecmwf, newave, ons
from qe_core.periodo import rotulo

TIPOS_MMGD = {"PCHgd", "PCTgd", "EOLgd", "UFVgd"}


# --- calendário ---------------------------------------------------------------------------------


def horas_mes(arm: Armazenamento, m: pd.Period) -> pd.DataFrame:
    """Horas por patamar × semana do mês. Usa o processed; se faltar, calcula do bruto do ano.

    Se o ano ainda não tem patamares publicados, usa o mesmo mês do ano anterior (D032 do
    analytics): só a proporção de horas por patamar entra no PLD e ela muda pouco.
    """
    if arm.existe(chaves.proc_patamares(m)):
        longo = ler_parquet(arm, chaves.proc_patamares(m))
        return longo.pivot(index="patamar", columns="semana", values="horas").reindex(
            ccee.PATAMARES
        )
    if arm.existe(chaves.raw_patamares(m.year)):
        return ccee.horas_por_semana(
            ccee.ler_patamares(arm.caminho_local(chaves.raw_patamares(m.year))), m.month
        )
    anterior = m - 12
    if arm.existe(chaves.raw_patamares(anterior.year)):
        warnings.warn(
            f"patamares de {m.year} indisponíveis; usando {rotulo(anterior)}", stacklevel=2
        )
        return horas_mes(arm, anterior)
    raise FileNotFoundError(f"sem patamares para {rotulo(m)} nem para {rotulo(anterior)}")


def tratar_patamares(arm: Armazenamento, m: pd.Period) -> str:
    if not arm.existe(chaves.raw_patamares(m.year)):
        return "sem bruto"
    h = ccee.horas_por_semana(
        ccee.ler_patamares(arm.caminho_local(chaves.raw_patamares(m.year))), m.month
    )
    longo = h.reset_index().melt(id_vars="patamar", var_name="semana", value_name="horas")
    gravar_parquet(arm, longo, chaves.proc_patamares(m))
    return "ok"


# --- base mensal (PMO + boletim) ----------------------------------------------------------------


def linha_mensal(arm: Armazenamento, m: pd.Period) -> dict:
    """Balanço do PMO, GH_band, ENA, EAR e boletim do mês (memorial da seção 3.5 do analytics)."""
    horas = horas_mes(arm, m)
    n_sem = horas.shape[1]

    def media(df, coluna):
        return regra.media_mensal_df(df, coluna, horas)

    relato = arm.caminho_local(chaves.raw_pmo(m, "relato.rv0"))
    bal = ons.ler_relato_balanco(relato, n_sem)
    peq = ons.ler_relato_pequenas(relato, n_sem)
    ter = ons.ler_relato_termicas(relato)
    ande_df = ons.ler_relato_ande(relato, n_sem)

    def pequenas(tipos):
        return media(peq[peq.tipo.isin(tipos)], "mw")

    # GH_band (Tabela 3 do boletim)
    f = regra.fatores_vigentes(m)
    gh_ons = media(bal, "ghid") + media(bal, "it60")
    ande = media(ande_df, "ande")
    pch_l = peq[peq.tipo == "PCH"]
    pch = {s: media(pch_l[pch_l.subsistema == s], "mw") for s in ("SE", "S", "NE", "N")}
    gh_cg = (gh_ons - ande) * (1 - f["perda_bruta_conexao"]) * (1 - f["perda_conexao_cg"])
    pch_cg = sum(pch.values()) * f["part_pch_mre"] * (1 - f["perda_pch_cg"])

    # Eólica e solar centralizadas: nas pequenas usinas até set/2025; no Geol depois.
    eol, ufv = pequenas({"EOL"}), pequenas({"UFV"})
    geol = media(bal, "geol")
    if geol > 0 and arm.existe(chaves.raw_pmo(m, "renovaveis.csv")):
        ren = ons.ler_renovaveis(arm.caminho_local(chaves.raw_pmo(m, "renovaveis.csv")), n_sem)
        eol = sum(regra.media_mensal(v, horas) for (fo, _), v in ren.items() if fo == "EOL")
        ufv = sum(regra.media_mensal(v, horas) for (fo, _), v in ren.items() if fo == "UFV")
    elif geol > 0:
        eol = ufv = float("nan")  # só a soma (Geol) disponível

    linha = {
        "mes": rotulo(m),
        "carga_bruta": media(bal, "mercado"),
        "mmgd": pequenas(TIPOS_MMGD),
        "renovaveis": pequenas({"EOL", "UFV"}) + geol,
        "eol": eol,
        "ufv": ufv,
        "termica": media(bal, "gter") + media(bal, "gterat"),
        "termica_antecipada": media(bal, "gterat"),
        "nuclear": media(ter[ter.nuclear], "ger"),
        "termica_inflexivel": media(ter, "inflexivel"),
        "pch": pequenas({"PCH"}),
        "pct": pequenas({"PCT"}),
        "bombeamento": media(bal, "cbomba"),
        "gh_ons": gh_ons,
        "ande": ande,
        **{f"pch_{s}": v for s, v in pch.items()},
        "gh_band": gh_cg + pch_cg,
    }
    linha["carga_liquida"] = linha["carga_bruta"] - linha["mmgd"]
    linha["termica_merito"] = (
        linha["termica"] - linha["termica_inflexivel"] - linha["termica_antecipada"]
    )
    linha["residuo"] = (
        linha["carga_liquida"]
        + linha["bombeamento"]
        - (gh_ons - ande)
        - linha["renovaveis"]
        - linha["termica"]
        - linha["pch"]
        - linha["pct"]
    )  # fechamento do balanço: deve ser ~0

    ena = ons.ler_ena(arm.caminho_local(chaves.raw_pmo(m, "ena.pdf")))
    for sub, r in ena.iterrows():
        linha[f"ena_{sub}"], linha[f"ena_mlt_{sub}"] = r.ena_mes, r.ena_mes_mlt
    linha["ena_sin"] = ena.ena_mes.sum()
    linha["ena_mlt_sin"] = 100 * ena.ena_mes.sum() / (ena.ena_mes / (ena.ena_mes_mlt / 100)).sum()

    ear = ons.ler_relato_ear(relato)
    for sub, r in ear.iterrows():
        linha[f"ear_ini_{sub}"] = r.ear_pct
    linha["ear_ini_sin"] = 100 * ear.ear_mwmes.sum() / (ear.ear_mwmes / (ear.ear_pct / 100)).sum()

    if arm.existe(chaves.raw_boletim(m)):
        bol = ccee.ler_boletim(arm.caminho_local(chaves.raw_boletim(m)), m.year)
        linha.update({f"{k}_boletim": v for k, v in bol.items()})
        linha["gsf_calc"] = regra.gsf_band(linha["gh_band"], bol["gf_band"])
        linha["cor_regra"] = regra.cor_bandeira(bol["gsf_band"], bol["pld_gatilho"])
    return linha


def tratar_mensal(arm: Armazenamento, m: pd.Period) -> str:
    if not arm.existe(chaves.raw_pmo(m, "relato.rv0")):
        return "sem bruto"
    linha = linha_mensal(arm, m)
    gravar_parquet(arm, pd.DataFrame([linha]), chaves.proc_mensal(m))
    return "ok" + ("" if "gf_band_boletim" in linha else " (sem boletim)")


# --- deck do NEWAVE --------------------------------------------------------------------------------


def tratar_newave(arm: Armazenamento, m: pd.Period) -> str:
    if not arm.existe(chaves.raw_newave(m, "ghtotsin.out")):
        return "sem bruto"

    def arq(nome):
        return arm.caminho_local(chaves.raw_newave(m, nome))

    gh = newave.para_periodos(newave.ler_nwlistop(arq("ghtotsin.out")))
    meses = set(gh.periodo)  # meses do estudo; vale para ENA e custo marginal
    ena = pd.concat(
        [
            newave.para_periodos(newave.ler_nwlistop(arq(f"eafbm00{i}.out")), meses).assign(
                submercado=s
            )
            for s, i in newave.SUBMERCADOS.items()
        ],
        ignore_index=True,
    )
    cmo = pd.concat(
        [
            newave.para_periodos(
                newave.ler_nwlistop(arq(f"cmarg00{i}.out"), somar_patamares=False), meses
            ).assign(submercado=s)
            for s, i in newave.SUBMERCADOS.items()
        ],
        ignore_index=True,
    )
    ent = newave.ler_entradas_deck(arq("c_adic.dat"), arq("sistema.dat"))
    entradas = pd.concat(
        [
            ent["ande"]
            .rename("valor")
            .rename_axis("periodo")
            .reset_index()
            .assign(variavel="ande", submercado="SIN"),
            ent["carga"]
            .rename_axis("periodo")
            .reset_index()
            .melt(id_vars="periodo", var_name="submercado", value_name="valor")
            .assign(variavel="carga"),
            ent["pch"]
            .rename_axis("periodo")
            .reset_index()
            .melt(id_vars="periodo", var_name="submercado", value_name="valor")
            .assign(variavel="pch"),
        ],
        ignore_index=True,
    )
    for nome, df in (("gh", gh), ("ena", ena), ("cmo", cmo), ("entradas", entradas)):
        gravar_parquet(arm, df, chaves.proc_newave(m, nome))
    return f"ok ({gh.serie.nunique()} séries, {gh.periodo.min()} a {gh.periodo.max()})"


# --- rodada do ECMWF -------------------------------------------------------------------------------


def tratar_ecmwf(arm: Armazenamento, m: pd.Period) -> str:
    arquivos = arm.listar(chaves.raw_ecmwf(m))
    if not arquivos:
        return "sem bruto"
    est, mem = [], []
    for chave in arquivos:
        caminho = arm.caminho_local(chave)
        df = ecmwf.ler_arquivo(caminho).assign(emissao=ecmwf.emissao(caminho))
        p = ecmwf.produto(caminho)
        if p["tipo"] == "membro":
            mem.append(df.assign(membro=p["membro"]))
        else:
            est.append(df.assign(estatistica=p["estatistica"], abordagem=p["abordagem"]))
    if est:
        gravar_parquet(arm, pd.concat(est, ignore_index=True), chaves.proc_ecmwf(m, "estatisticas"))
    if mem:
        gravar_parquet(arm, pd.concat(mem, ignore_index=True), chaves.proc_ecmwf(m, "membros"))
    n_mem = len({d.membro.iloc[0] for d in mem})
    return f"ok ({len(est)} estatísticas, {n_mem} membros)"


# --- histórico ANEEL -------------------------------------------------------------------------------


def tratar_historico(arm: Armazenamento) -> str:
    if not arm.existe(chaves.RAW_HISTORICO):
        return "sem bruto"
    h = aneel.ler_historico_bandeiras(arm.caminho_local(chaves.RAW_HISTORICO))
    gravar_parquet(arm, h, chaves.PROC_HISTORICO)
    return f"ok ({h.mes.min()} a {h.mes.max()})"


def tratar_mes(arm: Armazenamento, m: pd.Period) -> dict:
    """Todas as partes de um mês; devolve a situação de cada uma."""
    return {
        "patamares": tratar_patamares(arm, m),
        "mensal": tratar_mensal(arm, m),
        "newave": tratar_newave(arm, m),
        "ecmwf": tratar_ecmwf(arm, m),
        "historico": tratar_historico(arm),
    }


def base_mensal(arm: Armazenamento) -> pd.DataFrame:
    """Todas as linhas mensais tratadas, indexadas por Period (para a projeção e a página)."""
    partes = [
        ler_parquet(arm, c) for c in arm.listar(f"{chaves.PROC}/mensal") if c.endswith(".parquet")
    ]
    if not partes:
        return pd.DataFrame()
    base = pd.concat(partes, ignore_index=True)
    base.index = pd.PeriodIndex(base.pop("mes"), freq="M")
    return base.sort_index().replace({None: np.nan})
