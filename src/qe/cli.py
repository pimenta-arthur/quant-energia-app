"""Linha de comando da aplicação: `qe <funcionalidade> <etapa>` e `qe servir`."""

import typer

from qe_forecast_bandeiras.cli import app as forecast_bandeiras
from qe_hydro_inflow_similarity.cli import app as hydro_inflow_similarity
from qe_pricing_descolamento.cli import app as pricing_descolamento
from qe_risk_lab_dessem.cli import app as risk_lab_dessem

app = typer.Typer(
    help="quant-energia-app: pipelines e páginas por funcionalidade.", no_args_is_help=True
)
app.add_typer(forecast_bandeiras, name="forecast_bandeiras")
app.add_typer(risk_lab_dessem, name="risk_lab_dessem")
app.add_typer(pricing_descolamento, name="pricing_descolamento")
app.add_typer(hydro_inflow_similarity, name="hydro_inflow_similarity")


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
