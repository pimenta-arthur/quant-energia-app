"""Tratamento: raw/ → processed/hydro_inflow_similarity/ (pacote de promoção, seção 4).

- T1 ENA mensal: planilha 1931–2024 (configuração atual aplicada a todo o histórico) e, de 2025 em diante, a média
  mensal da ENA bruta diária (última versão de cada ano). Na planilha de bacias, o PARANA é acumulado e vira
  incremental (D013). % MLT = MWmed ÷ MLT (média 1931–2024 da planilha).
- T2 MLT por nível, nome e mês.
- T3 índices mensais: os de TSM calculados da grade ERSST v6 (caixas, peso cos(lat), anomalia 1991–2020) e os
  oficiais (ONI, RONI, PDO, AMO, SOI, AAO), desde 1930.
- ENA diária (última versão de cada ano), base da atualização com o mês em curso.
Tudo é refeito inteiro (segundos).
"""

import numpy as np
import pandas as pd

from qe_core.armazenamento import Armazenamento, gravar_parquet
from qe_core.leitores import noaa, ons
from qe_hydro_inflow_similarity import chaves
from qe_hydro_inflow_similarity.ingestao import versoes

ULTIMO_ANO_PLANILHA = 2024
AFLUENTES_PARANA = ["GRANDE", "PARANAIBA", "TIETE", "PARANAPANEMA"]

# --- índices de TSM da ERSST v6 (pesquisa: indices.py) --------------------------------------------------------
CLIMATOLOGIA = ("1991-01-01", "2020-12-01")
# (lat_sul, lat_norte, lon_oeste, lon_leste), longitude em 0–360
CAIXAS = {
    "nino34": (-5, 5, 190, 240),  # 5S–5N, 170W–120W
    "nino12": (-10, 0, 270, 280),  # 10S–0, 90W–80W
    "tna": (5.5, 23.5, 302.5, 345),  # 5,5N–23,5N, 57,5W–15W (definição do PSL)
    "tsa": (-20, 0, 330, 370),  # 20S–0, 30W–10E (atravessa o meridiano 0)
    "wtio": (-10, 10, 50, 70),  # Índico oeste (DMI)
    "setio": (-10, 0, 90, 110),  # Índico sudeste (DMI)
    "atl_sul_se": (-30, -20, 310, 320),  # costa do SE: 30S–20S, 50W–40W
    "atl_norte": (0, 60, 280, 360),  # AMO: Atlântico Norte 0–60N, 80W–0
    "tropicos": (-20, 20, 0, 360),  # média tropical (base do índice relativo)
    "global_60": (-60, 60, 0, 360),  # média 60S–60N (base da AMO relativa)
}


def _media_na_caixa(sst, caixa) -> pd.Series:
    """Média de TSM na caixa, ponderada por cos(lat), ignorando terra (NaN)."""
    sul, norte, oeste, leste = caixa
    lat = sst.lat.where((sst.lat >= sul) & (sst.lat <= norte), drop=True)
    if leste > 360:  # caixa que atravessa o meridiano 0
        lon = sst.lon.where((sst.lon >= oeste) | (sst.lon <= leste - 360), drop=True)
    else:
        lon = sst.lon.where((sst.lon >= oeste) & (sst.lon <= leste), drop=True)
    recorte = sst.sel(lat=lat, lon=lon)
    peso = np.cos(np.deg2rad(recorte.lat))
    return recorte.weighted(peso).mean(dim=("lat", "lon")).to_series()


def _anomalia(serie: pd.Series) -> pd.Series:
    """Subtrai a climatologia mensal de 1991–2020."""
    base = serie.loc[CLIMATOLOGIA[0] : CLIMATOLOGIA[1]]
    clima = base.groupby(base.index.month).mean()
    return serie - clima.reindex(serie.index.month).to_numpy()


