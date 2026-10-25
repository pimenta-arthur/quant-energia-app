"""Backtest fora da amostra (pacote de promoção, seção 5, blocos 4 e 5; decisão 4: reimplementar PER, C30 e SIM).

Emissões no fim de cada mês de `ano_ini` a `ano_fim` (pesquisa: 1961–2025), cada uma só com os dados até ela.
Métodos: CH (climatologia de todos os anos), C30 (dos últimos 30), PER (modelo-v1 em cada série), SPLIT (o SE do
modelo-v1, pela soma dos blocos) e SIM (recomposição pelos anos similares, h ≤ 6). Daqui saem:
- o CRPSS do modelo-v1 contra o C30 por antecedência (pesquisa: backtest B1);
- a comparação CH × PER × SIM contra o C30 (h = 1–6) e o desempenho dos similares em três recortes (D025);
- a camada de El Niño forte: o viés da PER em cada evento (pesquisa: vies.py).
"""

import numpy as np
import pandas as pd

from qe_hydro_inflow_similarity import modelo as M
from qe_hydro_inflow_similarity import similares as S

ANO_INI, ANO_FIM = 1961, 2025
H_SIM = 6
COLUNAS = ["metodo", "nome", "t", "h", "obs", "ponto", "p10", "p90", "crps", "n_membros"]


def _linha(metodo, nome, t, h, membros, obs):
    p10, p90 = np.quantile(membros, [0.1, 0.9])
    return (
        metodo,
        nome,
        t,
        h,
        obs,
        float(np.mean(membros)),
        p10,
        p90,
        M.crps_justo(membros, obs),
        len(membros),
    )


def rodar(
    ena: pd.DataFrame, indices: pd.DataFrame, ano_ini=ANO_INI, ano_fim=ANO_FIM, h_max=None
) -> pd.DataFrame:
    """Uma linha por (método, série, emissão, h)."""
    m = M.MODELO
    h_max = h_max or m.h_max
    series = M.montar_series(ena, indices)
    blocos, mlts = M.montar_blocos(ena, indices)
    fontes = {
        **{k: series[k] for k in M.SUBSISTEMAS},
        "SE-sul": blocos["SE-sul"],
        "SE-resto": blocos["SE-resto"],
    }
    linhas = []
    for nome, s in fontes.items():
        t_fim = min((ano_fim - m.ano_base) * 12 + 11, len(s.pct) - 1)
        for t in range((ano_ini - m.ano_base) * 12, t_fim + 1):
            if np.isnan(s.pct[t - 2 : t + 1]).any():
                continue
            sim = S.anos_similares(s.enso3, t, pct=s.pct)
            for h in range(1, h_max + 1):
                if t + h >= len(s.pct) or np.isnan(s.pct[t + h]):
                    continue
                obs = s.pct[t + h]
                metodos = [("C30", M.membros_c30(s, t, h)), ("PER", M.membros_per(s, t, h))]
                if nome in M.SUBSISTEMAS:
                    metodos.insert(0, ("CH", M.membros_ch(s, t, h)))
                if nome == "SE":
                    sul = M.membros_per_por_ano(blocos["SE-sul"], t, h)
                    resto = M.membros_per_por_ano(blocos["SE-resto"], t, h)
                    metodos.append(("SPLIT", M.juntar(sul, resto, mlts, t, h)))
                if sim is not None and h <= H_SIM:
                    metodos.append(("SIM", S.membros_recomposicao(s, t, h, sim[0])))
                linhas += [_linha(met, nome, t, h, x, obs) for met, x in metodos if x is not None]
    res = pd.DataFrame(linhas, columns=COLUNAS)
    res["emissao"] = res.t.map(M.data_da_posicao)
    res["alvo"] = (res.t + res.h).map(M.data_da_posicao)
    return res


# --- habilidade ---------------------------------------------------------------------------------------------


def habilidade(res: pd.DataFrame, metodos, referencia: str, n_boot=1000, semente=0) -> pd.DataFrame:
    """CRPSS = 1 − CRPS/CRPS_ref por (método, série, h), com IC de 90% reamostrando anos de emissão.

    Só os casos em que todos os métodos de `res` e a referência existem (pesquisa: backtest.habilidade)."""
    rng = np.random.default_rng(semente)
    piv = res.pivot_table(index=["nome", "h", "t"], columns="metodo", values="crps").dropna()
    piv["ano"] = piv.index.get_level_values("t") // 12
    linhas = []
    for (nome, h), g in piv.groupby(level=["nome", "h"]):
        por_ano = g.groupby("ano").sum()
        amostras = rng.integers(0, len(por_ano), size=(n_boot, len(por_ano)))
        for metodo in metodos:
            a, b = por_ano[metodo].to_numpy(), por_ano[referencia].to_numpy()
            boot = 1 - a[amostras].sum(axis=1) / b[amostras].sum(axis=1)
            linhas.append(
                (metodo, nome, h, 1 - a.sum() / b.sum(), *np.quantile(boot, [0.05, 0.95]), len(g))
            )
    return pd.DataFrame(linhas, columns=["metodo", "nome", "h", "crpss", "ic05", "ic95", "n"])


