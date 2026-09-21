"use client";

import { useState } from "react";
import { DEMO_DISCLOSURE } from "@/lib/disclosures";
import { formatPrice } from "@/lib/money";
import type { ProductResult, SavedItem } from "@/lib/types";
import { BagIcon, ExternalIcon, HeartIcon, ThumbDownIcon, ThumbUpIcon } from "./icons";
import { useStore } from "./store";

type FeedbackState = "idle" | "sending" | "yes" | "no" | "error";

export function ProductCard({ product, index }: { product: ProductResult; index: number }) {
  const { wishlist, cart, toggleWishlist, toggleCart } = useStore();
  const [feedback, setFeedback] = useState<FeedbackState>("idle");
  const [imgFailed, setImgFailed] = useState(false);

  const onSale = product.sale_price != null && product.sale_price < product.price;
  const current = onSale ? product.sale_price! : product.price;
  const discount = onSale ? Math.round((1 - current / product.price) * 100) : 0;
  const isAwin = product.source === "awin";
  const inWishlist = wishlist.some((i) => i.id === product.id);
  const inCart = cart.some((i) => i.id === product.id);

  const saved: SavedItem = {
    id: product.id,
    title: product.title,
    brand: product.brand,
    size: product.size,
    price: product.price,
    sale_price: product.sale_price,
    currency: product.currency,
  };

  async function sendFeedback(helpful: boolean) {
    setFeedback("sending");
    try {
      const res = await fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ productId: product.id, helpful }),
      });
      setFeedback(res.ok ? (helpful ? "yes" : "no") : "error");
    } catch {
      setFeedback("error");
    }
  }

  return (
    <article
      className="animate-rise group flex flex-col overflow-hidden rounded-2xl border border-line/70 bg-white shadow-[0_1px_0_rgba(50,25,34,0.04)] transition hover:-translate-y-0.5 hover:shadow-lg hover:shadow-wine/5"
      style={{ animationDelay: `${Math.min(index % 9, 8) * 40}ms` }}
    >
      <div className="relative aspect-square overflow-hidden bg-white">
        {product.image_link && !imgFailed ? (
          // eslint-disable-next-line @next/next/no-img-element -- immagini esterne dei negozi
          <img
            src={product.image_link}
            alt={product.title}
            loading="lazy"
            referrerPolicy="no-referrer"
            onError={() => setImgFailed(true)}
            className="size-full object-contain p-4 transition duration-500 group-hover:scale-[1.03]"
          />
        ) : (
          <div className="grid size-full place-items-center bg-blush text-sm text-muted">
            Immagine non disponibile
          </div>
        )}
        {onSale && (
          <span className="absolute left-3 top-3 rounded-full bg-peach px-2.5 py-1 text-xs font-bold text-wine-dark">
            −{discount}%
          </span>
        )}
        <button
          type="button"
          onClick={() => toggleWishlist(saved)}
          aria-pressed={inWishlist}
          aria-label={inWishlist ? "Rimuovi dai preferiti" : "Aggiungi ai preferiti"}
          className={`absolute right-3 top-3 grid size-9 place-items-center rounded-full border backdrop-blur transition ${
            inWishlist
              ? "border-wine bg-wine text-cream"
              : "border-line bg-white/85 text-wine hover:bg-blush"
          }`}
        >
          <HeartIcon filled={inWishlist} width={18} height={18} />
        </button>
      </div>

      <div className="flex flex-1 flex-col gap-3 p-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-muted">
            {product.brand} <span className="text-line">·</span> {product.merchant}
          </p>
          <h3 className="mt-1 font-display text-lg font-semibold leading-snug text-ink">
            {product.title}
          </h3>
          <p className="mt-1 text-sm text-muted">
            {[product.color, product.material, product.size && `Taglie ${product.size}`]
              .filter(Boolean)
              .join(" · ")}
          </p>
        </div>

        <div className="flex items-baseline gap-2">
          <span className="font-display text-2xl font-semibold text-wine">
            {formatPrice(current, product.currency)}
          </span>
          {onSale && (
            <span className="text-sm text-muted line-through">
              {formatPrice(product.price, product.currency)}
            </span>
          )}
        </div>

        {product.reasons.length > 0 && (
          <div>
            <p className="mb-1.5 text-xs font-medium text-muted">Perché lo vedi</p>
            <ul className="flex flex-wrap gap-1.5">
              {product.reasons.map((r) => (
                <li key={r} className="rounded-full bg-wine-soft px-2.5 py-0.5 text-xs text-wine">
                  {r}
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="mt-auto space-y-2 pt-1">
          <div className="flex gap-2">
            <a
              href={product.link}
              target="_blank"
              rel={isAwin ? "sponsored noopener noreferrer" : "noopener noreferrer"}
              className="flex flex-1 items-center justify-center gap-1.5 rounded-full bg-wine px-4 py-2.5 text-sm font-semibold text-cream transition hover:bg-wine-dark"
            >
              {isAwin ? "Vai al negozio" : "Apri prodotto"}
              <ExternalIcon width={16} height={16} />
            </a>
            <button
              type="button"
              onClick={() => toggleCart(saved)}
              aria-pressed={inCart}
              aria-label={inCart ? "Rimuovi dal carrello" : "Aggiungi al carrello"}
              title={inCart ? "Nel carrello" : "Aggiungi al carrello"}
              className={`grid size-11 shrink-0 place-items-center rounded-full border transition ${
                inCart ? "border-wine bg-wine-soft text-wine" : "border-line text-wine hover:bg-blush"
              }`}
            >
              <BagIcon width={18} height={18} />
            </button>
          </div>
          <p className="text-[11px] leading-snug text-muted">
            {isAwin
              ? "Link affiliato: potremmo ricevere una commissione. L'acquisto si conclude sul sito del negozio."
              : DEMO_DISCLOSURE}
            {isAwin && product.source_updated_at && ` Aggiornato: ${product.source_updated_at}.`}
          </p>
        </div>

        <div className="flex items-center justify-between border-t border-line/60 pt-3 text-xs text-muted">
          {feedback === "yes" || feedback === "no" ? (
            <span role="status">
              {feedback === "yes"
                ? "Grazie per il feedback."
                : "Grazie, useremo la segnalazione per migliorare."}
            </span>
          ) : feedback === "error" ? (
            <span role="status">Feedback non salvato. Riprova più tardi.</span>
          ) : (
            <>
              <span>Risultato pertinente?</span>
              <span className="flex gap-1">
                {[true, false].map((helpful) => (
                  <button
                    key={String(helpful)}
                    type="button"
                    disabled={feedback === "sending"}
                    onClick={() => sendFeedback(helpful)}
                    aria-label={helpful ? "Sì, pertinente" : "No, non pertinente"}
                    className="grid size-8 place-items-center rounded-full hover:bg-blush hover:text-wine disabled:opacity-50"
                  >
                    {helpful ? (
                      <ThumbUpIcon width={16} height={16} />
                    ) : (
                      <ThumbDownIcon width={16} height={16} />
                    )}
                  </button>
                ))}
              </span>
            </>
          )}
        </div>
      </div>
    </article>
  );
}
