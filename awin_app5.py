import json
import logging
import sqlite3
import time
from pathlib import Path

from google import genai
from google.genai import types
import pandas as pd
import streamlit as st

from src.awin_tracking import (
    AwinLinkBuilderClient,
    AwinTrackingError,
    build_click_parameters,
    resolve_tracking_url,
)
from src.config import ConfigurationError, database_path, get_setting
from src.disclosures import (
    AI_DISCLOSURE,
    DEMO_DISCLOSURE,
    MERCHANT_DISCLOSURE,
    RANKING_DISCLOSURE,
)
from src.feedback import record_product_feedback
from src.money import format_price
from src.ranking import rank_products
from src.security import (
    InputValidationError,
    append_filter_history,
    check_rate_limit,
    sanitize_query,
)
from src.site_config import load_site_identity
from src.site_ui import render_affiliate_notice, render_footer

# -----------------------------------------------------------------
# 1. CONFIGURAZIONE API GEMINI
# -----------------------------------------------------------------
st.set_page_config(
    page_title="Enterprise AI Shopping Assistant", page_icon="🛍️", layout="wide"
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent

try:
    GEMINI_API_KEY = get_setting(
        "GEMINI_API_KEY", st.secrets, required=True
    )
    configured_db_path = get_setting("DATABASE_PATH", st.secrets)
    APP_DEBUG = str(
        get_setting("APP_DEBUG", st.secrets, default="false")
    ).lower() in {"1", "true", "yes", "on"}
    AWIN_LINK_BUILDER_ENABLED = str(
        get_setting("AWIN_LINK_BUILDER_ENABLED", st.secrets, default="false")
    ).lower() in {"1", "true", "yes", "on"}
    awin_publisher_id = get_setting(
        "AWIN_PUBLISHER_ID", st.secrets, required=AWIN_LINK_BUILDER_ENABLED
    )
    awin_api_token = get_setting(
        "AWIN_API_TOKEN", st.secrets, required=AWIN_LINK_BUILDER_ENABLED
    )
    AWIN_TRACKING_CAMPAIGN = get_setting(
        "AWIN_TRACKING_CAMPAIGN", st.secrets, default="trovai-search"
    ) or "trovai-search"
    LOG_LEVEL = (
        get_setting("LOG_LEVEL", st.secrets, default="INFO") or "INFO"
    ).upper()
except ConfigurationError as exc:
    st.error(str(exc))
    st.stop()

DB_PATH = str(database_path(BASE_DIR, configured_db_path))
logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
client = genai.Client(api_key=GEMINI_API_KEY)
site_identity = load_site_identity(st.secrets)
LOGO_PATH = BASE_DIR / "assets" / "brand" / "trovai-logo-primary.png"
st.logo(str(LOGO_PATH), size="large")

try:
    awin_link_client = (
        AwinLinkBuilderClient(int(awin_publisher_id), awin_api_token or "")
        if AWIN_LINK_BUILDER_ENABLED
        else None
    )
except (TypeError, ValueError):
    st.error("AWIN_PUBLISHER_ID deve essere un identificativo numerico valido.")
    st.stop()

if "messages" not in st.session_state:
    st.session_state.messages = []
if "history_raw" not in st.session_state:
    st.session_state.history_raw = ""
if "wishlist" not in st.session_state:
    st.session_state.wishlist = []
if "cart" not in st.session_state:
    st.session_state.cart = []
if "request_timestamps" not in st.session_state:
    st.session_state.request_timestamps = []

st.image(str(LOGO_PATH), width=360)
st.caption(
    "Trova prodotti usando il linguaggio naturale e confronta le opzioni prima "
    "di acquistare sul sito del negozio."
)
render_affiliate_notice()
st.caption(AI_DISCLOSURE)
st.caption(MERCHANT_DISCLOSURE)
with st.expander("Come vengono ordinati i risultati"):
    st.write(RANKING_DISCLOSURE)
    st.write(
        "Il punteggio considera marca, categoria, colore, materiale, taglia, "
        "genere, negozio e parole chiave. Prezzo e disponibilità sono filtri, "
        "non informazioni generate dal modello."
    )

# --- SIDEBAR ---
with st.sidebar:
    st.title("Opzioni Chat")
    
    # Pulsante per resettare la chat e la cronologia
    if st.button("🧹 Nuova ricerca / Pulisci chat", use_container_width=True):
        # Azzera la cronologia visibile dei messaggi
        st.session_state.messages = []
        # Azzera anche la history testuale usata dall'IA
        st.session_state.history_raw = ""
        # Ricarica la pagina all'istante per applicare il reset
        st.rerun()
    if st.button("🗑️ Elimina dati della sessione", use_container_width=True):
        st.session_state.clear()
        st.rerun()
    st.markdown("### 🛒 I tuoi Spazi")
    tab_wish, tab_cart = st.tabs([
        f"❤️ Preferiti ({len(st.session_state.wishlist)})",
        f"🛍️ Carrello ({len(st.session_state.cart)})",
    ])

    with tab_wish:
        if not st.session_state.wishlist:
            st.caption("La tua wishlist è vuota.")
        else:
            for item in st.session_state.wishlist:
                st.write(f"**{item['title']}**")
                st.caption(
                    f"{item['brand']} · Taglia {item['size']} · "
                    f"{format_price(item['price'], item.get('currency', 'EUR'))}"
                )
                # Sostituito variant_id con id per coerenza con il nuovo database
                if st.button("❌ Rimuovi", key=f"rm_wish_{item['id']}"):
                    st.session_state.wishlist.remove(item)
                    st.rerun()
                st.divider()

    with tab_cart:
        if not st.session_state.cart:
            st.caption("Il carrello è vuoto.")
        else:
            total_price = 0
            for item in st.session_state.cart:
                final_p = (
                    item["sale_price"]
                    if item["sale_price"] and pd.notna(item["sale_price"])
                    else item["price"]
                )
                total_price += float(final_p)
                st.write(f"**{item['title']}**")
                st.caption(
                    f"Taglia {item['size']} · "
                    f"{format_price(final_p, item.get('currency', 'EUR'))}"
                )
                # Sostituito variant_id con id per coerenza con il nuovo database
                if st.button("❌ Rimuovi", key=f"rm_cart_{item['id']}"):
                    st.session_state.cart.remove(item)
                    st.rerun()
                st.divider()
            cart_currencies = {
                item.get("currency", "EUR") for item in st.session_state.cart
            }
            if len(cart_currencies) == 1:
                st.markdown(
                    f"**Totale Carrello: "
                    f"{format_price(total_price, cart_currencies.pop())}**"
                )
            else:
                st.caption(
                    "Il totale non è disponibile perché il carrello contiene "
                    "prodotti in valute diverse."
                )
            if st.button("💳 Procedi al Checkout", use_container_width=True):
                st.info(
                    "Il carrello è una simulazione: gli acquisti vengono "
                    "completati separatamente sui siti dei negozi."
                )

    st.markdown("---")
    st.markdown("### 🎛️ Filtri Rapidi (Sidebar)")
    
    manual_merchant = st.selectbox(
        "Negozio (Merchant)", 
        ["Tutti", "Nike Store", "Adidas Store", "Zalando", "Foot Locker", "Zara", "Puma Store", "Asos", "Under Armour", "JD Sports", "H&M", "The North Face", "Amazon", "Tommy Hilfiger", "Champion Store", "Mango"]
    )
    manual_gender = st.selectbox("Genere", ["Tutti", "Uomo", "Donna", "Unisex"])
    manual_size = st.selectbox(
        "Taglia", ["Tutte", "S", "M", "L", "XL", "XS", "28", "30", "32", "34", "39", "40", "41", "42", "43", "44"]
    )
    manual_max_price = st.slider(
        "Prezzo Massimo (€)", min_value=10, max_value=250, value=250, step=10
    )
    manual_on_sale = st.checkbox("🔥 Solo prodotti in saldo")

    st.markdown("---")
    
    st.markdown("### 🔒 Trasparenza")
    st.info(
        "I link affiliati sono indicati prima del reindirizzamento. "
        "La commissione non viene usata per ordinare i risultati."
    )

    st.markdown("---")
    if APP_DEBUG:
        st.markdown("### 🛠️ Parametri IA & Esclusioni (Debug)")
        debug_container = st.empty()
    else:
        debug_container = None

def extract_all_feed_parameters(user_query, chat_history, client):
    # 1. Definiamo i filtri basati esattamente sulle colonne reali del tuo DB/CSV
    # Aggiungiamo anche i campi per gestire le logiche AND/OR delle congiunzioni ("e" / "o")
    filter_properties = {
        "brand": {"type": "STRING", "nullable": True},
        "product_type": {"type": "STRING", "nullable": True},
        "sottocategoria": {"type": "STRING", "nullable": True},
        "gender": {"type": "STRING", "nullable": True},
        "age_group": {"type": "STRING", "nullable": True},
        "color": {"type": "STRING", "nullable": True},
        "color_logic": {"type": "STRING", "enum": ["AND", "OR"], "nullable": True}, # <-- Gestione congiunzione colori (es. "bianca e nera" = AND)
        "size": {"type": "STRING", "nullable": True},
        "material": {"type": "STRING", "nullable": True},
        "material_logic": {"type": "STRING", "enum": ["AND", "OR"], "nullable": True}, # <-- Gestione congiunzione materiali (es. "cotone e poliestere" = AND)
        "merchant": {"type": "STRING", "nullable": True},
        "condizione": {"type": "STRING", "nullable": True},
        "min_price": {"type": "NUMBER", "nullable": True},
        "max_price": {"type": "NUMBER", "nullable": True},
        "only_on_sale": {"type": "BOOLEAN", "nullable": True},
        "in_stock_only": {"type": "BOOLEAN", "nullable": True},
        "search_keywords": {"type": "STRING", "nullable": True},
        "excluded_color": {"type": "STRING", "nullable": True},
        "excluded_material": {"type": "STRING", "nullable": True},
        "excluded_product_type": {"type": "STRING", "nullable": True},
        "unwanted_features": {"type": "STRING", "nullable": True},
        "sort_by": {"type": "STRING", "nullable": True},
    }

    # 2. Schema finale che unisce i filtri principali e la lista sub_queries per richieste multiple
    response_schema = {
        "type": "OBJECT",
        "properties": {
            **filter_properties,
            "sub_queries": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": filter_properties
                },
                "nullable": True
            },
        },
    }

    prompt = f"""
    Sei il motore di intelligenza artificiale per un grande e-commerce multibrand. 
    Analizza la richiesta dell'utente e la cronologia per estrarre tutti i parametri di filtro.
    
    ### 🚨 REGOLA CRITICA ASSOLUTA (OBBLIGATORIO):
    Se l'utente nomina un capo d'abbigliamento o un articolo specifico (es. "t-shirt", "scarpe", "felpa", "giacca"), DEVI SEMPRE compilare tassativamente:
    1. `product_type` (es. "Abbigliamento" o "Scarpe")
    2. `sottocategoria` (es. "t-shirt", "Sneakers", "Felpe")
    Non estrarre mai solo il brand (es. se dice "t-shirt Adidas", devi mettere sia `brand: "Adidas"` che `sottocategoria: "t-shirt"` e `product_type: "Abbigliamento"`).

    ### 🚨 REGOLE PER LE CONGIUNZIONI ("E" / "O") SU COLORI E MATERIALI:
    Previa attenzione estrema all'uso delle congiunzioni nei parametri oggettivi:
    1. **Se l'utente usa la congiunzione "E" (AND)** (es. "una felpa bianca e nera", "maglia in cotone e poliestere"):
       - Inserisci i vari elementi separati da virgola nel campo principale (`color` o `material`), es. `color: "bianco, nero"` oppure `material: "cotone, poliestere"`.
       - Imposta tassativamente la relativa logica su `"AND"` (`color_logic: "AND"` oppure `material_logic: "AND"`). Questo servirà al sistema per applicare un filtro rigoroso e scartare i prodotti che non contengono contemporaneamente tutti gli elementi nello stesso campo.
    2. **Se l'utente usa la congiunzione "O" (OR)** (es. "una felpa bianca o nera"):
       - Inserisci gli elementi separati da virgola nel campo, es. `color: "bianco, nero"`.
       - Imposta la logica su `"OR"` (`color_logic: "OR"`).

    ### 🚨 REGOLA PER RICHIESTE GENERICHE O STILISTICHE (ES. "qualcosa di sportivo", "elegante", "estivo"):
    Se l'utente fa una richiesta di stile o generale (es. "mostrami qualcosa di sportivo") senza specificare un singolo capo preciso:
    - Lascia a `null` o non forzare i campi rigidi come `sottocategoria` o `product_type` (a meno che non siano ovvi).
    - DEVI popolare riccamente il campo `search_keywords` inserendo una lista di parole chiave, sinonimi e capi coerenti con lo stile richiesto.

    ### REGOLA PER RICHIESTE MULTIPLE (ES. "X di un colore e Y di un altro"):
    Se l'utente chiede più articoli diversi con caratteristiche o colori differenti nella stessa frase (es. "una felpa bianca e delle scarpe nere"), NON mescolare i filtri in un unico oggetto. 
    DEVI popolare la lista `sub_queries` creando un oggetto separato per ciascun articolo menzionato.

    ### REGOLE RIGOROSE PER LE NEGAZIONI E LE ESCLUSIONI:
    1. Se l'utente esprime una negazione o un'esclusione (es. "non nero", "senza cappuccio", "non in lana"):
       - Cattura il termine esatto e inseriscilo nell'apposito campo (`excluded_color`, `excluded_material`, `excluded_product_type`, oppure `unwanted_features`).
       
    Restituisci ESCLUSIVAMENTE un oggetto JSON valido.

    Mappatura delle regole basata ESATTAMENTE sulle colonne del database:
    - brand: Marca (es. 'Nike', 'Adidas')
    - product_type: Categoria principale (es. 'Abbigliamento', 'Scarpe')
    - sottocategoria: Sottocategoria specifica (es. 'Felpe', 'Sneakers', 't-shirt')
    - gender: 'Uomo', 'Donna', 'Unisex'
    - age_group: 'Adulti', 'Kids', 'Infant'
    - color: Colore/i desiderato/i separati da virgola (es. "bianco, nero")
    - color_logic: "AND" se ha usato la "e", "OR" se ha usato la "o"
    - size: Taglia (es. 'M', '42')
    - material: Materiale/i desiderato/i separati da virgola (es. "cotone, poliestere")
    - material_logic: "AND" se richiede tutti i materiali, "OR" se ne basta uno
    - merchant: Nome del venditore
    - min_price / max_price: Budget numerico
    - only_on_sale: true se chiede sconti
    - in_stock_only: true di default
    - search_keywords: Parole chiave generali o di stile
    - excluded_color: Colore esatto che l'utente NON vuole
    - excluded_material: Materiale esatto che l'utente NON vuole
    - excluded_product_type: Tipologia che l'utente NON vuole
    - unwanted_features: Dettagli indesiderati separati da virgola (es. "bottoni, zip")
    - sort_by: 'price_asc', 'price_desc'
    
    Cronologia: {chat_history}
    Nuovo Messaggio: "{user_query}"
    """

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-3.1-flash-lite",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=response_schema
                ),
            )
            return json.loads(response.text)
        except Exception as e:
            if ("503" in str(e) or "429" in str(e)) and attempt < max_retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            return {}
    return {}
