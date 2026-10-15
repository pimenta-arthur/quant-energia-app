"""Ingestão do PLD horário pela caixa de entrada (data/entrada/<fonte>/ → raw/).

Os casos sintéticos rodam sempre. O caso do DESSEM usa um dia real do raw/ local do app (fora do
git) e é pulado quando ele não existe: remonta os zips da CCEE (diário dentro do mensal) com os
mesmos arquivos e confere que a ingestão grava as mesmas chaves e o mesmo conteúdo.
"""

import datetime as dt
import gzip
import io
import zipfile
from pathlib import Path

import pytest

from qe_core.armazenamento import ArmazenamentoLocal
from qe_core.leitores import decomp, dessem
from qe_pld_horario import chaves, ingestao

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
DIA = dt.date(2026, 9, 30)
com_dados = pytest.mark.skipif(
    not (RAW / "ccee_dessem" / f"dia={DIA}").exists(), reason="sem data/raw local"
)

CSV = "MES_REFERENCIA;SUBMERCADO;PERIODO_COMERCIALIZACAO;DIA;HORA;PLD_HORA\n"


@pytest.fixture
def ambiente(tmp_path):
    arm = ArmazenamentoLocal(tmp_path / "dados")
    entrada = tmp_path / "dados" / "entrada"
    ingestao.preparar_entrada(entrada)
    return arm, entrada


def _pld_csv(dias: int) -> str:
    linhas = [
        f"202610;{s};1;{d};{h};{57.31 + h}"
        for d in range(1, dias + 1)
        for h in range(24)
        for s in ("SUDESTE", "SUL", "NORDESTE", "NORTE")
    ]
    return CSV + "\n".join(linhas) + "\n"


def _zip(arquivos: dict[str, bytes]) -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for nome, dados in arquivos.items():
            z.writestr(nome, dados)
    return b.getvalue()


# --- nomes dos zips -------------------------------------------------------------------------------


def test_data_do_deck_pelo_mes_operativo():
    assert dessem.data_do_deck("DS_CCEE_102026_SEMREDE_RV0D27.zip") == (
        dt.date(2026, 9, 27),
        "2026-10",
        0,
        False,
    )
    assert dessem.data_do_deck("Resultado_DS_CCEE_012026_SEMREDE_RV0D29.zip")[0] == dt.date(
        2025, 12, 29
    )
    assert dessem.data_do_deck("DS_CCEE_102026_SEMREDE_RV2D13.zip")[0] == dt.date(2026, 10, 13)
    with pytest.raises(ValueError):
        dessem.data_do_deck("DS_CCEE_102026_RV2D13.zip")


def test_semana_do_decomp_e_publicacao():
    assert decomp.semana_do_zip("DC202609-sem1_2aPublicacao.zip") == ("deck", "2026-09", 1, 2)
    assert decomp.semana_do_zip("DC202609-sem3.zip") == ("deck", "2026-09", 3, 1)
    assert decomp.semana_do_zip("Relatorio_Sumario-202609-sem1_1aPublicacao..zip") == (
        "relatorio",
        "2026-09",
        1,
        1,
    )
    assert decomp.semana_do_zip("Leia-me.pdf") is None


# --- PLD publicado: conjunto republicado pela CCEE ---------------------------------------------------


def test_pld_republicado_substitui(ambiente):
    arm, entrada = ambiente
    (entrada / "ccee_pld" / "pld_horario_2026.csv").write_text(_pld_csv(10))
    [r] = ingestao.ingerir_entrada(arm, entrada)
    assert r.removido and r.novo and arm.existe(chaves.raw_pld(2026))
    (entrada / "ccee_pld" / "pld_horario_2026.csv").write_text(_pld_csv(13))
    [r] = ingestao.ingerir_entrada(arm, entrada)
    assert r.removido and r.gravados[chaves.raw_pld(2026)] == "sobrescrito"


