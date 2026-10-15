"""Ingestão: da caixa de entrada (data/entrada/<fonte>/) para raw/ do armazenamento.

Você solta os arquivos como baixou (zip, PDF, txt, xlsx, csv; soltos ou numa pasta) na pasta da
fonte, e a ingestão:
1. identifica o mês (ou a emissão, ou o ano) pelo conteúdo, e na falta dele por uma subpasta AAAA-MM;
2. grava em raw/ só os arquivos que o modelo usa, idênticos aos originais (tirados do zip, se for o caso);
3. relê o que gravou e confere o hash;
4. só então apaga o original da entrada. Se algo falhar, o original fica onde está, com o motivo.

raw/ é imutável: arquivo já gravado e diferente do novo não é sobrescrito sem `sobrescrever`
(exceto o histórico da ANEEL, que é um conjunto atualizado pela fonte). O deck do NEWAVE é guardado
por mês e versão (hash do conteúdo) e o ECMWF por data de emissão, então uma republicação do deck ou
uma emissão extra entram ao lado das anteriores. Formato de cada fonte: docs/entrada.md.
"""

import hashlib
import io
import re
import tempfile
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from qe_core.armazenamento import Armazenamento, gravar_json
from qe_core.entrada import NaoReconhecido, Resultado, gravar_conferido, gravar_relatorio, remover
from qe_core.entrada import sha as _sha
from qe_core.leitores import aneel, ccee, ons
from qe_forecast_bandeiras import chaves

FONTES = {
    "ccee_newave": "zip (ou arquivos) do deck do NEWAVE da CCEE",
    "ons_pmo": "PMO do ONS: relato.rv0, PDF da ENA (Tabela 6) e renovaveis.csv",
    "ccee_infobandeira": "PDF do boletim InfoBandeira da CCEE",
    "ecmwf": "arquivos .txt de ENA do ECMWF (média, percentis e membros)",
    "ccee_patamares": "AAC001 (xlsx) dos patamares de carga do ano",
    "aneel_bandeiras": "csv do histórico de bandeiras da ANEEL (dados abertos)",
}
_NOMES_MES = (
    "JANEIRO FEVEREIRO MARCO ABRIL MAIO JUNHO JULHO AGOSTO SETEMBRO OUTUBRO NOVEMBRO DEZEMBRO"
)
MESES = {n: i for i, n in enumerate(_NOMES_MES.split(), 1)}
_RE_MES = "|".join(MESES)


@dataclass
class Pacote:
    """O que foi solto na pasta da fonte: um arquivo, um zip ou uma pasta (com zips dentro, se houver)."""

    origem: Path
    arquivos: dict[str, bytes]  # nome do arquivo (sem pasta) → conteúdo
    mes_pasta: pd.Period | None = None  # subpasta AAAA-MM, usada quando o conteúdo não diz o mês


# --- leitura dos pacotes --------------------------------------------------------------------------


def _sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().upper()


def _mes(ano: str, nome: str) -> pd.Period:
    return pd.Period(f"{ano}-{MESES[nome]:02d}", "M")


def _abrir_zip(dados: bytes, arquivos: dict[str, bytes]) -> None:
    with zipfile.ZipFile(io.BytesIO(dados)) as z:
        for info in z.infolist():
            nome = Path(info.filename).name
            if info.is_dir() or nome.startswith(".") or "__MACOSX" in info.filename:
                continue
            conteudo = z.read(info)
            if nome.lower().endswith(".zip"):
                _abrir_zip(conteudo, arquivos)
            elif nome in arquivos and arquivos[nome] != conteudo:
                raise NaoReconhecido(f"dois arquivos diferentes com o nome {nome}")
            else:
                arquivos[nome] = conteudo


def _ler_pacote(item: Path) -> Pacote:
    arquivos: dict[str, bytes] = {}
    caminhos = [p for p in sorted(item.rglob("*")) if p.is_file()] if item.is_dir() else [item]
    for p in caminhos:
        if p.name.startswith("."):
            continue
        dados = p.read_bytes()
        if p.suffix.lower() == ".zip":
            try:
                _abrir_zip(dados, arquivos)
            except zipfile.BadZipFile as e:
                raise NaoReconhecido(f"{p.name}: zip inválido ou ainda sendo copiado") from e
        else:
            arquivos[p.name] = dados
    mes_pasta = None
    if item.is_dir() and re.fullmatch(r"\d{4}-\d{2}", item.name):
        mes_pasta = pd.Period(item.name, "M")
    return Pacote(item, arquivos, mes_pasta)


def _achar(p: Pacote, nome: str) -> bytes | None:
    """Arquivo pelo nome, sem diferenciar maiúsculas."""
    return next((d for n, d in p.arquivos.items() if n.lower() == nome.lower()), None)


def _mes_conferido(p: Pacote, mes_conteudo: pd.Period | None, o_que: str) -> pd.Period:
    if mes_conteudo and p.mes_pasta and mes_conteudo != p.mes_pasta:
        raise NaoReconhecido(f"{o_que} é de {mes_conteudo}, mas está na subpasta {p.mes_pasta}")
    m = mes_conteudo or p.mes_pasta
    if m is None:
        raise NaoReconhecido(f"não achei o mês em {o_que}; ponha o arquivo numa subpasta AAAA-MM")
    return m


