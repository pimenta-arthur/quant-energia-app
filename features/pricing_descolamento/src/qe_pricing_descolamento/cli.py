"""Comandos do descolamento NE e N: `qe pricing_descolamento <etapa>`.

Fontes (todas comuns, ingeridas por qe_core.fontes): deck do NEWAVE (sistema_agrint), DESSEM (PDO_SIST e
PDO_RESTOPER), PLD publicado e limites, em data/entrada/<fonte>/.
"""

from pathlib import Path

import typer

from qe_core.armazenamento import armazenamento, gravar_parquet, ler_parquet
from qe_pricing_descolamento import chaves, ingestao, publicacao, referencias, tratamento

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
def backtest():
    """Backtest da página: modelo vigente em 16 decks com o SE realizado → processed/…/backtest.parquet."""
    from qe_pricing_descolamento import backtest as bt
    from qe_pricing_descolamento import modelo as M

    arm = armazenamento()
    x = bt.backtest(M.Base(arm))
    gravar_parquet(arm, x, chaves.PROC_BACKTEST)
    typer.echo(
        f"backtest {M.MODELO.versao}: {x['deck'].nunique()} decks, {x['mes'].nunique()} meses-alvo, {len(x)} linhas"
    )


@app.command()
def publicar(
    motivo: str | None = typer.Option(None, help="Por que esta rodada (padrão: o deck do NEWAVE)."),
    forcar: bool = typer.Option(
        False, help="Registra rodada mesmo com o deck e o modelo da última (exige --motivo)."
    ),
):
    """Regrava serving/pricing_descolamento/ com o deck vigente e registra uma rodada se o deck ou o modelo mudou."""
    try:
        meta = publicacao.publicar(armazenamento(), motivo, forcar)
    except publicacao.RodadaRepetida as e:
        raise typer.BadParameter(str(e)) from e
    typer.echo(
        f"página publicada: deck {meta['deck']}, modelo {meta['versao']}, dados até {meta['dados_ate']}, "
        f"horizonte {meta['horizonte'][0]} a {meta['horizonte'][1]}"
    )
    typer.echo(
        f"rodada {meta['rodada']} "
        + ("registrada" if meta["nova_rodada"] else "(mesmo deck e modelo da última)")
    )
    typer.echo("lembre de commitar data/serving/pricing_descolamento/")


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
