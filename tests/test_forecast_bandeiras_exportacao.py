"""Exportação da página como site estático: caminhos relativos e arquivos completos."""

import re

import pytest

from qe_core.armazenamento import ArmazenamentoLocal
from qe_forecast_bandeiras import chaves, exportacao


@pytest.fixture
def arm(tmp_path):
    a = ArmazenamentoLocal(tmp_path / "dados")
    a.gravar_bytes(b"window.DADOS = {};", chaves.SERVING_DADOS)
    return a


def test_site_completo_e_com_caminhos_relativos(arm, tmp_path):
    destino = tmp_path / "site"
    (destino).mkdir()
    (destino / "README.md").write_text("fica")
    escritos = exportacao.exportar(arm, destino)
    assert set(escritos) == {
        "index.html",
        "metodologia.html",
        "padrao/base.css",
        "padrao/painel.css",
        "dados/produto_dados.js",
        ".nojekyll",
    }
    assert (destino / "README.md").read_text() == "fica"
    for nome in ("index.html", "metodologia.html"):
        html = (destino / nome).read_text(encoding="utf-8")
        locais = re.findall(r'(?:href|src)="(?!https?:|#|mailto:)([^"]+)"', html)
        for caminho in locais:  # todo arquivo local referenciado existe no site
            assert (destino / caminho.split("#")[0]).exists() or caminho in ("./",), (nome, caminho)
    assert 'src="dados/produto_dados.js"' in (destino / "index.html").read_text(encoding="utf-8")


def test_sem_dados_publicados(tmp_path):
    with pytest.raises(ValueError, match="publicar"):
        exportacao.exportar(ArmazenamentoLocal(tmp_path / "vazio"), tmp_path / "site")
