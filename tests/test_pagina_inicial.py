"""Página inicial (web/index.html): a descrição de cada funcionalidade cabe em uma linha só, sem quebra.

A lista tem a largura da `main` menos o recuo dos marcadores. Cada caractere ocupa até ~7,9 px (medido no Chrome com a
fonte da página: de 6,8 a 7,8 px por caractere conforme as letras), então o limite de caracteres sai da largura da
própria página: se ela for alargada, o limite sobe junto. O detalhe de cada funcionalidade fica no topo da página dela,
não nesta lista.
"""

import math
import re
from pathlib import Path

import pytest

INDEX = Path(__file__).resolve().parents[1] / "web" / "index.html"
RECUO_LISTA_PX = 40  # padding-left padrão do <ul>, onde ficam os marcadores
PX_POR_CARACTERE = 7.9  # pior caso medido (letras maiúsculas e largas)


def _itens(html: str) -> list[tuple[str, str]]:
    return re.findall(r'<li><a href="[^"]+">([^<]+)</a>\s*<span>([^<]*)</span></li>', html)


def _limite_caracteres(html: str) -> int:
    largura = int(re.search(r"main\s*\{[^}]*max-width:\s*(\d+)px", html).group(1))
    return math.floor((largura - RECUO_LISTA_PX) / PX_POR_CARACTERE)


@pytest.fixture(scope="module")
def html() -> str:
    return INDEX.read_text(encoding="utf-8")


def test_a_pagina_lista_as_funcionalidades(html):
    nomes = [n for n, _ in _itens(html)]
    assert len(nomes) >= 4 and len(set(nomes)) == len(nomes)


def test_descricao_cabe_em_uma_linha(html):
    limite = _limite_caracteres(html)
    longas = [(n, len(f"{n} {d}")) for n, d in _itens(html) if len(f"{n} {d}") > limite]
    assert not longas, (
        f"descrição acima de {limite} caracteres (nome incluído); encurte o texto, o detalhe vai no topo da "
        f"página da funcionalidade: {longas}"
    )


def test_sem_quebra_de_linha_forcada_nas_descricoes(html):
    for n, d in _itens(html):
        assert "<br" not in d.lower() and "\n" not in d, n
