"use client";

import { DEFAULT_FILTERS, useStore } from "./store";

const selectClass =
  "mt-1.5 w-full appearance-none rounded-xl border border-line bg-white px-3 py-2.5 text-sm text-ink " +
  "bg-[url('data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2212%22 height=%2212%22 viewBox=%220 0 24 24%22 fill=%22none%22 stroke=%22%23681D35%22 stroke-width=%222.5%22><path d=%22M6 9l6 6 6-6%22/></svg>')] " +
  "bg-[length:12px] bg-[right_0.9rem_center] bg-no-repeat pr-9";

export function FiltersPanel({ merchants, sizes }: { merchants: string[]; sizes: string[] }) {
  const { manualFilters: f, setManualFilters, resetChat, clearSession, messages } = useStore();
  const set = (patch: Partial<typeof f>) => setManualFilters({ ...f, ...patch });
  const active =
    f.merchant !== "Tutti" || f.gender !== "Tutti" || f.size !== "Tutte" || f.maxPrice < 250 || f.onSale;

  return (
    <div className="space-y-6">
      <section>
        <div className="flex items-center justify-between">
          <h2 className="font-display text-lg font-semibold text-wine">Filtri rapidi</h2>
          {active && (
            <button
              type="button"
              onClick={() => setManualFilters(DEFAULT_FILTERS)}
              className="text-xs text-muted underline-offset-2 hover:text-wine hover:underline"
            >
              Azzera
            </button>
          )}
        </div>
        <p className="mt-1 text-xs text-muted">Applicati alla prossima ricerca.</p>

        <div className="mt-4 space-y-4">
          <label className="block text-sm font-medium text-ink">
            Negozio
            <select className={selectClass} value={f.merchant} onChange={(e) => set({ merchant: e.target.value })}>
              <option>Tutti</option>
              {merchants.map((m) => (
                <option key={m}>{m}</option>
              ))}
            </select>
          </label>

          <fieldset>
            <legend className="text-sm font-medium text-ink">Genere</legend>
            <div className="mt-1.5 grid grid-cols-4 gap-1 rounded-xl bg-blush p-1">
              {["Tutti", "Uomo", "Donna", "Unisex"].map((g) => (
                <button
                  key={g}
                  type="button"
                  aria-pressed={f.gender === g}
                  onClick={() => set({ gender: g })}
                  className={`rounded-lg py-1.5 text-xs font-medium transition ${
                    f.gender === g ? "bg-white text-wine shadow-sm" : "text-muted hover:text-wine"
                  }`}
                >
                  {g}
                </button>
              ))}
            </div>
          </fieldset>

          <label className="block text-sm font-medium text-ink">
            Taglia
            <select className={selectClass} value={f.size} onChange={(e) => set({ size: e.target.value })}>
              <option>Tutte</option>
              {sizes.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>

          <label className="block text-sm font-medium text-ink">
            <span className="flex justify-between">
              Prezzo massimo
              <span className="font-semibold text-wine">{f.maxPrice >= 250 ? "Nessun limite" : `€${f.maxPrice}`}</span>
            </span>
            <input
              type="range"
              min={10}
              max={250}
              step={10}
              value={f.maxPrice}
              onChange={(e) => set({ maxPrice: Number(e.target.value) })}
              className="mt-3 w-full accent-wine"
            />
          </label>

          <label className="flex cursor-pointer items-center justify-between rounded-xl border border-line bg-white px-3 py-2.5 text-sm font-medium text-ink">
            Solo prodotti in saldo
            <input
              type="checkbox"
              checked={f.onSale}
              onChange={(e) => set({ onSale: e.target.checked })}
              className="size-4 accent-wine"
            />
          </label>
        </div>
      </section>

      <section className="space-y-2 border-t border-line/70 pt-5">
        <button
          type="button"
          onClick={resetChat}
          disabled={messages.length === 0}
          className="w-full rounded-full border border-line bg-white py-2.5 text-sm font-medium text-wine transition hover:bg-blush disabled:opacity-50"
        >
          Nuova ricerca
        </button>
        <button
          type="button"
          onClick={clearSession}
          className="w-full rounded-full py-2 text-xs text-muted hover:text-wine hover:underline"
        >
          Elimina dati della sessione
        </button>
      </section>

      <section className="rounded-2xl bg-peach-soft p-4 text-xs leading-relaxed text-wine-dark">
        <p className="font-semibold">Trasparenza</p>
        <p className="mt-1">
          I link affiliati sono indicati prima del reindirizzamento. La commissione non viene usata per
          ordinare i risultati.
        </p>
      </section>
    </div>
  );
}