# --- TEST DI CONNESSIONE RAPIDO ---
try:
    with sqlite3.connect(DB_PATH) as conn:
        test_df = pd.read_sql_query("SELECT COUNT(*) as totale FROM prodotti", conn)
        totale_prodotti = test_df['totale'].values[0]
        st.success(f"CONNESSIONE RIUSCITA! Trovati {totale_prodotti} prodotti nel database.")
except Exception as e:
    st.error(f"ERRORE DI CONNESSIONE AL DATABASE: {e}")

def query_ecommerce_catalog(filters, limit=20, offset=0):
    with sqlite3.connect(DB_PATH) as conn:
        # --- 1. QUERY PRINCIPALE PER I DATI ---
        query = """
        SELECT 
            id, sku, title, description, brand, product_type, sottocategoria, 
            gender, age_group, color, size, material, price, sale_price, 
            availability, condizione, merchant, image_link, merchant_deep_link,
            advertiser_id, merchant_product_id, aw_deep_link, currency, source,
            source_updated_at
        FROM prodotti
        WHERE 1=1
        """
        params = []

        # --- 2. COUNT QUERY PER IL TOTALE ---
        count_query = """
        SELECT COUNT(DISTINCT id) 
        FROM prodotti
        WHERE 1=1
        """
        count_params = []

        # --- FILTRI STANDARD ---
        if filters.get("gender"):
            clause = " AND gender = ?"
            query += clause
            count_query += clause
            params.append(filters["gender"])
            count_params.append(filters["gender"])

        if filters.get("age_group"):
            clause = " AND age_group = ?"
            query += clause
            count_query += clause
            params.append(filters["age_group"])
            count_params.append(filters["age_group"])

        if filters.get("brand"):
            clause = " AND brand LIKE ?"
            query += clause
            count_query += clause
            val = f"%{filters['brand']}%"
            params.append(val)
            count_params.append(val)

        if filters.get("merchant"):
            clause = " AND merchant LIKE ?"
            query += clause
            count_query += clause
            val = f"%{filters['merchant']}%"
            params.append(val)
            count_params.append(val)

        if filters.get("condizione"):
            clause = " AND condizione = ?"
            query += clause
            count_query += clause
            params.append(filters["condizione"])
            count_params.append(filters["condizione"])

        # --- GESTIONE RIGIDA MATERIALI (Con supporto AND / OR) ---
        if filters.get("material"):
            raw_mat = filters["material"]
            mat_logic = filters.get("material_logic", "AND").upper()
            
            # Divide i materiali se l'utente ne ha inseriti più di uno (es. "cotone, poliestere" o separati da spazi/e)
            mats = [m.strip() for m in raw_mat.replace(" e ", ",").split(",") if m.strip()]
            
            if mats:
                mat_clauses = []
                for m in mats:
                    m_clean = m.lower()
                    if len(m_clean) > 3:
                        m_clean = m_clean.rstrip('aeiou')
                    val = f"%{m_clean}%"
                    mat_clauses.append("LOWER(material) LIKE ?")
                    params.append(val)
                    count_params.append(val)
                
                if mat_clauses:
                    connector = " AND " if mat_logic == "AND" else " OR "
                    clause = f" AND ({connector.join(mat_clauses)})"
                    query += clause
                    count_query += clause

        # --- CARATTERISTICHE INDESIDERATE ---
        if filters.get("unwanted_features"):
            features = [f.strip() for f in filters["unwanted_features"].split(",")]
            for feat in features:
                if feat:
                    clause = " AND title NOT LIKE ? AND description NOT LIKE ?"
                    query += clause
                    count_query += clause
                    ex_term = f"%{feat}%"
                    params.extend([ex_term, ex_term])
                    count_params.extend([ex_term, ex_term])

        # --- TIPOLOGIA PRODOTTO ---
        if filters.get("product_types_list") and isinstance(filters["product_types_list"], list):
            pt_queries = []
            for pt in filters["product_types_list"]:
                pt_queries.append("(product_type LIKE ? OR sottocategoria LIKE ? OR title LIKE ?)")
                search_term = f"%{pt}%"
                params.extend([search_term, search_term, search_term])
                count_params.extend([search_term, search_term, search_term])
            if pt_queries:
                clause = " AND (" + " OR ".join(pt_queries) + ")"
                query += clause
                count_query += clause
        elif filters.get("product_type"):
            clause = " AND (product_type LIKE ? OR sottocategoria LIKE ? OR title LIKE ?)"
            query += clause
            count_query += clause
            search_term = f"%{filters['product_type']}%"
            params.extend([search_term, search_term, search_term])
            count_params.extend([search_term, search_term, search_term])

        if filters.get("sottocategoria"):
            clause = " AND (sottocategoria LIKE ? OR title LIKE ?)"
            query += clause
            count_query += clause
            search_term = f"%{filters['sottocategoria']}%"
            params.extend([search_term, search_term])
            count_params.extend([search_term, search_term])

        # --- PAROLE CHIAVE ---
        if filters.get("search_keywords"):
            keywords = filters["search_keywords"].replace(",", " ").split()
            if keywords:
                sub_queries = []
                for kw in keywords:
                    sub_queries.append("(title LIKE ? OR description LIKE ? OR product_type LIKE ? OR sottocategoria LIKE ?)")
                    q_term = f"%{kw}%"
                    params.extend([q_term, q_term, q_term, q_term])
                    count_params.extend([q_term, q_term, q_term, q_term])
                clause = " AND (" + " OR ".join(sub_queries) + ")"
                query += clause
                count_query += clause

        # --- GESTIONE RIGIDA COLORI E ESCLUSIONI (Con supporto AND / OR) ---
        if filters.get("excluded_color"):
            clause = " AND (LOWER(color) NOT LIKE ? OR color IS NULL)"
            query += clause
            count_query += clause
            base_exc = filters['excluded_color'].strip().lower()
            if len(base_exc) > 3:
                base_exc = base_exc.rstrip('aeiou')
            val = f"%{base_exc}%"
            params.append(val)
            count_params.append(val)
            
        if filters.get("color"):
            raw_color = filters["color"]
            color_logic = filters.get("color_logic", "AND").upper()
            
            # Supporta separazione con virgola o congiunzione "e"
            colors = [c.strip() for c in raw_color.replace(" e ", ",").split(",") if c.strip()]
            
            if colors:
                color_queries = []
                for c in colors:
                    c_clean = c.lower()
                    if len(c_clean) > 3:
                        c_clean = c_clean.rstrip('aeiou')
                    val = f"%{c_clean}%"
                    color_queries.append("LOWER(color) LIKE ?")
                    params.append(val)
                    count_params.append(val)
                
                if color_queries:
                    connector = " AND " if color_logic == "AND" else " OR "
                    clause = f" AND ({connector.join(color_queries)})"
                    query += clause
                    count_query += clause

        # --- TAGLIE ---
        if filters.get("size"):
            clause = " AND size LIKE ?"
            query += clause
            count_query += clause
            val = f"%{filters['size']}%"
            params.append(val)
            count_params.append(val)

        # --- PREZZI E SALDI ---
        if filters.get("max_price") is not None:
            clause = " AND (CASE WHEN sale_price IS NOT NULL AND sale_price > 0 THEN sale_price ELSE price END) <= ?"
            query += clause
            count_query += clause
            val = float(filters["max_price"])
            params.append(val)
            count_params.append(val)

        if filters.get("min_price"):
            clause = " AND (CASE WHEN sale_price IS NOT NULL AND sale_price > 0 THEN sale_price ELSE price END) >= ?"
            query += clause
            count_query += clause
            val = float(filters["min_price"])
            params.append(val)
            count_params.append(val)

        if filters.get("only_on_sale") is True:
            clause = " AND sale_price IS NOT NULL AND sale_price < price"
            query += clause
            count_query += clause

        if filters.get("in_stock_only") is True:
            clause = " AND availability = 1"
            query += clause
            count_query += clause

        # --- ESCLUSIONI MATERIALE E TIPOLOGIA ---
        if filters.get("excluded_material"):
            clause = " AND (material NOT LIKE ? OR material IS NULL)"
            query += clause
            count_query += clause
            val = f"%{filters['excluded_material']}%"
            params.append(val)
            count_params.append(val)

        if filters.get("excluded_product_type"):
            clause = " AND product_type NOT LIKE ? AND title NOT LIKE ?"
            query += clause
            count_query += clause
            ex_term = f"%{filters['excluded_product_type']}%"
            params.extend([ex_term, ex_term])
            count_params.extend([ex_term, ex_term])

        # --- ORDINAMENTO E LIMITI ---
        if filters.get("sort_by") == "price_asc":
            query += " ORDER BY COALESCE(sale_price, price) ASC"
        elif filters.get("sort_by") == "price_desc":
            query += " ORDER BY COALESCE(sale_price, price) DESC"
        else:
            query += " ORDER BY id ASC"

        query += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        try:
            df = pd.read_sql_query(query, conn, params=params)
            
            cursor = conn.cursor()
            cursor.execute(count_query, count_params)
            totale_risultati = cursor.fetchone()[0]

            return df, totale_risultati
            
        except Exception:
            logger.exception("Errore durante la ricerca nel database")
            return pd.DataFrame(), 0



