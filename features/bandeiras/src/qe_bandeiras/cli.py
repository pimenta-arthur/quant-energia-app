"""Comandos da funcionalidade de bandeiras: `qe bandeiras <etapa>`."""

from pathlib import Path

import pandas as pd
import typer

from qe_bandeiras import ingestao, tratamento
from qe_core.armazenamento import armazenamento
from qe_core.periodo import mes, rotulo

app = typer.Typer(help="Projeção de bandeiras tarifárias.", no_args_is_help=True)


def _meses(inicio: str, fim: str | None) -> list[pd.Period]:
    a = mes(inicio)
    return list(pd.period_range(a, mes(fim) if fim else a, freq="M"))


@app.command()
def ingerir(
    origem: Path = typer.Option(
        ..., help="Pasta com os arquivos brutos (layout data/raw do analytics)."
    ),
    mes_ini: str = typer.Option(..., "--mes", help="Mês AAAA-MM."),
    ate: str | None = typer.Option(None, help="Último mês AAAA-MM, para ingerir um intervalo."),
    sobrescrever: bool = typer.Option(
        False, help="Substitui arquivos já gravados que estejam diferentes."
    ),
):
    """Copia os arquivos brutos da origem para raw/ (imutável)."""
    arm = armazenamento()
    contagem: dict[str, int] = {}
    for m in _meses(mes_ini, ate):
        for item in ingestao.ingerir_mes(arm, origem, m, sobrescrever):
            contagem[item.situacao] = contagem.get(item.situacao, 0) + 1
            if item.situacao in ("divergente (mantido)", "sobrescrito"):
                typer.echo(f"  {item.situacao}: {item.chave}")
        typer.echo(f"{rotulo(m)}: ingerido")
    h = ingestao.ingerir_historico(arm, origem)
    typer.echo(f"histórico ANEEL: {h.situacao}")
    typer.echo("arquivos: " + ", ".join(f"{k} {v}" for k, v in sorted(contagem.items())))


@app.command()
def tratar(
    mes_ini: str = typer.Option(..., "--mes", help="Mês AAAA-MM."),
    ate: str | None = typer.Option(None, help="Último mês AAAA-MM, para tratar um intervalo."),
):
    """Transforma raw/ em processed/bandeiras/ (Parquet)."""
    arm = armazenamento()
    for m in _meses(mes_ini, ate):
        r = tratamento.tratar_mes(arm, m)
        typer.echo(
            f"{rotulo(m)}: " + " · ".join(f"{k} {v}" for k, v in r.items() if k != "historico")
        )
    typer.echo(f"histórico ANEEL: {r['historico']}")


@app.command()
def projetar(mes_ini: str = typer.Option(..., "--mes", help="Mês do deck AAAA-MM.")):
    """Projeção do deck + ECMWF do mês (próxima etapa da migração)."""
    typer.echo("projetar: em construção (fase 2 — projeção e publicação)")
    raise typer.Exit(1)


@app.command()
def publicar(mes_ini: str = typer.Option(..., "--mes", help="Mês do deck AAAA-MM.")):
    """Gera o JSON da página e registra a rodada (próxima etapa da migração)."""
    typer.echo("publicar: em construção (fase 2 — projeção e publicação)")
    raise typer.Exit(1)