def indices_ersst(caminho_nc) -> pd.DataFrame:
    """Índices de TSM em anomalia (°C), mensais (1º dia do mês):
    - nino34, nino12, tna, tsa, atl_sul_se: anomalia na caixa;
    - grad_atl = tna − tsa; dmi = Índico oeste − sudeste;
    - nino34_rel = nino34 − média tropical 20S–20N (ideia do RONI, sem o reescalonamento do CPC): índice do modelo;
    - amo_rel = Atlântico Norte − média 60S–60N.
    """
    import xarray as xr

    with xr.open_dataset(caminho_nc) as ds:
        sst = ds["sst"].load()
    df = pd.DataFrame({n: _anomalia(_media_na_caixa(sst, c)) for n, c in CAIXAS.items()})
    df.index = pd.DatetimeIndex(df.index).to_period("M").to_timestamp()
    df["grad_atl"] = df.tna - df.tsa
    df["dmi"] = df.wtio - df.setio
    df["nino34_rel"] = df.nino34 - df.tropicos
    df["amo_rel"] = df.atl_norte - df.global_60
    return df.drop(columns=["wtio", "setio", "atl_norte", "tropicos", "global_60"])


# --- ENA -------------------------------------------------------------------------------------------------------


def parana_incremental(df: pd.DataFrame, chaves_mes: list[str]) -> pd.DataFrame:
    """Troca o Paraná acumulado pelo incremental: Paraná − Σ afluentes, mês a mês (`chaves_mes` identifica o mês)."""
    afluentes = df[df.nome.isin(AFLUENTES_PARANA)].groupby(chaves_mes).mwmed.sum()
    parana = df.nome == "PARANA"
    idx = (
        pd.MultiIndex.from_frame(df.loc[parana, chaves_mes])
        if len(chaves_mes) > 1
        else df.loc[parana, chaves_mes[0]]
    )
    df = df.copy()
    df.loc[parana, "mwmed"] = df[parana].mwmed.to_numpy() - afluentes.reindex(idx).to_numpy()
    return df


def arquivos_diaria(arm: Armazenamento, nivel: str) -> list:
    """Caminho local da versão mais recente (pela data da ingestão) do CSV de cada ano."""
    anos = sorted(
        {c.split("ano=")[1].split("/")[0] for c in arm.listar(f"{chaves.RAW_DIARIA}/{nivel}")}
    )
    saida = []
    for ano in anos:
        _, pasta = versoes(arm, f"{chaves.RAW_DIARIA}/{nivel}/ano={ano}")[-1]
        saida.append(arm.caminho_local(f"{pasta}/{chaves.ARQUIVO_DIARIA[nivel].format(ano=ano)}"))
    return saida


def ena_diaria(arm: Armazenamento, nivel: str) -> pd.DataFrame:
    return ons.ler_ena_diaria(arquivos_diaria(arm, nivel), nivel)


