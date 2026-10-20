"""Tabelas-base do descolamento: raw/ → processed/pricing_descolamento/ (pesquisa: pricing-descolamento-analytics,
promocao-quant-v1, seção 4 do pacote).

- T1 PLD publicado: horário em formato largo (uma coluna por submercado) e mensal (só meses completos), com o
  descolamento de cada submercado em relação ao SE e indicadores do mês (`pld_mensal`);
- T2 projeções do deck do NEWAVE (última publicação do conjunto sistema_agrint de cada deck): mercado, usinas não
  simuladas e limites dos agrupamentos de intercâmbio, com a coluna `deck` (AAAAMM);
- T3 balanço horário do DESSEM (média das duas meias-horas): demanda, renovável, hidráulica, térmica e saldo por
  submercado;
- T4 restrições de intercâmbio horárias, por composição: média de valor, linf e lsup; `mult` = máximo do módulo;
- T5 base horária: T3 + T4 (restrições conhecidas) + T1, junção interna com o PLD, desde 2021.

T3 e T4 são particionados por mês do dia do caso e só refeitos quando o conjunto de dias do mês muda em raw/;
T1, T2 e T5 são refeitos inteiros (segundos).
"""

import datetime as dt
import json
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from qe_core.armazenamento import Armazenamento, gravar_parquet, ler_parquet
from qe_core.leitores import ccee, dessem, newave
from qe_pricing_descolamento import chaves

SUBMERCADOS = ["SE", "S", "NE", "N"]
VARS_SIST = {
    "demanda": "demanda",
    "grenova": "renovavel",
    "somat_gh": "hidraulica",
    "somat_gt": "termica",
    "saldo": "saldo",
}
INICIO_BASE = "2021-01-01"

# Restrições de intercâmbio do DESSEM, identificadas pela composição (elementos com sinal): o número da RE muda
# entre decks (pesquisa: fisica.RESTRICOES)
RESTRICOES = {
    "+NE-FC +NE-SE -FC-NE -SE-NE": "EXP_NE",  # exportação total do NE (para o SE e para o nó de Imperatriz)
    "+FC-NE +SE-NE -NE-FC -NE-SE": "REC_NE",
    "+FC-SE +NE-SE -SE-FC -SE-NE": "REC_SE_NNE",  # SE recebe de N+NE (tronco N/NE→SE)
    "+FC-SE +IV-SE +NE-SE -SE-FC -SE-IV -SE-NE": "REC_SE_tot",
    "+SE-FC +SE-NE -FC-SE -NE-SE": "EXP_SE_NNE",
    "+N -FC -FC-N": "EXP_N",
    "+FC-N -N -FC": "REC_N",
    "+NE-FC -FC-NE": "NE>FC",
    "+FC-NE -NE-FC": "FC>NE",
    "+NE-SE -SE-NE": "NE>SE",
    "+SE-NE -NE-SE": "SE>NE",
    "+FC-SE -SE-FC": "FC>SE",
    "+SE-FC -FC-SE": "SE>FC",
    "+IV-S -S -IV": "IV-S",
    "+S -IV -IV-S": "S-IV",
    "+IV-SE -SE-IV": "IV>SE",
    "+SE-IV -IV-SE": "SE>IV",
}
# R$/MWh: multiplicador abaixo disso é penalidade numérica, não gargalo (trava = mult > LIMIAR_MULT)
LIMIAR_MULT = 1.0


# --- T1: PLD publicado --------------------------------------------------------------------------------


def limites(arm: Armazenamento) -> pd.DataFrame:
    return ccee.ler_limites_pld(arm.caminho_local(chaves.RAW_LIMITES)).set_index("ano")


def pld_horario(arm: Armazenamento) -> pd.DataFrame:
    """PLD publicado de todos os anos em formato largo: índice `data_hora`, colunas SE, S, NE e N."""
    anos = sorted(c for c in arm.listar(chaves.RAW_PLD) if c.endswith(".csv"))
    p = pd.concat([ccee.ler_pld_horario(arm.caminho_local(c)) for c in anos], ignore_index=True)
    p["data_hora"] = p["data"] + pd.to_timedelta(p["hora"], unit="h")
    largo = p.pivot_table(index="data_hora", columns="submercado", values="pld")
    largo = largo.reindex(columns=SUBMERCADOS)
    largo.columns.name = None
    return largo.sort_index()


