"""Ingestão pela caixa de entrada (data/entrada/<fonte>/ → raw/).

Os casos sintéticos rodam sempre. Os casos com arquivos reais usam o raw/ local do app (fora do git)
e são pulados quando ele não existe: refazem a ingestão a partir de zips e pastas montados com os
mesmos arquivos e conferem que as chaves e a versão do deck são as mesmas de hoje.
"""

import zipfile
from pathlib import Path

import pandas as pd
import pytest

from qe_core.armazenamento import ArmazenamentoLocal
from qe_forecast_bandeiras import ingestao

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
DECK_SET = RAW / "ccee_newave" / "deck=2026-09" / "v=a3084ea2"
com_dados = pytest.mark.skipif(not DECK_SET.exists(), reason="sem data/raw local")

ECMWF = "ENA_MLT_SUBSISTEMA_MENSAL_ECENSLTav_precip_simples-defasagem_20261015.txt"


@pytest.fixture
def ambiente(tmp_path):
    arm = ArmazenamentoLocal(tmp_path / "dados")
    entrada = tmp_path / "dados" / "entrada"
    ingestao.preparar_entrada(entrada)
    return arm, entrada


def _zip(destino: Path, arquivos: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(destino, "w") as z:
        for nome, dados in arquivos.items():
            z.writestr(nome, dados)
    return destino


# --- sintéticos -----------------------------------------------------------------------------------


def test_ecmwf_ingere_confere_e_apaga(ambiente):
    arm, entrada = ambiente
    (entrada / "ecmwf" / ECMWF).write_text("conteudo")
    [r] = ingestao.ingerir_entrada(arm, entrada)
    assert r.removido and r.novo and r.meses == {pd.Period("2026-10", "M")}
    assert arm.ler_bytes(f"raw/ecmwf/emissao=2026-10-15/{ECMWF}") == b"conteudo"
    assert not (entrada / "ecmwf" / ECMWF).exists()
    assert len(list((entrada / "relatorios").iterdir())) == 1


def test_arquivo_igual_nao_conta_como_novo(ambiente):
    arm, entrada = ambiente
    for _ in range(2):
        (entrada / "ecmwf" / ECMWF).write_text("conteudo")
        [r] = ingestao.ingerir_entrada(arm, entrada)
    assert r.removido and not r.novo and r.meses == set()


def test_conteudo_diferente_fica_na_entrada(ambiente):
    arm, entrada = ambiente
    (entrada / "ecmwf" / ECMWF).write_text("v1")
    ingestao.ingerir_entrada(arm, entrada)
    (entrada / "ecmwf" / ECMWF).write_text("v2")
    [r] = ingestao.ingerir_entrada(arm, entrada)
    assert not r.removido and "sobrescrever" in r.mensagem
    assert (entrada / "ecmwf" / ECMWF).exists()
    [r] = ingestao.ingerir_entrada(arm, entrada, sobrescrever=True)
    assert r.removido and arm.ler_bytes(f"raw/ecmwf/emissao=2026-10-15/{ECMWF}") == b"v2"


def test_nao_reconhecido_fica_na_entrada(ambiente):
    arm, entrada = ambiente
    (entrada / "ccee_newave" / "qualquer.txt").write_text("x")
    (entrada / "ccee_newave" / "pela_metade.zip").write_bytes(b"PK\x03\x04incompleto")
    (entrada / "ons_pmo" / "renovaveis.csv").write_text("PEE-GER-PER-PAT-CEN;1;1;1;1;1;10\n")
    res = {r.origem: r for r in ingestao.ingerir_entrada(arm, entrada)}
    assert "ghtotsin.out" in res["qualquer.txt"].mensagem
    assert "zip inválido" in res["pela_metade.zip"].mensagem
    assert "subpasta AAAA-MM" in res["renovaveis.csv"].mensagem
    assert not any(r.removido for r in res.values())
    assert arm.listar("raw") == []


def test_subpasta_do_mes_supre_o_conteudo(ambiente):
    arm, entrada = ambiente
    pasta = entrada / "ons_pmo" / "2026-10"
    pasta.mkdir()
    (pasta / "renovaveis.csv").write_text("PEE-GER-PER-PAT-CEN;1;1;1;1;1;10\n")
    [r] = ingestao.ingerir_entrada(arm, entrada)
    assert r.removido and arm.existe("raw/ons_pmo/2026-10/renovaveis.csv")


# --- com os arquivos reais do raw/ local ---------------------------------------------------------


@com_dados
def test_deck_em_zip_aninhado_tem_a_mesma_versao(ambiente):
    arm, entrada = ambiente
    arquivos = {p.name: p.read_bytes() for p in DECK_SET.iterdir() if p.name != "_ingestao.json"}
    interno = _zip(entrada.parent / "interno.zip", arquivos | {"outro_arquivo.dat": b"ignorado"})
    _zip(entrada / "ccee_newave" / "deck_nw_202609.zip", {"pasta/deck.zip": interno.read_bytes()})
    [r] = ingestao.ingerir_entrada(arm, entrada)
    assert r.removido and r.meses == {pd.Period("2026-09", "M")}
    gravados = arm.listar("raw/ccee_newave/deck=2026-09/v=a3084ea2")
    assert len(gravados) == 16  # 15 arquivos + _ingestao.json; o arquivo extra do zip não entra


@com_dados
def test_deck_incompleto_fica_na_entrada(ambiente):
    arm, entrada = ambiente
    _zip(
        entrada / "ccee_newave" / "deck.zip",
        {"ghtotsin.out": (DECK_SET / "ghtotsin.out").read_bytes()},
    )
    [r] = ingestao.ingerir_entrada(arm, entrada)
    assert not r.removido and "faltam" in r.mensagem


@com_dados
def test_pmo_boletim_e_patamares_pelo_conteudo(ambiente):
    arm, entrada = ambiente
    pmo = RAW / "ons_pmo" / "2026-10"
    pasta = entrada / "ons_pmo" / "PMO_qualquer_nome"
    pasta.mkdir()
    (pasta / "relato.rv0").write_bytes((pmo / "relato.rv0").read_bytes())
    (pasta / "Relatorio ENA.pdf").write_bytes((pmo / "ena.pdf").read_bytes())
    (pasta / "renovaveis.csv").write_bytes((pmo / "renovaveis.csv").read_bytes())
    boletim = RAW / "ccee_boletim" / "2026-10" / "infobandeira.pdf"
    (entrada / "ccee_infobandeira" / "102 - InfoBandeira.pdf").write_bytes(boletim.read_bytes())
    pat = RAW / "ccee_patamares" / "2026" / "AAC001.xlsx"
    (entrada / "ccee_patamares" / "AAC001 - Patamares 2026.xlsx").write_bytes(pat.read_bytes())
    res = {r.fonte: r for r in ingestao.ingerir_entrada(arm, entrada)}
    assert all(r.removido for r in res.values()), [r.mensagem for r in res.values()]
    for nome in ("relato.rv0", "ena.pdf", "renovaveis.csv"):
        assert arm.ler_bytes(f"raw/ons_pmo/2026-10/{nome}") == (pmo / nome).read_bytes()
    assert arm.ler_bytes("raw/ccee_boletim/2026-10/infobandeira.pdf") == boletim.read_bytes()
    assert arm.existe("raw/ccee_patamares/2026/AAC001.xlsx")
