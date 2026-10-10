"""Versões de insumo disponíveis e o conjunto vigente para uma rodada de projeção.

Uma rodada não está presa ao mês: usa os insumos mais recentes disponíveis no momento da
publicação (D033 do analytics). Pode haver várias rodadas no mesmo mês — por exemplo, quando sai
uma emissão extra do ECMWF ou o deck do NEWAVE é republicado.

- Deck: o mês de deck mais recente com boletim e PMO tratados; dentro dele, a versão ingerida por
  último. O horizonte (M+1 a M+6) conta a partir do mês do deck.
- ECMWF: a emissão mais recente. Para o próprio mês do deck a referência continua sendo a ENA do PMO;
  de M+1 em diante, a da emissão.
O backtest histórico mantém o pareamento mensal (deck de M com a emissão de M, D031).
"""

import re
from dataclasses import asdict, dataclass

import pandas as pd

from qe_bandeiras import chaves
from qe_core.armazenamento import Armazenamento, ler_json


@dataclass(frozen=True)
class Insumos:
    deck: str  # AAAA-MM
    deck_versao: str
    ecmwf_emissao: str  # AAAA-MM-DD

    @property
    def mes_deck(self) -> pd.Period:
        return pd.Period(self.deck, "M")

    def identificador(self) -> str:
        return f"deck={self.deck}_v={self.deck_versao}_ecmwf={self.ecmwf_emissao}"

    def como_dict(self) -> dict:
        return asdict(self)


def versoes_deck(arm: Armazenamento) -> pd.DataFrame:
    """Versões de deck ingeridas: deck (AAAA-MM), versao e ingerido_em."""
    linhas = []
    for chave in arm.listar(chaves.RAW_NEWAVE):
        m = re.search(r"deck=(\d{4}-\d{2})/v=(\w+)/_ingestao\.json$", chave)
        if m:
            info = ler_json(arm, chave)
            linhas.append(
                {"deck": m.group(1), "versao": m.group(2), "ingerido_em": info["ingerido_em"]}
            )
    return pd.DataFrame(linhas, columns=["deck", "versao", "ingerido_em"])


def versao_atual(arm: Armazenamento, deck: pd.Period) -> str | None:
    """A versão do deck do mês ingerida por último."""
    v = versoes_deck(arm)
    v = v[v.deck == str(deck)]
    return None if v.empty else v.sort_values("ingerido_em").versao.iloc[-1]


def emissoes_ecmwf(arm: Armazenamento) -> list[str]:
    """Datas de emissão do ECMWF ingeridas (AAAA-MM-DD), em ordem."""
    return sorted(
        {
            m.group(1)
            for c in arm.listar(chaves.RAW_ECMWF)
            if (m := re.search(r"emissao=(\d{4}-\d{2}-\d{2})/", c))
        }
    )


def emissao_do_mes(arm: Armazenamento, m: pd.Period) -> str | None:
    """A emissão mais recente dentro do mês m (pareamento mensal do backtest)."""
    do_mes = [e for e in emissoes_ecmwf(arm) if e.startswith(str(m))]
    return do_mes[-1] if do_mes else None


def vigentes(arm: Armazenamento, base: pd.DataFrame) -> Insumos:
    """Conjunto de insumos mais recente disponível para uma rodada."""
    v = versoes_deck(arm)
    com_boletim = {str(p) for p in base.index[base.gf_band_boletim.notna()]}
    v = v[v.deck.isin(com_boletim)]
    if v.empty:
        raise ValueError("nenhum deck com boletim do mês tratado")
    deck = v.deck.max()
    emissoes = emissoes_ecmwf(arm)
    if not emissoes:
        raise ValueError("nenhuma emissão do ECMWF ingerida")
    return Insumos(deck, versao_atual(arm, pd.Period(deck, "M")), emissoes[-1])
