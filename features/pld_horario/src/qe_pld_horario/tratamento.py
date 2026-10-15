"""Tratamento: raw/ → processed/pld_horario/ (Parquet).

Duas partes, para a atualização diária ser rápida:
- **decks do DESSEM** (a parte cara: ~2.000 dias): uma partição por mês civil do dia do caso, refeita
  só quando o conjunto de dias completos desse mês em raw/ muda (ou com `refazer`);
- **tabelas-base** (DECOMP, T1, T2, T3 e T5): refeitas inteiras a cada execução, em segundos.

Método (pesquisa risk-lab-dessem-analytics, D012, D017, D044, D048, D054):
- T1: PLD publicado pela CCEE; nos dias com deck e ainda sem publicação, PLD calculado do CMO do
  deck pela regra oficial (Regras de Comercialização, PLD 2026.1.0, seção 1.4.1, comandos 10 e 11);
- T2: hora a hora com o DECOMP vigente do dia (estágio 1 da revisão que começa no sábado da semana,
  última publicação; PLD semanal = média dos patamares ponderada pelas horas, com limites);
- T3: tipo de dia (útil, sábado, domingo/feriado; feriado = dia de semana sem patamar pesado no deck);
- T5: desvio do mês civil por bloco de horas (soma dos blocos = desvio do mês).
"""

import datetime as dt
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from qe_core.armazenamento import Armazenamento, gravar_parquet, ler_parquet
from qe_core.leitores import ccee, decomp, dessem
from qe_pld_horario import chaves
from qe_pld_horario.modelo import MODELO, SUBMERCADOS

INICIO_PLD_HORARIO = pd.Timestamp("2021-01-01")
PATAMAR = {"PESADA": 1, "MEDIA": 2, "LEVE": 3}
TABELAS_DESSEM = ("sist", "renovaveis")


# --- inventário de raw/ ----------------------------------------------------------------------------


@dataclass
class Inventario:
    """Dias de deck do DESSEM em raw/: completos (entrada e resultado) e incompletos."""

    completos: dict[dt.date, dict[str, str]] = field(default_factory=dict)  # dia → {arquivo: chave}
    incompletos: dict[dt.date, list[str]] = field(default_factory=dict)  # dia → o que falta

    def por_mes(self) -> dict[str, list[dt.date]]:
        meses: dict[str, list[dt.date]] = {}
        for d in sorted(self.completos):
            meses.setdefault(f"{d:%Y-%m}", []).append(d)
        return meses


def inventario_dessem(arm: Armazenamento) -> Inventario:
    arquivos: dict[dt.date, dict[str, str]] = {}
    for chave in arm.listar(chaves.RAW_DESSEM):
        partes = chave.split("/")
        if not partes[2].startswith("dia=") or not partes[3].endswith(".gz"):
            continue
        dia = dt.date.fromisoformat(partes[2][4:])
        arquivos.setdefault(dia, {})[partes[3][:-3]] = chave
    inv = Inventario()
    obrigatorios = [a for lista in chaves.ARQUIVOS_DESSEM.values() for a in lista]
    for dia, arqs in sorted(arquivos.items()):
        faltam = [a for a in obrigatorios if a not in arqs and a not in chaves.OPCIONAIS_DESSEM]
        if faltam:
            inv.incompletos[dia] = faltam
        else:
            inv.completos[dia] = arqs
    return inv


# --- decks do DESSEM: uma partição por mês ---------------------------------------------------------