def fracao_folga(d, folga_inf, folga_sup):
    """Fração da folga em [−1, 1]: −1 = submercado no piso, +1 = no teto, 0 = acoplado ao SE."""
    d, fi, fs = (np.asarray(x, dtype=float) for x in (d, folga_inf, folga_sup))
    with np.errstate(divide="ignore", invalid="ignore"):
        f = np.where(d < 0, d / np.maximum(fi, 1e-6), d / np.maximum(fs, 1e-6))
    # |d| < R$ 0,50 é ruído de arredondamento (evita fração ±1 com o SE no piso ou no teto)
    f = np.where(np.abs(d) < 0.5, 0.0, f)
    return np.clip(f, -1, 1)


def pld_mensal(horario: pd.DataFrame, lim: pd.DataFrame) -> pd.DataFrame:
    """PLD médio mensal (média simples das horas), só meses completos (todas as horas do calendário).

    Colunas: SE, S, NE, N; d_<sub> = sub − SE; horas_desc_<sub> (fração das horas com |sub − SE| > R$ 1);
    horas_piso_<sub> (fração das horas no piso); piso, teto (estrutural); folga_inf = SE − piso;
    folga_sup = teto − SE; frac_<sub> = fração da folga."""
    h = horario
    mes = h.index.to_period("M")
    horas = h.groupby(mes).size()
    esperadas = pd.Series([p.days_in_month * 24 for p in horas.index], index=horas.index)
    completos = horas.index[horas >= esperadas]
    piso_h = pd.Series(h.index.year, index=h.index).map(lim["piso"])
    m = h.groupby(mes).mean()
    out = m.copy()
    for s in ["S", "NE", "N"]:
        d = h[s] - h["SE"]
        out[f"d_{s}"] = m[s] - m["SE"]
        out[f"horas_desc_{s}"] = (d.abs() > 1).groupby(mes).mean()
        out[f"horas_piso_{s}"] = ((h[s] - piso_h).abs() < 0.5).groupby(mes).mean()
    out["piso"] = [lim.loc[p.year, "piso"] for p in out.index]
    out["teto"] = [lim.loc[p.year, "teto_estrutural"] for p in out.index]
    out["folga_inf"] = out["SE"] - out["piso"]
    out["folga_sup"] = out["teto"] - out["SE"]
    for s in ["S", "NE", "N"]:
        out[f"frac_{s}"] = fracao_folga(out[f"d_{s}"], out["folga_inf"], out["folga_sup"])
    out = out.loc[out.index.isin(completos)]
    out.index = out.index.astype(str)
    out.index.name = "mes"
    return out


# --- T2: projeções do deck do NEWAVE --------------------------------------------------------------------


def decks_sistema_agrint(arm: Armazenamento) -> dict[str, str]:
    """{AAAAMM: pasta em raw/ do conjunto sistema_agrint usado}: a última publicação de cada deck (empate: a
    ingerida por último)."""
    escolha = {}
    for c in arm.listar(chaves.RAW_NEWAVE):
        partes = c.split("/")
        if len(partes) != 6 or partes[3] != "sistema_agrint" or partes[5] != "_ingestao.json":
            continue
        marca = json.loads(arm.ler_bytes(c))
        deck = partes[2][5:].replace("-", "")
        ordem = (marca.get("publicacao") or 0, marca["ingerido_em"])
        if deck not in escolha or ordem > escolha[deck][0]:
            escolha[deck] = (ordem, "/".join(partes[:5]))
    return {d: p for d, (_, p) in sorted(escolha.items())}


def tratar_decks(arm: Armazenamento) -> dict[str, pd.DataFrame]:
    partes = {"mercado": [], "nao_simuladas": [], "agrint": []}
    for deck, pasta in decks_sistema_agrint(arm).items():
        s = newave.ler_sistema(arm.caminho_local(f"{pasta}/sistema.dat"))
        for k in ("mercado", "nao_simuladas"):
            partes[k].append(s[k].assign(deck=deck))
        partes["agrint"].append(
            newave.ler_agrint(arm.caminho_local(f"{pasta}/agrint.dat")).assign(deck=deck)
        )
    out = {k: pd.concat(v, ignore_index=True) for k, v in partes.items()}
    for k, v in out.items():
        gravar_parquet(arm, v, chaves.PROC_DECK[k])
    return out


