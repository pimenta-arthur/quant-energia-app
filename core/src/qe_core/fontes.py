"""Ingestão das fontes usadas por mais de uma funcionalidade: data/entrada/<fonte>/ → raw/<fonte>/.

A caixa de entrada apaga o original depois de gravar em raw/ (docs/entrada.md). Por isso uma fonte usada por
mais de uma funcionalidade tem uma ingestão só, aqui: ela grava em raw/ tudo o que qualquer funcionalidade usa,
e a ingestão de cada funcionalidade chama esta para essas fontes. Cada funcionalidade deduz das chaves gravadas
o que precisa tratar de novo.

| fonte | usada por | o que vai para raw/ |
|---|---|---|
| `ccee_newave` | bandeiras, descolamento | dois conjuntos independentes por deck, cada um com a sua versão (hash): o das bandeiras (15 arquivos, com as saídas do NEWAVE) e o `sistema_agrint` (SISTEMA.DAT e AGRINT.DAT do deck de entrada); grava cada conjunto completo no pacote |
| `ccee_dessem` | Risk Lab, descolamento | por dia, os arquivos usados, em .gz |
| `ccee_pld` | Risk Lab, descolamento | csv do PLD horário de cada ano |
| `ccee_limites_pld` | Risk Lab, descolamento | csv dos limites anuais |
"""

import datetime as dt
import hashlib
import io
import json
import re
import tempfile
import unicodedata
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

from qe_core.armazenamento import Armazenamento, gravar_json
from qe_core.entrada import (
    NaoReconhecido,
    Resultado,
    gravar_comprimido,
    gravar_conferido,
    remover,
    sha,
)
from qe_core.leitores import ccee, dessem
from qe_core.periodo import rotulo

COMUNS = {
    "ccee_newave": "deck do NEWAVE da CCEE: o zip mensal NWAAAAMM.zip (deck de entrada) ou o deck com as "
    "saídas (ghtotsin.out, cmarg…), soltos ou numa pasta",
    "ccee_dessem": "decks do DESSEM: DES_AAAAMM.zip ou os diários DS_CCEE_…zip e Resultado_DS_CCEE_…zip",
    "ccee_pld": "csv do PLD horário publicado pela CCEE (pld_horario_AAAA.csv, um por ano)",
    "ccee_limites_pld": "csv dos limites anuais do PLD (dados_pld.csv)",
}

# --- chaves de raw/ ----------------------------------------------------------------------------------

RAW_NEWAVE = "raw/ccee_newave"
RAW_DESSEM = "raw/ccee_dessem"
RAW_PLD = "raw/ccee_pld"
RAW_LIMITES = "raw/ccee_limites_pld/dados_pld.csv"

# deck do NEWAVE, conjunto das bandeiras: saídas do NEWAVE + sistema.dat e c_adic.dat
ARQUIVOS_NEWAVE = (
    ["ghtotsin.out", "sistema.dat", "c_adic.dat"]
    + [f"eafbm00{i}.out" for i in range(1, 5)]
    + [f"cmarg00{i}.out" for i in range(1, 5)]
    + [f"cmarg00{i}-med.out" for i in range(1, 5)]
)
# deck do NEWAVE, conjunto sistema_agrint (descolamento): mercado, usinas não simuladas e agrupamentos de
# intercâmbio do deck de entrada
ARQUIVOS_SISTEMA_AGRINT = ["sistema.dat", "agrint.dat"]
MARCA_NEWAVE = "_ingestao.json"


def raw_newave(deck: pd.Period, versao: str, arquivo: str = "") -> str:
    return f"{RAW_NEWAVE}/deck={rotulo(deck)}/v={versao}/{arquivo}"


def raw_sistema_agrint(deck: pd.Period, versao: str, arquivo: str = "") -> str:
    return f"{RAW_NEWAVE}/deck={rotulo(deck)}/sistema_agrint/v={versao}/{arquivo}"


