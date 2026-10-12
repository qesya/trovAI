"use client";

import { useCallback, useRef } from "react";
import { useDialogFocus } from "@/lib/use-dialog-focus";
import { effectivePrice, formatPrice } from "@/lib/money";
import type { SavedItem } from "@/lib/types";
import { BagIcon, CloseIcon, HeartIcon } from "./icons";
import { sizeLabel } from "@/lib/product-size";
import { useStore } from "./store";

function ItemRow({ item, onRemove }: { item: SavedItem; onRemove: () => void }) {
  const price = effectivePrice(item.price, item.sale_price);
  // Anche i vecchi elementi di sessione possono non avere un link.
  let link: string | null = null;
  try {
    if (item.link && new URL(item.link).protocol === "https:") link = item.link;
  } catch { /* Link non valido: serve una nuova ricerca. */ }
  return (
    <li className="flex items-start gap-3 border-b border-line/60 py-4 last:border-0">
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium text-ink">{item.title}</p>
        <p className="mt-0.5 text-sm text-muted">
          {[item.merchant, item.brand, sizeLabel(item.size, item.title)].filter(Boolean).join(" · ")}
        </p>
        {link ? (
          <a href={link} target="_blank" rel="sponsored noopener noreferrer"
            className="mt-2 inline-block text-sm font-semibold text-wine underline underline-offset-4">
            Vai al negozio{item.merchant ? ` · ${item.merchant}` : ""}
          </a>
        ) : (
          <p className="mt-2 text-xs text-muted">Ripeti la ricerca per aprire il negozio.</p>
        )}
      </div>
      <div className="flex flex-col items-end gap-1">
        <span className="font-semibold text-wine">{formatPrice(price, item.currency)}</span>
        <button
          type="button"
          onClick={onRemove}
          className="text-xs text-muted underline-offset-2 hover:text-wine hover:underline"
        >
          Rimuovi
        </button>
      </div>
    </li>
  );
}

export function SavedDrawer() {
  const { drawer, setDrawer, wishlist, cart, toggleWishlist, toggleCart } = useStore();
  const open = drawer !== null;
  const panel = useRef<HTMLElement>(null);
  const close = useCallback(() => setDrawer(null), [setDrawer]);
  useDialogFocus(panel, open, close);

  if (!open) return null;

  const items = drawer === "wishlist" ? wishlist : cart;
  const currencies = new Set(cart.map((i) => i.currency));
  const total = cart.reduce((sum, i) => sum + effectivePrice(i.price, i.sale_price), 0);

  const tab = (key: "wishlist" | "cart", label: string, count: number, icon: React.ReactNode) => (
    <button
      type="button"
      aria-pressed={drawer === key}
      onClick={() => setDrawer(key)}
      className={`flex flex-1 items-center justify-center gap-2 rounded-full py-2 text-sm font-medium transition ${
        drawer === key ? "bg-wine text-cream" : "text-muted hover:bg-blush"
      }`}
    >
      {icon}
      {label} ({count})
    </button>
  );

  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label="I tuoi spazi">
      <button
        type="button"
        aria-label="Chiudi"
        tabIndex={-1}
        className="absolute inset-0 bg-wine-dark/30 backdrop-blur-[2px]"
        onClick={() => setDrawer(null)}
      />
      <aside ref={panel} tabIndex={-1} className="animate-rise absolute inset-y-0 right-0 flex w-full max-w-md flex-col bg-cream shadow-2xl">
        <div className="flex items-center justify-between px-5 pb-3 pt-5">
          <h2 className="font-display text-xl font-semibold text-wine">I tuoi spazi</h2>
          <button
            type="button"
            onClick={() => setDrawer(null)}
            aria-label="Chiudi pannello"
            className="grid size-9 place-items-center rounded-full hover:bg-blush"
          >
            <CloseIcon />
          </button>
        </div>
        <div className="mx-5 flex gap-1 rounded-full bg-blush p-1" role="group" aria-label="Prodotti salvati">
          {tab("wishlist", "Preferiti", wishlist.length, <HeartIcon width={16} height={16} />)}
          {tab("cart", "Lista", cart.length, <BagIcon width={16} height={16} />)}
        </div>

        <p className="px-5 pt-3 text-xs leading-relaxed text-muted">
          I link ai negozi possono essere affiliati: potremmo ricevere una commissione.
        </p>
        <div className="flex-1 overflow-y-auto px-5 py-2">
          {items.length === 0 ? (
            <p className="py-12 text-center text-sm text-muted">
              {drawer === "wishlist" ? "La tua wishlist è vuota." : "La tua lista è vuota."}
            </p>
          ) : (
            <ul>
              {items.map((item) => (
                <ItemRow
                  key={item.id}
                  item={item}
                  onRemove={() => (drawer === "wishlist" ? toggleWishlist(item) : toggleCart(item))}
                />
              ))}
            </ul>
          )}
        </div>

        {drawer === "cart" && cart.length > 0 && (
          <div className="border-t border-line/70 bg-blush/40 px-5 py-4">
            {currencies.size === 1 ? (
              <div className="flex items-baseline justify-between">
                <span className="text-sm text-muted">Totale indicativo</span>
                <span className="font-display text-2xl font-semibold text-wine">
                  {formatPrice(total, [...currencies][0])}
                </span>
              </div>
            ) : (
              <p className="text-sm text-muted">
                Il totale non è disponibile perché la lista contiene prodotti in valute diverse.
              </p>
            )}
            <p className="mt-3 text-xs leading-relaxed text-muted">
              Acquisti separatamente sui siti dei negozi. Prezzi, disponibilità e spese di spedizione
              sono confermati dal partner. TrovAI non gestisce ordini o pagamenti.
            </p>
          </div>
        )}
      </aside>
    </div>
  );
}
