"""Leitores das saídas e entradas do NEWAVE (deck oficial da CCEE).

- nwlistop (ghtotsin, eafbm00x, cmarg00x): 2.000 séries × 5 anos por ano civil.
- c_adic.dat (ANDE + consumo interno de Itaipu) e sistema.dat (carga e PCH por submercado),
  em largura fixa;
- sistema.dat (mercado e todas as usinas não simuladas) e agrint.dat (limites dos agrupamentos de
  intercâmbio) do deck de entrada, em formato longo.
"""

import re
from pathlib import Path

import pandas as pd

SUBMERCADOS = {"SE": 1, "S": 2, "NE": 3, "N": 4}


def ler_nwlistop(caminho: Path, somar_patamares: bool = True) -> pd.DataFrame:
    """Saída anual do nwlistop: colunas ano, serie, (pat), mes, valor.

    Meses anteriores ao início do estudo vêm zerados. Arquivos por patamar têm 3 linhas por série;
    com `somar_patamares=True` elas são somadas (vale para grandezas em MWmês).
    """
    linhas, ano, serie, por_pat = [], None, None, False
    for ln in Path(caminho).read_text(encoding="latin-1").splitlines():
        m = re.match(r"\s+ANO:\s+(\d{4})", ln)
        if m:
            ano = int(m.group(1))
            continue
        p = ln.split()
        if p[:1] == ["PAT"]:
            por_pat = True
            continue
        if not ano or not p or not p[0].isdigit():
            continue
        if por_pat and len(p) == 15:
            serie, pat, valores = int(p[0]), int(p[1]), p[2:14]
        elif por_pat and len(p) == 14:
            pat, valores = int(p[0]), p[1:13]
        elif not por_pat and len(p) == 14:
            serie, pat, valores = int(p[0]), 0, p[1:13]
        else:
            continue
        linhas.append([ano, serie, pat] + [float(x) for x in valores])
    df = pd.DataFrame(linhas, columns=["ano", "serie", "pat"] + list(range(1, 13)))
    df = df.melt(id_vars=["ano", "serie", "pat"], var_name="mes", value_name="valor")
    if somar_patamares:
        return df.groupby(["ano", "serie", "mes"], as_index=False).valor.sum()
    return df


def para_periodos(df: pd.DataFrame, validos=None) -> pd.DataFrame:
    """Formato longo com coluna `periodo` (AAAA-MM), só com os meses do estudo.

    Sem `validos`, descarta os meses zerados (anteriores ao início do estudo). Para o custo
    marginal, passar os meses válidos do deck (os da geração hidráulica): um submercado pode ter
    custo marginal zero em todas as séries num mês do estudo (ex.: NE e N em abr/2025), e esse mês
    não pode ser descartado.
    """
    df = df.assign(periodo=[f"{a}-{m:02d}" for a, m in zip(df.ano, df.mes)])
    if validos is None:
        soma = df.groupby("periodo").valor.apply(lambda v: v.abs().sum())
        validos = soma[soma > 0].index
    return df[df.periodo.isin(validos)].drop(columns=["ano", "mes"]).reset_index(drop=True)


def _bloco_largura_fixa(linhas: list[str], inicio: int) -> pd.Series:
    """Linhas de ano após `inicio` (ano + 12 campos de 8) até o próximo cabeçalho."""
    valores = {}
    for ln in linhas[inicio + 1 :]:
        ano = ln[:4]
        if not ano.isdigit():
            break
        for i in range(12):
            campo = ln[7 + 8 * i : 14 + 8 * i].strip()
            if campo:
                valores[f"{ano}-{i + 1:02d}"] = float(campo)
    return pd.Series(valores)


def ler_entradas_deck(c_adic: Path, sistema: Path) -> dict:
    """ANDE (+ consumo interno de Itaipu), carga e PCH por submercado projetadas pelo deck.

    Retorna `ande` (Series por AAAA-MM), `carga` e `pch` (DataFrames AAAA-MM × submercado).
    """
    linhas_c = Path(c_adic).read_text(encoding="latin-1").splitlines()
    ande = sum(
        _bloco_largura_fixa(linhas_c, i)
        for i, ln in enumerate(linhas_c)
        if ln.rstrip().endswith(("ANDE", "CONS.ITAIPU"))
    )
    linhas_s = Path(sistema).read_text(encoding="latin-1").splitlines()
    i_mercado = next(i for i, ln in enumerate(linhas_s) if "MERCADO DE ENERGIA TOTAL" in ln)
    carga = {}
    for i, ln in enumerate(linhas_s[i_mercado + 3 :], start=i_mercado + 3):
        partes = ln.split()
        if len(partes) == 1 and partes[0].isdigit():
            carga[int(partes[0])] = _bloco_largura_fixa(linhas_s, i)
        elif partes and not partes[0].isdigit() and partes[0] != "POS":
            break
    i_peq = next(i for i, ln in enumerate(linhas_s) if "GERACAO DE USINAS NAO SIMULADAS" in ln)
    pch = {}
    for i, ln in enumerate(linhas_s[i_peq:], start=i_peq):
        partes = ln.split()
        if len(partes) == 3 and partes[2] == "PCH" and partes[1] == "1":
            pch[int(partes[0])] = _bloco_largura_fixa(linhas_s, i)
    nomes = {v: k for k, v in SUBMERCADOS.items()}
    return {
        "ande": ande,
        "carga": pd.DataFrame({nomes[s]: v for s, v in carga.items() if s in nomes}),
        "pch": pd.DataFrame({nomes[s]: v for s, v in pch.items() if s in nomes}),
    }


