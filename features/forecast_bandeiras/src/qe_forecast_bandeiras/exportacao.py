"""Exportação da página para um site estático (ex.: GitHub Pages do repositório forecast-bandeiras-page).

Copia as páginas (`web/forecast_bandeiras/`, com a conta do relato), o CSS e o JS do padrão visual (`web/padrao/`)
e os dados da última rodada publicada e da página do relato (serving/) para uma pasta, com os caminhos trocados por relativos, para abrir sem o
servidor do app. Só escreve os arquivos do site na pasta de destino (README, .git e outros ficam).
O app não lê nada da pasta de destino.
"""

import re
from pathlib import Path

from qe_core.armazenamento import Armazenamento
from qe_forecast_bandeiras import chaves

WEB = Path(__file__).resolve().parents[4] / "web"
PAGINAS = ("index.html", "metodologia.html", "relato.html")
COMPLEMENTOS = ("relato_conta.js",)  # arquivos de web/forecast_bandeiras/ que as páginas carregam
PADRAO = ("base.css", "painel.css", "graficos.js")
TROCAS = (
    ('href="../padrao/', 'href="padrao/'),
    ('src="../padrao/', 'src="padrao/'),
    ('src="/dados/forecast_bandeiras/produto_dados.js"', 'src="dados/produto_dados.js"'),
    ('src="/dados/forecast_bandeiras/relato_dados.js"', 'src="dados/relato_dados.js"'),
    ('<a class="marca" href="/">', '<a class="marca" href="./">'),
)


def exportar(arm: Armazenamento, destino: Path) -> list[str]:
    """Grava o site em `destino` e devolve os arquivos escritos (relativos ao destino)."""
    destino = Path(destino)
    escritos = []

    def gravar(rel: str, conteudo: bytes) -> None:
        caminho = destino / rel
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_bytes(conteudo)
        escritos.append(rel)

    for nome in PAGINAS:
        html = (WEB / "forecast_bandeiras" / nome).read_text(encoding="utf-8")
        for a, b in TROCAS:
            html = html.replace(a, b)
        # o site não tem o servidor do app: nenhum caminho absoluto ou fora da pasta pode sobrar
        sobra = re.findall(r'(?:href|src)="(/[^/"][^"]*|\.\./[^"]*)"', html)
        if sobra:
            raise ValueError(f"{nome}: caminhos que não funcionam fora do app: {sobra}")
        gravar(nome, html.encode("utf-8"))
    for nome in COMPLEMENTOS:
        gravar(nome, (WEB / "forecast_bandeiras" / nome).read_bytes())
    for nome in PADRAO:
        gravar(f"padrao/{nome}", (WEB / "padrao" / nome).read_bytes())
    if not arm.existe(chaves.SERVING_DADOS):
        raise ValueError("sem dados publicados: rode `qe forecast_bandeiras publicar` antes")
    gravar("dados/produto_dados.js", arm.ler_bytes(chaves.SERVING_DADOS))
    if not arm.existe(chaves.SERVING_RELATO_DADOS):
        raise ValueError("sem dados da página do relato: rode `qe forecast_bandeiras pagina` antes")
    gravar("dados/relato_dados.js", arm.ler_bytes(chaves.SERVING_RELATO_DADOS))
    gravar(".nojekyll", b"")  # GitHub Pages serve os arquivos como estão
    return escritos
