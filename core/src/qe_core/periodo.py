"""Mês de referência no formato AAAA-MM, usado nas chaves e na linha de comando."""

import pandas as pd


def mes(texto: str) -> pd.Period:
    """'2026-09' -> Period('2026-09', 'M')."""
    return pd.Period(texto, "M")


def rotulo(p: pd.Period) -> str:
    """Period -> '2026-09' (formato das chaves)."""
    return f"{p.year}-{p.month:02d}"