def habilidade_agregada(
    res: pd.DataFrame,
    metodo: str,
    referencia: str,
    n_boot=1000,
    semente=0,
    grupos: dict | None = None,
) -> pd.DataFrame:
    """CRPSS somando todos os casos de `res`, por série; IC reamostrando anos de emissão ou os `grupos` dados
    (posição → grupo, ex.: eventos de ENSO). Traz também a cobertura e a largura médias da faixa p10–p90."""
    rng = np.random.default_rng(semente)
    piv = res.pivot_table(index=["nome", "t", "h"], columns="metodo", values="crps")[
        [metodo, referencia]
    ].dropna()
    t_idx = pd.Series(piv.index.get_level_values("t"))
    piv["ano"] = (t_idx.map(grupos) if grupos is not None else t_idx // 12).to_numpy()
    faixa = res[res.metodo == metodo].assign(
        dentro=lambda d: (d.obs >= d.p10) & (d.obs <= d.p90), largura=lambda d: d.p90 - d.p10
    )
    linhas = []
    for nome, g in piv.groupby(level="nome"):
        por_ano = g.groupby("ano").sum()
        a, b = por_ano[metodo].to_numpy(), por_ano[referencia].to_numpy()
        amostras = rng.integers(0, len(a), size=(n_boot, len(a)))
        boot = 1 - a[amostras].sum(axis=1) / b[amostras].sum(axis=1)
        f = faixa[faixa.nome == nome]
        linhas.append(
            (
                nome,
                1 - a.sum() / b.sum(),
                *np.quantile(boot, [0.05, 0.95]),
                len(g),
                f.dentro.mean() * 100,
                f.largura.mean(),
            )
        )
    return pd.DataFrame(
        linhas, columns=["nome", "crpss", "ic05", "ic95", "n", "cobertura_p10_p90", "largura"]
    )


def eventos_de_regime(enso3: np.ndarray, limiar: float = M.MODELO.limiar_regime) -> dict[int, int]:
    """Posição → id do evento (início da sequência contínua de meses com |N| ≥ limiar)."""
    eventos, inicio = {}, None
    for t, v in enumerate(enso3):
        if not np.isnan(v) and abs(v) >= limiar:
            inicio = t if inicio is None else inicio
            eventos[t] = inicio
        else:
            inicio = None
    return eventos


def skill_modelo(res: pd.DataFrame) -> pd.DataFrame:
    """CRPSS do modelo-v1 (PER em S, NE e N; PER no SE agregado, como no B1) e da CH contra o C30, por h."""
    sub = res[res.nome.isin(M.SUBSISTEMAS) & res.metodo.isin(["CH", "C30", "PER"])]
    return habilidade(sub, ["CH", "PER"], "C30")


def desempenho_comparado(res: pd.DataFrame) -> pd.DataFrame:
    """CH, PER e SIM contra o C30, h = 1–6, somando os casos (página de metodologia)."""
    r = res[
        res.nome.isin(M.SUBSISTEMAS)
        & res.metodo.isin(["CH", "C30", "PER", "SIM"])
        & (res.h <= H_SIM)
    ]
    return pd.concat(
        [
            habilidade_agregada(r[r.metodo.isin([x, "C30"])], x, "C30").assign(metodo=x)
            for x in ["CH", "PER", "SIM"]
        ],
        ignore_index=True,
    )


def desempenho_similares(res: pd.DataFrame, enso3: np.ndarray) -> pd.DataFrame:
    """SIM contra C30 e PER, h = 1–6, em todos os anos, em El Niño (N ≥ 0,5) e em El Niño forte (N ≥ +1,5, IC por
    evento; D025)."""
    m = M.MODELO
    r = res[res.metodo.isin(["C30", "PER", "SIM"]) & (res.h <= H_SIM)]
    recortes = [
        ("todos", lambda t: True, None),
        ("El Niño (N≥0,5)", lambda t: enso3[t] >= m.fase, None),
        ("El Niño forte", lambda t: enso3[t] >= m.limiar_regime, eventos_de_regime(enso3)),
    ]
    saida = []
    for recorte, filtro, grupos in recortes:
        x = r[r.t.map(filtro)]
        for ref in ["C30", "PER"]:
            saida.append(
                habilidade_agregada(
                    x[x.metodo.isin(["SIM", ref])], "SIM", ref, grupos=grupos
                ).assign(recorte=recorte, ref=ref)
            )
    return pd.concat(saida, ignore_index=True)


# --- camada de El Niño forte (pesquisa: vies.py) -------------------------------------------------------------

NOMES_VIES = ["S", "SE-sul", "SE-resto", "SE", "N", "NE"]


def tabela_vies(res: pd.DataFrame, enso3: np.ndarray) -> pd.DataFrame:
    """Viés da PER (observado − previsto, h = 1–6) por evento de ENSO forte ('AAAA EN'/'AAAA LN') e série.
    SE pelo SPLIT; S, N, NE e os blocos pela PER."""
    eventos = eventos_de_regime(enso3)
    per = res[(res.metodo == "PER") & res.nome.isin(["S", "N", "NE", "SE-sul", "SE-resto"])]
    split = res[res.metodo == "SPLIT"]
    r = pd.concat([per, split])
    r = r[(r.h <= H_SIM) & r.t.isin(eventos)].copy()
    r["evento"] = r.t.map(eventos).map(
        lambda p: f"{M.data_da_posicao(p):%Y}" + (" EN" if enso3[p] > 0 else " LN")
    )
    r["vies"] = r.obs - r.ponto
    return r.pivot_table(index="evento", columns="nome", values="vies")[NOMES_VIES]


def resumo_el_nino(tabela: pd.DataFrame) -> pd.DataFrame:
    """Por série: média, mínimo, máximo e quantos El Niños tiveram viés positivo."""
    en = tabela[tabela.index.str.endswith("EN")]
    return pd.DataFrame(
        {
            "media": en.mean(),
            "minimo": en.min(),
            "maximo": en.max(),
            "positivos": (en > 0).sum(),
            "eventos": en.notna().sum(),
        }
    )


def direcao(linha) -> str:
    """'para cima' / 'para baixo' quando no máximo um evento discorda; senão 'sem direção'."""
    if linha.positivos >= linha.eventos - 1:
        return "para cima"
    if linha.positivos <= 1:
        return "para baixo"
    return "sem direção"