def _texto_pdf(dados: bytes) -> str:
    import pdfplumber

    try:
        with pdfplumber.open(io.BytesIO(dados)) as pdf:
            return pdf.pages[0].extract_text() or ""
    except Exception:  # noqa: BLE001 — PDF que não abre simplesmente não é reconhecido
        return ""


def _validar(leitor, dados: bytes, sufixo: str, *args):
    """Roda o leitor do qe_core sobre o arquivo antes de aceitá-lo (os leitores recebem caminho)."""
    with tempfile.TemporaryDirectory() as d:
        caminho = Path(d) / f"arquivo{sufixo}"
        caminho.write_bytes(dados)
        try:
            return leitor(caminho, *args)
        except Exception as e:  # qualquer falha do leitor recusa o arquivo
            raise NaoReconhecido(f"arquivo não passou na leitura: {e}") from e


# --- reconhecimento por fonte: {chave em raw/: conteúdo}, meses afetados e marca da ingestão ----


def versao_deck(conteudo: dict[str, bytes]) -> str:
    """Versão do deck = 8 primeiros caracteres do hash do conteúdo dos arquivos usados."""
    h = hashlib.sha256()
    for arq in chaves.ARQUIVOS_NEWAVE:
        h.update(arq.encode())
        h.update(_sha(conteudo[arq]).encode() if arq in conteudo else b"-")
    return h.hexdigest()[:8]


def _newave(p: Pacote, arm: Armazenamento):
    gh = _achar(p, "ghtotsin.out")
    if gh is None:
        raise NaoReconhecido("não achei ghtotsin.out (deck do NEWAVE)")
    faltam = [a for a in chaves.ARQUIVOS_NEWAVE if _achar(p, a) is None]
    if faltam:
        raise NaoReconhecido("deck incompleto, faltam: " + ", ".join(faltam))
    m = re.search(
        rf"PMO\s*-\s*({_RE_MES})\s*-\s*(\d{{4}})", _sem_acento(gh[:400].decode("latin-1"))
    )
    deck = _mes_conferido(p, _mes(m[2], m[1]) if m else None, "ghtotsin.out")
    conteudo = {a: _achar(p, a) for a in chaves.ARQUIVOS_NEWAVE}
    versao = versao_deck(conteudo)
    marca = {
        "chave": chaves.raw_newave(deck, versao, "_ingestao.json"),
        "origem": p.origem.name,
        "origem_sha256": _sha(p.origem.read_bytes()) if p.origem.is_file() else None,
    }
    return {chaves.raw_newave(deck, versao, a): d for a, d in conteudo.items()}, {deck}, marca


def _pmo(p: Pacote, arm: Armazenamento):
    relato = _achar(p, "relato.rv0")
    ena = next(
        (
            d
            for n, d in p.arquivos.items()
            if n.lower().endswith(".pdf") and "TABELA 6" in _texto_pdf(d)
        ),
        None,
    )
    renov = _achar(p, "renovaveis.csv") or next(
        (d for d in p.arquivos.values() if b"PEE-GER-PER-PAT-CEN" in d[:200_000]), None
    )
    if relato is None and ena is None and renov is None:
        raise NaoReconhecido("não achei relato.rv0, PDF da ENA (Tabela 6) nem renovaveis.csv")
    meses = set()
    if relato is not None:
        m = re.search(
            rf"PMO\s*-\s*({_RE_MES})/(\d{{2}})", _sem_acento(relato[:20_000].decode("latin-1"))
        )
        if m:
            meses.add(_mes("20" + m[2], m[1]))
    if ena is not None:
        _validar(ons.ler_ena, ena, ".pdf")
        m = re.search(rf"({_RE_MES})/(\d{{4}})", _sem_acento(_texto_pdf(ena)))
        if m:
            meses.add(_mes(m[2], m[1]))
    if len(meses) > 1:
        raise NaoReconhecido(f"relato e ENA de meses diferentes: {sorted(map(str, meses))}")
    # o renovaveis.csv não traz o mês: só entra junto do relato/ENA ou numa subpasta AAAA-MM
    m = _mes_conferido(p, next(iter(meses), None), "relato.rv0/ENA")
    saida = {
        chaves.raw_pmo(m, nome): d
        for nome, d in (("relato.rv0", relato), ("ena.pdf", ena), ("renovaveis.csv", renov))
        if d is not None
    }
    return saida, {m}, None


def _infobandeira(p: Pacote, arm: Armazenamento):
    pdfs = [d for n, d in p.arquivos.items() if n.lower().endswith(".pdf")]
    if len(pdfs) != 1:
        raise NaoReconhecido(f"esperado um PDF do boletim por pacote, achados {len(pdfs)}")
    m = re.search(rf"N\S?\s*\d+\s*-\s*({_RE_MES})/(\d{{4}})", _sem_acento(_texto_pdf(pdfs[0])))
    mes_bol = _mes_conferido(p, _mes(m[2], m[1]) if m else None, "boletim")
    _validar(ccee.ler_boletim, pdfs[0], ".pdf", mes_bol.year)
    return {chaves.raw_boletim(mes_bol): pdfs[0]}, {mes_bol}, None


