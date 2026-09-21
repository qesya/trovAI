import "server-only";
import { GoogleGenAI, Type, type Schema } from "@google/genai";
import type { Filters } from "../types";
import { getSetting, requireSetting } from "./config";

// Estrazione dei filtri strutturati con Gemini (porting di extract_all_feed_parameters).

const MODEL = getSetting("GEMINI_MODEL", "gemini-3.1-flash-lite")!;

let client: GoogleGenAI | null = null;
function getClient(): GoogleGenAI {
  if (!client) client = new GoogleGenAI({ apiKey: requireSetting("GEMINI_API_KEY") });
  return client;
}

const str: Schema = { type: Type.STRING, nullable: true };
const logic: Schema = { type: Type.STRING, enum: ["AND", "OR"], nullable: true };

const FILTER_PROPERTIES: Record<string, Schema> = {
  brand: str,
  product_type: str,
  sottocategoria: str,
  gender: str,
  age_group: str,
  color: str,
  color_logic: logic,
  size: str,
  material: str,
  material_logic: logic,
  merchant: str,
  condizione: str,
  min_price: { type: Type.NUMBER, nullable: true },
  max_price: { type: Type.NUMBER, nullable: true },
  only_on_sale: { type: Type.BOOLEAN, nullable: true },
  in_stock_only: { type: Type.BOOLEAN, nullable: true },
  search_keywords: str,
  excluded_color: str,
  excluded_material: str,
  excluded_product_type: str,
  unwanted_features: str,
  sort_by: str,
};

const RESPONSE_SCHEMA: Schema = {
  type: Type.OBJECT,
  properties: {
    ...FILTER_PROPERTIES,
    sub_queries: {
      type: Type.ARRAY,
      items: { type: Type.OBJECT, properties: FILTER_PROPERTIES },
      nullable: true,
    },
  },
};

function buildPrompt(userQuery: string, chatHistory: string): string {
  return `
    Sei il motore di intelligenza artificiale per un grande e-commerce multibrand.
    Analizza la richiesta dell'utente e la cronologia per estrarre tutti i parametri di filtro.

    ### 🚨 REGOLA CRITICA ASSOLUTA (OBBLIGATORIO):
    Se l'utente nomina un capo d'abbigliamento o un articolo specifico (es. "t-shirt", "scarpe", "felpa", "giacca"), DEVI SEMPRE compilare tassativamente:
    1. \`product_type\` (es. "Abbigliamento" o "Scarpe")
    2. \`sottocategoria\` (es. "t-shirt", "Sneakers", "Felpe")
    Non estrarre mai solo il brand (es. se dice "t-shirt Adidas", devi mettere sia \`brand: "Adidas"\` che \`sottocategoria: "t-shirt"\` e \`product_type: "Abbigliamento"\`).

    ### 🚨 REGOLE PER LE CONGIUNZIONI ("E" / "O") SU COLORI E MATERIALI:
    Previa attenzione estrema all'uso delle congiunzioni nei parametri oggettivi:
    1. **Se l'utente usa la congiunzione "E" (AND)** (es. "una felpa bianca e nera", "maglia in cotone e poliestere"):
       - Inserisci i vari elementi separati da virgola nel campo principale (\`color\` o \`material\`), es. \`color: "bianco, nero"\` oppure \`material: "cotone, poliestere"\`.
       - Imposta tassativamente la relativa logica su \`"AND"\` (\`color_logic: "AND"\` oppure \`material_logic: "AND"\`). Questo servirà al sistema per applicare un filtro rigoroso e scartare i prodotti che non contengono contemporaneamente tutti gli elementi nello stesso campo.
    2. **Se l'utente usa la congiunzione "O" (OR)** (es. "una felpa bianca o nera"):
       - Inserisci gli elementi separati da virgola nel campo, es. \`color: "bianco, nero"\`.
       - Imposta la logica su \`"OR"\` (\`color_logic: "OR"\`).

    ### 🚨 REGOLA PER RICHIESTE GENERICHE O STILISTICHE (ES. "qualcosa di sportivo", "elegante", "estivo"):
    Se l'utente fa una richiesta di stile o generale (es. "mostrami qualcosa di sportivo") senza specificare un singolo capo preciso:
    - Lascia a \`null\` o non forzare i campi rigidi come \`sottocategoria\` o \`product_type\` (a meno che non siano ovvi).
    - DEVI popolare riccamente il campo \`search_keywords\` inserendo una lista di parole chiave, sinonimi e capi coerenti con lo stile richiesto.

    ### REGOLA PER RICHIESTE MULTIPLE (ES. "X di un colore e Y di un altro"):
    Se l'utente chiede più articoli diversi con caratteristiche o colori differenti nella stessa frase (es. "una felpa bianca e delle scarpe nere"), NON mescolare i filtri in un unico oggetto.
    DEVI popolare la lista \`sub_queries\` creando un oggetto separato per ciascun articolo menzionato.

    ### REGOLE RIGOROSE PER LE NEGAZIONI E LE ESCLUSIONI:
    1. Se l'utente esprime una negazione o un'esclusione (es. "non nero", "senza cappuccio", "non in lana"):
       - Cattura il termine esatto e inseriscilo nell'apposito campo (\`excluded_color\`, \`excluded_material\`, \`excluded_product_type\`, oppure \`unwanted_features\`).

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

    Cronologia: ${chatHistory}
    Nuovo Messaggio: "${userQuery}"
    `;
}

/** Restituisce i filtri estratti, oppure null se il modello non e disponibile. */
export async function extractFilters(
  userQuery: string,
  chatHistory: string,
): Promise<Filters | null> {
  const maxRetries = 3;
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      const response = await getClient().models.generateContent({
        model: MODEL,
        contents: buildPrompt(userQuery, chatHistory),
        config: { responseMimeType: "application/json", responseSchema: RESPONSE_SCHEMA },
      });
      const parsed = JSON.parse(response.text ?? "{}");
      return parsed && typeof parsed === "object" ? (parsed as Filters) : null;
    } catch (error) {
      const message = String(error);
      const retryable = message.includes("503") || message.includes("429");
      if (retryable && attempt < maxRetries - 1) {
        await new Promise((r) => setTimeout(r, 2000 * (attempt + 1)));
        continue;
      }
      console.error("Estrazione Gemini non riuscita:", message.slice(0, 300));
      return null;
    }
  }
  return null;
}
