"""Linha de comando da aplicação: `qe <funcionalidade> <etapa>` e `qe servir`."""

import typer

from qe_bandeiras.cli import app as bandeiras
from qe_pld_horario.cli import app as pld_horario

app = typer.Typer(
    help="quant-energia-app: pipelines e páginas por funcionalidade.", no_args_is_help=True
)
app.add_typer(bandeiras, name="bandeiras")
app.add_typer(pld_horario, name="pld_horario")


@app.command()
def servir(porta: int = typer.Option(8000, help="Porta local."), recarregar: bool = False):
    """Sobe a API e as páginas em http://localhost:<porta>."""
    from pathlib import Path

    import uvicorn

    # recarrega só quando o código Python muda; data/ e web/ são lidos a cada requisição
    raiz = Path(__file__).resolve().parents[2]
    pastas = [str(raiz / p) for p in ("core", "features", "api", "src")]
    uvicorn.run(
        "qe_api.app:app",
        host="127.0.0.1",
        port=porta,
        reload=recarregar,
        reload_dirs=pastas if recarregar else None,
    )


@app.command()
def config():
    """Mostra a configuração em uso (variáveis QE_*)."""
    from qe_core.config import configuracao

    for k, v in configuracao().model_dump().items():
        typer.echo(f"{k}: {v}")
