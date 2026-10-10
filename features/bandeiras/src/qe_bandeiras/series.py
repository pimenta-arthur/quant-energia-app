"""Séries do deck do NEWAVE prontas para a projeção: ENA, GSF e PLD gatilho de cada uma das 2.000 séries.

Tudo com informação disponível na data do deck: ANDE, PCH e carga projetadas pelo próprio deck;
GF_band e PLD mínimo/máximo do boletim do mês do deck. Mesma conta do analytics
(backtest.preparar_deck).
"""

import pandas as pd

from qe_bandeiras import chaves, modelo, regra, tratamento
from qe_core.armazenamento import Armazenamento, gravar_parquet, ler_parquet
from qe_core.leitores.newave import SUBMERCADOS

HORIZONTE = modelo.MODELO.horizonte  # M+1 a M+6 (alcance da emissão do ECMWF)


def _por_periodo(df: pd.DataFrame, colunas: str = "periodo") -> pd.DataFrame:
    t = df.pivot_table(index="serie", columns=colunas, values="valor", aggfunc="sum")
    t.columns = pd.PeriodIndex(t.columns, freq="M")
    return t


def preparar_deck(arm: Armazenamento, deck: pd.Period, versao: str, base: pd.DataFrame) -> dict:
    """ENA (série × período), GSF e PLD gatilho (série × mês-alvo) de uma versão do deck, M a M+6."""
    gh = _por_periodo(ler_parquet(arm, chaves.proc_newave(deck, versao, "gh")))
    ena = _por_periodo(ler_parquet(arm, chaves.proc_newave(deck, versao, "ena")))
    cmo = ler_parquet(arm, chaves.proc_newave(deck, versao, "cmo"))
    ent = ler_parquet(arm, chaves.proc_newave(deck, versao, "entradas"))
    ent["periodo"] = pd.PeriodIndex(ent.periodo, freq="M")
    ande = ent[ent.variavel == "ande"].set_index("periodo").valor
    carga = ent[ent.variavel == "carga"].pivot(
        index="periodo", columns="submercado", values="valor"
    )
    pch = ent[ent.variavel == "pch"].pivot(index="periodo", columns="submercado", values="valor")

    r0 = base.loc[deck]  # boletim do mês do deck
    gf_band, pld_min, pld_max = r0.gf_band_boletim, r0.pld_min_boletim, r0.pld_max_boletim
    f = regra.fatores_vigentes(deck)
    kf = (1 - f["perda_bruta_conexao"]) * (1 - f["perda_conexao_cg"])
    k_pch = f["part_pch_mre"] * (1 - f["perda_pch_cg"])

    alvos = [deck + h for h in range(HORIZONTE + 1) if deck + h in gh.columns]
    gsf, pld = {}, {}
    for alvo in alvos:
        gh_band = (gh[alvo] - ande[alvo]) * kf + pch.loc[alvo].sum() * k_pch
        gsf[alvo] = gh_band / gf_band
        horas = tratamento.horas_mes(arm, alvo)
        peso_pat = (horas.sum(axis=1) / horas.to_numpy().sum()).to_numpy()
        c = cmo[cmo.periodo == str(alvo)]
        total = 0.0
        for s in SUBMERCADOS:
            d = (
                c[c.submercado == s]
                .pivot(index="serie", columns="pat", values="valor")
                .sort_index(axis=1)
            )
            total = (
                total
                + pd.Series(
                    (d.clip(pld_min, pld_max).to_numpy() * peso_pat).sum(axis=1), index=d.index
                )
                * carga.loc[alvo, s]
                / carga.loc[alvo].sum()
            )
        pld[alvo] = total
    return {
        "inicio": deck,
        "alvos": alvos,
        "ena": ena,
        "gh": gh,
        "ande": ande,
        "pch": pch,
        "fatores": f,
        "gf_band": gf_band,
        "gsf": pd.DataFrame(gsf),
        "pld": pd.DataFrame(pld),
    }


def series_do_deck(arm: Armazenamento, deck: pd.Period, versao: str, base: pd.DataFrame) -> dict:
    """`preparar_deck` com cache em processed/bandeiras/series/ (GSF e PLD por série e versão)."""
    chave_gsf = chaves.proc_series(deck, versao, "gsf")
    chave_pld = chaves.proc_series(deck, versao, "pld")
    if arm.existe(chave_gsf) and arm.existe(chave_pld):
        prep = preparar_deck_leve(arm, deck, versao, base)
        for nome, chave in (("gsf", chave_gsf), ("pld", chave_pld)):
            t = ler_parquet(arm, chave)
            t.columns = pd.PeriodIndex(t.columns, freq="M")
            prep[nome] = t
        prep["alvos"] = list(prep["gsf"].columns)
        return prep
    prep = preparar_deck(arm, deck, versao, base)
    for nome, chave in (("gsf", chave_gsf), ("pld", chave_pld)):
        t = prep[nome].copy()
        t.columns = [str(c) for c in t.columns]
        gravar_parquet(arm, t, chave)
    return prep


def preparar_deck_leve(
    arm: Armazenamento, deck: pd.Period, versao: str, base: pd.DataFrame
) -> dict:
    """As partes baratas do deck (ENA, geração e entradas), sem recalcular GSF e PLD."""
    gh = _por_periodo(ler_parquet(arm, chaves.proc_newave(deck, versao, "gh")))
    ena = _por_periodo(ler_parquet(arm, chaves.proc_newave(deck, versao, "ena")))
    ent = ler_parquet(arm, chaves.proc_newave(deck, versao, "entradas"))
    ent["periodo"] = pd.PeriodIndex(ent.periodo, freq="M")
    return {
        "inicio": deck,
        "ena": ena,
        "gh": gh,
        "ande": ent[ent.variavel == "ande"].set_index("periodo").valor,
        "pch": ent[ent.variavel == "pch"].pivot(
            index="periodo", columns="submercado", values="valor"
        ),
        "fatores": regra.fatores_vigentes(deck),
        "gf_band": base.loc[deck].gf_band_boletim,
    }


def decks_disponiveis(arm: Armazenamento) -> list[pd.Period]:
    """Meses com alguma versão de deck do NEWAVE tratada."""
    import re

    return sorted(
        {
            pd.Period(m.group(1), "M")
            for c in arm.listar(f"{chaves.PROC}/newave")
            if (m := re.search(r"deck=(\d{4}-\d{2})/v=\w+/gh\.parquet$", c))
        }
    )
