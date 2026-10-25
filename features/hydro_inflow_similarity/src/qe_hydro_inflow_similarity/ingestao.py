"""Ingestão da projeção de ENA: da caixa de entrada (data/entrada/<fonte>/) para raw/.

Fontes só desta funcionalidade (chaves.py). Os coletores do `energia-data-ingestion` (ons-ena-diaria, noaa-indices,
noaa-ersst, cpc-enso-previsao) gravam exatamente o que se solta aqui; a planilha 1931–2024 é manual. Cada arquivo
reconhecido é lido pelo leitor antes de ir para raw/ (o que não passa fica na entrada), e o original só é apagado
depois de tudo gravado e conferido. Formato de cada fonte: docs/entrada.md.
"""

import datetime as dt
import re
import tempfile
from pathlib import Path

from qe_core.armazenamento import Armazenamento, gravar_json, ler_json
from qe_core.entrada import (
    NaoReconhecido,
    Resultado,
    gravar_conferido,
    gravar_relatorio,
    itens,
    remover,
    sha,
)
from qe_core.fontes import ler_item
from qe_core.leitores import noaa, ons
from qe_hydro_inflow_similarity import chaves

FONTES = {
    "ons_ena_historica": "planilhas do ONS 1931–2024 (Enas_Subsistemas_1931-2024.xls, Enas_bacias_1931-2024.xls)",
    "ons_ena_diaria": "ENA diária dos Dados Abertos do ONS (ENA_DIARIO_SUBSISTEMA_AAAA.csv, "
    "ENA_DIARIO_BACIAS_AAAA.csv), um por ano",
    "noaa_ersst": "grade ERSST v6 (sst.mnmean.nc ou ersst.v6.sst.mnmean.nc)",
    "noaa_indices": "índices da NOAA: oni.ascii.txt, RONI.ascii.txt, soi.txt, aao_mensal.txt (CPC), "
    "ersst.v5.pdo.dat, ersst.v5.amo.dat (NCEI)",
    "cpc_enso_previsao": "páginas de probabilidade do ENSO do CPC (HTML, por fase e por força)",
}
PREFIXO_RELATORIO = "hydro_inflow_similarity_"
RE_DIARIA = re.compile(r"ENA_DIARIO_(SUBSISTEMA|BACIAS)_(\d{4})\.csv$", re.IGNORECASE)
NOME_INDICE = {alt.lower(): canonico for canonico, alts in chaves.INDICES.items() for alt in alts}
LEITOR_INDICE = {
    "oni.ascii.txt": noaa.ler_indice_trimestral_cpc,
    "RONI.ascii.txt": noaa.ler_indice_trimestral_cpc,
    "soi.txt": noaa.ler_soi_cpc,
    "aao_mensal.txt": noaa.ler_aao_cpc,
    "ersst.v5.pdo.dat": noaa.ler_pdo_ncei,
    "ersst.v5.amo.dat": noaa.ler_amo_ncei,
}
MESES_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
            "October", "November", "December"]  # fmt: skip