# --- deck de entrada: SISTEMA.DAT (mercado e usinas não simuladas) e AGRINT.DAT ------------------------

SUBMERCADO_DE = {1: "SE", 2: "S", 3: "NE", 4: "N", 11: "FC"}


def _valores_ano(linha: str) -> tuple[int, dict[int, float]] | None:
    """'2027    11034.  11010. …' → (2027, {1: 11034., 2: 11010., …}); colunas fixas de 8 caracteres."""
    m = re.match(r"\s*(\d{4}|POS)\s", linha)
    if not m or m.group(1) == "POS":
        return None
    vals = {}
    for k in range(12):
        campo = linha[7 + 8 * k : 7 + 8 * (k + 1)].strip()
        if campo:
            try:
                vals[k + 1] = float(campo)
            except ValueError:
                pass
    return int(m.group(1)), vals


def ler_sistema(caminho: Path) -> dict[str, pd.DataFrame]:
    """SISTEMA.DAT em formato longo: `mercado` (sub, ano, mes, mw: carga total) e `nao_simuladas` (sub, tipo,
    ano, mes, mw: PCH, PCT, EOL, UFV e as parcelas de MMGD)."""
    linhas = Path(caminho).read_text(encoding="latin-1").splitlines()
    i_merc = next(i for i, ln in enumerate(linhas) if "MERCADO DE ENERGIA TOTAL" in ln)
    i_ger = next(i for i, ln in enumerate(linhas) if "GERACAO DE USINAS NAO SIMULADAS" in ln)
    merc, sub = [], None
    for ln in linhas[i_merc + 3 : i_ger]:
        p = ln.split()
        if len(p) == 1 and p[0].isdigit():
            sub = int(p[0])
            if sub == 999:
                break
            continue
        r = _valores_ano(ln)
        if r and sub:
            merc += [(SUBMERCADO_DE.get(sub, sub), r[0], m, v) for m, v in r[1].items()]
    ger, chave = [], None
    for ln in linhas[i_ger + 3 :]:
        m = re.match(r"\s+(\d+)\s+(\d+)\s+(\S.*?)\s*$", ln)
        if m and not re.match(r"\s*\d{4}\s", ln):
            if m.group(1) == "999":
                break
            chave = (int(m.group(1)), m.group(3).strip())
            continue
        r = _valores_ano(ln)
        if r and chave:
            ger += [
                (SUBMERCADO_DE.get(chave[0], chave[0]), chave[1], r[0], mm, v)
                for mm, v in r[1].items()
            ]
    return {
        "mercado": pd.DataFrame(merc, columns=["sub", "ano", "mes", "mw"]),
        "nao_simuladas": pd.DataFrame(ger, columns=["sub", "tipo", "ano", "mes", "mw"]),
    }


def ler_agrint(caminho: Path) -> pd.DataFrame:
    """AGRINT.DAT: limites por agrupamento de intercâmbio, uma linha por (grupo, nome, ano, mes) com os
    limites dos três patamares (`lim_p1`…`lim_p3`). Intervalo sem fim vale por 120 meses; a última definição de
    cada (grupo, ano, mês) prevalece."""
    lin, em_limites = [], False
    for ln in Path(caminho).read_text(encoding="latin-1").splitlines():
        if "LIMITES POR GRUPO" in ln:
            em_limites = True
            continue
        if not em_limites:
            continue
        m = re.match(
            r"\s+(\d+)\s+(\d+)\s+(\d{4})\s+(\d+)?\s*(\d{4})?\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(.*)$",
            ln,
        )
        if not m:
            continue
        g, mi, ai, mf, af = int(m[1]), int(m[2]), int(m[3]), m[4], m[5]
        ini = pd.Period(f"{ai}-{mi:02d}", "M")
        fim = pd.Period(f"{af}-{int(mf):02d}", "M") if mf and af else ini + 120
        lim = (float(m[6]), float(m[7]), float(m[8]))
        lin += [
            (g, m[9].strip(), p.year, p.month, *lim) for p in pd.period_range(ini, fim, freq="M")
        ]
    df = pd.DataFrame(lin, columns=["grupo", "nome", "ano", "mes", "lim_p1", "lim_p2", "lim_p3"])
    return df.drop_duplicates(["grupo", "ano", "mes"], keep="last")
