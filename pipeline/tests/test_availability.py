"""Disponibilita' letta dalle colonne usate dai feed Awin reali."""

from __future__ import annotations

import pytest

from trovai_pipeline.awin_sync import is_available


@pytest.mark.parametrize(
    "row, expected",
    [
        ({"availability": "in_stock"}, True),
        ({"availability": "out_of_stock"}, False),
        # Feed reale: nessuna colonna availability, solo in_stock.
        ({"in_stock": "1"}, True),
        ({"in_stock": "0"}, False),
        ({"in_stock": "", "stock_status": "in stock"}, True),
        ({"in_stock": "", "stock_status": "out of stock"}, False),
        ({"in_stock": "", "stock_status": "", "is_for_sale": "1"}, True),
        # Senza alcuna indicazione l'articolo resta escluso.
        ({}, False),
        ({"in_stock": "", "stock_status": "", "is_for_sale": ""}, False),
    ],
)
def test_is_available(row, expected):
    assert is_available(row) is expected


def test_availability_column_wins_over_in_stock():
    """Il feed di prova usa availability: resta la fonte prioritaria."""
    assert is_available({"availability": "out_of_stock", "in_stock": "1"}) is False