def _agora() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _validar(nome: str, dados: bytes, leitor):
    """Roda o leitor sobre uma cópia temporária; erro de leitura = arquivo não reconhecido."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / nome
        p.write_bytes(dados)
        try:
            return leitor(p)
        except Exception as e:  # qualquer falha do leitor recusa o arquivo
            raise NaoReconhecido(f"{nome}: o leitor não conseguiu ler ({e})") from e


def _gravar_versao(arm, prefixo: str, arquivo: str, dados: bytes, origem: str) -> tuple[str, str]:
    """Versão por hash ao lado das anteriores: igual se alguma versão já tem o mesmo conteúdo."""
    versao = sha(dados)[:12]
    chave = f"{prefixo}/v={versao}/{arquivo}"
    if arm.existe(chave):
        return chave, "igual"
    situacao = gravar_conferido(arm, chave, dados, False)
    gravar_json(
        arm,
        {"origem": origem, "gravado_em": _agora(), "sha256": sha(dados)},
        f"{prefixo}/v={versao}/{chaves.MARCA}",
    )
    return chave, situacao


def _historica(arm, item, sobrescrever):
    gravados = {}
    nomes = {v.lower(): (k, v) for k, v in chaves.PLANILHAS.items()}
    for nome, dados in ler_item(item, lambda n: n.lower() in nomes):
        nivel, canonico = nomes[nome.lower()]
        _validar(canonico, dados, lambda p, n=nivel: ons.ler_planilha_ena(p, n))
        chave = f"{chaves.RAW_HISTORICA}/{canonico}"
        gravados[chave] = gravar_conferido(arm, chave, dados, sobrescrever)
    return gravados


def _diaria(arm, item, _sobrescrever):
    gravados = {}
    for nome, dados in ler_item(item, lambda n: bool(RE_DIARIA.search(n))):
        m = RE_DIARIA.search(nome)
        nivel = "subsistema" if m.group(1).upper() == "SUBSISTEMA" else "bacia"
        ano = int(m.group(2))
        canonico = chaves.ARQUIVO_DIARIA[nivel].format(ano=ano)
        _validar(canonico, dados, lambda p, n=nivel: ons.ler_ena_diaria(p, n))
        chave, s = _gravar_versao(
            arm, f"{chaves.RAW_DIARIA}/{nivel}/ano={ano}", canonico, dados, nome
        )
        gravados[chave] = s
    return gravados


def _indices(arm, item, _sobrescrever):
    gravados = {}
    for nome, dados in ler_item(item, lambda n: n.lower() in NOME_INDICE):
        canonico = NOME_INDICE[nome.lower()]
        serie = _validar(canonico, dados, LEITOR_INDICE[canonico])
        if serie.empty:
            raise NaoReconhecido(f"{nome}: nenhum valor lido")
        chave, s = _gravar_versao(arm, f"{chaves.RAW_INDICES}/{canonico}", canonico, dados, nome)
        gravados[chave] = s
    return gravados


def _ersst(arm, item, _sobrescrever):
    """Só a publicação mais recente fica em raw/ (decisão da promoção); o hash de cada uma vai para
    _publicacoes.json, com o último mês da grade."""
    import xarray as xr

    gravados = {}
    for nome, dados in ler_item(item, lambda n: n.lower().endswith(".nc")):

        def ultimo_mes(p):
            with xr.open_dataset(p) as ds:
                return str(ds["sst"].time.values.max())[:7]

        fim = _validar(nome, dados, ultimo_mes)
        pub = (
            ler_json(arm, chaves.RAW_ERSST_PUBLICACOES)
            if arm.existe(chaves.RAW_ERSST_PUBLICACOES)
            else []
        )
        if pub and pub[-1]["sha256"] == sha(dados):
            gravados[chaves.RAW_ERSST] = "igual"
            continue
        gravados[chaves.RAW_ERSST] = gravar_conferido(arm, chaves.RAW_ERSST, dados, True)
        pub.append({"sha256": sha(dados), "ate": fim, "origem": nome, "gravado_em": _agora()})
        gravar_json(arm, pub, chaves.RAW_ERSST_PUBLICACOES)
    return gravados


def _cpc(arm, item, sobrescrever):
    gravados = {}
    for nome, dados in ler_item(item, lambda n: n.lower().endswith((".html", ".htm"))):
        p = _validar(nome, dados, noaa.ler_probabilidades_enso)
        if not p["emitida"] or not p["linhas"]:
            raise NaoReconhecido(f"{nome}: sem data de emissão ou sem tabela de probabilidades")
        mes, ano = p["emitida"].split()
        emissao = f"{ano}-{MESES_EN.index(mes) + 1:02d}"
        tipo = "probabilidades.html" if len(p["linhas"][0]["valores"]) == 3 else "forca.html"
        chave = chaves.raw_cpc(emissao, tipo)
        gravados[chave] = gravar_conferido(arm, chave, dados, sobrescrever)
    return gravados


RECONHECER = {
    "ons_ena_historica": _historica,
    "ons_ena_diaria": _diaria,
    "noaa_ersst": _ersst,
    "noaa_indices": _indices,
    "cpc_enso_previsao": _cpc,
}


def ingerir_pacote(arm: Armazenamento, fonte: str, item: Path, sobrescrever: bool) -> Resultado:
    """Ingere um item solto em entrada/<fonte>/; só apaga o original se tudo foi gravado."""
    try:
        gravados = RECONHECER[fonte](arm, item, sobrescrever)
    except NaoReconhecido as e:
        return Resultado(fonte, item.name, False, f"mantido na entrada: {e}")
    if not gravados:
        return Resultado(
            fonte, item.name, False, f"mantido na entrada: nenhum arquivo de {FONTES[fonte]}"
        )
    divergentes = [c for c, s in gravados.items() if s == "divergente"]
    if divergentes:
        return Resultado(
            fonte,
            item.name,
            False,
            f"mantido na entrada: {len(divergentes)} arquivo(s) já existem em raw/ com conteúdo "
            f"diferente (ex.: {divergentes[0]}); para substituir, rode com --sobrescrever",
            gravados,
        )
    remover(item)
    novos = sum(s in ("novo", "sobrescrito") for s in gravados.values())
    texto = f"{novos} arquivo(s) novo(s) em raw/" if novos else "já estava em raw/ (nada novo)"
    return Resultado(fonte, item.name, True, f"ingerido: {texto}", gravados)


def preparar_entrada(entrada: Path) -> None:
    for fonte in FONTES:
        (entrada / fonte).mkdir(parents=True, exist_ok=True)
    (entrada / "relatorios").mkdir(parents=True, exist_ok=True)


def ingerir_entrada(
    arm: Armazenamento, entrada: Path, sobrescrever: bool = False, aviso=None
) -> list[Resultado]:
    """Ingere tudo o que estiver em entrada/<fonte>/ das fontes desta funcionalidade e grava um relatório."""
    preparar_entrada(entrada)
    resultados = []
    for fonte in FONTES:
        for item in itens(entrada / fonte):
            r = ingerir_pacote(arm, fonte, item, sobrescrever)
            resultados.append(r)
            if aviso:
                aviso(f"{r.fonte}/{r.origem}: {r.mensagem}")
    gravar_relatorio(entrada, resultados, PREFIXO_RELATORIO)
    return resultados


def versoes(arm: Armazenamento, prefixo: str) -> list[tuple[str, str]]:
    """(gravado_em, pasta da versão) de cada versão sob `prefixo`, da mais antiga à mais recente."""
    marcas = [c for c in arm.listar(prefixo) if c.endswith(chaves.MARCA)]
    return sorted((ler_json(arm, c)["gravado_em"], c.rsplit("/", 1)[0]) for c in marcas)
