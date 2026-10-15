"""Leitores dos decks do DESSEM da CCEE (entrada e resultado, um deck por dia).

Funções puras sobre o caminho do arquivo. Os arquivos podem estar em texto ou comprimidos (.gz,
como ficam guardados em raw/); o conteúdo lido é o mesmo.

- `conferir_tm` (entdados.dat): os 48 primeiros registros TM são as meias-horas do dia do caso;
- `ler_pdo_sist` (PDO_SIST.DAT): balanço por meia-hora e submercado (CMO, demanda, renovável…);
- `ler_renovaveis` (renovaveis.dat): previsão de geração por meia-hora, submercado e tipo de fonte.
"""

import calendar
import datetime as dt
import gzip
import io
import re
from pathlib import Path

import numpy as np
import pandas as pd

SUBMERCADOS = ["SE", "S", "NE", "N"]

# Nome dos zips diários da CCEE: o MMAAAA é o mês operativo (PMO), não o mês civil.
PADRAO_DECK = re.compile(r"^(Resultado_)?DS_CCEE_(\d{2})(\d{4})_SEMREDE_RV(\d)D(\d{2})\.zip$")

# Sufixo do nome da usina no renovaveis.dat -> tipo de fonte.
TIPO_RENOVAVEL = {
    "UEE": "eolica",
    "EOL": "eolica",
    "UFV": "solar",
    "MGD": "mmgd",
    "PCH": "pch",
    "CGH": "pch",
    "UHE": "pch",
    "UTE": "pct",
}

COLUNAS_PDO_SIST = {
    "Cmo": "cmo",
    "Demanda": "demanda",
    "Perdas": "perdas",
    "GpQusi": "gpqusi",
    "GfixBar": "gfixbar",
    "Grenova": "grenova",
    "SomatGH": "somat_gh",
    "SomatGT": "somat_gt",
    "ConsEleva": "cons_eleva",
    "Import.": "importacao",
    "Export.": "exportacao",
    "CortCarg.": "corte_carga",
    "Saldo": "saldo",
    "Recebimento": "recebimento",
    "SomaGTMin": "soma_gt_min",
    "SomatGTMax": "somat_gt_max",
    "Earm": "earm",
}


def texto(caminho: Path) -> str:
    """Conteúdo do arquivo (latin-1), comprimido em .gz ou não."""
    caminho = Path(caminho)
    dados = caminho.read_bytes()
    if caminho.suffix == ".gz":
        dados = gzip.decompress(dados)
    return dados.decode("latin1")


def data_do_deck(nome: str) -> tuple[dt.date, str, int, bool]:
    """Nome do zip diário -> (dia do caso, PMO 'AAAA-MM', revisão, é resultado).

    O mês do nome é o mês operativo; na RV0, os dias >= 20 caem no mês civil anterior
    (ex.: DS_CCEE_102026_SEMREDE_RV0D27 = 27/09/2026).
    """
    m = PADRAO_DECK.match(nome)
    if not m:
        raise ValueError(f"nome fora do padrão do deck do DESSEM: {nome}")
    res, mes, ano, rv, dia = m[1], int(m[2]), int(m[3]), int(m[4]), int(m[5])
    pmo = f"{ano}-{mes:02d}"
    if rv == 0 and dia >= 20:
        ano, mes = (ano - 1, 12) if mes == 1 else (ano, mes - 1)
    return dt.date(ano, mes, dia), pmo, rv, bool(res)


def conferir_tm(caminho: Path, data: dt.date) -> None:
    """Os 48 primeiros registros TM do entdados.dat têm de ser as meias-horas do dia do caso."""
    tm = [ln.split() for ln in texto(caminho).splitlines() if ln.startswith("TM")][:48]
    esperado = [(data.day, h, m, 0.5) for h in range(24) for m in (0, 1)]
    obtido = [(int(t[1]), int(t[2]), int(t[3]), float(t[4])) for t in tm]
    if obtido != esperado:
        raise ValueError(f"{data}: discretização TM inesperada no dia do caso")