def test_pld_que_perde_horas_fica_na_entrada(ambiente):
    arm, entrada = ambiente
    (entrada / "ccee_pld" / "pld_horario_2026.csv").write_text(_pld_csv(13))
    ingestao.ingerir_entrada(arm, entrada)
    (entrada / "ccee_pld" / "pld_horario_2026.csv").write_text(_pld_csv(10))
    [r] = ingestao.ingerir_entrada(arm, entrada)
    assert not r.removido and (entrada / "ccee_pld" / "pld_horario_2026.csv").exists()
    [r] = ingestao.ingerir_entrada(arm, entrada, sobrescrever=True)
    assert r.removido


def test_zip_pela_metade_fica_na_entrada(ambiente):
    arm, entrada = ambiente
    (entrada / "ccee_dessem" / "DES_202610.zip").write_bytes(b"PK\x03\x04 incompleto")
    [r] = ingestao.ingerir_entrada(arm, entrada)
    assert not r.removido and "zip inválido" in r.mensagem


# --- DESSEM com arquivos reais ----------------------------------------------------------------------


def _dia_real() -> dict[str, bytes]:
    pasta = RAW / "ccee_dessem" / f"dia={DIA}"
    return {p.name[:-3]: gzip.decompress(p.read_bytes()) for p in pasta.glob("*.gz")}


@com_dados
def test_dessem_mensal_com_diarios_dentro(ambiente):
    arm, entrada = ambiente
    arqs = _dia_real()
    ent = _zip({"entdados.dat": arqs["entdados.dat"], "renovaveis.dat": arqs["renovaveis.dat"]})
    res = _zip({"PDO_SIST.DAT": arqs["PDO_SIST.DAT"], "PDO_OUTRO.DAT": b"ignorado"})
    mensal = _zip(
        {
            "DS_CCEE_102026_SEMREDE_RV0D30.zip": ent,
            "Resultado_DS_CCEE_102026_SEMREDE_RV0D30.zip": res,
        }
    )
    (entrada / "ccee_dessem" / "DES_202610.zip").write_bytes(mensal)
    [r] = ingestao.ingerir_entrada(arm, entrada)
    assert r.removido and r.novo
    for nome in ("entdados.dat", "renovaveis.dat", "PDO_SIST.DAT"):
        guardado = arm.ler_bytes(chaves.raw_dessem(DIA, nome + ".gz"))
        assert gzip.decompress(guardado) == arqs[nome]
    assert not arm.existe(chaves.raw_dessem(DIA, "PDO_OUTRO.DAT.gz"))

    # o mesmo zip de novo (o mensal da CCEE cresce ao longo do mês): nada novo
    (entrada / "ccee_dessem" / "DES_202610.zip").write_bytes(mensal)
    [r] = ingestao.ingerir_entrada(arm, entrada)
    assert r.removido and not r.novo

    # outro conteúdo para o mesmo dia: raw/ é imutável, o pacote fica na entrada
    alterado = arqs["PDO_SIST.DAT"].replace(b"Grenova", b"Grenova", 1) + b"\n"
    outro = _zip({"Resultado_DS_CCEE_102026_SEMREDE_RV0D30.zip": _zip({"PDO_SIST.DAT": alterado})})
    (entrada / "ccee_dessem" / "DES_202610.zip").write_bytes(outro)
    [r] = ingestao.ingerir_entrada(arm, entrada)
    assert not r.removido and "conteúdo" in r.mensagem


@com_dados
def test_dessem_recusa_dia_que_nao_confere(ambiente):
    arm, entrada = ambiente
    arqs = _dia_real()
    # o PDO_SIST de 30/09 com o nome do deck de 29/09: a "Data do Caso" não confere
    res = _zip({"PDO_SIST.DAT": arqs["PDO_SIST.DAT"]})
    (entrada / "ccee_dessem" / "Resultado_DS_CCEE_102026_SEMREDE_RV0D29.zip").write_bytes(res)
    [r] = ingestao.ingerir_entrada(arm, entrada)
    assert not r.removido and "Data do Caso" in r.mensagem