def rank_product_dataframe(df_products, filters):
    """Ordina un DataFrame con regole locali e aggiunge spiegazioni verificabili."""
    if df_products is None or df_products.empty:
        return df_products
    ranked = rank_products(df_products.to_dict("records"), filters)
    ordered = df_products.iloc[[item.position for item in ranked]].copy()
    ordered["_match_score"] = [item.score for item in ranked]
    ordered["_match_reasons"] = [", ".join(item.reasons) for item in ranked]
    return ordered.reset_index(drop=True)


def generate_natural_response(user_query, count, filters, client=None):
    """Risposta deterministica: il conteggio non viene affidato al modello."""
    del user_query, filters, client
    if count == 0:
        return (
            "Non ho trovato articoli che rispettino tutti i filtri. "
            "Prova a rimuoverne uno o ad ampliare la fascia di prezzo."
        )
    if count == 1:
        return "Ho trovato 1 articolo compatibile con i filtri applicati."
    return f"Ho trovato {count} articoli compatibili, ordinati per pertinenza."


def resolve_product_link(row, position):
    """Restituisce un link Awin tracciato o il miglior fallback disponibile."""
    awin_link = row.get("aw_deep_link")
    has_awin_link = pd.notna(awin_link) and bool(str(awin_link).strip())
    fallback = (
        str(awin_link).strip()
        if has_awin_link
        else (
            str(row.get("merchant_deep_link")).strip()
            if pd.notna(row.get("merchant_deep_link"))
            and str(row.get("merchant_deep_link")).strip()
            else "#"
        )
    )

    advertiser_id = row.get("advertiser_id")
    destination_url = row.get("merchant_deep_link")
    can_use_link_builder = (
        awin_link_client is not None
        and row.get("source") == "awin"
        and pd.notna(advertiser_id)
        and pd.notna(destination_url)
        and bool(str(destination_url).strip())
    )
    if not can_use_link_builder:
        return fallback

    parameters = build_click_parameters(
        product_id=int(row["id"]),
        position=position,
        campaign=AWIN_TRACKING_CAMPAIGN,
    )
    try:
        with sqlite3.connect(DB_PATH) as conn:
            return resolve_tracking_url(
                conn,
                awin_link_client,
                int(advertiser_id),
                str(destination_url).strip(),
                parameters,
            )
    except (AwinTrackingError, sqlite3.Error):
        logger.exception(
            "Impossibile generare il tracking link per advertiser %s",
            advertiser_id,
        )
        return fallback