# arquivos usados de cada metade do deck diário do DESSEM (nome no zip → guardado como <nome>.gz). Opcionais:
# PDO_OPER_USIH.DAT (ausente ou truncado em alguns decks) e PDO_RESTOPER.DAT (restrições operativas, usado pelo
# descolamento): o dia fica sem esse dado
ARQUIVOS_DESSEM = {
    "entrada": ["entdados.dat", "renovaveis.dat"],
    "resultado": ["PDO_SIST.DAT", "PDO_OPER_USIH.DAT", "PDO_RESTOPER.DAT"],
}
OPCIONAIS_DESSEM = {"PDO_OPER_USIH.DAT", "PDO_RESTOPER.DAT"}
# marca de cada metade ingerida: nome do zip, PMO, revisão e hash dos originais
MARCA_DESSEM = {"entrada": "_entrada.json", "resultado": "_resultado.json"}


def raw_dessem(dia: dt.date, arquivo: str = "") -> str:
    return f"{RAW_DESSEM}/dia={dia:%Y-%m-%d}/{arquivo}"


def raw_pld(ano: int) -> str:
    return f"{RAW_PLD}/pld_horario_{ano}.csv"


# --- percorrer o que foi solto: arquivos soltos, pastas e zips dentro de zips ----------------------------


def abrir_zip(nome: str, origem) -> zipfile.ZipFile:
    """Zip a partir do caminho (lido em fluxo) ou dos bytes de um zip interno."""
    try:
        return zipfile.ZipFile(origem if isinstance(origem, Path) else io.BytesIO(origem))
    except zipfile.BadZipFile as e:
        raise NaoReconhecido(f"{nome}: zip inválido ou ainda sendo copiado") from e


def _ignorado(info: zipfile.ZipInfo) -> bool:
    nome = Path(info.filename).name
    return info.is_dir() or nome.startswith(".") or "__MACOSX" in info.filename


def _dentro_do_zip(z: zipfile.ZipFile, reconhece) -> Iterator[tuple[str, bytes]]:
    for info in z.infolist():
        if _ignorado(info):
            continue
        nome = Path(info.filename).name
        if reconhece(nome):
            yield nome, z.read(info)
        elif nome.lower().endswith(".zip"):
            with abrir_zip(nome, z.read(info)) as interno:
                yield from _dentro_do_zip(interno, reconhece)
        # outros arquivos (Leia-me.pdf etc.): ignorados


def ler_item(item: Path, reconhece) -> Iterator[tuple[str, bytes]]:
    """(nome, bytes) de cada arquivo que `reconhece(nome)` aceita: soltos, em pastas ou dentro de zips
    (recursivo). Um zip grande é lido em fluxo, um arquivo interno por vez."""
    caminhos = [p for p in sorted(item.rglob("*")) if p.is_file()] if item.is_dir() else [item]
    for p in caminhos:
        if p.name.startswith("."):
            continue
        if reconhece(p.name):
            yield p.name, p.read_bytes()
        elif p.suffix.lower() == ".zip":
            with abrir_zip(p.name, p) as z:
                yield from _dentro_do_zip(z, reconhece)


def do_zip(nome: str, dados: bytes, nomes: list[str]) -> dict[str, bytes]:
    """Arquivos `nomes` de dentro de um zip (sem diferenciar maiúsculas)."""
    z = abrir_zip(nome, dados)
    por_nome = {Path(i.filename).name.lower(): i for i in z.infolist() if not i.is_dir()}
    return {n: z.read(por_nome[n.lower()]) for n in nomes if n.lower() in por_nome}


def validar(leitor, dados: bytes, *args, sufixo: str = ""):
    """Roda o leitor do qe_core sobre o arquivo antes de aceitá-lo (os leitores recebem caminho)."""
    with tempfile.TemporaryDirectory() as d:
        caminho = Path(d) / f"arquivo{sufixo}"
        caminho.write_bytes(dados)
        try:
            return leitor(caminho, *args)
        except Exception as e:  # qualquer falha do leitor recusa o arquivo
            raise NaoReconhecido(f"arquivo não passou na leitura: {e}") from e


# --- NEWAVE ----------------------------------------------------------------------------------------------

_NOMES_MES = (
    "JANEIRO FEVEREIRO MARCO ABRIL MAIO JUNHO JULHO AGOSTO SETEMBRO OUTUBRO NOVEMBRO DEZEMBRO"
)
MESES = {n: i for i, n in enumerate(_NOMES_MES.split(), 1)}
_RE_MES = "|".join(MESES)
# deck republicado pela CCEE: NWAAAAMM.zip com NWAAAAMM_1aPublicacao.zip, NWAAAAMM_2aPublicacao.zip… dentro
PADRAO_PUBLICACAO = re.compile(r"^NW\d{6}_(\d+)aPublicacao\.zip$", re.IGNORECASE)
PADRAO_NW = re.compile(r"NW(\d{4})(\d{2})", re.IGNORECASE)


def sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().upper()


def versao(conteudo: dict[str, bytes], arquivos: list[str]) -> str:
    """Versão de um conjunto = 8 primeiros caracteres do hash do conteúdo dos arquivos do conjunto."""
    h = hashlib.sha256()
    for arq in arquivos:
        h.update(arq.encode())
        h.update(sha(conteudo[arq]).encode() if arq in conteudo else b"-")
    return h.hexdigest()[:8]


@dataclass
class _Grupo:
    """Arquivos de uma publicação do deck (ou de tudo o que foi solto, sem publicações separadas)."""

    arquivos: dict[str, bytes] = field(default_factory=dict)
    nomes: list[str] = field(default_factory=list)  # zips e pastas de origem, de fora para dentro
    publicacao: int | None = None

    def achar(self, nome: str) -> bytes | None:
        return next((d for n, d in self.arquivos.items() if n.lower() == nome.lower()), None)

    def juntar(self, nome: str, dados: bytes) -> None:
        if nome in self.arquivos and self.arquivos[nome] != dados:
            raise NaoReconhecido(f"dois arquivos diferentes com o nome {nome}")
        self.arquivos[nome] = dados


def _grupos_newave(item: Path) -> list[_Grupo]:
    """Cada publicação (NWAAAAMM_kaPublicacao.zip) vira um grupo; o resto do que foi solto, outro."""
    base = _Grupo(nomes=[item.name])
    grupos = [base]

    def zip_(nome: str, dados: bytes, g: _Grupo) -> None:
        m = PADRAO_PUBLICACAO.match(nome)
        if m:
            g = _Grupo(nomes=[*g.nomes, nome], publicacao=int(m[1]))
            grupos.append(g)
        else:
            g.nomes.append(nome)
        with abrir_zip(nome, dados) as z:
            for info in z.infolist():
                if _ignorado(info):
                    continue
                n = Path(info.filename).name
                if n.lower().endswith(".zip"):
                    zip_(n, z.read(info), g)
                else:
                    g.juntar(n, z.read(info))

    caminhos = [p for p in sorted(item.rglob("*")) if p.is_file()] if item.is_dir() else [item]
    for p in caminhos:
        if p.name.startswith("."):
            continue
        if p.suffix.lower() == ".zip":
            zip_(p.name, p.read_bytes(), base)
        else:
            base.juntar(p.name, p.read_bytes())
    return [g for g in grupos if g.arquivos]


def _mes_da_pasta(item: Path) -> pd.Period | None:
    return pd.Period(item.name, "M") if re.fullmatch(r"\d{4}-\d{2}", item.name) else None


def _mes_conferido(item: Path, mes: pd.Period | None, o_que: str) -> pd.Period:
    pasta = _mes_da_pasta(item)
    if mes and pasta and mes != pasta:
        raise NaoReconhecido(f"{o_que} é de {mes}, mas está na subpasta {pasta}")
    if (mes or pasta) is None:
        raise NaoReconhecido(f"não achei o mês em {o_que}; ponha o arquivo numa subpasta AAAA-MM")
    return mes or pasta


