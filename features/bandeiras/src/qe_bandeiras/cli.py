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
def backtest():
    """Refaz o backtest sem vazamento de todos os decks com rodada do ECMWF (σ e rodadas passadas)."""
    from qe_bandeiras import backtest as bt

    r = bt.rodar(armazenamento())
    a = r["referencia"]
    typer.echo(
        f"backtest: {a.deck.nunique()} decks, {len(a)} previsões com bandeira oficial; "
        f"acerto {(a.cor_media == a.cor_oficial).mean():.0%} (M+1 a M+6)"
    )


@app.command()
def projetar(mes_ini: str = typer.Option(..., "--mes", help="Mês do deck AAAA-MM.")):
    """Projeção da rodada (deck do NEWAVE + ECMWF do mês): M+1 a M+6, três cenários e probabilidade."""
    from qe_bandeiras import backtest as bt
    from qe_bandeiras import projecao

    arm = armazenamento()
    cen = projecao.projetar(arm, mes(mes_ini), bt.carregar(arm)["referencia"])
    for r in cen.itertuples():
        typer.echo(f"{r.alvo} (M+{r.h}): {r.cor_esp} · seco {r.cor_li} · úmido {r.cor_ls}")


@app.command()
def publicar(mes_ini: str = typer.Option(..., "--mes", help="Mês do deck AAAA-MM.")):
    """Gera os dados da página (serving/bandeiras) e registra a rodada publicada."""
    from qe_bandeiras import backtest as bt
    from qe_bandeiras import chaves, publicacao
    from qe_core.armazenamento import ler_parquet

    arm = armazenamento()
    m = mes(mes_ini)
    cen = ler_parquet(arm, chaves.proc_projecao(m))
    cen["deck"] = pd.PeriodIndex(cen.deck, freq="M")
    cen["alvo"] = pd.PeriodIndex(cen.alvo, freq="M")
    dados = publicacao.publicar(arm, m, cen, bt.carregar(arm))
    typer.echo(
        f"publicado: {chaves.SERVING_DADOS} (rodada {dados['deck']}, {len(dados['projecoes'])} meses)"
    )


@app.command()
def rodar(
    mes_ini: str = typer.Option(..., "--mes", help="Mês do deck AAAA-MM."),
    origem: Path | None = typer.Option(None, help="Se informada, ingere antes de tratar."),
):
    """Sequência completa do mês: [ingerir] → tratar → backtest → projetar → publicar."""
    if origem:
        ingerir(origem=origem, mes_ini=mes_ini, ate=None, sobrescrever=False)
    tratar(mes_ini=mes_ini, ate=None)
    backtest()
    projetar(mes_ini=mes_ini)
    publicar(mes_ini=mes_ini)