def save_product_feedback(product_id, helpful):
    try:
        record_product_feedback(DB_PATH, product_id, helpful)
        return True
    except sqlite3.Error:
        logger.exception("Impossibile salvare il feedback per il prodotto %s", product_id)
        return False


@st.fragment
def display_product_grid(
    filters, message_index, user_query="", precalculated_df=None
):
    limit_key = f"limit_msg_{message_index}"
    if limit_key not in st.session_state:
        st.session_state[limit_key] = 9

    prodotti_correnti_limite = st.session_state[limit_key]

    # --- LA SOLUZIONE DEFINITIVA ---
    # Usiamo SEMPRE e SOLO il DataFrame precalcolato passato dal flusso principale.
    # Nessuna chiamata AI viene eseguita durante il rendering della griglia.
    if precalculated_df is not None:
        raw_df = precalculated_df
    else:
        # Fallback di sicurezza solo se non è stato passato nulla
        raw_df, _ = query_ecommerce_catalog(filters, limit=20, offset=0)
        if raw_df is not None and not raw_df.empty:
            raw_df = rank_product_dataframe(raw_df, filters)

    # 3. Gestione paginazione
    if raw_df is not None and not raw_df.empty:
        totale_risultati = len(raw_df)
        df_results = raw_df.iloc[:prodotti_correnti_limite]
    else:
        df_results = None
        totale_risultati = 0

    if df_results is None or df_results.empty:
        st.info(
            "Nessun prodotto rispetta tutti i filtri applicati. Prova a rimuovere "
            "un filtro o a formulare la richiesta in modo diverso."
        )
        return

    if df_results is not None and not df_results.empty:
        st.markdown(
            f"### 🎯 Mostrati {len(df_results)} prodotti ordinati per pertinenza (su"
            f" {totale_risultati} totali)"
        )
        cols = st.columns(3)
        for idx, row in df_results.iterrows():
            with cols[idx % 3]:
                # Mappatura corretta colonna image_link
                img_url = row.get("image_link")
                if pd.notna(img_url):
                    st.image(img_url, use_container_width=True)
                
                # Mappatura corretta colonna title
                st.markdown(f"##### {row['title']}")
                
                # Mappatura corretta brand, merchant, color, size
                st.write(
                    f"**{row['brand']}** ({row['merchant']}) · {row['color']} · Taglie: {row['size']}"
                )

                # Gestione prezzi normali e scontati dal nuovo DB
                sale_val = row.get("sale_price")
                base_val = row.get("price")
                
                try:
                    sale_float = float(sale_val) if sale_val is not None and pd.notna(sale_val) and str(sale_val).strip() != "" else None
                except (ValueError, TypeError):
                    sale_float = None

                base_float = float(base_val) if base_val is not None and pd.notna(base_val) else 0.0
                currency = row.get("currency") or "EUR"

                if sale_float is not None and sale_float < base_float:
                    price_display = (
                        f"~~{format_price(base_float, currency)}~~ <span"
                        " style='color:#681D35; font-weight:bold;'>🔥 "
                        f"{format_price(sale_float, currency)}</span>"
                    )
                    current_price = sale_float
                else:
                    price_display = format_price(base_float, currency)
                    current_price = base_float

                st.markdown(f"**Prezzo:** {price_display}", unsafe_allow_html=True)
                st.caption(
                    f"Materiale: {row.get('material', 'N/D')} | Sottocategoria: {row.get('sottocategoria', 'N/D')}"
                )
                reasons = row.get("_match_reasons")
                if pd.notna(reasons) and str(reasons).strip():
                    st.caption(f"**Perché lo vedi:** {reasons}")
                if row.get("source") == "awin":
                    updated = row.get("source_updated_at") or "data non disponibile"
                    st.caption(f"Dati da product feed · Aggiornamento: {updated}")
                else:
                    st.warning(DEMO_DISCLOSURE)

                # Generazione link affiliato sicuro dal campo merchant_deep_link del database
                affiliate_url = resolve_product_link(row, position=idx + 1)
                is_awin_product = row.get("source") == "awin"
                button_label = (
                    "🛒 Vai al negozio · link affiliato"
                    if is_awin_product
                    else "🔗 Apri prodotto dimostrativo"
                )
                st.link_button(button_label, affiliate_url, use_container_width=True)
                if is_awin_product:
                    st.caption(
                        "Link affiliato: potremmo ricevere una commissione. "
                        "L'acquisto si conclude sul sito del negozio."
                    )
                else:
                    st.caption("Link esterno non presentato come tracking Awin.")

                col_btn1, col_btn2 = st.columns(2)

                is_in_wishlist = any(
                    item["id"] == row["id"]
                    for item in st.session_state.wishlist
                )
                with col_btn1:
                    prefix_key = f"m_{message_index}_"
                    if not is_in_wishlist:
                        if st.button("❤️ Preferiti", key=f"{prefix_key}wish_{row['id']}"):
                            st.session_state.wishlist.append({
                                "id": row["id"],
                                "title": row["title"],
                                "brand": row["brand"],
                                "size": row["size"],
                                "price": current_price,
                                "currency": currency,
                            })
                            st.rerun()
                    else:
                        if st.button(
                            "❤️ Salvato",
                            key=f"{prefix_key}unwish_{row['id']}",
                            type="primary",
                        ):
                            st.session_state.wishlist = [
                                i
                                for i in st.session_state.wishlist
                                if i["id"] != row["id"]
                            ]
                            st.rerun()

                is_in_cart = any(
                    item["id"] == row["id"]
                    for item in st.session_state.cart
                )
                with col_btn2:
                    if not is_in_cart:
                        if st.button("🛍️ Aggiungi", key=f"{prefix_key}cart_{row['id']}"):
                            st.session_state.cart.append({
                                "id": row["id"],
                                "title": row["title"],
                                "brand": row["brand"],
                                "size": row["size"],
                                "price": row["price"],
                                "sale_price": row.get("sale_price"),
                                "currency": currency,
                            })
                            st.rerun()
                    else:
                        if st.button(
                            "🛍️ Nel Carrello",
                            key=f"{prefix_key}uncart_{row['id']}",
                            type="primary",
                        ):
                            st.session_state.cart = [
                                i
                                for i in st.session_state.cart
                                if i["id"] != row["id"]
                            ]
                            st.rerun()

                st.caption("Questo risultato è pertinente?")
                feedback_yes, feedback_no = st.columns(2)
                with feedback_yes:
                    if st.button(
                        "👍 Sì",
                        key=f"{prefix_key}feedback_yes_{row['id']}",
                        use_container_width=True,
                    ):
                        if save_product_feedback(row["id"], True):
                            st.toast("Grazie per il feedback.")
                        else:
                            st.toast("Feedback non salvato. Riprova più tardi.")
                with feedback_no:
                    if st.button(
                        "👎 No",
                        key=f"{prefix_key}feedback_no_{row['id']}",
                        use_container_width=True,
                    ):
                        if save_product_feedback(row["id"], False):
                            st.toast("Grazie, useremo la segnalazione per migliorare.")
                        else:
                            st.toast("Feedback non salvato. Riprova più tardi.")

                st.divider()

        if prodotti_correnti_limite < totale_risultati:
            st.markdown("---")
            if st.button(
                "➕ Carica altri prodotti",
                key=f"load_more_{message_index}",
                use_container_width=True,
            ):
                st.session_state[limit_key] += 9
                st.rerun()


