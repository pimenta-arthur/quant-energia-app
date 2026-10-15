"""Comandos da funcionalidade do PLD horário: `qe risk_lab_dessem <etapa>`.

Dia a dia (o deck do DESSEM sai todo dia; o DECOMP toda semana; o PLD publicado é republicado):
    arquivos baixados em data/entrada/<fonte>/ → `qe risk_lab_dessem atualizar` → `qe risk_lab_dessem publicar`
`atualizar` = ingerir → tratar (meses do DESSEM que mudaram + tabelas-base) → status. Não publica.
O acompanhamento é descritivo: `publicar` regrava os dados da página, sem registro de rodada.
"""

from pathlib import Path

import typer

from qe_core.armazenamento import armazenamento
from qe_risk_lab_dessem import ingestao, tratamento

app = typer.Typer(
    help="Risk Lab DESSEM: PLD horário, acompanhamento do DESSEM sobre o DECOMP.",
    no_args_is_help=True,
)


def _entrada() -> Path:
    from qe_core.config import configuracao

    return Path(configuracao().dados) / "entrada"


def _ingerir(arm, sobrescrever: bool):
    entrada = _entrada()
    resultados = ingestao.ingerir_entrada(arm, entrada, sobrescrever, aviso=typer.echo)
    if not resultados:
        typer.echo(f"entrada vazia ({entrada}/<fonte>/ do PLD horário)")
    return resultados


def _data(d) -> str:
    return f"{d:%d/%m/%Y}"


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
    refazer: bool = typer.Option(
        False, help="Relê todos os decks do DESSEM, não só os que mudaram."
    ),
):
    """raw/ → processed/risk_lab_dessem/: meses do DESSEM que mudaram e as tabelas-base (T1 a T5)."""
    arm = armazenamento()
    feitos = tratamento.tratar_dessem(arm, refazer, aviso=typer.echo)
    if not feitos:
        typer.echo("DESSEM: nenhum mês mudou")
    r = tratamento.tratar_tabelas(arm)
    for a in r["avisos"]:
        typer.echo(f"aviso: {a}")
    typer.echo(f"tabelas-base refeitas ({r['semanas_decomp']} semanas do DECOMP)")
    status()


@app.command()
def status():
    """Estado da base: último deck, último PLD publicado, dias calculados e lacunas."""
    import pandas as pd

    from qe_core.armazenamento import ler_parquet
    from qe_risk_lab_dessem import chaves

    arm = armazenamento()
    inv = tratamento.inventario_dessem(arm)
    if not inv.completos:
        typer.echo("nenhum deck do DESSEM em raw/")
        return
    dias = sorted(inv.completos)
    typer.echo(f"DESSEM: {len(dias)} dias, de {_data(dias[0])} a {_data(dias[-1])}")
    faltando = sorted(set(pd.date_range(dias[0], dias[-1]).date) - set(dias))
    if faltando:
        mostra = ", ".join(_data(d) for d in faltando[:5]) + (" …" if len(faltando) > 5 else "")
        typer.echo(f"  dias sem deck: {len(faltando)} ({mostra})")
    for d, f in sorted(inv.incompletos.items()):
        typer.echo(f"  {_data(d)} incompleto (falta {', '.join(f)}): aguardando a outra metade")
    if not arm.existe(chaves.PROC_PLD):
        typer.echo("tabelas-base ainda não geradas: rode `qe risk_lab_dessem tratar`")
        return
    t1 = ler_parquet(arm, chaves.PROC_PLD)
    pub = t1.loc[t1["origem"] == "publicado", "data"].max()
    calc = sorted(t1.loc[t1["origem"] != "publicado", "data"].unique())
    typer.echo(f"PLD publicado até {_data(pub)}")
    if calc:
        typer.echo(
            f"  calculado do deck (publicação pendente): {_data(calc[0])} a {_data(calc[-1])}"
        )
    tratado = pd.to_datetime(t1["data"]).max().date()
    if tratado < dias[-1]:
        typer.echo(f"  tabelas-base até {_data(tratado)}: rode `qe risk_lab_dessem tratar`")
    h = ler_parquet(arm, chaves.PROC_HORARIO)
    sem = h[h["decomp_pld"].isna()]
    if len(sem):
        meses = sorted(sem["mes"].unique())
        typer.echo(f"  horas sem DECOMP vigente: {len(sem)} (meses {', '.join(meses)})")


@app.command()
def conferir(
    dias: int = typer.Option(30, help="Últimos dias publicados com deck."),
):
    """Recalcula do deck o PLD dos últimos dias publicados e compara com o da CCEE (tolerância R$ 0,01)."""
    arm = armazenamento()
    sist = tratamento.ler_dessem(arm, "sist", ["data", "periodo", "submercado", "cmo"])
    dif, datas = tratamento.conferir_calculo(
        tratamento.pld_publicado(arm), sist, tratamento.limites(arm), dias
    )
    typer.echo(
        f"{len(datas)} dias ({_data(datas[0])} a {_data(datas[-1])}), {len(dif)} horas: "
        f"diferença máxima R$ {dif.max():.2f}; acima de R$ 0,01: {(dif > 0.0100001).sum()} horas"
    )
    if (dif > 0.0100001).any():
        raise typer.Exit(1)


@app.command()
def atualizar(
    sobrescrever: bool = typer.Option(
        False, help="Substitui arquivos de raw/ que estejam diferentes dos novos."
    ),
):
    """Entrada → raw/ → tratamento do que mudou → status. Não publica."""
    arm = armazenamento()
    novos = [r for r in _ingerir(arm, sobrescrever) if r.novo]
    if not novos:
        typer.echo("nada novo: base inalterada")
        return
    tratar(refazer=False)
    typer.echo("para publicar a página: uv run qe risk_lab_dessem publicar")


@app.command()
def publicar():
    """Regrava os dados da página (serving/risk_lab_dessem/) com a base atual. Sem registro de rodada."""
    from qe_risk_lab_dessem import publicacao

    e = publicacao.publicar(armazenamento())
    calc = e["calculados"]
    typer.echo(
        f"página do PLD horário publicada: dados até {e['ultimo_deck']}, PLD publicado até "
        f"{e['ultimo_publicado']}"
        + (f" (calculado do deck de {calc[0]} a {calc[1]})" if calc else "")
    )


@app.command()
def congelar(
    destino: Path = typer.Option(Path("tests/referencias"), help="Pasta das referências."),
):
    """Grava as referências dos períodos fechados (rodar só quando a mudança for intencional)."""
    from qe_risk_lab_dessem import referencias

    p = referencias.congelar(armazenamento(), destino)
    typer.echo(f"referências gravadas em {p}: revise a diferença no git")
