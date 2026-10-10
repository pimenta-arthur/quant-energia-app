"""Leitores de arquivos do PMO do ONS (DECOMP revisão 0): relato.rv0, ena.pdf e renovaveis.csv.

Funções puras sobre o caminho do arquivo. `n_sem` é o número de semanas operativas do mês
(colunas de `ccee.horas_por_semana`); as semanas do mês seguinte são descartadas.
"""

import io
import re
from pathlib import Path

import numpy as np
import pandas as pd

from qe_core.leitores.ccee import _num_br

SUBSISTEMAS = {"SECO": "SE", "SUL": "S", "NE": "NE", "N": "N"}


def _linhas(caminho: Path) -> list[str]:
    return Path(caminho).read_text(encoding="latin-1").splitlines()


def ler_ena(caminho: Path) -> pd.DataFrame:
    """Tabela 6 do ena.pdf: ENA da 1ª semana e previsão mensal inicial por subsistema (MWmed, % MLT)."""
    import pdfplumber

    with pdfplumber.open(caminho) as pdf:
        texto = pdf.pages[0].extract_text()
    nomes = {"SUDESTE": "SE", "SUL": "S", "NORDESTE": "NE", "NORTE": "N"}
    linhas = texto.splitlines()
    inicio = next(i for i, ln in enumerate(linhas) if "TABELA 6" in ln)
    dados = {}
    for ln in linhas[inicio : inicio + 12]:
        m = re.match(r"(SUDESTE|SUL|NORDESTE|NORTE)\s+([\d.]+)\s+(\d+)\s+([\d.]+)\s+(\d+)", ln)
        if m:
            dados[nomes[m.group(1)]] = {
                "ena_sem1": _num_br(m.group(2)),
                "ena_sem1_mlt": float(m.group(3)),
                "ena_mes": _num_br(m.group(4)),
                "ena_mes_mlt": float(m.group(5)),
            }
    if len(dados) != 4:
        raise ValueError(f"{caminho}: Tabela 6 com {len(dados)} subsistemas")
    return pd.DataFrame(dados).T


def ler_renovaveis(caminho: Path, n_sem: int) -> dict:
    """Eólica e solar centralizadas do renovaveis.csv: (fonte, subsistema) -> patamar × semana (MW)."""
    linhas = [ln for ln in _linhas(caminho) if ln.startswith("PEE-GER-PER-PAT-CEN")]
    g = pd.read_csv(
        io.StringIO("\n".join(linhas)),
        sep=";",
        header=None,
        names=["id", "pee", "per_ini", "per_fin", "pat", "cen", "mw"],
    )
    g = g[g.per_ini <= n_sem]
    if (g.cen != 1).any():
        raise ValueError("esperado cenário único nas semanas do mês")
    codigos = {1: "SE", 2: "S", 3: "NE", 4: "N"}  # 1-4 eólica; 11-14 fotovoltaica
    saida = {}
    for pee, d in g.groupby("pee"):
        fonte = "EOL" if pee < 10 else "UFV"
        saida[(fonte, codigos[pee % 10])] = (
            d.pivot(index="pat", columns="per_ini", values="mw").sort_index().to_numpy()
        )
    return saida


def ler_relato_balanco(caminho: Path, n_sem: int) -> pd.DataFrame:
    """RELATORIO DO BALANCO ENERGETICO: uma linha por semana, subsistema e patamar (MWmed).

    Colunas localizadas pelo cabeçalho (o layout mudou: até set/2025 não há `Geol` e as pequenas
    usinas se chamam `Bacia`). GH ONS = soma de ghid + it60.
    """
    nomes = {
        "Mercado": "mercado",
        "PQUsi": "pqusi",
        "Bacia": "pqusi",
        "Cbomba": "cbomba",
        "Ghid": "ghid",
        "Gter": "gter",
        "GterAT": "gterat",
        "Geol": "geol",
    }
    linhas, semana, sub, colunas = [], None, None, None
    for ln in _linhas(caminho):
        m = re.search(r"SEMANA (\d) - ESTAGIO", ln)
        if m:
            semana = int(m.group(1))
        m = re.match(r"\s+Subsistema (\w+)\s*$", ln)
        if m:
            sub = m.group(1)
        if ln.split()[:1] == ["Mercado"]:
            cabecalho = ln.split()
            colunas = cabecalho[: cabecalho.index("Interligacao")]
            continue
        m = re.match(r"\s+Pat_(\d)\s+(.*)", ln)
        if m and semana and sub and colunas:
            valores = [float(x) for x in m.group(2).split()[: len(colunas)]]
            linha = {"semana": semana, "subsistema": sub, "pat": int(m.group(1))}
            linha.update({nomes[c]: v for c, v in zip(colunas, valores) if c in nomes})
            it50, it60 = (float(x) for x in ln.split()[-2:]) if sub == "SE" else (0, 0)
            linha.update({"it50": it50, "it60": it60})
            linhas.append(linha)
    df = pd.DataFrame(linhas).drop_duplicates(["semana", "subsistema", "pat"])
    for coluna in ("geol", "gterat"):
        if coluna not in df:
            df[coluna] = 0.0
    return df[df.semana <= n_sem].fillna(0.0).reset_index(drop=True)


