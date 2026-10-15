"""Ingestão do PLD horário: da caixa de entrada (data/entrada/<fonte>/) para raw/.

Você solta os arquivos como baixou da CCEE na pasta da fonte (zip mensal, zips diários ou semanais,
csv; soltos ou numa pasta) e a ingestão, para cada item:
1. identifica o dia (DESSEM), a semana e a publicação (DECOMP) ou o ano (PLD) pelo nome ou conteúdo;
2. roda o leitor do qe_core sobre o arquivo antes de aceitá-lo;
3. grava em raw/ só os arquivos usados (DESSEM e DECOMP em .gz) e confere a releitura;
4. só então apaga o original da entrada. Se algo falhar, o original fica, com o motivo.

O deck mensal do DESSEM (DES_AAAAMM.zip) é lido em fluxo: um zip diário por vez e, de dentro dele,
só os arquivos usados. Baixar de novo o zip mensal (que cresce ao longo do mês) não duplica nada:
os dias já gravados dão "igual". Formato de cada fonte: docs/entrada.md.
"""

import io
import json
import tempfile
import zipfile
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pandas as pd

from qe_core.armazenamento import Armazenamento
from qe_core.entrada import (
    NaoReconhecido,
    Resultado,
    gravar_comprimido,
    gravar_conferido,
    gravar_relatorio,
    itens,
    remover,
    sha,
)
from qe_core.leitores import ccee, decomp, dessem
from qe_pld_horario import chaves

FONTES = {
    "ccee_pld": "csv do PLD horário publicado pela CCEE (pld_horario_AAAA.csv, um por ano)",
    "ccee_limites_pld": "csv dos limites anuais do PLD (dados_pld.csv)",
    "ccee_dessem": "decks do DESSEM: DES_AAAAMM.zip ou os diários DS_CCEE_…zip e Resultado_DS_CCEE_…zip",
    "ccee_decomp": "decks do DECOMP: DCAAAAMM.zip ou os semanais DCAAAAMM-semN….zip e Relatorio_Sumario-…zip",
}
PREFIXO_RELATORIO = "pld_horario_"


def preparar_entrada(entrada: Path) -> None:
    for fonte in FONTES:
        (entrada / fonte).mkdir(parents=True, exist_ok=True)
    (entrada / "relatorios").mkdir(parents=True, exist_ok=True)


# --- percorrer o que foi solto: arquivos soltos, pastas e zips dentro de zips ----------------------


def _abrir_zip(nome: str, origem) -> zipfile.ZipFile:
    """Zip a partir do caminho (lido em fluxo) ou dos bytes de um zip interno."""
    try:
        return zipfile.ZipFile(origem if isinstance(origem, Path) else io.BytesIO(origem))
    except zipfile.BadZipFile as e:
        raise NaoReconhecido(f"{nome}: zip inválido ou ainda sendo copiado") from e


def _dentro_do_zip(z: zipfile.ZipFile, reconhece) -> Iterator[tuple[str, bytes]]:
    for info in z.infolist():
        nome = Path(info.filename).name
        if info.is_dir() or nome.startswith(".") or "__MACOSX" in info.filename:
            continue
        if reconhece(nome):
            yield nome, z.read(info)
        elif nome.lower().endswith(".zip"):
            with _abrir_zip(nome, z.read(info)) as interno:
                yield from _dentro_do_zip(interno, reconhece)
        # outros arquivos (Leia-me.pdf etc.): ignorados


def _ler_item(item: Path, reconhece) -> Iterator[tuple[str, bytes]]:
    """(nome, bytes) de cada arquivo que `reconhece(nome)` aceita: soltos, em pastas ou dentro de
    zips (recursivo). Um zip mensal é lido em fluxo, um arquivo interno por vez."""
    caminhos = [p for p in sorted(item.rglob("*")) if p.is_file()] if item.is_dir() else [item]
    for p in caminhos:
        if p.name.startswith("."):
            continue
        if reconhece(p.name):
            yield p.name, p.read_bytes()
        elif p.suffix.lower() == ".zip":
            with _abrir_zip(p.name, p) as z:
                yield from _dentro_do_zip(z, reconhece)


def _do_zip(nome: str, dados: bytes, nomes: list[str]) -> dict[str, bytes]:
    """Arquivos `nomes` de dentro de um zip diário/semanal (sem diferenciar maiúsculas)."""
    z = _abrir_zip(nome, dados)
    por_nome = {Path(i.filename).name.lower(): i for i in z.infolist() if not i.is_dir()}
    return {n: z.read(por_nome[n.lower()]) for n in nomes if n.lower() in por_nome}


def _validar(leitor, dados: bytes, *args):
    """Roda o leitor do qe_core sobre o arquivo antes de aceitá-lo (os leitores recebem caminho)."""
    with tempfile.TemporaryDirectory() as d:
        caminho = Path(d) / "arquivo"
        caminho.write_bytes(dados)
        try:
            return leitor(caminho, *args)
        except Exception as e:  # qualquer falha do leitor recusa o arquivo
            raise NaoReconhecido(f"arquivo não passou na leitura: {e}") from e


# --- reconhecimento por fonte: grava e devolve {chave: situação} e os meses afetados ---------------


