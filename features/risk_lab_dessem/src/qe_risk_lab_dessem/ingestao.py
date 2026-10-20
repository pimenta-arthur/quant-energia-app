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

from pathlib import Path

import pandas as pd

from qe_core import fontes
from qe_core.armazenamento import Armazenamento
from qe_core.entrada import (
    NaoReconhecido,
    Resultado,
    gravar_comprimido,
    gravar_relatorio,
    itens,
    remover,
)
from qe_core.fontes import abrir_zip, ler_item, validar
from qe_core.leitores import decomp
from qe_risk_lab_dessem import chaves

# DESSEM, PLD e limites são fontes comuns (também do descolamento): ingeridas por qe_core.fontes, que grava em
# raw/ o que qualquer funcionalidade usa; o DECOMP é só desta funcionalidade
FONTES = {
    "ccee_pld": fontes.COMUNS["ccee_pld"],
    "ccee_limites_pld": fontes.COMUNS["ccee_limites_pld"],
    "ccee_dessem": fontes.COMUNS["ccee_dessem"],
    "ccee_decomp": "decks do DECOMP: DCAAAAMM.zip ou os semanais DCAAAAMM-semN….zip e Relatorio_Sumario-…zip",
}
PREFIXO_RELATORIO = "risk_lab_dessem_"


def preparar_entrada(entrada: Path) -> None:
    for fonte in FONTES:
        (entrada / fonte).mkdir(parents=True, exist_ok=True)
    (entrada / "relatorios").mkdir(parents=True, exist_ok=True)


def _decomp(arm: Armazenamento, item: Path, sobrescrever: bool):
    gravados, meses, achados = {}, set(), 0
    reconhece = lambda n: decomp.semana_do_zip(n) is not None
    for nome, dados in ler_item(item, reconhece):
        tipo, pmo, sem, pub = decomp.semana_do_zip(nome)
        prefixo, guardado = chaves.ARQUIVOS_DECOMP[tipo]
        z = abrir_zip(nome, dados)
        interno = next(
            (i for i in z.infolist() if Path(i.filename).name.lower().startswith(prefixo)), None
        )
        if interno is None:
            raise NaoReconhecido(f"{nome}: não achei o arquivo {prefixo}*")
        conteudo = z.read(interno)
        validar(decomp.ler_dadger_dp if tipo == "deck" else decomp.ler_sumario_cmo, conteudo)
        chave = chaves.raw_decomp(pmo, sem, pub, guardado)
        gravados[chave] = gravar_comprimido(arm, chave, conteudo, sobrescrever)
        achados += 1
        if gravados[chave] in ("novo", "sobrescrito"):
            meses.add(pd.Period(pmo, "M"))
    if not achados:
        raise NaoReconhecido("não achei zips DCAAAAMM-semN….zip nem Relatorio_Sumario-…zip")
    return gravados, meses


RECONHECER = {"ccee_decomp": _decomp}


def _ingerir_pacote(arm: Armazenamento, fonte: str, item: Path, sobrescrever: bool) -> Resultado:
    if fonte in fontes.COMUNS:
        return fontes.ingerir_pacote(arm, fonte, item, sobrescrever)
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
