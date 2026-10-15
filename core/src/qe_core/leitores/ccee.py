"""Leitores de arquivos da CCEE: patamares de carga (AAC001), boletim InfoBandeira, PLD horário
publicado e limites anuais do PLD.

Funções puras: recebem o caminho do arquivo bruto e devolvem dados; não sabem onde o arquivo
está guardado (isso é do armazenamento).
"""

import re
import unicodedata
from pathlib import Path

import pandas as pd

PATAMARES = ["PESADO", "MEDIO", "LEVE"]  # mesma ordem dos patamares 1, 2 e 3 do DECOMP


def _normaliza(texto) -> str:
    """Remove acentos, espaços nas pontas e passa para maiúsculas."""
    return (
        unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().strip().upper()
    )


def _num_br(texto: str) -> float:
    """Número no formato brasileiro (1.234,5) -> float."""
    return float(texto.replace(".", "").replace(",", "."))


def ler_patamares(caminho: Path) -> pd.DataFrame:
    """Arquivo horário de patamares da CCEE (AAC001) de um ano: colunas `ts` e `patamar`.

    O layout muda entre anos (2025: DIA + HORA; 2026: DATA REFERÊNCIA), então o cabeçalho e as
    colunas são localizados pelo nome.
    """
    bruto = pd.read_excel(caminho, header=None)
    linha = next(i for i, r in bruto.iterrows() if any(_normaliza(v) == "PATAMAR" for v in r))
    df = bruto.iloc[linha + 1 :].copy()
    df.columns = [_normaliza(c) for c in bruto.iloc[linha]]
    if "DATA REFERENCIA" in df:
        ts = pd.to_datetime(df["DATA REFERENCIA"])
    else:
        ts = pd.to_datetime(df["DIA"]) + pd.to_timedelta(df["HORA"].astype(str))
    out = pd.DataFrame({"ts": ts, "patamar": df["PATAMAR"].map(_normaliza)}).dropna()
    if len(out) not in (8760, 8784):
        raise ValueError(f"{Path(caminho).name}: esperado um ano de horas, encontrado {len(out)}")
    return out.reset_index(drop=True)


def horas_por_semana(patamares: pd.DataFrame, mes: int) -> pd.DataFrame:
    """Horas de cada patamar em cada semana operativa do mês (patamar × semana).

    Semana operativa de sábado a sexta; a semana 1 é a que contém o dia 1. Mesmo formato da
    Tabela 11 do boletim InfoBandeira. `patamares` é a saída de `ler_patamares` do ano.
    """
    h = patamares[patamares.ts.dt.month == mes].copy()
    dia = h.ts.dt.normalize()
    h["inicio_semana"] = dia - pd.to_timedelta((dia.dt.dayofweek - 5) % 7, unit="D")
    h["semana"] = h.inicio_semana.rank(method="dense").astype(int)
    tabela = h.groupby(["patamar", "semana"]).size().unstack(fill_value=0)
    return tabela.reindex(PATAMARES, fill_value=0)


