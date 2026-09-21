"use client";

import { useEffect, useRef, useState } from "react";
import {
  AFFILIATE_DISCLOSURE,
  AFFILIATE_DISCLOSURE_TITLE,
  AI_DISCLOSURE,
  MERCHANT_DISCLOSURE,
  RANKING_DISCLOSURE,
} from "@/lib/disclosures";
import type { SearchResponse } from "@/lib/types";
import { FiltersPanel } from "./FiltersPanel";
import { CloseIcon, InfoIcon, SendIcon, SlidersIcon, SparkIcon } from "./icons";
import { ProductCard } from "./ProductCard";
import { useStore, type ChatMessage } from "./store";

const SUGGESTIONS = [
  "Una felpa Nike che non sia nera",
  "Sneakers bianche sotto i 100€",
  "Qualcosa di sportivo in saldo",
  "Una giacca e delle scarpe nere",
];

const PAGE_SIZE = 9;
const MAX_QUERY = 500;

const uid = () => Math.random().toString(36).slice(2, 10);

function ProductGrid({ message }: { message: ChatMessage }) {
  const [visible, setVisible] = useState(PAGE_SIZE);
  const products = message.products ?? [];
  if (!products.length) return null;
  const shown = products.slice(0, visible);

  return (
    <div className="mt-4">
      <p className="mb-3 text-sm text-muted">
        Mostrati <strong className="text-ink">{shown.length}</strong> di {products.length} prodotti,
        ordinati per pertinenza
      </p>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {shown.map((p, i) => (
          <ProductCard key={p.id} product={p} index={i} />
        ))}
      </div>
      {visible < products.length && (
        <button
          type="button"
          onClick={() => setVisible((v) => v + PAGE_SIZE)}
          className="mx-auto mt-5 block rounded-full border border-line bg-white px-6 py-2.5 text-sm font-medium text-wine transition hover:bg-blush"
        >
          Carica altri prodotti
        </button>
      )}
    </div>
  );
}

function Message({ message }: { message: ChatMessage }) {
  if (message.role === "user") {
    return (
      <div className="animate-rise flex justify-end">
        <p className="max-w-[85%] rounded-3xl rounded-br-md bg-wine px-4 py-2.5 text-cream">
          {message.content}
        </p>
      </div>
    );
  }
  return (
    <div className="animate-rise">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-full bg-peach text-wine-dark">
          <SparkIcon width={16} height={16} />
        </span>
        <p
          className={`rounded-3xl rounded-tl-md px-4 py-2.5 ${
            message.error ? "bg-red-50 text-red-900" : "bg-white text-ink ring-1 ring-line/70"
          }`}
        >
          {message.content}
        </p>
      </div>
      {message.debugFilters && (
        <details className="ml-11 mt-2 text-xs text-muted">
          <summary className="cursor-pointer">Parametri IA (debug)</summary>
          <pre className="mt-1 overflow-x-auto rounded-lg bg-white p-3 ring-1 ring-line/70">
            {JSON.stringify(message.debugFilters, null, 2)}
          </pre>
        </details>
      )}
      <ProductGrid message={message} />
    </div>
  );
}

function Disclosure() {
  return (
    <div className="rounded-2xl border border-peach/60 bg-peach-soft/70 p-4 text-sm leading-relaxed text-wine-dark">
      <p>
        <strong>{AFFILIATE_DISCLOSURE_TITLE}:</strong> {AFFILIATE_DISCLOSURE} {RANKING_DISCLOSURE}
      </p>
      <details className="mt-2 group">
        <summary className="inline-flex cursor-pointer items-center gap-1 font-medium text-wine hover:underline">
          <InfoIcon width={15} height={15} /> Come vengono ordinati i risultati
        </summary>
        <div className="mt-2 space-y-1.5 text-wine-dark/90">
          <p>
            Il punteggio considera marca, categoria, colore, materiale, taglia, genere, negozio e parole
            chiave. Prezzo e disponibilità sono filtri, non informazioni generate dal modello.
          </p>
          <p>{AI_DISCLOSURE}</p>
          <p>{MERCHANT_DISCLOSURE}</p>
        </div>
      </details>
    </div>
  );
}

