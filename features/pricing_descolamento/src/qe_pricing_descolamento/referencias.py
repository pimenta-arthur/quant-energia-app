"""Referências congeladas do descolamento (tests/referencias/pricing_descolamento/).

Na migração (2026-10-19), as saídas do app foram conferidas contra o pacote de promoção da pesquisa
(pricing-descolamento-analytics, tag promocao-quant-v1, reports/promocao/2026-10/; teste opt-in
tests/test_pricing_descolamento_paridade.py) e congeladas aqui. Só entram períodos fechados, que não mudam com dados
novos: leitores em três dias (um de cada formato do PDO_RESTOPER) e em dois decks, o PLD mensal até set/2026, as
tabelas dos decks até out/2026 e o PLD horário e a base horária nos meses desses três dias (a base inteira foi
conferida na migração; congelada inteira, ocuparia 14 MB no git). Do modelo (bloco 2): o treino no deck de out/2026
(dados até ago/2026) e os cenários com SE plano de R$ 200 até dez/2030, com coeficientes e faixas por período; e o
backtest da página inteiro (decks até jul/2026, meses-alvo até set/2026); e o acompanhamento do nível da hidráulica
do NE (usado × realizado, D039) dos meses fechados, até set/2026. Regerar só quando a mudança for intencional:
`uv run qe pricing_descolamento congelar` e revisar a diferença no git.
"""

import datetime as dt
import json
from pathlib import Path

import pandas as pd

from qe_core.armazenamento import Armazenamento, ler_parquet
from qe_core.leitores import dessem, newave
from qe_pricing_descolamento import chaves, publicacao, tratamento
from qe_pricing_descolamento import modelo as M

PASTA = "pricing_descolamento"
FIM = pd.Timestamp("2026-09-30 23:00")  # último mês fechado
ULTIMO_DECK = "202610"
# um dia de cada formato das linhas do PDO_RESTOPER (18, 19 e 20 campos)
DIAS_LEITORES = [dt.date(2023, 3, 15), dt.date(2025, 3, 15), dt.date(2026, 9, 15)]
DECKS_LEITORES = ["202401", "202610"]
MESES = [f"{d:%Y-%m}" for d in DIAS_LEITORES]  # meses do PLD horário e da base horária congelados
DECK_MODELO, FIM_MODELO, SE_REF = "2026-10", "2030-12", 200.0  # rodada de referência do modelo


def calcular(arm: Armazenamento) -> dict[str, pd.DataFrame]:
    """Tabelas de referência a partir do estado atual de raw/ e processed/."""
    sist, re_ = [], []
    for d in DIAS_LEITORES:
        sist.append(
            dessem.ler_pdo_sist(arm.caminho_local(chaves.raw_dessem(d, "PDO_SIST.DAT.gz")), d)
        )
        re_.append(
            dessem.ler_re_inte(arm.caminho_local(chaves.raw_dessem(d, "PDO_RESTOPER.DAT.gz")), d)
        )
    out = {
        "leitor_pdo_sist": pd.concat(sist, ignore_index=True),
        "leitor_re_inte": pd.concat(re_, ignore_index=True),
    }
    pastas = tratamento.decks_sistema_agrint(arm)
    for deck in DECKS_LEITORES:
        s = newave.ler_sistema(arm.caminho_local(f"{pastas[deck]}/sistema.dat"))
        out[f"sistema_mercado_{deck}"] = s["mercado"]
        out[f"sistema_nao_simuladas_{deck}"] = s["nao_simuladas"]
        out[f"agrint_{deck}"] = newave.ler_agrint(arm.caminho_local(f"{pastas[deck]}/agrint.dat"))
    horario = ler_parquet(arm, chaves.PROC_PLD_HORARIO)
    out["pld_horario"] = horario[horario.index.strftime("%Y-%m").isin(MESES)]
    mensal = ler_parquet(arm, chaves.PROC_PLD_MENSAL)
    out["pld_mensal"] = mensal[mensal.index <= str(FIM.to_period("M"))]
    for k, c in chaves.PROC_DECK.items():
        t = ler_parquet(arm, c)
        out[f"deck_{k}"] = t[t["deck"] <= ULTIMO_DECK].reset_index(drop=True)
    base = ler_parquet(arm, chaves.PROC_BASE)
    out["base_horaria"] = base[base.index.strftime("%Y-%m").isin(MESES)]
    return out | modelo_ref(arm)


