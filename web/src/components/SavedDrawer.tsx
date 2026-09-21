"use client";

import { useEffect, useState } from "react";
import { effectivePrice, formatPrice } from "@/lib/money";
import type { SavedItem } from "@/lib/types";
import { BagIcon, CloseIcon, HeartIcon } from "./icons";
import { useStore } from "./store";

function ItemRow({ item, onRemove }: { item: SavedItem; onRemove: () => void }) {
  const price = effectivePrice(item.price, item.sale_price);
  return (
    <li className="flex items-start gap-3 border-b border-line/60 py-4 last:border-0">
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium text-ink">{item.title}</p>
        <p className="mt-0.5 text-sm text-muted">
          {[item.brand, item.size && `Taglie ${item.size}`].filter(Boolean).join(" · ")}
        </p>
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
  const [checkoutNote, setCheckoutNote] = useState(false);
  const open = drawer !== null;

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setDrawer(null);
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, setDrawer]);

  if (!open) return null;

  const items = drawer === "wishlist" ? wishlist : cart;
  const currencies = new Set(cart.map((i) => i.currency));
  const total = cart.reduce((sum, i) => sum + effectivePrice(i.price, i.sale_price), 0);

  const tab = (key: "wishlist" | "cart", label: string, count: number, icon: React.ReactNode) => (
    <button
      type="button"
      role="tab"
      aria-selected={drawer === key}
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
        className="absolute inset-0 bg-wine-dark/30 backdrop-blur-[2px]"
        onClick={() => setDrawer(null)}
      />
      <aside className="animate-rise absolute inset-y-0 right-0 flex w-full max-w-md flex-col bg-cream shadow-2xl">
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
        <div className="mx-5 flex gap-1 rounded-full bg-blush p-1" role="tablist">
          {tab("wishlist", "Preferiti", wishlist.length, <HeartIcon width={16} height={16} />)}
          {tab("cart", "Carrello", cart.length, <BagIcon width={16} height={16} />)}
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-2">
          {items.length === 0 ? (
            <p className="py-12 text-center text-sm text-muted">
              {drawer === "wishlist" ? "La tua wishlist è vuota." : "Il carrello è vuoto."}
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
                <span className="text-sm text-muted">Totale</span>
                <span className="font-display text-2xl font-semibold text-wine">
                  {formatPrice(total, [...currencies][0])}
                </span>
              </div>
            ) : (
              <p className="text-sm text-muted">
                Il totale non è disponibile perché il carrello contiene prodotti in valute diverse.
              </p>
            )}
            <button
              type="button"
              onClick={() => setCheckoutNote(true)}
              className="mt-3 w-full rounded-full bg-wine py-3 text-sm font-semibold text-cream transition hover:bg-wine-dark"
            >
              Procedi al checkout
            </button>
            {checkoutNote && (
              <p className="mt-3 rounded-xl bg-cream p-3 text-xs leading-relaxed text-muted" role="status">
                Il carrello è una simulazione: gli acquisti vengono completati separatamente sui siti
                dei negozi.
              </p>
            )}
          </div>
        )}
      </aside>
    </div>
  );
}
