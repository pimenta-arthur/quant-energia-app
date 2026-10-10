"""Leitores das saídas e entradas do NEWAVE (deck oficial da CCEE).

- nwlistop (ghtotsin, eafbm00x, cmarg00x): 2.000 séries × 5 anos por ano civil.
- c_adic.dat (ANDE + consumo interno de Itaipu) e sistema.dat (carga e PCH por submercado),
  em largura fixa.
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