def tabela_modelo(mod: dict) -> pd.DataFrame:
    """O modelo treinado numa tabela longa (parâmetro, chave, valor)."""
    lin = [("mu", f, v) for f, v in mod["mu"].items()] + [
        ("sd", f, v) for f, v in mod["sd"].items()
    ]
    lin += [("vies_car", "NE", mod["vies_car"]), ("vies_car", "N", mod["vies_car_n"])]
    lin += [("perfil_se", f"{m:02d}-{h:02d}", v) for (m, h), v in mod["perfil_se"].items()]
    for reg in M.REGIMES:
        for s in M.SUBS:
            c = mod[("p", reg, s)]
            coef = [] if c is None else [*c.coef_[0], c.intercept_[0]]
            lin += [(f"p_trava_{reg}_{s}", str(i), v) for i, v in enumerate(coef)]
            lin.append((f"k_reserva_{reg}", s, mod[("k", reg, s)]))
        for s in M.SUBS:
            for (ano, r), v in sorted(mod[("kano", s)].items()):
                if r == reg:
                    lin += [
                        (f"k_ano_{s}", f"{ano}-{r}", v["k"]),
                        (f"folga_ano_{s}", f"{ano}-{r}", v["folga_media"]),
                    ]
                    lin.append((f"horas_ano_{s}", f"{ano}-{r}", float(v["horas"])))
    return pd.DataFrame(lin, columns=["parametro", "chave", "valor"])


def modelo_ref(arm: Armazenamento) -> dict[str, pd.DataFrame]:
    b, d = M.Base(arm), pd.Period(DECK_MODELO, "M")
    mod = M.treinar(b, d)
    meses = list(pd.period_range(d + 1, pd.Period(FIM_MODELO, "M"), freq="M"))
    cen = pd.concat([M.prever(b, d, m, SE_REF, mod) for m in meses], ignore_index=True)
    x = M.projecao(b, d, pd.Series(SE_REF, index=meses), mod)
    faixas = pd.concat(
        [
            M.faixa_periodos(x, p).reset_index().rename(columns={p: "periodo"})
            for p in ("trimestre", "semestre", "ano")
        ],
        ignore_index=True,
    )
    bt = ler_parquet(arm, chaves.PROC_BACKTEST).assign(mes=lambda d: d["mes"].astype(str))
    hne = pd.DataFrame(publicacao.acompanhamento_hidr_ne(b)["linhas"])
    return {
        "hidr_ne": hne[hne["mes"] <= str(FIM.to_period("M"))].reset_index(drop=True),
        "modelo": tabela_modelo(mod),
        "modelo_cenarios": cen,
        "modelo_faixas": faixas,
        "backtest": bt,
    }


def congelar(arm: Armazenamento, destino: Path) -> Path:
    pasta = Path(destino) / PASTA
    pasta.mkdir(parents=True, exist_ok=True)
    for nome, df in calcular(arm).items():
        df.to_parquet(pasta / f"{nome}.parquet")
    (pasta / "manifesto.json").write_text(
        json.dumps(
            {
                "fim": str(FIM),
                "ultimo_deck": ULTIMO_DECK,
                "dias_leitores": [str(d) for d in DIAS_LEITORES],
                "decks_leitores": DECKS_LEITORES,
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    return pasta


def ler_congeladas(destino: Path) -> dict[str, pd.DataFrame]:
    return {p.stem: pd.read_parquet(p) for p in sorted((Path(destino) / PASTA).glob("*.parquet"))}
