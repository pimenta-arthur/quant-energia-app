"""Comandos da projeção de ENA e dos anos similares: `qe hydro_inflow_similarity <etapa>`.

Fontes (só desta funcionalidade): planilhas do ONS 1931–2024, ENA diária, ERSST v6, índices da NOAA e previsão do
ENSO do CPC, em data/entrada/<fonte>/ (docs/entrada.md).
"""

from pathlib import Path

import typer

from qe_core.armazenamento import armazenamento
from qe_hydro_inflow_similarity import ingestao, tratamento

app = typer.Typer(
    help="Hydro Inflow Similarity: projeção da ENA por subsistema e anos similares ao regime de ENSO.",
    no_args_is_help=True,
)


def _entrada() -> Path:
    from qe_core.config import configuracao

    return Path(configuracao().dados) / "entrada"


@app.command()
def ingerir(
    sobrescrever: bool = typer.Option(
        False, help="Substitui planilhas e páginas do CPC de raw/ que estejam diferentes das novas."
    ),
):
    """Entrada → raw/ (planilhas 1931–2024, ENA diária, ERSST, índices da NOAA, previsão do CPC)."""
    resultados = ingestao.ingerir_entrada(
        armazenamento(), _entrada(), sobrescrever, aviso=typer.echo
    )
    if not resultados:
        typer.echo("entrada vazia")


@app.command()
def tratar():
    """raw/ → processed/hydro_inflow_similarity/: ENA mensal, MLT, índices mensais e ENA diária."""
    for k, v in tratamento.tratar(armazenamento()).items():
        typer.echo(f"{k}: {v}")


@app.command()
def backtest():
    """Backtest fora da amostra (CH, C30, PER, SPLIT, SIM), emissões de 1961 ao fim do último ano completo."""
    from qe_core.armazenamento import gravar_parquet, ler_parquet
    from qe_hydro_inflow_similarity import backtest as bt
    from qe_hydro_inflow_similarity import chaves

    arm = armazenamento()
    ena = ler_parquet(arm, chaves.PROC_ENA)
    ind = ler_parquet(arm, chaves.PROC_INDICES)
    ultimo = ena[ena.completo].data.max()
    ano_fim = ultimo.year if ultimo.month == 12 else ultimo.year - 1
    res = bt.rodar(ena, ind, bt.ANO_INI, ano_fim)
    gravar_parquet(arm, res, chaves.PROC_BACKTEST)
    typer.echo(
        f"backtest: emissões {bt.ANO_INI}–{ano_fim}, {len(res)} linhas, {res.metodo.nunique()} métodos"
    )


@app.command()
def publicar():
    """Registra a rodada do mês (se a ENA e a ERSST do mês estão completas e ela ainda não existe) e regrava
    serving/hydro_inflow_similarity/ (produto, fundamentos, metodologia e clima)."""
    from qe_hydro_inflow_similarity import publicacao

    r = publicacao.publicar(armazenamento())
    typer.echo(f"rodada nova: {r['rodada'] or 'nenhuma'} (última: {r['ultima_rodada']})")
    typer.echo(f"atualização: {r['atualizacao'] or 'sem mês em curso (vale a rodada)'}")
    typer.echo("lembre de commitar data/serving/hydro_inflow_similarity/")


@app.command()
def legado(
    arquivo: Path = typer.Argument(..., help="R10_historico_rodadas.json do pacote de promoção"),
):
    """Grava o registro de rodadas da pesquisa (legado) se o do app ainda não existe."""
    import json

    from qe_core.armazenamento import gravar_json
    from qe_hydro_inflow_similarity import chaves

    arm = armazenamento()
    if arm.existe(chaves.SERVING_REGISTRO):
        raise typer.BadParameter("o registro de rodadas já existe; o legado só entra uma vez")
    rodadas = json.loads(arquivo.read_text(encoding="utf-8"))
    gravar_json(arm, rodadas, chaves.SERVING_REGISTRO)
    typer.echo(f"{len(rodadas)} rodada(s) do legado: {', '.join(r['id'] for r in rodadas)}")


@app.command()
def congelar():
    """Regrava as referências dos testes (tests/referencias/hydro_inflow_similarity/) com o estado atual."""
    from qe_hydro_inflow_similarity import referencias

    raiz = Path(__file__).resolve().parents[4]
    pasta = referencias.congelar(armazenamento(), raiz / "tests" / "referencias")
    typer.echo(f"referências gravadas em {pasta.relative_to(raiz)}: revise a diferença no git")
