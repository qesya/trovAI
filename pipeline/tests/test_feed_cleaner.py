from __future__ import annotations

import pytest

from trovai_pipeline.feed_cleaner import (
    _normalize_size,
    _parse_price,
    _valid_ean,
    _valid_mpn,
    clean_display_title,
    clean_row,
    clean_title,
)


# --- Taglie -----------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("one size", "taglia unica"),
    ("One Size", "taglia unica"),
    ("taglia unica", "taglia unica"),  # prima diventava "taglia taglia unicaca"
    ("UNI", "taglia unica"),
    ("TU", "taglia unica"),
    ("S / M / L", "s, m, l"),
    ("IT 42", "42"),
    ("EU 38,5", "38.5"),
    ("M, M, L", "m, l"),
    ("", None),
    (None, None),
])
def test_normalize_size(raw, expected):
    assert _normalize_size(raw) == expected


def test_normalize_size_does_not_touch_words_containing_uni():
    assert _normalize_size("unisex") == "unisex"


# --- Prezzi e identificativi ---------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("129,00 EUR", 129.0),
    ("1.299,50", 1299.5),
    ("1,299.50", 1299.5),
    ("€ 12", 12.0),
    ("abc", None),
    (None, None),
])
def test_parse_price(raw, expected):
    assert _parse_price(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("8051234567893", "8051234567893"),
    ("805-1234-567893", "8051234567893"),
    ("0000000000000", None),
    ("123", None),
    (None, None),
])
def test_valid_ean(raw, expected):
    assert _valid_ean(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("DD1391-100", "DD1391-100"),
    ("n/a", None),
    ("0", None),
    ("ab", None),
])
def test_valid_mpn(raw, expected):
    assert _valid_mpn(raw) == expected


# --- Titoli ---------------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    # Materiali tolti dal titolo non devono lasciare "in e".
    ("Energy Sneakers in tessuto intrecciato e pelle Lime - 42", "Energy Sneakers Lime"),
    ("Energy sneakers in tessuto intrecciato e", "Energy sneakers"),
    # "taglia unica" restava nel titolo visibile.
    ("Cappello taglia unica Nero", "Cappello"),
    ("Sciarpa - One Size", "Sciarpa"),
    ("Pantaloni Jean 19 Militare in", "Pantaloni Jeans 19"),
    ("Polo Uomo in Cotone Blu - XL", "Polo"),
    # Il modello resta riconoscibile.
    ("Air Force 1 07", "Air Force 1 07"),
    ("Borsa a spalla Nera", "Borsa a spalla"),
    ("Sneakers Bianche - 40", "Sneakers"),
])
def test_clean_display_title(raw, expected):
    assert clean_display_title(raw) == expected


def test_clean_display_title_removes_brand():
    assert clean_display_title("Nike Air Jordan 1 Low Bred Toe", brand="nike") == "Air Jordan 1 Low Bred Toe"


def test_clean_title_removes_marketing_and_normalizes_units():
    assert clean_title("Zaino 20 L Spedizione Gratuita!") == "zaino 20 l"
    assert clean_title("Power bank 10.000 mAh") == "power bank 10 000mah"


# --- Riga completa del feed ------------------------------------------------------

def test_clean_row_extracts_attributes(make_row):
    product = clean_row(make_row(
        title="Energy Sneakers in tessuto intrecciato e pelle Lime - 42",
        brand="Boris Firenze", price="129,00 EUR", gtin="8051234567893",
        description="Sneakers uomo in pelle",
    ))
    assert product is not None
    assert product.title == "Energy Sneakers Lime"
    assert product.source_title == "Energy Sneakers in tessuto intrecciato e pelle Lime - 42"
    assert product.product_type == "scarpe"
    assert product.sottocategoria == "sneakers"
    assert product.gender == "uomo"
    assert product.material == "pelle"
    assert product.size == "42"
    assert product.brand == "boris firenze"
    assert product.ean == "8051234567893"
    assert product.merchant_product_id == "8051234567893"  # l'EAN vince sull'id del feed
    assert product.data_quality == "rules"


def test_clean_row_jordan_is_shoe_even_with_accessory_category(make_row):
    product = clean_row(make_row(
        title="Nike Air Jordan 1 Low Bred Toe", brand="Nike",
        product_type="Accessories > Shoes", description="Supporto laterale in mesh",
    ))
    assert (product.product_type, product.sottocategoria) == ("scarpe", "sneakers")


def test_clean_row_blazer_is_jacket(make_row):
    product = clean_row(make_row(title="Blazer Antoine Donna Blu Taglia M", brand="Costumein"))
    assert product.title == "Blazer Antoine"
    assert (product.product_type, product.sottocategoria) == ("abbigliamento", "giacche")
    assert (product.gender, product.color, product.size) == ("donna", "blu", "m")


def test_clean_row_one_size_column(make_row):
    product = clean_row(make_row(title="Cappello taglia unica Nero", size="One Size"))
    assert product.size == "taglia unica"
    assert product.title == "Cappello"


def test_clean_row_sale_price_and_discount(make_row):
    product = clean_row(make_row(price="189.90", sale_price="159.90"))
    assert product.price == pytest.approx(189.90)
    assert product.sale_price == pytest.approx(159.90)
    assert product.discount_percentage == pytest.approx(15.8)


def test_clean_row_ignores_sale_price_not_lower(make_row):
    product = clean_row(make_row(price="50", sale_price="60"))
    assert product.sale_price is None
    assert product.discount_percentage is None


@pytest.mark.parametrize("overrides", [
    {"advertiser_id": ""},
    {"advertiser_id": "non-numerico"},
    {"id": ""},
    {"title": ""},
    {"price": "0"},
    {"price": "gratis"},
    {"link": "", "aw_deep_link": ""},
])
def test_clean_row_rejects_invalid_rows(make_row, overrides):
    assert clean_row(make_row(**overrides)) is None


def test_clean_row_tolerates_extra_csv_values(make_row):
    row = make_row()
    row[None] = ["valore oltre l'ultima colonna"]  # come lo espone csv.DictReader
    assert clean_row(row) is not None


def test_content_hash_ignores_price_but_not_title(make_row):
    base = clean_row(make_row())
    assert clean_row(make_row(price="12.00")).content_hash == base.content_hash
    assert clean_row(make_row(title="Camicia Andrea a quadri")).content_hash != base.content_hash


def test_apply_enrichment_validates_vocabulary(make_row):
    product = clean_row(make_row(title="Felpa con cappuccio"))
    product.apply_enrichment({
        "color": "Black", "gender": "women", "material": "plastica magica",
        "product_type": "elettronica", "model_match_confidence": "forse", "size": "one size",
    })
    assert product.color == "nero"
    assert product.gender == "donna"
    assert product.material is None          # fuori vocabolario: scartato
    assert product.product_type == "abbigliamento"  # valore non ammesso: resta quello delle regole
    assert product.model_match_confidence is None
    assert product.size == "taglia unica"
