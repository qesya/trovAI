"""Formattazione coerente dei prezzi del catalogo."""

from __future__ import annotations


SYMBOLS = {"EUR": "€", "GBP": "£", "USD": "$"}


def format_price(amount: float, currency: str = "EUR") -> str:
    code = (currency or "EUR").upper()
    symbol = SYMBOLS.get(code)
    if symbol:
        return f"{symbol}{float(amount):.2f}"
    return f"{float(amount):.2f} {code}"
