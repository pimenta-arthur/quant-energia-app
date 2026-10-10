"""Comandos da funcionalidade de bandeiras: `qe bandeiras <etapa>`.

Fluxo de uma rodada (sempre que algum insumo mudar, não necessariamente uma vez por mês):
    ingerir → tratar → status → publicar
"""

from pathlib import Path

import pandas as pd
import typer

from qe_bandeiras import ingestao, insumos, tratamento
from qe_core.armazenamento import armazenamento
from qe_core.periodo import mes, rotulo

app = typer.Typer(help="Projeção de bandeiras tarifárias.", no_args_is_help=True)


def _meses(inicio: str, fim: str | None) -> list[pd.Period]:
    a = mes(inicio)
    return list(pd.period_range(a, mes(fim) if fim else a, freq="M"))


def _insumos(arm, deck: str | None, versao: str | None, ecmwf: str | None) -> insumos.Insumos:
    """Insumos vigentes, com a opção de fixar o deck, a versão do deck ou a emissão do ECMWF."""
    from qe_bandeiras import backtest as bt

    vig = insumos.vigentes(arm, bt.base_oficial(arm))
    d = deck or vig.deck
    v = versao or (insumos.versao_atual(arm, mes(d)) if deck else vig.deck_versao)
    return insumos.Insumos(d, v, ecmwf or vig.ecmwf_emissao)


@app.command()
def ingerir(
    origem: Path = typer.Option(
        ..., help="Pasta com os arquivos brutos no formato de docs/entrada.md."
    ),
    mes_ini: str = typer.Option(..., "--mes", help="Mês AAAA-MM."),
    ate: str | None = typer.Option(None, help="Último mês AAAA-MM, para ingerir um intervalo."),
    sobrescrever: bool = typer.Option(
        False, help="Substitui arquivos já gravados que estejam diferentes."
    ),
):
    """Copia os arquivos brutos da origem para raw/ (imutável; deck e ECMWF versionados)."""
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
    refazer: bool = typer.Option(
        False, help="Trata de novo versões de deck e emissões já tratadas."
    ),
):
    """Transforma raw/ em processed/bandeiras/ (Parquet)."""
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
    from qe_bandeiras import backtest as bt

    r = bt.rodar(armazenamento())
    a = r["referencia"]
    typer.echo(
        f"backtest: {a.deck.nunique()} decks, {len(a)} previsões com bandeira oficial; "
        f"acerto {(a.cor_media == a.cor_oficial).mean():.0%} (M+1 a M+6)"
    )


@app.command()
def status():
    """Insumos vigentes × última rodada publicada: diz se vale publicar uma nova rodada."""
    from qe_bandeiras import publicacao

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
    from qe_bandeiras import backtest as bt
    from qe_bandeiras import projecao

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
    """Projeta e publica uma nova rodada: serving/bandeiras/ + registro da rodada."""
    from qe_bandeiras import backtest as bt
    from qe_bandeiras import projecao, publicacao

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
        "lembre de commitar data/serving/bandeiras/historico_projecoes.json"
    )


@app.command()
def pagina():
    """Refaz os dados da página para a última rodada publicada, sem registrar rodada nova."""
    from qe_bandeiras import backtest as bt
    from qe_bandeiras import publicacao

    dados = publicacao.regravar_pagina(armazenamento(), bt.carregar(armazenamento()))
    typer.echo(f"página regravada para a rodada {dados['rodada']['id']}")


@app.command()
def congelar(
    destino: Path = typer.Option(Path("tests/referencias"), help="Pasta das referências."),
):
    """Grava as referências da versão do modelo em uso (rodar só quando a mudança for intencional)."""
    from qe_bandeiras import modelo, referencias

    arm = armazenamento()
    p = referencias.congelar(arm, destino)
    q = referencias.congelar_tratamento(arm, destino)
    typer.echo(
        f"referências gravadas em {p} (modelo {modelo.MODELO.versao}) e {q} — revise a diferença no git"
    )


@app.command()
def rodar(
    mes_ini: str = typer.Option(..., "--mes", help="Mês dos insumos novos (AAAA-MM)."),
    origem: Path | None = typer.Option(None, help="Se informada, ingere antes de tratar."),
    motivo: str | None = typer.Option(None, help="Motivo da rodada."),
):
    """Sequência completa: [ingerir] → tratar → backtest → publicar (se algum insumo mudou)."""
    if origem:
        ingerir(origem=origem, mes_ini=mes_ini, ate=None, sobrescrever=False)
    tratar(mes_ini=mes_ini, ate=None, refazer=False)
    backtest()
    publicar(motivo=motivo, forcar=False, deck=None, versao=None, ecmwf=None)