def _ler_mes(dias: list[tuple[dt.date, dict[str, str]]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Lê os dias de um mês (no processo filho): (PDO_SIST, previsão de renováveis)."""
    sist, ren = [], []
    for dia, caminhos in dias:
        dessem.conferir_tm(caminhos["entdados.dat"], dia)
        sist.append(dessem.ler_pdo_sist(caminhos["PDO_SIST.DAT"], dia))
        ren.append(dessem.ler_renovaveis(caminhos["renovaveis.dat"], dia))
    s = pd.concat(sist, ignore_index=True)
    r = pd.concat(ren, ignore_index=True)
    s["data"], r["data"] = pd.to_datetime(s["data"]), pd.to_datetime(r["data"])
    return (
        s.sort_values(["data", "periodo", "submercado"], ignore_index=True),
        r.sort_values(["data", "periodo", "submercado", "tipo"], ignore_index=True),
    )


def _dias_tratados(arm: Armazenamento, mes: str) -> set[dt.date]:
    chave = chaves.proc_dessem("sist", mes)
    if not all(arm.existe(chaves.proc_dessem(t, mes)) for t in TABELAS_DESSEM):
        return set()
    return {d.date() for d in pd.to_datetime(ler_parquet(arm, chave)["data"].unique())}


def tratar_dessem(arm: Armazenamento, refazer: bool = False, aviso=None) -> dict[str, int]:
    """Refaz as partições mensais cujo conjunto de dias completos mudou em raw/. {mes: dias}."""
    inv = inventario_dessem(arm)
    pendentes = {
        mes: dias
        for mes, dias in inv.por_mes().items()
        if refazer or _dias_tratados(arm, mes) != set(dias)
    }
    if not pendentes:
        return {}
    tarefas = [
        [(d, {a: str(arm.caminho_local(c)) for a, c in inv.completos[d].items()}) for d in dias]
        for dias in pendentes.values()
    ]
    feitos = {}
    with ProcessPoolExecutor() as ex:
        for mes, (sist, ren) in zip(pendentes, ex.map(_ler_mes, tarefas)):
            gravar_parquet(arm, sist, chaves.proc_dessem("sist", mes))
            gravar_parquet(arm, ren, chaves.proc_dessem("renovaveis", mes))
            feitos[mes] = len(pendentes[mes])
            if aviso:
                aviso(f"DESSEM {mes}: {feitos[mes]} dias")
    return feitos


def ler_dessem(arm: Armazenamento, tabela: str, colunas: list[str] | None = None) -> pd.DataFrame:
    """Todas as partições de uma tabela do DESSEM (sist ou renovaveis)."""
    prefixo = f"{chaves.PROC}/dessem/{tabela}/"
    partes = [ler_parquet(arm, c) for c in arm.listar(prefixo) if c.endswith(".parquet")]
    d = pd.concat(partes, ignore_index=True)
    return d[colunas] if colunas else d


# --- DECOMP ----------------------------------------------------------------------------------------


def semanas_decomp(arm: Armazenamento) -> tuple[pd.DataFrame, list[str]]:
    """Uma linha por (PMO, semana) com a última publicação (D012) e as chaves do dadger e do
    sumário; e os avisos de semanas cuja última publicação está incompleta em raw/."""
    pubs: dict[tuple[str, int, int], dict[str, str]] = {}
    for chave in arm.listar(chaves.RAW_DECOMP):
        _, _, pmo, sem, pub, arq = chave.split("/")
        pubs.setdefault((pmo[4:], int(sem[4:]), int(pub[4:])), {})[arq] = chave
    linhas, avisos = [], []
    ultima: dict[tuple[str, int], int] = {}
    for pmo, sem, pub in sorted(pubs):
        if "dadger.gz" in pubs[(pmo, sem, pub)]:
            ultima[(pmo, sem)] = pub
    for (pmo, sem), pub in sorted(ultima.items()):
        arqs = pubs[(pmo, sem, pub)]
        if "sumario.gz" not in arqs:
            avisos.append(f"DECOMP {pmo} sem{sem} publicação {pub}: falta o sumário")
            continue
        linhas.append(
            {
                "pmo": pmo,
                "sem": sem,
                "publicacao": pub,
                "dadger": arqs["dadger.gz"],
                "sumario": arqs["sumario.gz"],
            }
        )
    return pd.DataFrame(linhas), avisos


def _decomp_semana(s: dict) -> pd.DataFrame:
    inicio, rv, dp = decomp.ler_dadger_dp(s["dadger"])
    rodada, cmo = decomp.ler_sumario_cmo(s["sumario"])
    d = cmo.merge(dp, on=["estagio", "submercado", "patamar"], how="left")
    d["inicio_estagio"] = [inicio + dt.timedelta(days=7 * (e - 1)) for e in d["estagio"]]
    d = d.assign(
        pmo=s["pmo"],
        sem=s["sem"],
        rv=rv,
        publicacao=s["publicacao"],
        inicio_estudo=inicio,
        rodada=rodada,
    )
    horas = d.loc[d["submercado"] != "FC", "horas"].groupby([d["estagio"], d["submercado"]]).sum()
    if not (horas == 168).all():
        raise ValueError(f"DECOMP {s['pmo']} sem{s['sem']}: estágio semanal sem 168 h")
    return d


def tratar_decomp(arm: Armazenamento) -> tuple[pd.DataFrame, list[str]]:
    """decomp_cmo: CMO, horas e carga por PMO, revisão, estágio, submercado e patamar."""
    sem, avisos = semanas_decomp(arm)
    tarefas = [
        {
            **s,
            "dadger": str(arm.caminho_local(s["dadger"])),
            "sumario": str(arm.caminho_local(s["sumario"])),
        }
        for s in sem.to_dict("records")
    ]
    with ProcessPoolExecutor() as ex:
        d = pd.concat(ex.map(_decomp_semana, tarefas), ignore_index=True)
    for c in ("inicio_estagio", "inicio_estudo", "rodada"):
        d[c] = pd.to_datetime(d[c])
    d = d.sort_values(["pmo", "sem", "estagio", "submercado", "patamar"], ignore_index=True)
    gravar_parquet(arm, d, chaves.PROC_DECOMP)
    return d, avisos


# --- limites e PLD publicado ------------------------------------------------------------------------


def limites(arm: Armazenamento) -> pd.DataFrame:
    return ccee.ler_limites_pld(arm.caminho_local(chaves.RAW_LIMITES))


def pld_publicado(arm: Armazenamento) -> pd.DataFrame:
    partes = [
        ccee.ler_pld_horario(arm.caminho_local(c))
        for c in arm.listar(chaves.RAW_PLD)
        if c.endswith(".csv")
    ]
    pld = pd.concat(partes, ignore_index=True)
    if pld.duplicated(["data", "hora", "submercado"]).any():
        raise ValueError("linhas duplicadas no PLD horário (mesma hora em dois arquivos)")
    return pld.sort_values(["data", "hora", "submercado"], ignore_index=True)


# --- T1: PLD publicado + calculado do deck (D048) ---------------------------------------------------


def cmo_horario(cmo_semi: pd.DataFrame) -> pd.DataFrame:
    """CMO_SR_EA: média dos dois CMOs semi-horários de cada hora (períodos 2h+1 e 2h+2)."""
    d = cmo_semi.assign(hora=(cmo_semi["periodo"] - 1) // 2)
    return d.groupby(["data", "hora", "submercado"], as_index=False)["cmo"].mean()


def pld_a_partir_do_cmo(
    cmo_h: pd.DataFrame, piso: float, teto_horario: float, teto_estrutural: float, max_iter=100
) -> pd.Series:
    """Piso, teto horário e o processo iterativo do teto estrutural (média diária), como na regra.

    `cmo_h` tem colunas data, hora, submercado, cmo, com as 24 horas de cada dia e submercado.
    """
    grupo = [cmo_h["data"], cmo_h["submercado"]]
    inter = cmo_h["cmo"].clip(lower=piso, upper=teto_horario)
    for _ in range(max_iter):
        media = inter.groupby(grupo).transform("mean")
        acima = media > teto_estrutural + 1e-9
        if not acima.any():
            return inter
        fator = np.round(teto_estrutural / media, 12)
        inter = inter.where(~acima, np.maximum(fator * inter, piso))
    raise RuntimeError("processo do teto estrutural não convergiu")


def pld_calculado(cmo_semi: pd.DataFrame, lim: pd.DataFrame) -> pd.DataFrame:
    """PLD horário calculado a partir do CMO semi-horário, com os limites oficiais de cada ano."""
    lim = lim.set_index("ano")
    c = cmo_horario(cmo_semi)
    c = c[c["data"] >= INICIO_PLD_HORARIO]
    partes = []
    for ano, g in c.groupby(c["data"].dt.year):
        lm = lim.loc[ano]
        g = g.sort_values(["data", "submercado", "hora"])
        pld = pld_a_partir_do_cmo(g, lm.piso, lm.teto_horario, lm.teto_estrutural)
        partes.append(g.assign(pld=pld.round(2)))
    return pd.concat(partes, ignore_index=True)


def pld_horario(pub: pd.DataFrame, sist: pd.DataFrame, lim: pd.DataFrame) -> pd.DataFrame:
    """T1: publicado e, nos dias com deck depois do último publicado, calculado do deck."""
    pub = pub.assign(origem="publicado")
    sist = sist[(sist["periodo"] <= 48) & sist["submercado"].isin(SUBMERCADOS)]
    novos = sist[sist["data"] > pub["data"].max()]
    if novos.empty:
        return pub
    calc = pld_calculado(novos, lim)[["data", "hora", "submercado", "pld"]].assign(
        origem="calculado (deck)"
    )
    return pd.concat([pub, calc], ignore_index=True)


def conferir_calculo(pub: pd.DataFrame, sist: pd.DataFrame, lim: pd.DataFrame, dias=30):
    """Diferença absoluta entre o PLD calculado do deck e o publicado nos últimos `dias` publicados
    que têm deck (lacuna L4 da pesquisa: lá conferido só em 10 dias)."""
    datas = sorted(set(pub["data"].unique()) & set(sist["data"].unique()))[-dias:]
    s = sist[
        (sist["periodo"] <= 48) & sist["data"].isin(datas) & sist["submercado"].isin(SUBMERCADOS)
    ]
    c = pld_calculado(s, lim).merge(
        pub, on=["data", "hora", "submercado"], suffixes=("_calc", "_pub")
    )
    return (c["pld_calc"] - c["pld_pub"]).abs(), datas


# --- T2: hora a hora com o DECOMP vigente (D012, D017) -----------------------------------------------


def _bloco(hora: pd.Series) -> np.ndarray:
    return np.where(
        hora.isin(MODELO.vale), "vale", np.where(hora.isin(MODELO.ponta), "ponta", "resto")
    )


def decomp_diario(dec: pd.DataFrame, lim: pd.DataFrame) -> pd.DataFrame:
    """Por data e submercado: PLD semanal do DECOMP vigente (com e sem limites) em cada dia.

    Estágio 1 da revisão que começa no sábado (última publicação). PLD semanal = média dos CMOs dos
    patamares ponderada pelas horas (DP); com limites, cada CMO em [piso, teto horário] e a média
    limitada ao teto estrutural (aproximação: o deck semanal não diz a hora de cada patamar).
    """
    e = dec[(dec["estagio"] == 1) & dec["submercado"].isin(SUBMERCADOS)].copy()
    e = e.sort_values("publicacao").drop_duplicates(
        ["inicio_estudo", "submercado", "patamar"], keep="last"
    )
    dias = [
        (ini + pd.Timedelta(days=k), ini)
        for ini in pd.to_datetime(e["inicio_estudo"].unique())
        for k in range(7)
    ]
    cal = pd.DataFrame(dias, columns=["data", "inicio_estudo"])
    x = cal.merge(
        e[["inicio_estudo", "submercado", "patamar", "cmo", "horas", "rv"]], on="inicio_estudo"
    )
    lm = lim.set_index("ano")
    ano = x["data"].dt.year
    x["piso"], x["teto_h"], x["teto_e"] = (
        ano.map(lm[c]) for c in ["piso", "teto_horario", "teto_estrutural"]
    )
    x["cmo_lim"] = x["cmo"].clip(lower=x["piso"], upper=x["teto_h"])
    g = x.groupby(["data", "submercado"])
    # np.average por grupo, como na pesquisa: outra ordem de soma muda o arredondamento a 1 casa
    out = pd.DataFrame(
        {
            "decomp_cmo": g.apply(
                lambda t: np.average(t["cmo"], weights=t["horas"]), include_groups=False
            ),
            "decomp_pld": g.apply(
                lambda t: np.average(t["cmo_lim"], weights=t["horas"]), include_groups=False
            ),
            "teto_e": g["teto_e"].first(),
            "piso": g["piso"].first(),
            "rv": g["rv"].first(),
            "semana": g["inicio_estudo"].first(),
        }
    ).reset_index()
    out["decomp_pld"] = out[["decomp_pld", "teto_e"]].min(axis=1)
    return out.drop(columns="teto_e")


def tabela_horaria(pld: pd.DataFrame, dec: pd.DataFrame, lim: pd.DataFrame) -> pd.DataFrame:
    """T2: PLD do DESSEM (T1), DECOMP vigente do dia (com e sem limites), mês civil e bloco."""
    h = pld.rename(columns={"pld": "pld_dessem"}).merge(
        decomp_diario(dec, lim), on=["data", "submercado"], how="left"
    )
    h["mes"] = h["data"].dt.strftime("%Y-%m")
    h["bloco"] = _bloco(h["hora"])
    return h


# --- T3: tipo de dia ---------------------------------------------------------------------------------


def _sabado(datas: pd.Series) -> pd.Series:
    return datas - pd.to_timedelta((datas.dt.dayofweek - 5) % 7, unit="D")


def _pelo_dia_da_semana(datas: pd.DatetimeIndex) -> pd.Series:
    dow = datas.dayofweek
    return pd.Series(
        np.select([dow == 5, dow == 6], ["sábado", "domingo/feriado"], "útil"), index=datas
    )


def tipos_de_dia(
    sist: pd.DataFrame, dec: pd.DataFrame, pld: pd.DataFrame, pub_max: pd.Timestamp, sub="SE"
) -> pd.Series:
    """Útil, sábado ou domingo/feriado de cada data desde 2021.

    Feriado = dia de semana sem nenhuma hora no patamar pesado no PDO_SIST do deck (SE), nos dias
    com deck pareado ao DECOMP vigente e com PLD (o pareamento da pesquisa). Os outros dias: só pelo
    dia da semana (feriado não identificado).
    """
    s = sist.loc[sist["submercado"] == sub, ["data", "periodo", "patamar"]].copy()
    s["patamar"] = s["patamar"].map(PATAMAR)
    s["inicio_estagio"] = _sabado(s["data"])
    d = dec.loc[(dec["estagio"] == 1) & (dec["submercado"] == sub)]
    d = d[["inicio_estudo", "patamar", "cmo"]].rename(columns={"inicio_estudo": "inicio_estagio"})
    x = s.merge(d, on=["inicio_estagio", "patamar"], how="left").dropna(subset=["cmo"])
    x["hora"] = (x["periodo"] - 1) // 2
    h = x.groupby(["data", "hora"], as_index=False)["patamar"].min()
    h = h[h.groupby("data")["hora"].transform("size") == 24]
    h = h[h["data"] >= INICIO_PLD_HORARIO]
    p = pld.loc[pld["submercado"] == sub, ["data", "hora"]]
    h = h.merge(p, on=["data", "hora"], how="inner")
    tem_pesada = h.groupby("data")["patamar"].apply(lambda v: (v == 1).any())
    dow = tem_pesada.index.dayofweek
    t = pd.Series(
        np.select(
            [dow == 5, (dow == 6) | ~tem_pesada.to_numpy()], ["sábado", "domingo/feriado"], "útil"
        ),
        index=tem_pesada.index,
    )
    todas = pd.date_range(INICIO_PLD_HORARIO, max(pub_max, t.index.max()))
    base = _pelo_dia_da_semana(todas)
    base.loc[t.index.intersection(todas)] = t
    return base.rename_axis("data").rename("tipo")


# --- T5: desvio do mês civil por bloco ---------------------------------------------------------------


def delta_mes_civil(h: pd.DataFrame) -> pd.DataFrame:
    """Por mês civil e submercado: DESSEM médio, DECOMP médio (com e sem limites), Δ e a
    contribuição de cada bloco (Σ desvio nas horas do bloco / nº de horas do mês; soma = Δ).

    `completo` = sem hora sem DECOMP e todos os dias do mês presentes.
    """
    h = h.assign(desvio=h["pld_dessem"] - h["decomp_pld"])
    g = h.groupby(["mes", "submercado"])
    t = g.agg(
        dessem=("pld_dessem", "mean"),
        decomp=("decomp_pld", "mean"),
        decomp_sem_limite=("decomp_cmo", "mean"),
        piso=("piso", "first"),
        dias=("data", "nunique"),
        horas_sem_decomp=("decomp_pld", lambda s: s.isna().sum()),
    )
    t["delta"] = t["dessem"] - t["decomp"]
    t["delta_sem_limite"] = t["dessem"] - t["decomp_sem_limite"]
    n = g.size()
    for b in ["vale", "ponta", "resto"]:
        t[f"delta_{b}"] = h[h["bloco"] == b].groupby(["mes", "submercado"])["desvio"].sum() / n
    dias_mes = pd.PeriodIndex(t.index.get_level_values("mes"), freq="M").days_in_month
    t["completo"] = (t["horas_sem_decomp"] == 0) & (t["dias"] == dias_mes)
    return t.reset_index()


# --- tudo --------------------------------------------------------------------------------------------


def tratar_tabelas(arm: Armazenamento) -> dict:
    """DECOMP, T1, T2, T3 e T5 a partir de raw/ e das partições do DESSEM. Devolve um resumo."""
    lim = limites(arm)
    dec, avisos = tratar_decomp(arm)
    sist = ler_dessem(arm, "sist", ["data", "periodo", "patamar", "submercado", "cmo"])
    pub = pld_publicado(arm)
    t1 = pld_horario(pub, sist, lim)
    gravar_parquet(arm, t1, chaves.PROC_PLD)
    t2 = tabela_horaria(t1, dec, lim)
    gravar_parquet(arm, t2, chaves.PROC_HORARIO)
    t3 = tipos_de_dia(sist, dec, t1, pub["data"].max()).reset_index()
    gravar_parquet(arm, t3, chaves.PROC_TIPOS)
    gravar_parquet(arm, delta_mes_civil(t2), chaves.PROC_DELTA)
    calc = t1.loc[t1["origem"] != "publicado", "data"]
    return {
        "ultimo_deck": sist["data"].max(),
        "ultimo_publicado": pub["data"].max(),
        "dias_calculados": sorted(calc.unique()),
        "semanas_decomp": int(dec[["pmo", "sem"]].drop_duplicates().shape[0]),
        "avisos": avisos,
    }
