"""Pulizia incrementale e arricchimento mirato dei feed Awin."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional

from google import genai
from google.genai import types


# Incrementare questa versione fa riesaminare la semantica del prodotto quando
# il feed viene risincronizzato: una correzione delle regole non deve restare
# nascosta nella cache di arricchimento Gemini.
NORMALIZATION_VERSION = "2026-10-05"
PRODUCT_TYPES = {"abbigliamento", "scarpe", "accessori", "altro"}
MARKETING_PHRASES = (
    "spedizione gratuita", "spedizione gratis", "best seller", "best-seller",
    "garanzia italia", "in offerta", "promo", "promozione", "offerta",
    "sconto", "gratis", "novita",
)

_CATEGORY_RULES = (
    ("scarpe", "air jordan", "jordan", "sneakers", "sneaker", "stivali", "sandali", "mocassini", "loafer", "ciabatte", "scarpa", "footwear"),
    ("accessori", "borsa", "zaino", "cappello", "berretto", "cintura", "portafoglio", "occhiali", "sciarpa", "guanti", "gioiello", "orecchini", "collana", "bracciale", "accessory", "accessories"),
    ("abbigliamento", "apparel", "clothing", "felpa", "t-shirt", "t shirt", "maglietta", "pantaloni", "jeans", "giacca", "cappotto", "camicia", "abito", "gonna", "shorts", "pantaloncini", "maglione", "cardigan", "polo", "body", "leggings", "top", "tuta", "costume", "intimo", "calze", "pigiama"),
)
_SUBCATEGORY_RULES = (
    ("sneakers", "air jordan", "jordan"),
    ("felpe", "felpa", "hoodie", "sweatshirt"), ("magliette", "t-shirt", "t shirt", "maglietta", "tee"),
    ("top", "top", "canotta", "tank top", "crop top"), ("polo", "polo"),
    ("pantaloni", "pantaloni", "trousers", "jogger", "chino"), ("jeans", "jeans"), ("leggings", "leggings", "legging"),
    ("giacche", "giacca", "jacket", "bomber", "blazer"), ("cappotti", "cappotto", "coat", "piumino", "parka"),
    ("camicie", "camicia", "shirt", "blusa"), ("abiti", "abito", "dress", "vestito"), ("gonne", "gonna", "skirt"),
    ("pantaloncini", "shorts", "pantaloncini"), ("tute", "tuta", "tracksuit", "jumpsuit"), ("costumi", "costume", "swimwear", "bikini"),
    ("intimo", "intimo", "lingerie", "bra", "slip", "brief"), ("calze", "calze", "socks"), ("pigiami", "pigiama", "pyjama"),
    ("sneakers", "sneaker", "sneakers"), ("stivali", "stivali", "stivale", "boots", "boot"), ("sandali", "sandali", "sandalo", "sandals"),
    ("scarpe", "scarpe", "scarpa", "loafer", "mocassini", "ciabatte"),
    ("borse", "borsa", "bag"), ("zaini", "zaino", "backpack"), ("cappelli", "cappello", "berretto", "cap", "beanie"),
    ("cinture", "cintura", "belt"), ("portafogli", "portafoglio", "wallet"), ("occhiali", "occhiali", "glasses", "sunglasses"),
    ("gioielli", "gioiello", "jewellery", "jewelry", "orecchini", "collana", "bracciale", "anello"),
)
_SUBCATEGORY_PRODUCT_TYPES = {
    "sneakers": "scarpe", "stivali": "scarpe", "sandali": "scarpe", "scarpe": "scarpe",
    "borse": "accessori", "zaini": "accessori", "cappelli": "accessori",
    "cinture": "accessori", "portafogli": "accessori", "occhiali": "accessori", "gioielli": "accessori",
}
# Anche forme femminili e plurali ("borsa nera", "sneakers bianche"): prima
# restavano nel titolo visibile e non venivano riconosciute come colore.
_COLOR_RULES = (("nero", "nero", "nera", "neri", "nere", "black"), ("bianco", "bianco", "bianca", "bianchi", "bianche", "white"), ("grigio", "grigio", "grigia", "grigi", "grigie", "grey", "gray"), ("blu", "blu", "blue", "navy"), ("rosso", "rosso", "rossa", "rossi", "rosse", "red"), ("verde", "verde", "verdi", "green", "militare", "army"), ("giallo", "giallo", "gialla", "gialli", "gialle", "yellow"), ("rosa", "rosa", "pink"), ("viola", "viola", "purple"), ("arancione", "arancione", "orange"), ("marrone", "marrone", "brown"), ("beige", "beige", "cream", "panna", "avorio", "ivory", "ecru", "camel", "sabbia", "sand", "taupe"), ("multicolore", "multicolore", "multicolor", "multi colour"))
_MATERIAL_RULES = (("cotone", "cotone", "cotton"), ("lana", "lana", "wool"), ("pelle", "pelle", "leather"), ("denim", "denim"), ("lino", "lino", "linen"), ("seta", "seta", "silk"), ("poliestere", "poliestere", "polyester"), ("nylon", "nylon"), ("viscosa", "viscosa", "viscose"), ("poliammide", "poliammide", "polyamide"), ("elastan", "elastan", "elastane", "spandex"), ("cashmere", "cashmere", "cashmere"))
_GENDER_RULES = (("donna", "donna", "women", "woman", "female", "ladies"), ("uomo", "uomo", "men", "man", "male", "mens"), ("bambino", "kids", "kid", "bambino", "bambina", "junior", "boys", "girls"), ("unisex", "unisex"))
_AGE_GROUP_RULES = (("adulto", "adult", "adults", "adulto", "adulta"), ("bambino", "kids", "kid", "bambino", "bambina", "junior", "boys", "girls"))
_SIZE_VALUE = r"(?:xxs|xs|s|m|l|xl|xxl|xxxl|[2-6]xl|taglia unica|one size|uni|(?:it|eu)\s*(?:[0-5]?\d(?:[.,]\d+)?)|(?:uk|us)\s*(?:[3-9]|1[0-5])(?:[.,]\d+)?|w\s*\d{2}\s*l\s*\d{2}|[3-5]\d(?:[.,]\d+)?)"
_SIZE_PATTERN = re.compile(rf"(?:taglia|size|misura)\s*[:\-]?\s*({_SIZE_VALUE}(?:\s*[/,;|\-]\s*{_SIZE_VALUE})*)\b", re.IGNORECASE)
_TRAILING_SIZE_PATTERN = re.compile(rf"(?:\s*[-|,]\s*|\s+)({_SIZE_VALUE})$", re.IGNORECASE)
_ONE_SIZE_PATTERN = re.compile(r"(?i)(?:\s*[-|,]\s*)?\b(?:taglia\s+unica|one\s*size|onesize)\b")
_INLINE_ALPHA_SIZE_PATTERN = re.compile(r"(?i)(?<!\w)(?:xxs|xs|xl|xxl|xxxl|[2-6]xl)(?!\w)")
_TRAILING_CONNECTOR_PATTERN = re.compile(r"(?i)(?:\s*[-|,/]\s*|\s+)\b(?:in|di|da|con|per|for|with|made)\b\s*$")
_TRAILING_BROKEN_CONNECTOR_PATTERN = re.compile(r"(?i)(?:\s*[-|,/]\s*|\s+)\b(?:in|di|da|con|per|for|with|made)\s+(?:e|ed|and|&|a)\b\s*$")
# "in e", "con e", "di ed" in mezzo al titolo: restano quando si tolgono i
# materiali da "in tessuto intrecciato e pelle". Non sono mai grammaticali.
_DANGLING_CONNECTOR_PAIR_PATTERN = re.compile(r"(?i)(?<!\w)(?:in|di|da|con|per)\s+(?:e|ed)(?!\w)")
_TRAILING_CONJUNCTION_PATTERN = re.compile(r"(?i)(?:\s*[-|,/]\s*|\s+)\b(?:e|ed|and|&|o|or)\b\s*$")
# Sono parole descrittive del materiale, non nomi di modello. Alcuni feed le
# inseriscono nel titolo senza compilare la colonna `material`; qui le togliamo
# soltanto dal titolo leggibile, senza inventare né sovrascrivere il materiale.
_DISPLAY_ONLY_MATERIAL_TERMS = (
    "tessuto", "intrecciato", "intrecciata", "maglia", "mesh", "suede",
    "scamosciato", "scamosciata", "sintetico", "sintetica", "tecnico",
    "tecnica", "riciclato", "riciclata", "impermeabile", "trapuntato",
    "trapuntata", "jersey", "canvas", "rafia", "rafia", "crochet",
)
_UNIT_PATTERN = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*[- ]?\s*(gb|tb|mb|ram|mah|kg|g|cm|mm|pollici|inch)\b", re.IGNORECASE)
_MODEL_PATTERN = re.compile(r"\b(?=[a-z0-9-]{6,}\b)(?=[a-z0-9-]*[a-z])(?=[a-z0-9-]*\d)[a-z0-9-]+\b", re.IGNORECASE)


def normalized_text(value: Any) -> Optional[str]:
    """Uniforma il testo ricercabile; URL e identificativi non passano qui."""
    if value is None:
        return None
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.lower().replace(",", " ")
    text = re.sub(r"[^\w\s%+./-]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def clean_title(value: Any) -> Optional[str]:
    """Titolo di ricerca normalizzato, separato dal titolo leggibile mostrato all'utente."""
    text = normalized_text(value)
    if not text:
        return None
    text = _UNIT_PATTERN.sub(lambda match: f"{match.group(1).replace(',', '.')}{match.group(2).lower()}", text)
    for phrase in MARKETING_PHRASES:
        text = re.sub(rf"\b{re.escape(phrase)}\b", " ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _safe_display_text(value: Any) -> Optional[str]:
    """Rimuove solo caratteri di controllo, senza alterare il titolo commerciale originale."""
    if value is None:
        return None
    text = unicodedata.normalize("NFC", str(value))
    text = "".join(" " if unicodedata.category(char).startswith("C") else char for char in text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _normalize_brand(value: Any) -> Optional[str]:
    """Non trasforma valori generici o segnaposto in una marca inesistente."""
    text = normalized_text(value)
    if not text or text in {"n/a", "na", "null", "none", "unknown", "no brand", "brandless", "generico"}:
        return None
    return text


def _first_rule_match(text: str, rules: Iterable[tuple[str, ...]]) -> Optional[str]:
    padded = f" {text} "
    for rule in rules:
        value, *terms = rule
        if any(f" {term} " in padded or text.endswith(f" {term}") for term in terms):
            return value
    return None


def _parse_price(value: Any) -> Optional[float]:
    if value is None:
        return None
    raw = re.sub(r"[^0-9,.-]", "", str(value)).strip()
    if not raw:
        return None
    if "," in raw and "." in raw:
        decimal = "," if raw.rfind(",") > raw.rfind(".") else "."
        raw = raw.replace("." if decimal == "," else ",", "").replace(decimal, ".")
    elif "," in raw:
        raw = raw.replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def _valid_ean(value: Any) -> Optional[str]:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) not in {8, 12, 13, 14} or not digits.strip("0"):
        return None
    return digits


def _valid_mpn(value: Any) -> Optional[str]:
    raw = str(value or "").strip()
    if not raw or raw.lower() in {"n/a", "na", "null", "none", "-", "0"}:
        return None
    return raw if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{2,79}", raw) else None


def _extract_model(title: str, mpn: Optional[str]) -> Optional[str]:
    if mpn:
        return mpn
    # Nei feed moda questo campo e' opzionale: evitiamo di inventarlo con l'IA.
    for candidate in _MODEL_PATTERN.findall(title):
        if not candidate.isdigit():
            return candidate.upper()
    return None


def _extract_size(text: str) -> Optional[str]:
    match = _SIZE_PATTERN.search(text) or _TRAILING_SIZE_PATTERN.search(text)
    return _normalize_size(match.group(1)) if match else None


def _normalize_size(value: Any) -> Optional[str]:
    if value is None:
        return None
    # normalized_text trasforma le virgole in spazi: prima "S, M, L" diventava
    # l'unica taglia "s m l" e "38,5" diventava "38 5". Proteggiamo la virgola
    # decimale e trattiamo le altre virgole come separatori di taglie.
    raw = re.sub(r"(\d),(\d)", r"\1.\2", str(value)).replace(",", "/")
    text = normalized_text(raw)
    if not text:
        return None
    # Sostituzioni a parola intera: un semplice str.replace("uni", ...) agiva
    # anche dentro "taglia unica" e produceva "taglia taglia unicaca".
    text = re.sub(r"\b(?:one\s*size|onesize|tu|uni)\b", "taglia unica", text)
    text = re.sub(r"\b(?:it|eu)\s*", "", text)
    values = [part.strip() for part in re.split(r"\s*[/,;|]\s*", text) if part.strip()]
    unique = list(dict.fromkeys(values))
    return ", ".join(unique) if unique else None


def _strip_size_from_title(title: str) -> str:
    """Rimuove taglie esplicite; quelle numeriche restano prudentemente finali."""
    title = _SIZE_PATTERN.sub("", title)
    # "taglia unica" non e' catturata da _SIZE_PATTERN (la parola "taglia" e'
    # gia' consumata come prefisso) e restava nel titolo visibile.
    title = _ONE_SIZE_PATTERN.sub("", title)
    title = _INLINE_ALPHA_SIZE_PATTERN.sub("", title)
    return _TRAILING_SIZE_PATTERN.sub("", title).strip(" -|, ")


def _attribute_terms(value: Optional[str], rules: Iterable[tuple[str, ...]]) -> tuple[str, ...]:
    """Restituisce i termini originali equivalenti a un valore normalizzato."""
    if not value:
        return ()
    for rule in rules:
        canonical, *terms = rule
        if canonical == value:
            return tuple(terms)
    return (value,)


def clean_display_title(
    title: str,
    *,
    brand: Optional[str] = None,
    color: Optional[str] = None,
    material: Optional[str] = None,
    gender: Optional[str] = None,
    age_group: Optional[str] = None,
) -> str:
    """Titolo breve per l'interfaccia; gli attributi restano in colonne dedicate.

    Il tipo di capo e il modello non vengono rimossi: ``air force 1`` o
    ``camicia oxford`` devono rimanere riconoscibili anche fuori dai filtri.
    """
    result = _strip_size_from_title(title)
    for phrase in MARKETING_PHRASES:
        result = re.sub(rf"(?i)(?<!\w){re.escape(phrase)}(?!\w)", " ", result)
    if brand:
        result = re.sub(rf"(?i)(?<!\w){re.escape(brand)}(?!\w)", " ", result)
    for value, rules in (
        (color, _COLOR_RULES),
        (material, _MATERIAL_RULES),
        (gender, _GENDER_RULES),
        (age_group, _AGE_GROUP_RULES),
    ):
        for term in _attribute_terms(value, rules):
            result = re.sub(rf"(?i)(?<!\w){re.escape(term)}(?!\w)", " ", result)
    # Anche se il merchant ha scritto l'attributo nella colonna sbagliata, non
    # lo lasciamo nel titolo. Le parole rimosse vengono estratte nei loro campi
    # dalle regole o da Gemini quando il contesto le supporta.
    for rules in (_COLOR_RULES, _MATERIAL_RULES, _GENDER_RULES, _AGE_GROUP_RULES):
        for _, *terms in rules:
            for term in terms:
                result = re.sub(rf"(?i)(?<!\w){re.escape(term)}(?!\w)", " ", result)
    # `tessuto intrecciato` (o `mesh`) spesso non appare nella colonna
    # materiale. Non deve quindi lasciare residui come "in ... e" nel nome
    # del modello, ma resta invariato nel titolo e nella descrizione originali.
    for term in _DISPLAY_ONLY_MATERIAL_TERMS:
        result = re.sub(rf"(?i)(?<!\w){re.escape(term)}(?!\w)", " ", result)
    # Dopo una parola eliminata il feed puo lasciare una coda come "in.",
    # "con e" o "di /". Rimuoviamo prima la punteggiatura di chiusura e poi
    # ripetiamo le regole finche il titolo non termina con parole complete.
    result = _DANGLING_CONNECTOR_PAIR_PATTERN.sub(" ", result)
    while True:
        previous = result
        result = re.sub(r"[\s\-–—|,;:/.]+$", "", result).strip()
        result = _TRAILING_BROKEN_CONNECTOR_PATTERN.sub("", result).strip()
        result = _TRAILING_CONJUNCTION_PATTERN.sub("", result).strip()
        result = _TRAILING_CONNECTOR_PATTERN.sub("", result).strip()
        if result == previous:
            break
    # Correzione lessicale molto prudente: "pantaloni jean" e' una grafia
    # ricorrente dei feed, non il nome di un modello, quindi diventa "jeans".
    result = re.sub(r"(?i)\bpantaloni\s+jean\b", "Pantaloni Jeans", result)
    result = re.sub(r"\s+", " ", result).strip(" -|,/:;.")
    return result or _strip_size_from_title(title)


def _canonical_value(value: Optional[str], rules: Iterable[tuple[str, ...]]) -> Optional[str]:
    text = normalized_text(value)
    if not text:
        return None
    return _first_rule_match(text, rules) or text


def _known_canonical_value(value: Optional[str], rules: Iterable[tuple[str, ...]]) -> Optional[str]:
    """Accetta solo valori presenti nel vocabolario, evitando campi contaminati."""
    text = normalized_text(value)
    return _first_rule_match(text, rules) if text else None


def _coalesce_text(row: Mapping[str, Any], *names: str) -> Optional[str]:
    # Alcuni feed CSV contengono sporadicamente valori oltre l'ultima intestazione:
    # csv.DictReader li espone con chiave None, che non è una colonna utilizzabile.
    canonical = {
        re.sub(r"[^a-z0-9]", "", str(key).lower()): value
        for key, value in row.items()
        if key is not None
    }
    for name in names:
        value = canonical.get(re.sub(r"[^a-z0-9]", "", name.lower()))
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


@dataclass
class CleanProduct:
    source_product_id: str
    advertiser_id: int
    advertiser_name: str
    ean: Optional[str]
    title: str
    source_title: str
    clean_title: str
    description: Optional[str]
    brand: Optional[str]
    product_type: Optional[str]
    sottocategoria: Optional[str]
    gender: Optional[str]
    age_group: Optional[str]
    color: Optional[str]
    size: Optional[str]
    material: Optional[str]
    price: float
    sale_price: Optional[float]
    discount_percentage: Optional[float]
    extracted_model: Optional[str]
    model_title: Optional[str]
    colorway_name: Optional[str]
    model_match_confidence: Optional[str]
    merchant_deep_link: Optional[str]
    aw_deep_link: Optional[str]
    image_link: Optional[str]
    currency: str
    content_hash: str
    data_quality: str
    # Offerta gia' presente nel database (impostata dal confronto incrementale).
    offer_id: Optional[int] = None
    # Impronta operativa calcolata sui valori del feed, prima di cache/IA: una
    # taglia completata dall'IA non deve far sembrare "cambiato" il prodotto.
    feed_operational_hash: str = ""

    @property
    def merchant_product_id(self) -> str:
        return self.ean or self.source_product_id

    @property
    def operational_hash(self) -> str:
        """Impronta dei campi operativi del feed: si aggiornano direttamente, senza IA."""
        return self.feed_operational_hash or self._operational_values_hash()

    def _operational_values_hash(self) -> str:
        values = (
            f"{self.price:.2f}",
            f"{self.sale_price:.2f}" if self.sale_price is not None else "",
            self.size or "",
            self.ean or "",
            self.currency,
            self.advertiser_name,
            self.merchant_deep_link or "",
            self.aw_deep_link or "",
            self.image_link or "",
        )
        return hashlib.sha256("|".join(values).encode("utf-8")).hexdigest()

    @property
    def needs_ai(self) -> bool:
        return (
            not self.brand
            or not self.product_type
            or not self.sottocategoria
            or not self.gender
            or not self.age_group
            or not self.color
            or not self.size
            or not self.material
            or not self.model_match_confidence
        )

    def apply_enrichment(self, fields: Mapping[str, Any]) -> None:
        for field in (
            "brand",
            "product_type",
            "sottocategoria",
            "gender",
            "age_group",
            "color",
            "size",
            "material",
            "model_title",
            "colorway_name",
            "model_match_confidence",
        ):
            # I valori del feed e delle regole sono solo una prima ipotesi.
            # Nel bootstrap Gemini esegue una revisione completa e puo
            # correggere anche un valore gia popolato.
            value = normalized_text(fields.get(field))
            if field == "brand":
                value = _normalize_brand(value)
            if field == "gender":
                value = _known_canonical_value(value, _GENDER_RULES)
            elif field == "color":
                value = _known_canonical_value(value, _COLOR_RULES)
            elif field == "material":
                value = _known_canonical_value(value, _MATERIAL_RULES)
            elif field == "age_group":
                value = _known_canonical_value(value, _AGE_GROUP_RULES)
            elif field == "size":
                # La taglia e' un dato operativo del feed: l'IA la completa solo
                # se manca, cosi' una risposta in cache non la sovrascrive.
                value = None if self.size else _normalize_size(value)
            elif field == "model_match_confidence":
                value = value if value in {"high", "low"} else None
            elif field == "product_type":
                # Un valore fuori elenco non deve cancellare la categoria
                # gia' ricavata dalle regole.
                value = value if value in PRODUCT_TYPES else None
            if value:
                setattr(self, field, value)
        if self.product_type not in PRODUCT_TYPES:
            self.product_type = None
        # Il titolo di visualizzazione non deve ripetere attributi che ora sono
        # colonne del database. source_title conserva sempre il testo originale.
        self.title = clean_display_title(
            self.source_title,
            brand=self.brand,
            color=self.color,
            material=self.material,
            gender=self.gender,
            age_group=self.age_group,
        )
        if self.model_title:
            self.model_title = clean_display_title(
                self.model_title,
                brand=self.brand,
                color=self.color,
                material=self.material,
                gender=self.gender,
                age_group=self.age_group,
            )
        if self.colorway_name:
            # La colorazione può contenere parole come "chicago", ma mai taglie,
            # marca, materiale, genere o fascia d'età.
            self.colorway_name = clean_display_title(
                self.colorway_name,
                brand=self.brand,
                material=self.material,
                gender=self.gender,
                age_group=self.age_group,
            )
        self.clean_title = clean_title(self.title)
        self.data_quality = "ai" if self.product_type and self.sottocategoria else "partial"


def clean_row(row: Mapping[str, Any]) -> Optional[CleanProduct]:
    advertiser_raw = _coalesce_text(row, "advertiser_id", "merchant_id")
    source_product_id = _coalesce_text(row, "id", "merchant_product_id", "product_id")
    raw_title = _safe_display_text(_coalesce_text(row, "title", "product_name", "name"))
    title_without_size = _strip_size_from_title(raw_title) if raw_title else None
    title_for_search = clean_title(raw_title)
    merchant_deep_link = _coalesce_text(row, "link", "merchant_deep_link", "product_url")
    aw_deep_link = _coalesce_text(row, "aw_deep_link")
    regular_price = _parse_price(_coalesce_text(row, "price", "search_price", "store_price"))
    sale_price = _parse_price(_coalesce_text(row, "sale_price"))
    active_price = sale_price if sale_price is not None and sale_price > 0 else regular_price
    if not advertiser_raw or not source_product_id or not raw_title or not title_without_size or not title_for_search or not merchant_deep_link and not aw_deep_link or active_price is None or active_price <= 0:
        return None
    try:
        advertiser_id = int(advertiser_raw)
    except ValueError:
        return None
    # La descrizione visualizzata rimane fedele al feed. Usiamo una copia
    # normalizzata soltanto per classificare e ricercare, senza sovrascriverla.
    description = _safe_display_text(_coalesce_text(row, "description", "product_description", "product_detail"))
    searchable_description = normalized_text(description)
    source_category = normalized_text(_coalesce_text(row, "product_type", "google_product_category", "merchant_category"))
    searchable = " ".join(filter(None, (title_for_search, searchable_description, source_category)))
    subcategory = _first_rule_match(searchable, _SUBCATEGORY_RULES)
    # La sottocategoria e' piu' affidabile di parole generiche nella descrizione
    # (es. una giacca non deve diventare "accessori" solo perche' il testo cita accessori).
    product_type = _SUBCATEGORY_PRODUCT_TYPES.get(subcategory, "abbigliamento" if subcategory else None)
    if product_type is None:
        product_type = _first_rule_match(searchable, _CATEGORY_RULES)
    color = _known_canonical_value(_coalesce_text(row, "color", "colour"), _COLOR_RULES) or _first_rule_match(searchable, _COLOR_RULES)
    material = _known_canonical_value(_coalesce_text(row, "material", "fabric"), _MATERIAL_RULES) or _first_rule_match(searchable, _MATERIAL_RULES)
    gender = _known_canonical_value(_coalesce_text(row, "gender", "sex"), _GENDER_RULES) or _first_rule_match(searchable, _GENDER_RULES)
    age_group = _known_canonical_value(_coalesce_text(row, "age_group"), _AGE_GROUP_RULES) or _first_rule_match(searchable, _AGE_GROUP_RULES)
    size = _normalize_size(_coalesce_text(row, "size", "sizes", "available_sizes", "taglia")) or _extract_size(raw_title or "") or _extract_size(description or "")
    title = clean_display_title(
        title_without_size,
        brand=_normalize_brand(_coalesce_text(row, "brand", "brand_name")),
        color=color,
        material=material,
        gender=gender,
        age_group=age_group,
    )
    if regular_price is not None and regular_price <= 0:
        regular_price = None
    if sale_price is not None and (sale_price <= 0 or regular_price is None or sale_price >= regular_price):
        sale_price = None
    price = regular_price or sale_price
    if price is None or price <= 0:
        return None
    discount_percentage = round((regular_price - sale_price) / regular_price * 100, 2) if regular_price and sale_price else None
    mpn = _valid_mpn(_coalesce_text(row, "mpn", "model", "manufacturer_part_number"))
    # Impronta dei contenuti usati dall'IA. Prezzo, disponibilita' e taglie
    # disponibili NON entrano qui: cambiano spesso e vanno aggiornati senza IA
    # (vedi CleanProduct.operational_hash). Gli attributi testuali invece
    # invalidano la cache quando il merchant li modifica.
    semantic_values = (
        NORMALIZATION_VERSION, raw_title, searchable_description, _normalize_brand(_coalesce_text(row, "brand", "brand_name")), source_category,
        normalized_text(_coalesce_text(row, "color", "colour")),
        normalized_text(_coalesce_text(row, "material", "fabric")),
        normalized_text(_coalesce_text(row, "gender", "sex")),
    )
    content_hash = hashlib.sha256("|".join(filter(None, semantic_values)).encode("utf-8")).hexdigest()
    product = CleanProduct(source_product_id=str(source_product_id), advertiser_id=advertiser_id, advertiser_name=normalized_text(_coalesce_text(row, "advertiser_name", "merchant_name")) or "awin", ean=_valid_ean(_coalesce_text(row, "gtin", "ean")), title=title, source_title=raw_title, clean_title=clean_title(title), description=description, brand=_normalize_brand(_coalesce_text(row, "brand", "brand_name")), product_type=product_type, sottocategoria=subcategory, gender=gender, age_group=age_group, color=color, size=size, material=material, price=price, sale_price=sale_price, discount_percentage=discount_percentage, extracted_model=_extract_model(title, mpn), model_title=None, colorway_name=None, model_match_confidence=None, merchant_deep_link=merchant_deep_link, aw_deep_link=aw_deep_link, image_link=_coalesce_text(row, "image_link", "aw_image_url", "merchant_image_url"), currency=(normalized_text(_coalesce_text(row, "currency")) or "eur").upper(), content_hash=content_hash, data_quality="rules" if product_type and subcategory else "partial")
    product.feed_operational_hash = product._operational_values_hash()
    return product


class EnrichmentBatch(dict):
    """Risultato di un blocco Gemini (hash -> campi) con i token consumati."""

    prompt_tokens: int = 0
    output_tokens: int = 0


def enrich_with_gemini(products: list[CleanProduct], api_key: str, model: str) -> EnrichmentBatch:
    if not products:
        return EnrichmentBatch()
    client = genai.Client(api_key=api_key)
    payload = [
        {
            "hash": item.content_hash,
            "source_title": item.source_title,
            "description": item.description,
            "merchant_name": item.advertiser_name,
            "known_brand": item.brand,
            "known_product_type": item.product_type,
            "known_sottocategoria": item.sottocategoria,
            "known_gender": item.gender,
            "known_age_group": item.age_group,
            "known_color": item.color,
            "known_size": item.size,
            "known_material": item.material,
        }
        for item in products
    ]
    prompt = """Classifica prodotti moda per un catalogo e-commerce italiano.
Restituisci SOLO JSON: una lista di oggetti. Per ogni hash inserisci ESATTAMENTE:
hash, brand, product_type, sottocategoria, gender, age_group, color, size, material,
model_title, colorway_name, model_match_confidence.

Regole fondamentali:
- Tratta ogni campo known_* come una prima ipotesi, non come verita. Devi
  revisionare OGNI campo di OGNI riga confrontandolo con titolo originale e
  descrizione: se un dato e sbagliato, incompleto o nel campo errato, restituisci
  il valore corretto nel suo campo. Non copiare automaticamente un known_*.
- Ogni campo deve contenere soltanto il proprio tipo di informazione: una taglia
  non puo stare in model_title o colorway_name; un colore non puo stare in
  model_title; materiale, genere, fascia d'eta e brand non possono contaminare
  titolo, colorazione o categoria.
- product_type puo essere solo abbigliamento, scarpe, accessori o altro.
- Correggi eventuali categorie errate del feed quando il contesto e chiaro. In
  particolare Air Jordan, Jordan Retro, Nike Dunk, Air Force e modelli simili
  sono product_type=scarpe e sottocategoria=sneakers: parole come "mesh",
  "rete" o "supporto laterale" descrivono una scarpa e non la rendono un accessorio.
- Restituisci valori italiani, minuscoli, senza accenti e senza virgole. Esempi:
  women -> donna, men -> uomo, black -> nero, white -> bianco, cotton -> cotone,
  leather -> pelle; taglie come xs, s, m, 42 o taglia unica.
- Leggi il titolo originale, la descrizione e i campi gia presenti. Estrai un
  valore anche quando e scritto in un'altra lingua o in modo implicito ma
  inequivocabile: "women's" implica gender=donna e age_group=adulto; "kids",
  "boy" o "girl" implica age_group=bambino.
- Una sola taglia numerica, anche "34", non e una prova sufficiente del genere
  o della fascia d'eta: puo indicare scarpe, jeans, vita o una numerazione di
  adulto. Usa bambino solo con segnali espliciti come kids, junior, boys, girls
  o una categoria chiaramente infantile; in caso contrario lascia null.
- Non inventare informazioni: colore, materiale, taglia, marca e categoria
  devono essere supportati chiaramente dal contesto. Se non lo sono, usa null.
- Per brand cerca prima una marca reale in titolo, descrizione o tag. Se brand
  e nullo, puoi usare merchant_name SOLO quando il merchant e chiaramente anche
  il produttore/marchio proprietario dell'articolo (per esempio Zara per un
  articolo Zara, o ASOS Design); non farlo per un negozio multi-marca. Un
  semplice negozio che rivende capi generici non e una marca: in quel caso
  restituisci brand=null. Non usare mai "unknown", "generico" o valori simili.
- model_title e il nome del modello/famiglia senza marca, colore, taglia o
  colorazione; per esempio "Nike Air Jordan 1 Chicago" diventa "air jordan 1".
  colorway_name e la colorazione commerciale, per esempio "chicago". Usa
  model_match_confidence="high" SOLTANTO se titolo o descrizione identificano
  chiaramente un modello preciso; per un generico "felpa con cappuccio" usa
  model_title=null e model_match_confidence="low". Questo campo serve a unire
  offerte di merchant diversi senza rischiare falsi raggruppamenti.
- model_title deve essere un testo italiano/inglese leggibile e grammaticalmente
  completo: non restituire mai frammenti residui come "in e", codici di taglia
  come "2xl" o colori come "panna". Se non esiste un modello preciso, restituisci
  semplicemente il tipo di capo identificabile, per esempio "polo".
- Non limitarti a cancellare singole parole dal titolo: rileggi il risultato
  finale. Se la rimozione di un attributo lascia una preposizione, una
  congiunzione o un frammento descrittivo senza significato (per esempio
  "energy sneakers in tessuto intrecciato e"), restituisci il titolo pulito e
  grammaticalmente completo ("energy sneakers").
- model_title diventa il titolo che vedra l'utente dopo l'aggiunta della marca:
  deve quindi far capire senza ambiguita di quale prodotto si parla. Mantieni il
  tipo di capo e l'eventuale modello utile (es. "polo", "air jordan 4"), ma mai
  taglia, colore, materiale, genere, eta, parole promozionali o testo incompleto.
- Non restituire un campo title. Il programma locale rimuove dal titolo visibile
  gli attributi che hanno una colonna dedicata (marca, genere, fascia d'eta,
  colore, taglia e materiale). Il nome del capo e l'eventuale modello devono
  invece restare riconoscibili nel titolo.

""" + json.dumps(payload, ensure_ascii=False)
    # Nessun try/except generico: prima ogni errore (anche un 429 di quota)
    # diventava un risultato vuoto e i prodotti restavano senza revisione IA
    # senza alcun avviso. Ora l'errore risale al chiamante, che ritenta i
    # limiti di quota e registra gli altri fallimenti.
    response = client.models.generate_content(model=model, contents=prompt, config=types.GenerateContentConfig(response_mime_type="application/json"))
    parsed = json.loads(response.text or "[]")
    if not isinstance(parsed, list):
        raise ValueError("Gemini ha restituito un JSON che non e' una lista di prodotti.")
    allowed = {item.content_hash for item in products}
    result = EnrichmentBatch({
        str(item["hash"]): {
            field: normalized_text(item.get(field))
            for field in (
                "brand",
                "product_type",
                "sottocategoria",
                "gender",
                "age_group",
                "color",
                "size",
                "material",
                "model_title",
                "colorway_name",
                "model_match_confidence",
            )
        }
        for item in parsed
        if isinstance(item, dict) and item.get("hash") in allowed
    })
    usage = getattr(response, "usage_metadata", None)
    result.prompt_tokens = int(getattr(usage, "prompt_token_count", 0) or 0)
    result.output_tokens = int(getattr(usage, "candidates_token_count", 0) or 0)
    return result