def ler_pdo_sist(caminho: Path, data: dt.date) -> pd.DataFrame:
    """Períodos 1–48 (meias-horas do dia do caso) do PDO_SIST.DAT, por submercado."""
    t = texto(caminho)
    caso = re.search(r"Data do Caso: (\d\d/\d\d/\d{4})", t)
    if caso is None or dt.datetime.strptime(caso.group(1), "%d/%m/%Y").date() != data:
        raise ValueError(f"{data}: 'Data do Caso' do PDO_SIST.DAT não confere")
    linhas = t.splitlines()
    cab = next(i for i, ln in enumerate(linhas) if "Grenova" in ln)
    nomes = [c.strip() for c in linhas[cab].split(";")][3:]
    registros = []
    for ln in linhas[cab + 1 :]:
        p = [c.strip() for c in ln.split(";")]
        if len(p) < 4 or not p[0].isdigit():
            continue
        if int(p[0]) > 48 or p[2] not in SUBMERCADOS:
            continue
        valores = [np.nan if v in ("-", "") else float(v) for v in p[3 : 3 + len(nomes)]]
        registros.append([int(p[0]), p[1], p[2], *valores])
    d = pd.DataFrame(registros, columns=["periodo", "patamar", "submercado", *nomes])
    d = d.loc[:, [c for c in d.columns if c]].rename(columns=COLUNAS_PDO_SIST)
    if len(d) != 48 * len(SUBMERCADOS):
        raise ValueError(f"{data}: PDO_SIST.DAT com {len(d)} linhas no dia do caso")
    d.insert(0, "data", data)
    return d


def ler_renovaveis(caminho: Path, data: dt.date) -> pd.DataFrame:
    """Previsão de geração (MW) por meia-hora do dia do caso, submercado e tipo de fonte.

    A geração vem em intervalos (dia, hora e meia de início e fim; "F" = fim do horizonte) que podem
    atravessar a virada do mês. Cada intervalo é convertido em meias-horas relativas ao início do
    dia do caso e somado por diferença acumulada.
    """
    usina_nome, usina_sub, geracao = {}, {}, []
    for ln in texto(caminho).splitlines():
        if ln.startswith("EOLICA-GERACAO"):
            geracao.append(ln)
        elif ln.startswith("EOLICASUBM"):
            p = ln.split(";")
            usina_sub[p[1].strip()] = p[2].strip()
        elif ln.startswith("EOLICA "):
            p = ln.split(";")
            usina_nome[p[1].strip()] = p[2].strip()

    # Decks até 2021-01-07 não trazem o tipo no nome da usina: só o total é aproveitável.
    sufixos = {u: n.rsplit("_", 1)[-1] for u, n in usina_nome.items()}
    conhecidos = [s in TIPO_RENOVAVEL for s in sufixos.values()]
    if not any(conhecidos):
        usina_tipo = dict.fromkeys(sufixos, "sem_tipo")
    elif all(conhecidos):
        usina_tipo = {u: TIPO_RENOVAVEL[s] for u, s in sufixos.items()}
    else:
        estranhos = [usina_nome[u] for u, s in sufixos.items() if s not in TIPO_RENOVAVEL]
        raise ValueError(f"{data}: sufixo de usina desconhecido: {estranhos[:5]}")

    g = pd.read_csv(io.StringIO("\n".join(geracao)), sep=";", header=None, dtype=str)
    g = g.iloc[:, 1:9].apply(lambda s: s.str.strip())
    g.columns = ["usina", "di", "hi", "mi", "df", "hf", "mf", "mw"]
    dias_mes = calendar.monthrange(data.year, data.month)[1]

    def meia_hora(dia: pd.Series, hora: pd.Series, meia: pd.Series) -> np.ndarray:
        """Índice da meia-hora relativo ao início do dia do caso (0 = 00:00 do dia do caso)."""
        d = pd.to_numeric(dia, errors="coerce")
        desloc = np.where(d >= data.day, d - data.day, d + dias_mes - data.day)
        idx = desloc * 48 + hora.astype(int).to_numpy() * 2 + meia.astype(int).to_numpy()
        return np.where(d.isna(), 10**6, idx).astype(int)  # 'F' (fim do horizonte)

    ini = np.clip(meia_hora(g["di"], g["hi"], g["mi"]), 0, 48)
    fim = np.clip(meia_hora(g["df"], g["hf"], g["mf"]), 0, 48)
    tipo = g["usina"].map(usina_tipo)
    sub = g["usina"].map(usina_sub)
    if tipo.isna().any() or sub.isna().any():
        raise ValueError(f"{data}: geração de usina sem cadastro EOLICA/EOLICASUBM")

    chaves = pd.MultiIndex.from_product([SUBMERCADOS, sorted(set(usina_tipo.values()))])
    pos = {k: i for i, k in enumerate(chaves)}
    linha_chave = np.array([pos[k] for k in zip(sub, tipo)])
    acum = np.zeros((len(chaves), 49))
    mw = g["mw"].astype(float).to_numpy()
    np.add.at(acum, (linha_chave, ini), mw)
    np.add.at(acum, (linha_chave, fim), -mw)
    serie = np.cumsum(acum, axis=1)[:, :48]

    d = pd.DataFrame(serie, index=chaves, columns=range(1, 49))
    d = d.rename_axis(index=["submercado", "tipo"], columns="periodo").stack().rename("mw")
    d = d.reset_index()
    d.insert(0, "data", data)
    return d
