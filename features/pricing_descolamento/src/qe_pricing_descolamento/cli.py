"""Comandos do descolamento NE e N: `qe pricing_descolamento <etapa>`.

Fontes (todas comuns, ingeridas por qe_core.fontes): deck do NEWAVE (sistema_agrint), DESSEM (PDO_SIST e
PDO_RESTOPER), PLD publicado e limites, em data/entrada/<fonte>/.
"""

from pathlib import Path

import typer

from qe_core.armazenamento import armazenamento, ler_parquet
from qe_pricing_descolamento import chaves, ingestao, referencias, tratamento

app = typer.Typer(
    help="Pricing Descolamento: descolamento do PLD do NE e do N em relação ao SE.",
    no_args_is_help=True,
)


def _entrada() -> Path:
    from qe_core.config import configuracao

    return Path(configuracao().dados) / "entrada"


@app.command()
def ingerir(
    sobrescrever: bool = typer.Option(
        False, help="Substitui arquivos de raw/ que estejam diferentes dos novos."
    ),
):
    """Entrada → raw/ (fontes comuns: deck do NEWAVE, DESSEM, PLD publicado e limites)."""
    resultados = ingestao.ingerir_entrada(
        armazenamento(), _entrada(), sobrescrever, aviso=typer.echo
    )
    if not resultados:
        typer.echo("entrada vazia")


@app.command()
def tratar(refazer: bool = typer.Option(False, help="Refaz todas as partições do DESSEM.")):
    """raw/ → processed/pricing_descolamento/: tabelas-base T1 a T5."""
    r = tratamento.tratar(armazenamento(), refazer, aviso=typer.echo)
    for k, v in r.items():
        typer.echo(f"{k}: {v}")


@app.command()
def status():
    """Período de cada tabela-base e dias do DESSEM sem PDO_RESTOPER."""
    arm = armazenamento()
    meses = tratamento.dias_dessem(arm)
    dias = [d for m in meses.values() for d in m]
    sem_re = [d for m in meses.values() for d, a in m.items() if "PDO_RESTOPER.DAT" not in a]
    typer.echo(
        f"DESSEM: {len(dias)} dias com PDO_SIST, de {min(dias):%d/%m/%Y} a {max(dias):%d/%m/%Y}"
    )
    typer.echo(
        f"  sem PDO_RESTOPER: {len(sem_re)}"
        + (
            f" ({', '.join(f'{d:%d/%m/%Y}' for d in sem_re[:5])}{' …' if len(sem_re) > 5 else ''})"
            if sem_re
            else ""
        )
    )
    decks = tratamento.decks_sistema_agrint(arm)
    typer.echo(f"decks do NEWAVE (sistema_agrint): {len(decks)}, {min(decks)} a {max(decks)}")
    if arm.existe(chaves.PROC_BASE):
        b = ler_parquet(arm, chaves.PROC_BASE)
        typer.echo(
            f"base horária: {b.index.min():%d/%m/%Y} a {b.index.max():%d/%m/%Y}, {len(b)} horas"
        )


@app.command()
def congelar():
    """Regrava as referências dos testes (tests/referencias/pricing_descolamento/) com o estado atual."""
    raiz = Path(__file__).resolve().parents[4]
    pasta = referencias.congelar(armazenamento(), raiz / "tests" / "referencias")
    typer.echo(f"referências gravadas em {pasta.relative_to(raiz)}: revise a diferença no git")
