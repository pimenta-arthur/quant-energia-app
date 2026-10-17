"""Comandos da funcionalidade de bandeiras: `qe forecast_bandeiras <etapa>`.

Dia a dia (sempre que algum insumo mudar, não necessariamente uma vez por mês):
    arquivos baixados em data/entrada/<fonte>/ → `qe forecast_bandeiras atualizar` → `qe forecast_bandeiras publicar`
`atualizar` = ingerir → tratar (meses afetados) → backtest → status → projetar (prévia).
"""

from pathlib import Path

import pandas as pd
import typer

from qe_core.armazenamento import armazenamento
from qe_core.periodo import mes, rotulo
from qe_forecast_bandeiras import ingestao, insumos, tratamento

app = typer.Typer(help="Projeção de bandeiras tarifárias.", no_args_is_help=True)


def _meses(inicio: str, fim: str | None) -> list[pd.Period]:
    a = mes(inicio)
    return list(pd.period_range(a, mes(fim) if fim else a, freq="M"))


def _insumos(arm, deck: str | None, versao: str | None, ecmwf: str | None) -> insumos.Insumos:
    """Insumos vigentes, com a opção de fixar o deck, a versão do deck ou a emissão do ECMWF."""
    from qe_forecast_bandeiras import backtest as bt

    vig = insumos.vigentes(arm, bt.base_oficial(arm))
    d = deck or vig.deck
    v = versao or (insumos.versao_atual(arm, mes(d)) if deck else vig.deck_versao)
    return insumos.Insumos(d, v, ecmwf or vig.ecmwf_emissao)


def _entrada() -> Path:
    from qe_core.config import configuracao

    return Path(configuracao().dados) / "entrada"


def _ingerir(arm, sobrescrever: bool) -> list[ingestao.Resultado]:
    entrada = _entrada()
    resultados = ingestao.ingerir_entrada(arm, entrada, sobrescrever)
    if not resultados:
        typer.echo(f"entrada vazia ({entrada}/<fonte>/)")
    for r in resultados:
        typer.echo(f"{r.fonte}/{r.origem}: {r.mensagem}")
    return resultados


@app.command()
def ingerir(
    sobrescrever: bool = typer.Option(
        False, help="Substitui arquivos de raw/ que estejam diferentes dos novos."
    ),
):
    """Leva o que estiver em data/entrada/<fonte>/ para raw/ e apaga os originais conferidos."""
    _ingerir(armazenamento(), sobrescrever)


@app.command()
def tratar(
    mes_ini: str = typer.Option(..., "--mes", help="Mês AAAA-MM."),
    ate: str | None = typer.Option(None, help="Último mês AAAA-MM, para tratar um intervalo."),
    refazer: bool = typer.Option(
        False, help="Trata de novo versões de deck e emissões já tratadas."
    ),
):
    """Transforma raw/ em processed/forecast_bandeiras/ (Parquet)."""
    arm = armazenamento()
    for m in _meses(mes_ini, ate):
        r = tratamento.tratar_mes(arm, m, refazer)
        typer.echo(
            f"{rotulo(m)}: " + " · ".join(f"{k} {v}" for k, v in r.items() if k != "historico")
        )
    typer.echo(f"histórico ANEEL: {r['historico']}")


@app.command()
def backtest():
    """Refaz o backtest sem vazamento (pareamento mensal deck × ECMWF): σ e rodadas passadas."""
    from qe_forecast_bandeiras import backtest as bt

    r = bt.rodar(armazenamento())
    a = r["referencia"]
    typer.echo(
        f"backtest: {a.deck.nunique()} decks, {len(a)} previsões com bandeira oficial; "
        f"acerto {(a.cor_media == a.cor_oficial).mean():.0%} (M+1 a M+6)"
    )


@app.command()
def status():
    """Insumos vigentes × última rodada publicada: diz se vale publicar uma nova rodada."""
    from qe_forecast_bandeiras import publicacao

    arm = armazenamento()
    vig = _insumos(arm, None, None, None)
    typer.echo(
        f"insumos vigentes: deck {vig.deck} (versão {vig.deck_versao}) · ECMWF emissão {vig.ecmwf_emissao}"
    )
    ultima = publicacao.ultima_rodada(publicacao.carregar_registro(arm))
    if not ultima:
        typer.echo("nenhuma rodada publicada ainda → publicar")
        return
    rid, e = ultima
    typer.echo(f"última rodada: {rid} · {e['motivo']}")
    mudou = [
        f"{k}: {e['insumos'].get(k)} → {v}"
        for k, v in vig.como_dict().items()
        if e["insumos"].get(k) != v
    ]
    if mudou:
        typer.echo("mudaram: " + "; ".join(mudou) + " → recomenda publicar nova rodada")
    else:
        typer.echo("nada mudou desde a última rodada")