export function ShoppingChat({
  merchants,
  sizes,
  productCount,
}: {
  merchants: string[];
  sizes: string[];
  productCount: number;
}) {
  const { messages, history, manualFilters, addMessages, pushHistory, hydrated } = useStore();
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const lastUserMsg = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (loading) endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    else if (messages.length) lastUserMsg.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [messages.length, loading]);

  async function search(raw: string) {
    const query = raw.trim();
    if (!query || loading) return;
    setInput("");
    addMessages({ id: uid(), role: "user", content: query });
    setLoading(true);
    try {
      const res = await fetch("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, history, manualFilters }),
      });
      const data = (await res.json()) as SearchResponse & { error?: string };
      if (!res.ok) {
        addMessages({ id: uid(), role: "assistant", content: data.error ?? "Errore imprevisto.", error: true });
        return;
      }
      addMessages({
        id: uid(),
        role: "assistant",
        content: data.message,
        products: data.products,
        filters: data.filters,
        debugFilters: data.debugFilters,
      });
      pushHistory(data.filters);
    } catch {
      addMessages({
        id: uid(),
        role: "assistant",
        content: "Connessione non riuscita. Controlla la rete e riprova.",
        error: true,
      });
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }

  const lastUserIndex = messages.findLastIndex((m) => m.role === "user");
  const empty = hydrated && messages.length === 0;

  return (
    <div className="mx-auto flex max-w-7xl gap-8 px-4 sm:px-6">
      <aside className="sticky top-24 hidden h-fit w-72 shrink-0 py-8 lg:block">
        <FiltersPanel merchants={merchants} sizes={sizes} />
      </aside>

      <div className="flex min-h-[calc(100dvh-4rem)] min-w-0 flex-1 flex-col">
        {empty ? (
          <section className="flex flex-col items-center py-12 text-center sm:py-20">
            <span className="rounded-full bg-peach-soft px-3 py-1 text-xs font-medium text-wine">
              {productCount} prodotti nel catalogo
            </span>
            <h1 className="mt-5 max-w-2xl font-display text-4xl font-semibold leading-tight tracking-tight text-wine sm:text-5xl">
              Descrivi cosa cerchi, <span className="italic text-wine-dark/80">come lo diresti a un amico.</span>
            </h1>
            <p className="mt-4 max-w-xl text-muted">
              Trova prodotti usando il linguaggio naturale e confronta le opzioni prima di acquistare sul
              sito del negozio.
            </p>
            <div className="mt-8 flex max-w-2xl flex-wrap justify-center gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => search(s)}
                  className="rounded-full border border-line bg-white px-4 py-2 text-sm text-ink transition hover:border-wine hover:text-wine"
                >
                  {s}
                </button>
              ))}
            </div>
            <div className="mt-10 w-full max-w-2xl text-left">
              <Disclosure />
            </div>
          </section>
        ) : (
          <div className="flex-1 space-y-6 py-8">
            <Disclosure />
            {messages.map((m, i) => (
              <div key={m.id} ref={i === lastUserIndex ? lastUserMsg : undefined} className="scroll-mt-24">
                <Message message={m} />
              </div>
            ))}
            {loading && (
              <div className="flex items-center gap-3 text-sm text-muted" role="status">
                <span className="grid size-8 place-items-center rounded-full bg-peach text-wine-dark">
                  <SparkIcon width={16} height={16} className="animate-spin [animation-duration:2.5s]" />
                </span>
                Analisi della richiesta e ricerca nel catalogo…
              </div>
            )}
            <div ref={endRef} />
          </div>
        )}

        <form
          onSubmit={(e) => {
            e.preventDefault();
            search(input);
          }}
          className="sticky bottom-0 bg-gradient-to-t from-cream via-cream to-cream/0 pb-4 pt-6"
        >
          <div className="flex items-end gap-2 rounded-3xl border border-line bg-white p-2 shadow-lg shadow-wine/5 focus-within:border-wine">
            <button
              type="button"
              onClick={() => setFiltersOpen(true)}
              aria-label="Filtri rapidi"
              className="grid size-10 shrink-0 place-items-center rounded-full text-wine hover:bg-blush lg:hidden"
            >
              <SlidersIcon />
            </button>
            <textarea
              ref={inputRef}
              rows={1}
              value={input}
              maxLength={MAX_QUERY}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  search(input);
                }
              }}
              placeholder="Cosa stai cercando? Es. “una felpa Nike che non sia nera”"
              aria-label="Cosa stai cercando?"
              className="max-h-40 min-h-10 flex-1 resize-none bg-transparent px-2 py-2 text-ink outline-none placeholder:text-muted/70 [field-sizing:content]"
            />
            <button
              type="submit"
              disabled={!input.trim() || loading}
              aria-label="Cerca"
              className="grid size-10 shrink-0 place-items-center rounded-full bg-wine text-cream transition hover:bg-wine-dark disabled:bg-line disabled:text-white"
            >
              <SendIcon />
            </button>
          </div>
          <p className="mt-2 text-center text-[11px] text-muted">
            Non inserire dati personali o di pagamento. {input.length > 400 && `${input.length}/${MAX_QUERY}`}
          </p>
        </form>
      </div>

      {filtersOpen && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Filtri rapidi">
          <button
            type="button"
            aria-label="Chiudi"
            className="absolute inset-0 bg-wine-dark/30"
            onClick={() => setFiltersOpen(false)}
          />
          <div className="animate-rise absolute inset-x-0 bottom-0 max-h-[85dvh] overflow-y-auto rounded-t-3xl bg-cream p-5">
            <div className="mb-2 flex justify-end">
              <button
                type="button"
                onClick={() => setFiltersOpen(false)}
                aria-label="Chiudi filtri"
                className="grid size-9 place-items-center rounded-full hover:bg-blush"
              >
                <CloseIcon />
              </button>
            </div>
            <FiltersPanel merchants={merchants} sizes={sizes} />
          </div>
        </div>
      )}
    </div>
  );
}