def ler_relato_termicas(caminho: Path) -> pd.DataFrame:
    """Geração térmica por usina, semana e patamar, com GTmin/GTmax do cadastro (MWmed).

    Parcela inflexível de cada usina = min(geração, GTmin).
    """
    linhas = _linhas(caminho)
    inicio = next(
        i
        for i, ln in enumerate(linhas)
        if ln.strip() == "Relatorio  dos  Dados  de  Usinas  Termicas"
    )
    cadastro, usina = [], None
    for ln in linhas[inicio + 5 :]:
        if ln.strip().startswith("X-"):
            break
        m = re.match(r"\s+\d+ (.{10})\s+(\w+)\s+(\d+)\s+(.*)", ln)
        if m:
            usina = (m.group(1).strip(), m.group(2))
            estagio, valores = int(m.group(3)), m.group(4).split()
        else:
            m = re.match(r"\s+(\d+)\s+([\d.]+\s.*)", ln)
            if not m or usina is None:
                continue
            estagio, valores = int(m.group(1)), m.group(2).split()
        valores = [float(x) for x in valores]
        for p in range(3):
            cadastro.append(
                {
                    "usina": usina[0],
                    "subsistema": usina[1],
                    "semana": estagio,
                    "pat": p + 1,
                    "gtmin": valores[3 * p],
                    "gtmax": valores[3 * p + 1],
                }
            )
    flag = r"\s+([\d.]+)([IS]?)"
    padrao = re.compile(r"\s+(SE|S|NE|N|FC)\s+(.{10})" + flag * 3 + r"\s+[\d.]+")
    operacao, semana = [], None
    for i, ln in enumerate(linhas):
        if "RELATORIO  DA  OPERACAO  TERMICA E CONTRATOS" in ln:
            semana = int(re.search(r"SEMANA (\d)", linhas[i + 2]).group(1))
            continue
        if "RELATORIO  DO  BALANCO  ENERGETICO" in ln:
            semana = None
        m = padrao.match(ln) if semana else None
        if m:
            for p in range(3):
                operacao.append(
                    {
                        "semana": semana,
                        "subsistema": m.group(1),
                        "usina": m.group(2).strip(),
                        "pat": p + 1,
                        "ger": float(m.group(3 + 2 * p)),
                        "flag": m.group(4 + 2 * p),
                    }
                )
    df = pd.DataFrame(operacao).merge(
        pd.DataFrame(cadastro), on=["usina", "subsistema", "semana", "pat"], how="left"
    )
    if df.gtmin.isna().any():
        raise ValueError(f"usinas sem cadastro: {df[df.gtmin.isna()].usina.unique()}")
    df["inflexivel"] = np.minimum(df.ger, df.gtmin)
    df["nuclear"] = df.usina.str.startswith("ANGRA")
    return df


def ler_relato_pequenas(caminho: Path, n_sem: int) -> pd.DataFrame:
    """Pequenas usinas: tipo (PCH, PCT, EOL, UFV e as `gd` da MMGD), subsistema, semana, pat, mw."""
    linhas = _linhas(caminho)
    inicio = next(
        i for i, ln in enumerate(linhas) if ln.strip() == "Relatorio dos Dados de Pequenas Usinas"
    )
    saida, usina, bordas = [], None, 0
    for ln in linhas[inicio + 1 :]:
        if ln.strip().startswith("X-"):
            bordas += 1
            if bordas == 3:
                break
            continue
        m = re.match(r"\s+(SECO|SUL|NE|N)_(PCH|PCT|EOL|UFV)(gd)?\s+\w+\s+(\d+)\s+(.*)", ln)
        if m:
            usina = (m.group(2) + (m.group(3) or ""), SUBSISTEMAS[m.group(1)])
            estagio, valores = int(m.group(4)), m.group(5).split()
        else:
            m = re.match(r"\s+(\d+)\s+([\d.]+\s.*)", ln)
            if not m or usina is None:
                continue
            estagio, valores = int(m.group(1)), m.group(2).split()
        if estagio > n_sem:
            continue
        for p, v in enumerate(valores[:3], start=1):
            saida.append(
                {
                    "tipo": usina[0],
                    "subsistema": usina[1],
                    "semana": estagio,
                    "pat": p,
                    "mw": float(v),
                }
            )
    return pd.DataFrame(saida)


def ler_relato_ande(caminho: Path, n_sem: int) -> pd.DataFrame:
    """ANDE (Itaipu para o Paraguai + consumo interno) por semana e patamar (MWmed)."""
    linhas = _linhas(caminho)
    inicio = next(
        i for i, ln in enumerate(linhas) if "Relatorio de eco  das informacoes de ITAIPU" in ln
    )
    saida = []
    for ln in linhas[inicio + 5 :]:
        if ln.strip().startswith("X-"):
            break
        per, pat, *_, ande = ln.split()
        if int(per) <= n_sem:
            saida.append({"semana": int(per), "pat": int(pat), "ande": float(ande)})
    return pd.DataFrame(saida)


def ler_relato_ear(caminho: Path) -> pd.DataFrame:
    """EAR inicial do mês por subsistema (cabeçalho do balanço da semana 1): MWmês e % EARmax."""
    linhas = _linhas(caminho)
    inicio = next(i for i, ln in enumerate(linhas) if "RELATORIO  DO  BALANCO  ENERGETICO" in ln)
    saida = {}
    for i in range(inicio, inicio + 200):
        m = re.match(r"\s+Subsistema (SE|S|NE|N)\s*$", linhas[i])
        if m:
            mwmes = float(re.search(r"EAR_ini:\s*([\d.]+)", linhas[i + 1]).group(1))
            pct = float(linhas[i + 2].split()[0])
            saida[m.group(1)] = {"ear_mwmes": mwmes, "ear_pct": pct}
    return pd.DataFrame(saida).T
