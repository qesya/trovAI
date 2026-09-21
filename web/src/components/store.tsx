"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { Filters, ManualFilters, ProductResult, SavedItem } from "@/lib/types";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  products?: ProductResult[];
  filters?: Filters;
  debugFilters?: Filters;
  error?: boolean;
}

export const DEFAULT_FILTERS: ManualFilters = {
  merchant: "Tutti",
  gender: "Tutti",
  size: "Tutte",
  maxPrice: 250,
  onSale: false,
};

interface State {
  messages: ChatMessage[];
  history: Filters[];
  wishlist: SavedItem[];
  cart: SavedItem[];
  manualFilters: ManualFilters;
}

const EMPTY: State = {
  messages: [],
  history: [],
  wishlist: [],
  cart: [],
  manualFilters: DEFAULT_FILTERS,
};

const STORAGE_KEY = "trovai-session-v1";
const MAX_MESSAGES = 10;

interface Store extends State {
  hydrated: boolean;
  drawer: "wishlist" | "cart" | null;
  setDrawer: (d: "wishlist" | "cart" | null) => void;
  addMessages: (...msgs: ChatMessage[]) => void;
  pushHistory: (f: Filters) => void;
  toggleWishlist: (item: SavedItem) => void;
  toggleCart: (item: SavedItem) => void;
  setManualFilters: (f: ManualFilters) => void;
  resetChat: () => void;
  clearSession: () => void;
}

const StoreContext = createContext<Store | null>(null);

function toggle(list: SavedItem[], item: SavedItem) {
  return list.some((i) => i.id === item.id)
    ? list.filter((i) => i.id !== item.id)
    : [...list, item];
}

export function StoreProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>(EMPTY);
  const [hydrated, setHydrated] = useState(false);
  const [drawer, setDrawer] = useState<"wishlist" | "cart" | null>(null);
  const skipSave = useRef(true);

  // I dati restano solo per la sessione del browser, come descritto nell'informativa.
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      if (raw) {
        const saved = JSON.parse(raw) as Partial<State>;
        // eslint-disable-next-line react-hooks/set-state-in-effect -- lettura una tantum da sessionStorage
        setState({ ...EMPTY, ...saved, manualFilters: { ...DEFAULT_FILTERS, ...saved.manualFilters } });
      }
    } catch {
      // sessionStorage non disponibile: si riparte vuoti
    }
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (skipSave.current) {
      skipSave.current = false;
      return;
    }
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {
      // ignorato
    }
  }, [state]);

  const addMessages = useCallback((...msgs: ChatMessage[]) => {
    setState((s) => ({ ...s, messages: [...s.messages, ...msgs].slice(-MAX_MESSAGES) }));
  }, []);

  const pushHistory = useCallback((f: Filters) => {
    setState((s) => ({ ...s, history: [...s.history, f].slice(-5) }));
  }, []);

  const store = useMemo<Store>(
    () => ({
      ...state,
      hydrated,
      drawer,
      setDrawer,
      addMessages,
      pushHistory,
      toggleWishlist: (item) => setState((s) => ({ ...s, wishlist: toggle(s.wishlist, item) })),
      toggleCart: (item) => setState((s) => ({ ...s, cart: toggle(s.cart, item) })),
      setManualFilters: (manualFilters) => setState((s) => ({ ...s, manualFilters })),
      resetChat: () => setState((s) => ({ ...s, messages: [], history: [] })),
      clearSession: () => {
        try {
          sessionStorage.removeItem(STORAGE_KEY);
        } catch {
          // ignorato
        }
        setState(EMPTY);
      },
    }),
    [state, hydrated, drawer, addMessages, pushHistory],
  );

  return <StoreContext.Provider value={store}>{children}</StoreContext.Provider>;
}

export function useStore(): Store {
  const ctx = useContext(StoreContext);
  if (!ctx) throw new Error("useStore deve essere usato dentro StoreProvider");
  return ctx;
}