@app.command()
def projetar(
    deck: str | None = typer.Option(None, help="Fixa o mês do deck (AAAA-MM). Padrão: vigente."),
    versao: str | None = typer.Option(None, help="Fixa a versão do deck."),
    ecmwf: str | None = typer.Option(None, help="Fixa a emissão do ECMWF (AAAA-MM-DD)."),
):
    """Prévia da projeção com os insumos vigentes (ou fixados), sem publicar."""
    from qe_forecast_bandeiras import backtest as bt
    from qe_forecast_bandeiras import projecao

    arm = armazenamento()
    ins = _insumos(arm, deck, versao, ecmwf)
    typer.echo(f"insumos: deck {ins.deck} (v={ins.deck_versao}) · ECMWF {ins.ecmwf_emissao}")
    cen = projecao.projetar(arm, ins, bt.carregar(arm)["referencia"])
    for r in cen.itertuples():
        typer.echo(f"{r.alvo} (M+{r.h}): {r.cor_esp} · seco {r.cor_li} · úmido {r.cor_ls}")


@app.command()
def publicar(
    motivo: str | None = typer.Option(
        None, help="Por que esta rodada (ex.: 'emissão extra do ECMWF')."
    ),
    forcar: bool = typer.Option(
        False, help="Publica mesmo sem mudança de insumo (exige --motivo)."
    ),
    deck: str | None = typer.Option(None, help="Fixa o mês do deck (AAAA-MM). Padrão: vigente."),
    versao: str | None = typer.Option(None, help="Fixa a versão do deck."),
    ecmwf: str | None = typer.Option(None, help="Fixa a emissão do ECMWF (AAAA-MM-DD)."),
):
    """Projeta e publica uma nova rodada: serving/forecast_bandeiras/ + registro da rodada."""
    from qe_forecast_bandeiras import backtest as bt
    from qe_forecast_bandeiras import projecao, publicacao

    arm = armazenamento()
    ins = _insumos(arm, deck, versao, ecmwf)
    historico = bt.carregar(arm)
    cen = projecao.projetar(arm, ins, historico["referencia"])
    try:
        dados = publicacao.publicar(arm, ins, cen, historico, motivo, forcar)
    except publicacao.RodadaRepetida as e:
        typer.echo(f"não publicado: {e}")
        raise typer.Exit(1) from e
    typer.echo(
        f"publicada a rodada {dados['rodada']['id']} (deck {ins.deck}, ECMWF {ins.ecmwf_emissao}); "
        "lembre de commitar data/serving/forecast_bandeiras/"
    )


@app.command()
def pagina():
    """Refaz os dados da página para a última rodada publicada, sem registrar rodada nova."""
    from qe_forecast_bandeiras import backtest as bt
    from qe_forecast_bandeiras import publicacao

    dados = publicacao.regravar_pagina(armazenamento(), bt.carregar(armazenamento()))
    typer.echo(f"página regravada para a rodada {dados['rodada']['id']}")


@app.command()
def exportar(
    destino: Path = typer.Option(
        ..., help="Pasta do site estático (ex.: ../forecast-bandeiras-page)."
    ),
):
    """Grava a página da última rodada como site estático (GitHub Pages), com caminhos relativos."""
    from qe_forecast_bandeiras import exportacao

    escritos = exportacao.exportar(armazenamento(), destino)
    typer.echo(f"{len(escritos)} arquivos em {destino}: " + ", ".join(escritos))


@app.command()
def congelar(
    destino: Path = typer.Option(
        Path("tests/referencias/forecast_bandeiras"), help="Pasta das referências."
    ),
):
    """Grava as referências da versão do modelo em uso (rodar só quando a mudança for intencional)."""
    from qe_forecast_bandeiras import modelo, referencias

    arm = armazenamento()
    p = referencias.congelar(arm, destino)
    q = referencias.congelar_tratamento(arm, destino)
    typer.echo(
        f"referências gravadas em {p} (modelo {modelo.MODELO.versao}) e {q} — revise a diferença no git"
    )


@app.command()
def atualizar(
    sobrescrever: bool = typer.Option(
        False, help="Substitui arquivos de raw/ que estejam diferentes dos novos."
    ),
):
    """Entrada → raw/ → tratamento dos meses afetados → backtest → status e prévia. Não publica."""
    arm = armazenamento()
    novos = [r for r in _ingerir(arm, sobrescrever) if r.novo]
    if not novos:
        typer.echo("nada novo: projeção inalterada")
        return
    for m in sorted(set().union(*(r.meses for r in novos))):
        r = tratamento.tratar_mes(arm, m)
        typer.echo(
            f"tratado {rotulo(m)}: "
            + " · ".join(f"{k} {v}" for k, v in r.items() if k != "historico")
        )
    if any(r.fonte == "aneel_bandeiras" for r in novos):
        typer.echo(f"histórico ANEEL: {tratamento.tratar_historico(arm)}")
    backtest()
    try:
        status()
        projetar(deck=None, versao=None, ecmwf=None)
    except ValueError as e:
        typer.echo(f"sem prévia: {e}")
        return
    typer.echo('para publicar: uv run qe forecast_bandeiras publicar --motivo "<o que mudou>"')