def _newave(arm: Armazenamento, item: Path, sobrescrever: bool):
    gravados, meses, conjuntos = {}, set(), 0
    for g in _grupos_newave(item):
        gh = g.achar("ghtotsin.out")
        deck = None
        if gh is not None:
            # deck com as saídas do NEWAVE (bandeiras): os 15 arquivos, mês pelo cabeçalho do ghtotsin.out
            faltam = [a for a in ARQUIVOS_NEWAVE if g.achar(a) is None]
            if faltam:
                raise NaoReconhecido("deck incompleto, faltam: " + ", ".join(faltam))
            m = re.search(
                rf"PMO\s*-\s*({_RE_MES})\s*-\s*(\d{{4}})", sem_acento(gh[:400].decode("latin-1"))
            )
            deck = _mes_conferido(
                item, pd.Period(f"{m[2]}-{MESES[m[1]]:02d}", "M") if m else None, "ghtotsin.out"
            )
            conteudo = {a: g.achar(a) for a in ARQUIVOS_NEWAVE}
            v = versao(conteudo, ARQUIVOS_NEWAVE)
            gravados |= {
                raw_newave(deck, v, a): gravar_conferido(
                    arm, raw_newave(deck, v, a), d, sobrescrever
                )
                for a, d in conteudo.items()
            }
            marca = raw_newave(deck, v, MARCA_NEWAVE)
            if not arm.existe(marca):
                gravar_json(
                    arm,
                    {
                        "ingerido_em": datetime.now().isoformat(timespec="seconds"),
                        "origem": item.name,
                        "origem_sha256": sha(item.read_bytes()) if item.is_file() else None,
                    },
                    marca,
                )
            conjuntos += 1
        if all(g.achar(a) is not None for a in ARQUIVOS_SISTEMA_AGRINT):
            # deck de entrada (descolamento): mês pelo ghtotsin.out, se houver, ou pelo nome NWAAAAMM
            if deck is None:
                nw = next(
                    (PADRAO_NW.search(n) for n in reversed(g.nomes) if PADRAO_NW.search(n)), None
                )
                deck = _mes_conferido(
                    item, pd.Period(f"{nw[1]}-{nw[2]}", "M") if nw else None, "nome do zip NWAAAAMM"
                )
            conteudo = {a: g.achar(a) for a in ARQUIVOS_SISTEMA_AGRINT}
            v = versao(conteudo, ARQUIVOS_SISTEMA_AGRINT)
            gravados |= {
                raw_sistema_agrint(deck, v, a): gravar_conferido(
                    arm, raw_sistema_agrint(deck, v, a), d, sobrescrever
                )
                for a, d in conteudo.items()
            }
            marca = raw_sistema_agrint(deck, v, MARCA_NEWAVE)
            if not arm.existe(marca):
                gravar_json(
                    arm,
                    {
                        "ingerido_em": datetime.now().isoformat(timespec="seconds"),
                        "origem": "/".join(g.nomes),
                        "publicacao": g.publicacao,
                        "sha256": {a: sha(d) for a, d in conteudo.items()},
                    },
                    marca,
                )
            conjuntos += 1
        if deck is not None and any(
            s in ("novo", "sobrescrito")
            for c, s in gravados.items()
            if c.startswith(f"{RAW_NEWAVE}/deck={rotulo(deck)}/")
        ):
            meses.add(deck)
    if not conjuntos:
        raise NaoReconhecido(
            "não achei ghtotsin.out (deck do NEWAVE com as saídas) nem SISTEMA.DAT e AGRINT.DAT "
            "(deck de entrada)"
        )
    return gravados, meses


# --- DESSEM ----------------------------------------------------------------------------------------------


def _dessem(arm: Armazenamento, item: Path, sobrescrever: bool):
    gravados, meses, vistos = {}, set(), {}
    reconhece = lambda n: dessem.PADRAO_DECK.match(n) is not None
    for nome, dados in ler_item(item, reconhece):
        dia, pmo, rv, eh_resultado = dessem.data_do_deck(nome)
        metade = "resultado" if eh_resultado else "entrada"
        if vistos.setdefault((dia, metade), nome) != nome:
            raise NaoReconhecido(f"dois decks para {dia}: {vistos[(dia, metade)]} e {nome}")
        arquivos = do_zip(nome, dados, ARQUIVOS_DESSEM[metade])
        faltam = [
            a for a in ARQUIVOS_DESSEM[metade] if a not in arquivos and a not in OPCIONAIS_DESSEM
        ]
        if faltam:
            raise NaoReconhecido(f"{nome}: faltam {', '.join(faltam)}")
        if metade == "entrada":
            validar(dessem.conferir_tm, arquivos["entdados.dat"], dia)
        else:
            validar(dessem.ler_pdo_sist, arquivos["PDO_SIST.DAT"], dia)
        marca_chave = raw_dessem(dia, MARCA_DESSEM[metade])
        if arm.existe(marca_chave):
            anterior = json.loads(arm.ler_bytes(marca_chave))
            if anterior["deck"] != nome and not sobrescrever:
                gravados[marca_chave] = "divergente"
                continue
        situacoes = {
            raw_dessem(dia, a + ".gz"): gravar_comprimido(
                arm, raw_dessem(dia, a + ".gz"), d, sobrescrever
            )
            for a, d in arquivos.items()
        }
        gravados |= situacoes
        if any(s in ("novo", "sobrescrito") for s in situacoes.values()) or not arm.existe(
            marca_chave
        ):
            marca = {
                "deck": nome,
                "pmo": pmo,
                "rv": rv,
                "origem": item.name,
                "ingerido_em": datetime.now().isoformat(timespec="seconds"),
                "sha256": {a: sha(d) for a, d in arquivos.items()},
            }
            arm.gravar_bytes(json.dumps(marca, ensure_ascii=False, indent=1).encode(), marca_chave)
            meses.add(pd.Period(dia, "M"))
    if not vistos:
        raise NaoReconhecido("não achei zips diários DS_CCEE_…_RVnDdd.zip (nem dentro de zips)")
    return gravados, meses


