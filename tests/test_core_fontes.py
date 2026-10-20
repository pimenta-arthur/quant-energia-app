"""Ingestão das fontes comuns (qe_core.fontes): o que uma funcionalidade usa entra em raw/ mesmo quando é a
outra que ingere, e cada funcionalidade só trata de novo o que é dela."""

import gzip
import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from qe_core import fontes
from qe_core.armazenamento import ArmazenamentoLocal
from qe_forecast_bandeiras import ingestao as ing_bandeiras
from qe_risk_lab_dessem import ingestao as ing_risk_lab

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
DIA_DESSEM = RAW / "ccee_dessem" / "dia=2026-09-30"


@pytest.fixture
def ambiente(tmp_path):
    arm = ArmazenamentoLocal(tmp_path / "dados")
    entrada = tmp_path / "dados" / "entrada"
    ing_bandeiras.preparar_entrada(entrada)
    ing_risk_lab.preparar_entrada(entrada)
    return arm, entrada


def _zip(arquivos: dict[str, bytes]) -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for nome, dados in arquivos.items():
            z.writestr(nome, dados)
    return b.getvalue()


def test_deck_de_entrada_com_publicacoes(ambiente):
    """NWAAAAMM.zip com a 1ª e a 2ª publicação: cada uma vira uma versão do sistema_agrint, com a publicação
    na marca; o tratamento das bandeiras não muda (nenhum mês a refazer)."""
    arm, entrada = ambiente
    pub = lambda k: _zip(
        {"SISTEMA.DAT": b"sistema", "AGRINT.DAT": f"agrint {k}".encode(), "HIDR.DAT": b"x"}
    )
    (entrada / "ccee_newave" / "NW202401.zip").write_bytes(
        _zip({"NW202401_1aPublicacao.zip": pub(1), "NW202401_2aPublicacao.zip": pub(2)})
    )
    [r] = ing_bandeiras.ingerir_entrada(arm, entrada)
    assert r.removido and r.novo and r.meses == set()  # nada para as bandeiras
    marcas = [
        c for c in arm.listar("raw/ccee_newave/deck=2024-01/sistema_agrint") if c.endswith(".json")
    ]
    pubs = sorted(json.loads(arm.ler_bytes(c))["publicacao"] for c in marcas)
    assert pubs == [1, 2]
    assert not any("/v=" in c.split("sistema_agrint")[0] for c in arm.listar("raw/ccee_newave"))


def test_publicacoes_iguais_contam_como_novo(ambiente):
    """Duas publicações com SISTEMA e AGRINT iguais são uma versão só, e o pacote conta como novo."""
    arm, entrada = ambiente
    pub = _zip({"SISTEMA.DAT": b"s", "AGRINT.DAT": b"a"})
    (entrada / "ccee_newave" / "NW202609.zip").write_bytes(
        _zip({"NW202609_1aPublicacao.zip": pub, "NW202609_2aPublicacao.zip": pub})
    )
    [r] = ing_bandeiras.ingerir_entrada(arm, entrada)
    assert r.novo and "2 arquivo(s) novo(s)" in r.mensagem
    [marca] = [c for c in arm.listar("raw/ccee_newave/deck=2026-09") if c.endswith(".json")]
    assert json.loads(arm.ler_bytes(marca))["origem"] == "NW202609.zip/NW202609_1aPublicacao.zip"


def test_deck_de_entrada_sem_mes_fica_na_entrada(ambiente):
    arm, entrada = ambiente
    (entrada / "ccee_newave" / "deck.zip").write_bytes(
        _zip({"SISTEMA.DAT": b"s", "AGRINT.DAT": b"a"})
    )
    [r] = ing_bandeiras.ingerir_entrada(arm, entrada)
    assert not r.removido and "NWAAAAMM" in r.mensagem


def test_deck_de_entrada_numa_subpasta_do_mes(ambiente):
    arm, entrada = ambiente
    pasta = entrada / "ccee_newave" / "2026-10"
    pasta.mkdir()
    (pasta / "SISTEMA.DAT").write_bytes(b"s")
    (pasta / "AGRINT.DAT").write_bytes(b"a")
    [r] = ing_bandeiras.ingerir_entrada(arm, entrada)
    assert r.removido
    assert any(
        c.endswith("agrint.dat") for c in arm.listar("raw/ccee_newave/deck=2026-10/sistema_agrint")
    )


@pytest.mark.skipif(not DIA_DESSEM.exists(), reason="sem data/raw local")
def test_restoper_entra_no_dia_ingerido_pelo_risk_lab(ambiente):
    """O Risk Lab ingere o deck do DESSEM e o PDO_RESTOPER.DAT (do descolamento) entra em raw/ junto."""
    arm, entrada = ambiente
    arqs = {p.name[:-3]: gzip.decompress(p.read_bytes()) for p in DIA_DESSEM.glob("*.gz")}
    ent = _zip({"entdados.dat": arqs["entdados.dat"], "renovaveis.dat": arqs["renovaveis.dat"]})
    res = _zip({"PDO_SIST.DAT": arqs["PDO_SIST.DAT"], "PDO_RESTOPER.DAT": b"restricoes"})
    (entrada / "ccee_dessem" / "DES_202610.zip").write_bytes(
        _zip(
            {
                "DS_CCEE_102026_SEMREDE_RV0D30.zip": ent,
                "Resultado_DS_CCEE_102026_SEMREDE_RV0D30.zip": res,
            }
        )
    )
    [r] = ing_risk_lab.ingerir_entrada(arm, entrada)
    assert r.removido
    chave = fontes.raw_dessem(pd.Timestamp("2026-09-30").date(), "PDO_RESTOPER.DAT.gz")
    assert gzip.decompress(arm.ler_bytes(chave)) == b"restricoes"