# --- T3 e T4: DESSEM, uma partição por mês ----------------------------------------------------------------


def dias_dessem(arm: Armazenamento) -> dict[str, dict[dt.date, dict[str, str]]]:
    """{mes: {dia: {PDO_SIST.DAT / PDO_RESTOPER.DAT: caminho}}} dos dias com PDO_SIST.DAT em raw/."""
    dias: dict[dt.date, dict[str, str]] = {}
    for c in arm.listar(chaves.RAW_DESSEM):
        partes = c.split("/")
        if len(partes) != 4 or not partes[2].startswith("dia="):
            continue
        if partes[3] in ("PDO_SIST.DAT.gz", "PDO_RESTOPER.DAT.gz"):
            dia = dt.date.fromisoformat(partes[2][4:])
            dias.setdefault(dia, {})[partes[3][:-3]] = str(arm.caminho_local(c))
    meses: dict[str, dict[dt.date, dict[str, str]]] = {}
    for dia, arqs in sorted(dias.items()):
        if "PDO_SIST.DAT" in arqs:
            meses.setdefault(f"{dia:%Y-%m}", {})[dia] = arqs
    return meses


def _hora(data: dt.date, periodo: pd.Series) -> pd.Series:
    return pd.Timestamp(data) + pd.to_timedelta((periodo - 1) // 2, unit="h")


def _ler_mes(dias: dict[dt.date, dict[str, str]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """T3 e T4 de um mês (no processo filho)."""
    sist, re_ = [], []
    for dia, arqs in sorted(dias.items()):
        s = dessem.ler_pdo_sist(arqs["PDO_SIST.DAT"], dia)
        s = s.assign(hora=_hora(dia, s["periodo"]))[["hora", "submercado", *VARS_SIST]]
        sist.append(s.groupby(["hora", "submercado"]).mean().reset_index())
        if "PDO_RESTOPER.DAT" in arqs:
            r = dessem.ler_re_inte(arqs["PDO_RESTOPER.DAT"], dia)
            if len(r):
                r = r.assign(hora=_hora(dia, r["periodo"]))
                re_.append(
                    r.groupby(["hora", "composicao"])
                    .agg(
                        valor=("valor", "mean"),
                        linf=("linf", "mean"),
                        lsup=("lsup", "mean"),
                        mult=("mult", lambda m: m.abs().max()),
                    )
                    .reset_index()
                )
    s = pd.concat(sist, ignore_index=True).rename(columns={"submercado": "sub", **VARS_SIST})
    r = (
        pd.concat(re_, ignore_index=True)
        if re_
        else pd.DataFrame(columns=["hora", "composicao", "valor", "linf", "lsup", "mult"])
    )
    return s, r


def _dias_tratados(arm: Armazenamento, mes: str) -> set[dt.date]:
    if not all(arm.existe(chaves.proc_dessem(t, mes)) for t in ("sist", "re")):
        return set()
    marca = ler_parquet(arm, chaves.proc_dessem("sist", mes))["hora"].dt.date.unique()
    return set(marca)


def tratar_dessem(arm: Armazenamento, refazer: bool = False, aviso=None) -> dict[str, int]:
    """Refaz as partições mensais de T3 e T4 cujo conjunto de dias mudou em raw/. Devolve {mes: dias}."""
    meses = dias_dessem(arm)
    pendentes = {m: d for m, d in meses.items() if refazer or _dias_tratados(arm, m) != set(d)}
    feitos = {}
    with ProcessPoolExecutor() as ex:
        for mes, (s, r) in zip(pendentes, ex.map(_ler_mes, pendentes.values())):
            gravar_parquet(arm, s, chaves.proc_dessem("sist", mes))
            gravar_parquet(arm, r, chaves.proc_dessem("re", mes))
            feitos[mes] = len(pendentes[mes])
            if aviso:
                aviso(f"DESSEM {mes}: {feitos[mes]} dias")
    return feitos


def _ler_particoes(arm: Armazenamento, tabela: str) -> pd.DataFrame:
    prefixo = f"{chaves.PROC}/dessem/{tabela}/"
    return pd.concat(
        [ler_parquet(arm, c) for c in sorted(arm.listar(prefixo)) if c.endswith(".parquet")],
        ignore_index=True,
    )


# --- T5: base horária ------------------------------------------------------------------------------------


def base_horaria(
    horario: pd.DataFrame, pld: pd.DataFrame, re_: pd.DataFrame, desde: str = INICIO_BASE
) -> pd.DataFrame:
    """Uma linha por hora: balanço por submercado, fluxo/limite/trava de cada restrição conhecida e PLD
    (junção interna), com as derivadas do modelo (pesquisa: fisica.base_horaria)."""
    w = horario.pivot_table(
        index="hora",
        columns="sub",
        values=["demanda", "renovavel", "hidraulica", "termica", "saldo"],
    )
    w.columns = [f"{a}_{b}" for a, b in w.columns]
    r = re_.assign(rest=re_["composicao"].map(RESTRICOES))
    r = r[r["rest"].notna()]
    r = r.assign(trava=r["mult"] > LIMIAR_MULT)
    rr = r.pivot_table(
        index="hora", columns="rest", values=["valor", "lsup", "trava"], aggfunc="max"
    )
    rr.columns = [f"{a}_{b}" for a, b in rr.columns]
    x = w.join(rr).join(pld, how="inner")
    x = x[x.index >= desde].copy()
    for s in ("NE", "N"):
        x[f"d_{s}"] = x[s] - x["SE"]
        x[f"desc_{s}"] = x[f"d_{s}"] < -1
    x["regime"] = np.where(x.index.month <= 6, "1S", "2S")
    x["sobra_ren_NE"] = x["renovavel_NE"] - x["demanda_NE"]
    x["sobra_NE"] = x["sobra_ren_NE"] + x["hidraulica_NE"] + x["termica_NE"]
    x["sobra_N"] = x["renovavel_N"] + x["hidraulica_N"] + x["termica_N"] - x["demanda_N"]
    x["sobra_NNE"] = x["sobra_NE"] + x["sobra_N"]
    x["margem_exp_NE"] = x["sobra_ren_NE"] - x["lsup_EXP_NE"]
    # sem térmica (térmica é despacho, não insumo exógeno): usadas no modelo
    x["sobra_N_st"] = x["renovavel_N"] + x["hidraulica_N"] - x["demanda_N"]
    x["sobra_NNE_st"] = x["sobra_ren_NE"] + x["hidraulica_NE"] + x["sobra_N_st"]
    x.index.name = "hora"
    return x


# --- tudo ------------------------------------------------------------------------------------------------


def tratar(arm: Armazenamento, refazer: bool = False, aviso=None) -> dict:
    """T1 a T5. Devolve um resumo."""
    feitos = tratar_dessem(arm, refazer, aviso)
    horario = pld_horario(arm)
    gravar_parquet(arm, horario, chaves.PROC_PLD_HORARIO)
    mensal = pld_mensal(horario, limites(arm))
    gravar_parquet(arm, mensal, chaves.PROC_PLD_MENSAL)
    decks = tratar_decks(arm)
    base = base_horaria(_ler_particoes(arm, "sist"), horario, _ler_particoes(arm, "re"))
    gravar_parquet(arm, base, chaves.PROC_BASE)
    return {
        "meses_dessem_refeitos": len(feitos),
        "pld": f"{horario.index.min():%d/%m/%Y} a {horario.index.max():%d/%m/%Y %Hh}",
        "meses_completos": f"{mensal.index.min()} a {mensal.index.max()} ({len(mensal)})",
        "decks": f"{decks['mercado']['deck'].min()} a {decks['mercado']['deck'].max()} "
        f"({decks['mercado']['deck'].nunique()})",
        "base_horaria": f"{base.index.min():%d/%m/%Y} a {base.index.max():%d/%m/%Y}, {len(base)} horas",
    }