def ler_boletim(caminho: Path, ano: int) -> dict:
    """Boletim InfoBandeira: GH_band, GF_band, GSF_band, PLDs (mín, gatilho, máx), fatores e cor."""
    import pdfplumber

    with pdfplumber.open(caminho) as pdf:
        texto = "\n".join(p.extract_text() or "" for p in pdf.pages)
    padroes = {
        "gh_band": r"𝑮𝑯\s*(?:𝒃𝒂𝒏𝒅\s*)?\(𝑴𝑾𝒎𝒆𝒅\)\s*([\d.]+)",
        "gf_band": r"𝑮𝑭\s*(?:𝒃𝒂𝒏𝒅\s*)?\(𝑴𝑾𝒎𝒆𝒅\)\s*([\d.]+)",
        "gsf_band": r"𝑮𝑺𝑭\s*(?:𝒃𝒂𝒏𝒅\s*)?([\d,]+)",
    }
    saida = {}
    for chave, padrao in padroes.items():
        m = re.search(padrao, texto)
        if not m:
            raise ValueError(f"{Path(caminho).name}: não encontrado {chave}")
        saida[chave] = _num_br(m.group(1))
    # A Tabela 15 traz três PLDs com o mesmo rótulo (máximo, mínimo e gatilho); o gatilho
    # está sempre entre os outros dois, então é a mediana.
    plds = [_num_br(v) for v in re.findall(r"𝑷𝑳𝑫\s*(?:[^\s(]+\s*)?\(𝑹\$/𝑴𝑾𝒉\)\s*([\d.,]+)", texto)]
    if len(plds) != 3:
        raise ValueError(
            f"{Path(caminho).name}: esperados 3 PLDs na Tabela 15, achados {len(plds)}"
        )
    saida["pld_min"], saida["pld_gatilho"], saida["pld_max"] = sorted(plds)

    opcionais = {
        "gh_ons": r"GH ONS ([\d.]+)",
        "ande": r"ANDE \+ C\. I\. Itaipu ([\d.]+)",
        "f_bruta_conexao": r"Bruta p/ Conexão\) ([\d,]+)%",
        "f_conexao_cg": r"Hidráulica \(Conexão p/ Centro de Gravidade\) ([\d,]+)%",
        "f_part_pch": r"Participação de PCH e CGH no MRE ([\d,]+)%",
        "f_perda_pch": r"Perda de PCH e CGH \(Conexão p/ Centro de Gravidade\) ([\d,]+)%",
        "gfom": r"𝑮𝑭𝑶𝑴\s*\(𝑴𝑾𝒎𝒆𝒅\)\s*([\d.,]+)",
    }
    for chave, padrao in opcionais.items():
        m = re.search(padrao, texto)
        saida[chave] = _num_br(m.group(1)) if m else None
    for chave in ("f_bruta_conexao", "f_conexao_cg", "f_part_pch", "f_perda_pch"):
        if saida[chave] is not None:
            saida[chave] /= 100
    # Cor: em alguns boletins a Tabela 17 é imagem; aí fica None.
    m = re.search(
        rf"\w+ [Dd]e {ano} (Verde|Amarela|Vermelha(?: Patamar)? ?\d?)\s*$", texto, re.MULTILINE
    )
    saida["cor"] = m.group(1).strip() if m else None
    return saida


SUBMERCADO_PLD = {"SUDESTE": "SE", "SUL": "S", "NORDESTE": "NE", "NORTE": "N"}


def ler_pld_horario(caminho: Path) -> pd.DataFrame:
    """PLD horário publicado (pld_horario_AAAA.csv, `;`): colunas data, hora (0–23), submercado
    (SE/S/NE/N) e pld (R$/MWh)."""
    d = pd.read_csv(caminho, sep=";", dtype=str)
    ref = d["MES_REFERENCIA"].str.strip()
    pld = pd.DataFrame(
        {
            "data": pd.to_datetime(ref.str[:4] + "-" + ref.str[4:6] + "-" + d["DIA"].str.zfill(2)),
            "hora": d["HORA"].astype(int),
            "submercado": d["SUBMERCADO"].str.strip().map(SUBMERCADO_PLD),
            "pld": d["PLD_HORA"].astype(float),
        }
    )
    if pld["submercado"].isna().any():
        raise ValueError(f"{Path(caminho).name}: submercado desconhecido no PLD horário")
    if pld.duplicated(["data", "hora", "submercado"]).any():
        raise ValueError(f"{Path(caminho).name}: linhas duplicadas no PLD horário")
    return pld.sort_values(["data", "hora", "submercado"], ignore_index=True)


def ler_limites_pld(caminho: Path) -> pd.DataFrame:
    """Limites anuais do PLD (R$/MWh; vírgula decimal, "-" = vazio): ano, piso, teto_estrutural,
    teto_horario, custo_deficit."""
    d = pd.read_csv(caminho, dtype=str)
    d.columns = ["ano", "piso", "teto_estrutural", "teto_horario", "custo_deficit"]

    def numero(s: pd.Series) -> pd.Series:
        s = s.str.replace(r"\s", "", regex=True).str.replace(",", ".")
        return pd.to_numeric(s.replace("-", None))

    return d.assign(ano=d["ano"].astype(int), **{c: numero(d[c]) for c in d.columns[1:]})