def ena_mensal(arm: Armazenamento) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """(T1, T2, ENA diária por nível)."""
    series, mlts, diarias = [], [], {}
    for nivel, arq in chaves.PLANILHAS.items():
        planilha, medias = ons.ler_planilha_ena(
            arm.caminho_local(f"{chaves.RAW_HISTORICA}/{arq}"), nivel
        )
        if nivel == "bacia":
            planilha = parana_incremental(planilha, ["ano", "mes"]).drop(columns="pct_media")
            medias = parana_incremental(medias, ["mes"])
        mlt = medias[["nome", "mes", "mwmed"]].rename(columns={"mwmed": "mlt"}).assign(nivel=nivel)

        diaria = ena_diaria(arm, nivel)
        diarias[nivel] = diaria
        d = diaria[(diaria.data.dt.year > ULTIMO_ANO_PLANILHA) & diaria.nome.isin(mlt.nome)]
        mensal = (
            d.groupby([d.nome, d.data.dt.to_period("M").rename("periodo")])
            .agg(mwmed=("bruta_mwmed", "mean"), dias=("bruta_mwmed", "size"))
            .reset_index()
        )
        mensal["ano"] = mensal.periodo.dt.year
        mensal["mes"] = mensal.periodo.dt.month
        mensal["completo"] = mensal.dias == mensal.periodo.dt.days_in_month
        mensal["fonte"] = "ons_diaria"

        planilha = planilha.assign(fonte="planilha_1931_2024", completo=True)
        colunas = ["nome", "ano", "mes", "mwmed", "fonte", "completo"]
        serie = pd.concat([planilha[colunas], mensal[colunas]], ignore_index=True).merge(
            mlt[["nome", "mes", "mlt"]], on=["nome", "mes"]
        )
        serie["nivel"] = nivel
        serie["data"] = pd.to_datetime({"year": serie.ano, "month": serie.mes, "day": 1})
        serie["pct_mlt"] = serie.mwmed / serie.mlt * 100
        series.append(serie)
        mlts.append(mlt)
    colunas = [
        "nivel",
        "nome",
        "data",
        "ano",
        "mes",
        "mwmed",
        "mlt",
        "pct_mlt",
        "fonte",
        "completo",
    ]
    ena = pd.concat(series, ignore_index=True)[colunas].sort_values(["nivel", "nome", "data"])
    mlt = pd.concat(mlts, ignore_index=True)[["nivel", "nome", "mes", "mlt"]]
    return ena.reset_index(drop=True), mlt, diarias


def indice_oficial(arm: Armazenamento, nome: str) -> pd.Series:
    """Série da versão mais recente do índice oficial `nome` (nome canônico em raw/)."""
    _, pasta = versoes(arm, f"{chaves.RAW_INDICES}/{nome}")[-1]
    leitor = {
        "oni.ascii.txt": noaa.ler_indice_trimestral_cpc,
        "RONI.ascii.txt": noaa.ler_indice_trimestral_cpc,
        "ersst.v5.pdo.dat": noaa.ler_pdo_ncei,
        "ersst.v5.amo.dat": noaa.ler_amo_ncei,
        "soi.txt": noaa.ler_soi_cpc,
        "aao_mensal.txt": noaa.ler_aao_cpc,
    }[nome]
    return leitor(arm.caminho_local(f"{pasta}/{nome}"))


def indices_mensais(arm: Armazenamento) -> pd.DataFrame:
    df = indices_ersst(arm.caminho_local(chaves.RAW_ERSST))
    oficiais = {
        "oni": "oni.ascii.txt",
        "roni": "RONI.ascii.txt",
        "pdo": "ersst.v5.pdo.dat",
        "amo_ncei": "ersst.v5.amo.dat",
        "soi": "soi.txt",
        "aao": "aao_mensal.txt",
    }
    for coluna, nome in oficiais.items():
        df[coluna] = indice_oficial(arm, nome)
    df.index.name = "data"
    return df[df.index >= "1930-01-01"]


def tratar(arm: Armazenamento, aviso=None) -> dict:
    ena, mlt, diarias = ena_mensal(arm)
    gravar_parquet(arm, ena, chaves.PROC_ENA)
    gravar_parquet(arm, mlt, chaves.PROC_MLT)
    for nivel, d in diarias.items():
        gravar_parquet(arm, d, chaves.PROC_DIARIA[nivel])
    ind = indices_mensais(arm)
    gravar_parquet(arm, ind, chaves.PROC_INDICES)
    sub = ena[ena.nivel == "subsistema"]
    return {
        "ena_mensal": f"{len(ena)} linhas, {ena.data.min():%Y-%m} a {ena.data.max():%Y-%m}"
        f" (último mês completo {sub[sub.completo].data.max():%Y-%m})",
        "ena_diaria": f"até {diarias['subsistema'].data.max():%d/%m/%Y}",
        "indices": f"ERSST até {ind.nino34_rel.dropna().index.max():%Y-%m}, "
        f"ONI até {ind.oni.dropna().index.max():%Y-%m}",
    }