def _ecmwf(p: Pacote, arm: Armazenamento):
    saida, meses = {}, set()
    for nome, d in p.arquivos.items():
        m = re.fullmatch(r"ENA_MLT_SUBSISTEMA_MENSAL_ECENSLT.*_(\d{8})\.txt", nome)
        if m:
            emissao = f"{m[1][:4]}-{m[1][4:6]}-{m[1][6:]}"
            saida[chaves.raw_ecmwf(emissao, nome)] = d
            meses.add(pd.Period(emissao[:7], "M"))
    if not saida:
        raise NaoReconhecido("não achei arquivos ENA_MLT_SUBSISTEMA_MENSAL_ECENSLT…_AAAAMMDD.txt")
    return saida, meses, None


def _patamares(p: Pacote, arm: Armazenamento):
    xls = [
        d
        for n, d in p.arquivos.items()
        if n.upper().startswith("AAC001") and n.lower().endswith(".xlsx")
    ]
    if len(xls) != 1:
        raise NaoReconhecido(f"esperado um arquivo AAC001…xlsx por pacote, achados {len(xls)}")
    ano = int(_validar(ccee.ler_patamares, xls[0], ".xlsx").ts.dt.year.mode()[0])
    # muda o tratamento dos meses desse ano que já têm PMO
    meses = {
        pd.Period(c.split("/")[2], "M")
        for c in arm.listar("raw/ons_pmo")
        if c.split("/")[2].startswith(str(ano))
    }
    return {chaves.raw_patamares(ano): xls[0]}, meses, None


def _aneel(p: Pacote, arm: Armazenamento):
    csvs = [d for n, d in p.arquivos.items() if n.lower().endswith(".csv")]
    if len(csvs) != 1:
        raise NaoReconhecido(f"esperado um csv por pacote, achados {len(csvs)}")
    _validar(aneel.ler_historico_bandeiras, csvs[0], ".csv")
    return {chaves.RAW_HISTORICO: csvs[0]}, set(), None


RECONHECER = {
    "ccee_newave": _newave,
    "ons_pmo": _pmo,
    "ccee_infobandeira": _infobandeira,
    "ecmwf": _ecmwf,
    "ccee_patamares": _patamares,
    "aneel_bandeiras": _aneel,
}


# --- gravação e laço principal ---------------------------------------------------------------------


def preparar_entrada(entrada: Path) -> None:
    for fonte in FONTES:
        (entrada / fonte).mkdir(parents=True, exist_ok=True)
    (entrada / "relatorios").mkdir(parents=True, exist_ok=True)


def _ingerir_pacote(arm: Armazenamento, fonte: str, item: Path, sobrescrever: bool) -> Resultado:
    try:
        arquivos, meses, marca = RECONHECER[fonte](_ler_pacote(item), arm)
    except NaoReconhecido as e:
        return Resultado(fonte, item.name, False, f"mantido na entrada: {e}")
    sobrescreve = sobrescrever or fonte == "aneel_bandeiras"  # conjunto atualizado pela fonte
    gravados = {c: gravar_conferido(arm, c, d, sobrescreve) for c, d in arquivos.items()}
    if marca and not arm.existe(marca["chave"]):
        info = {k: v for k, v in marca.items() if k != "chave"}
        gravar_json(
            arm,
            {"ingerido_em": datetime.now().isoformat(timespec="seconds")} | info,
            marca["chave"],
        )
    novos = sum(s in ("novo", "sobrescrito") for s in gravados.values())
    divergentes = [c for c, s in gravados.items() if s == "divergente"]
    if divergentes:
        return Resultado(
            fonte,
            item.name,
            False,
            "mantido na entrada: já existe em raw/ com conteúdo diferente ("
            + ", ".join(divergentes)
            + "); para substituir, rode com --sobrescrever",
            gravados,
            meses if novos else set(),
        )
    remover(item)
    texto = f"{novos} arquivo(s) novo(s) em raw/" if novos else "já estava em raw/ (nada novo)"
    return Resultado(
        fonte, item.name, True, f"ingerido: {texto}", gravados, meses if novos else set()
    )


def ingerir_entrada(
    arm: Armazenamento, entrada: Path, sobrescrever: bool = False
) -> list[Resultado]:
    """Ingere tudo o que estiver em entrada/<fonte>/ e grava um relatório em entrada/relatorios/."""
    preparar_entrada(entrada)
    resultados = [
        _ingerir_pacote(arm, fonte, item, sobrescrever)
        for fonte in FONTES
        for item in sorted((entrada / fonte).iterdir())
        if not item.name.startswith(".")
    ]
    gravar_relatorio(entrada, resultados)
    return resultados
