"""Anos similares ao regime de ENSO e recomposição da ENA (pesquisa: seção 22, D020; pacote, seção 5, bloco 4).

Estado na emissão t: N = Niño 3.4 relativo de 3 meses e ΔN = N − N de 3 meses antes. Candidatos: o mesmo mês em
anos anteriores, com os 18 meses seguintes conhecidos, na mesma fase (N ≥ 0,5 se hoje é El Niño; ≤ −0,5 se La
Niña). Os 5 mais próximos em (N, ΔN) padronizados. Recomposição de cada ano = normal de hoje do mês-alvo × (ENA do
ano ÷ normal da época). É cenário ao lado do modelo-v1, não o altera.
"""

import numpy as np

from qe_hydro_inflow_similarity import modelo as M


def anos_similares(
    enso3: np.ndarray, t: int, pct: np.ndarray | None = None, m: M.Modelo = M.MODELO
):
    """(posições, distâncias) dos k anos mais parecidos, ou None se faltarem candidatos.

    `pct`: série usada só para exigir que os 18 meses seguintes de cada candidato existam."""
    n0, d0 = enso3[t], enso3[t] - enso3[t - 3]
    candidatos = []
    for p in range(t % 12 + 12, t - m.h_max + 1, 12):
        n, d = enso3[p], enso3[p] - enso3[p - 3]
        if np.isnan(n) or np.isnan(d):
            continue
        if pct is not None and np.isnan(pct[p - 2 : p + m.h_max + 1]).any():
            continue
        if (n0 >= m.fase and n < m.fase) or (n0 <= -m.fase and n > -m.fase):
            continue
        candidatos.append((p, n, d))
    if len(candidatos) < m.k_similares:
        return None
    z = np.array([[n, d] for _, n, d in candidatos])
    media, desvio = z.mean(axis=0), z.std(axis=0)
    desvio[desvio == 0] = 1
    dist = np.sqrt(
        (((z - media) / desvio - (np.array([n0, d0]) - media) / desvio) ** 2).sum(axis=1)
    )
    ordem = np.argsort(dist)[: m.k_similares]
    return np.array([candidatos[i][0] for i in ordem]), dist[ordem]


def membros_recomposicao(s: M.Serie, t: int, h: int, posicoes) -> np.ndarray:
    """% MLT do mês-alvo t+h se cada ano similar se repetir: normal de hoje × razão daquele ano."""
    razoes = np.exp([M.anomalia_alvo(s, p, h) for p in posicoes])
    return M.clim30(s.pct, t, (t + h) % 12) * razoes


def descrever(enso3, t, posicoes, dist) -> list[dict]:
    return [
        {
            "ano": int(M.data_da_posicao(p).year),
            "mes": f"{M.data_da_posicao(p):%Y-%m}",
            "n": round(float(enso3[p]), 2),
            "dn": round(float(enso3[p] - enso3[p - 3]), 2),
            "distancia": round(float(d), 2),
        }
        for p, d in zip(posicoes, dist, strict=True)
    ]


def recompor(series: dict, blocos: dict, mlts: dict, t: int, h_max: int = 12) -> dict:
    """Anos similares da emissão t e a recomposição (média, mínimo, máximo e cada ano) por série.

    A lista de anos é a do SE; o SE é a soma do SE-sul e do SE-resto em MWmed, ano a ano. Só lê posições ≤ t."""
    se = blocos["SE"]
    sim = anos_similares(se.enso3, t, pct=se.pct)
    if sim is None:
        return {}
    posicoes, dist = sim
    anos = [int(M.data_da_posicao(p).year) for p in posicoes]
    saida = {"anos": descrever(se.enso3, t, posicoes, dist), "por_nome": {}}
    fontes = {
        "SE-sul": blocos["SE-sul"],
        "SE-resto": blocos["SE-resto"],
        "S": series["S"],
        "NE": series["NE"],
        "N": series["N"],
    }
    valores = {
        nome: {h: membros_recomposicao(s, t, h, posicoes) for h in range(1, h_max + 1)}
        for nome, s in fontes.items()
    }
    for h in range(1, h_max + 1):
        ms, mr, mse = (M.mlt_do_alvo(mlts, n, t, h) for n in ("SE-sul", "SE-resto", "SE"))
        mw = (valores["SE-sul"][h] * ms + valores["SE-resto"][h] * mr) / 100
        valores.setdefault("SE", {})[h] = mw / mse * 100
    for nome, por_h in valores.items():
        saida["por_nome"][nome] = [
            {
                "h": h,
                "alvo": f"{M.data_da_posicao(t + h):%Y-%m}",
                "media": round(float(v.mean()), 1),
                "minimo": round(float(v.min()), 1),
                "maximo": round(float(v.max()), 1),
                "anos": {str(a): round(float(x), 1) for a, x in zip(anos, v, strict=True)},
            }
            for h, v in por_h.items()
        ]
    return saida