# --- GESTIONE CHAT ---
for msg_idx, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "filters" in msg and msg["filters"] is not None:
            display_product_grid(
                filters=msg["filters"],
                message_index=msg_idx,
                user_query=msg.get("user_query", ""),
                precalculated_df=msg.get("df_ranked", msg.get("df_validated")),
            )

if user_input := st.chat_input(
    "Cosa stai cercando? (es: 'Trovami una felpa Nike che non sia nera')"
):
    try:
        user_input = sanitize_query(user_input)
    except InputValidationError as exc:
        st.error(str(exc))
        st.stop()

    request_allowed, recent_requests = check_rate_limit(
        st.session_state.get("request_timestamps", []), time.time()
    )
    st.session_state.request_timestamps = recent_requests
    if not request_allowed:
        st.warning(
            "Hai effettuato troppe ricerche in poco tempo. Attendi un minuto e riprova."
        )
        st.stop()

    with st.chat_message("user"):
        st.markdown(user_input)
    st.session_state.messages.append({"role": "user", "content": user_input})

    with st.spinner("Analisi della richiesta e ricerca nel catalogo..."):
        
        # 1. USIAMO L'IA PER ETRARRE I FILTRI DALLA CHAT (INCLUSO SUB_QUERIES)
        filters_data = extract_all_feed_parameters(
            user_query=user_input, 
            chat_history=st.session_state.get("history_raw", ""), 
            client=client
        )
        if not filters_data:
            logger.warning(
                "Estrazione AI non disponibile: applicato fallback per parole chiave"
            )
            filters_data = {
                "search_keywords": user_input,
                "in_stock_only": True,
            }

        # Funzione di supporto per applicare i filtri manuali della sidebar a qualsiasi dizionario di filtri
        def apply_manual_filters(f_dict):
            if manual_merchant != "Tutti":
                f_dict["merchant"] = manual_merchant
            if manual_gender != "Tutti":
                f_dict["gender"] = manual_gender
            if manual_size != "Tutte":
                f_dict["size"] = manual_size
            if manual_max_price < 250:
                f_dict["max_price"] = float(manual_max_price)
            if manual_on_sale:
                f_dict["only_on_sale"] = True
            return f_dict

        all_results = []
        sub_queries = filters_data.get("sub_queries")

        # 2. INTERROGAZIONE DEL DATABASE (MULTIPLA O SINGOLA)
        if sub_queries and len(sub_queries) > 0:
            # Se ci sono più richieste, le eseguiamo una alla volta applicando i filtri manuali a ognuna
            for sub_f in sub_queries:
                sub_f_with_manual = apply_manual_filters(sub_f.copy())
                clean_sub_f = {k: v for k, v in sub_f_with_manual.items() if v is not None}
                if clean_sub_f:
                    df_part, _ = query_ecommerce_catalog(clean_sub_f, limit=15, offset=0)
                    if not df_part.empty:
                        all_results.append(
                            rank_product_dataframe(df_part, clean_sub_f)
                        )
            
            # Per il debug e la risposta usiamo il dizionario principale o il primo della lista
            json_filters = filters_data
        else:
            # Altrimenti è una ricerca classica singola
            json_filters = apply_manual_filters(filters_data)
            clean_filters = {k: v for k, v in json_filters.items() if k != "sub_queries" and v is not None}
            df_part, _ = query_ecommerce_catalog(clean_filters, limit=30, offset=0)
            if not df_part.empty:
                all_results.append(
                    rank_product_dataframe(df_part, clean_filters)
                )

        if debug_container is not None:
            debug_container.json(json_filters)

        # 3. UNIONE DEI DATAFRAME GREZZI
        if all_results:
            import pandas as pd
            df_raw = (
                pd.concat(all_results, ignore_index=True)
                .sort_values("_match_score", ascending=False, kind="stable")
                .drop_duplicates(subset=["id"])
                .reset_index(drop=True)
            )
        else:
            df_raw = pd.DataFrame()

        totale_risultati = len(df_raw)

        # 4. I risultati sono gia filtrati in SQL e ordinati con regole locali.
        df_ranked = df_raw

        totale_risultati = len(df_ranked) if df_ranked is not None else 0

        # 5. Il conteggio e la risposta non vengono affidati al modello.
        bot_response = generate_natural_response(
            user_input, totale_risultati, json_filters
        )

        if "history_raw" not in st.session_state:
            st.session_state.history_raw = ""

        # Conserva solo filtri strutturati: il testo originale non viene duplicato.
        st.session_state.history_raw = append_filter_history(
            st.session_state.history_raw, json_filters
        )

    with st.chat_message("assistant"):
        st.markdown(bot_response)
        new_msg_index = len(st.session_state.messages)

        display_product_grid(
            filters=json_filters,
            message_index=new_msg_index,
            user_query=user_input,
            precalculated_df=df_ranked,
        )

    # Aggiungi la risposta dell'assistente allo stato della chat
    st.session_state.messages.append({
        "role": "assistant",
        "content": bot_response,
        "filters": json_filters,
        "user_query": user_input,
        "df_ranked": df_ranked,
    })

    # === TAGLIO DELLA CRONOLOGIA VISIBILE (Mantiene solo gli ultimi 10 messaggi) ===
    if len(st.session_state.messages) > 10:
        st.session_state.messages = st.session_state.messages[-10:]

render_footer(site_identity)