# --- PLD e limites ---------------------------------------------------------------------------------------


def _pld(arm: Armazenamento, item: Path, sobrescrever: bool):
    gravados, meses = {}, set()
    csvs = list(ler_item(item, lambda n: n.lower().endswith(".csv")))
    if not csvs:
        raise NaoReconhecido("não achei csv do PLD horário")
    for nome, dados in csvs:
        novo = validar(ccee.ler_pld_horario, dados)
        anos = novo["data"].dt.year.unique()
        if len(anos) != 1:
            raise NaoReconhecido(f"{nome}: esperado um ano por arquivo, achados {sorted(anos)}")
        chave = raw_pld(int(anos[0]))
        # conjunto republicado pela CCEE: substitui, desde que não perca horas já publicadas
        encolheu = False
        if arm.existe(chave) and not sobrescrever:
            antigo = ccee.ler_pld_horario(arm.caminho_local(chave))
            k = ["data", "hora", "submercado"]
            encolheu = len(antigo.merge(novo[k], on=k)) < len(antigo)
        if encolheu:
            gravados[chave] = "divergente"
            continue
        gravados[chave] = gravar_conferido(arm, chave, dados, sobrescrever=True)
        if gravados[chave] != "igual":
            meses |= set(novo["data"].dt.to_period("M"))
    return gravados, meses


def _limites(arm: Armazenamento, item: Path, sobrescrever: bool):
    csvs = list(ler_item(item, lambda n: n.lower().endswith(".csv")))
    if len(csvs) != 1:
        raise NaoReconhecido(f"esperado um csv dos limites por pacote, achados {len(csvs)}")
    validar(ccee.ler_limites_pld, csvs[0][1])
    return {RAW_LIMITES: gravar_conferido(arm, RAW_LIMITES, csvs[0][1], True)}, set()


RECONHECER = {
    "ccee_newave": _newave,
    "ccee_dessem": _dessem,
    "ccee_pld": _pld,
    "ccee_limites_pld": _limites,
}


def ingerir_pacote(arm: Armazenamento, fonte: str, item: Path, sobrescrever: bool) -> Resultado:
    """Ingere um item solto em entrada/<fonte>/ de uma fonte comum; só apaga o original se tudo foi gravado.

    `Resultado.meses` traz os meses com algum arquivo novo; cada funcionalidade filtra pelas chaves que usa."""
    try:
        gravados, meses = RECONHECER[fonte](arm, item, sobrescrever)
    except NaoReconhecido as e:
        return Resultado(fonte, item.name, False, f"mantido na entrada: {e}")
    novos = sum(s in ("novo", "sobrescrito") for s in gravados.values())
    divergentes = [c for c, s in gravados.items() if s == "divergente"]
    if divergentes:
        return Resultado(
            fonte,
            item.name,
            False,
            f"mantido na entrada: {len(divergentes)} arquivo(s) já existem em raw/ com conteúdo "
            f"diferente (ex.: {divergentes[0]}); para substituir, rode com --sobrescrever",
            gravados,
            meses,
        )
    remover(item)
    texto = f"{novos} arquivo(s) novo(s) em raw/" if novos else "já estava em raw/ (nada novo)"
    return Resultado(fonte, item.name, True, f"ingerido: {texto}", gravados, meses)