def _dessem(arm: Armazenamento, item: Path, sobrescrever: bool):
    gravados, meses, vistos = {}, set(), {}
    reconhece = lambda n: dessem.PADRAO_DECK.match(n) is not None
    for nome, dados in _ler_item(item, reconhece):
        dia, pmo, rv, eh_resultado = dessem.data_do_deck(nome)
        metade = "resultado" if eh_resultado else "entrada"
        if vistos.setdefault((dia, metade), nome) != nome:
            raise NaoReconhecido(f"dois decks para {dia}: {vistos[(dia, metade)]} e {nome}")
        arquivos = _do_zip(nome, dados, chaves.ARQUIVOS_DESSEM[metade])
        faltam = [
            a
            for a in chaves.ARQUIVOS_DESSEM[metade]
            if a not in arquivos and a not in chaves.OPCIONAIS_DESSEM
        ]
        if faltam:
            raise NaoReconhecido(f"{nome}: faltam {', '.join(faltam)}")
        if metade == "entrada":
            _validar(dessem.conferir_tm, arquivos["entdados.dat"], dia)
        else:
            _validar(dessem.ler_pdo_sist, arquivos["PDO_SIST.DAT"], dia)
        marca_chave = chaves.raw_dessem(dia, chaves.MARCA_DESSEM[metade])
        if arm.existe(marca_chave):
            anterior = json.loads(arm.ler_bytes(marca_chave))
            if anterior["deck"] != nome and not sobrescrever:
                gravados[marca_chave] = "divergente"
                continue
        situacoes = {
            chaves.raw_dessem(dia, a + ".gz"): gravar_comprimido(
                arm, chaves.raw_dessem(dia, a + ".gz"), d, sobrescrever
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


def _decomp(arm: Armazenamento, item: Path, sobrescrever: bool):
    gravados, meses, achados = {}, set(), 0
    reconhece = lambda n: decomp.semana_do_zip(n) is not None
    for nome, dados in _ler_item(item, reconhece):
        tipo, pmo, sem, pub = decomp.semana_do_zip(nome)
        prefixo, guardado = chaves.ARQUIVOS_DECOMP[tipo]
        z = _abrir_zip(nome, dados)
        interno = next(
            (i for i in z.infolist() if Path(i.filename).name.lower().startswith(prefixo)), None
        )
        if interno is None:
            raise NaoReconhecido(f"{nome}: não achei o arquivo {prefixo}*")
        conteudo = z.read(interno)
        _validar(decomp.ler_dadger_dp if tipo == "deck" else decomp.ler_sumario_cmo, conteudo)
        chave = chaves.raw_decomp(pmo, sem, pub, guardado)
        gravados[chave] = gravar_comprimido(arm, chave, conteudo, sobrescrever)
        achados += 1
        if gravados[chave] in ("novo", "sobrescrito"):
            meses.add(pd.Period(pmo, "M"))
    if not achados:
        raise NaoReconhecido("não achei zips DCAAAAMM-semN….zip nem Relatorio_Sumario-…zip")
    return gravados, meses


def _pld(arm: Armazenamento, item: Path, sobrescrever: bool):
    gravados, meses = {}, set()
    csvs = list(_ler_item(item, lambda n: n.lower().endswith(".csv")))
    if not csvs:
        raise NaoReconhecido("não achei csv do PLD horário")
    for nome, dados in csvs:
        novo = _validar(ccee.ler_pld_horario, dados)
        anos = novo["data"].dt.year.unique()
        if len(anos) != 1:
            raise NaoReconhecido(f"{nome}: esperado um ano por arquivo, achados {sorted(anos)}")
        chave = chaves.raw_pld(int(anos[0]))
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
    csvs = list(_ler_item(item, lambda n: n.lower().endswith(".csv")))
    if len(csvs) != 1:
        raise NaoReconhecido(f"esperado um csv dos limites por pacote, achados {len(csvs)}")
    _validar(ccee.ler_limites_pld, csvs[0][1])
    return {chaves.RAW_LIMITES: gravar_conferido(arm, chaves.RAW_LIMITES, csvs[0][1], True)}, set()


RECONHECER = {
    "ccee_pld": _pld,
    "ccee_limites_pld": _limites,
    "ccee_dessem": _dessem,
    "ccee_decomp": _decomp,
}


def _ingerir_pacote(arm: Armazenamento, fonte: str, item: Path, sobrescrever: bool) -> Resultado:
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


def ingerir_entrada(
    arm: Armazenamento, entrada: Path, sobrescrever: bool = False, aviso=None
) -> list[Resultado]:
    """Ingere tudo o que estiver em entrada/<fonte>/ desta funcionalidade e grava um relatório.

    `aviso(texto)` é chamado a cada pacote terminado (o deck mensal do DESSEM leva alguns segundos).
    """
    preparar_entrada(entrada)
    resultados = []
    for fonte in FONTES:
        for item in itens(entrada / fonte):
            r = _ingerir_pacote(arm, fonte, item, sobrescrever)
            resultados.append(r)
            if aviso:
                aviso(f"{r.fonte}/{r.origem}: {r.mensagem}")
    gravar_relatorio(entrada, resultados, PREFIXO_RELATORIO)
    return resultados
