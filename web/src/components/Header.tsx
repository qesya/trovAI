"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { NAV_LINKS } from "@/lib/nav";
import { BagIcon, CloseIcon, HeartIcon, MenuIcon } from "./icons";
import { useStore } from "./store";


function CountButton({
  label,
  count,
  onClick,
  children,
}: {
  label: string;
  count: number;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={`${label} (${count})`}
      className="relative grid size-10 place-items-center rounded-full text-wine transition hover:bg-blush"
    >
      {children}
      {count > 0 && (
        <span className="absolute -right-0.5 -top-0.5 grid min-w-5 place-items-center rounded-full bg-wine px-1 text-[11px] font-semibold leading-5 text-cream">
          {count}
        </span>
      )}
    </button>
  );
}

export function Header() {
  const { wishlist, cart, setDrawer } = useStore();
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <header className="sticky top-0 z-30 border-b border-line/70 bg-cream/85 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-7xl items-center gap-4 px-4 sm:px-6">
        <Link href="/" className="shrink-0" aria-label="TrovAI, torna alla ricerca">
          <Image
            src="/trovai-logo-primary.png"
            alt="TrovAI"
            width={1974}
            height={797}
            priority
            sizes="112px"
            className="h-9 w-auto"
          />
        </Link>

        <nav className="ml-4 hidden items-center gap-1 lg:flex" aria-label="Pagine informative">
          {NAV_LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className={`rounded-full px-3 py-1.5 text-sm transition hover:bg-blush ${
                pathname === l.href ? "bg-blush font-medium text-wine" : "text-muted"
              }`}
            >
              {l.label}
            </Link>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-1">
          <CountButton label="Preferiti" count={wishlist.length} onClick={() => setDrawer("wishlist")}>
            <HeartIcon />
          </CountButton>
          <CountButton label="Carrello" count={cart.length} onClick={() => setDrawer("cart")}>
            <BagIcon />
          </CountButton>
          <button
            type="button"
            className="grid size-10 place-items-center rounded-full text-wine hover:bg-blush lg:hidden"
            aria-label={menuOpen ? "Chiudi menu" : "Apri menu"}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((o) => !o)}
          >
            {menuOpen ? <CloseIcon /> : <MenuIcon />}
          </button>
        </div>
      </div>

      {menuOpen && (
        <nav className="border-t border-line/70 px-4 py-2 lg:hidden" aria-label="Pagine informative">
          {NAV_LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              onClick={() => setMenuOpen(false)}
              className="block rounded-lg px-3 py-2.5 text-sm text-ink hover:bg-blush"
            >
              {l.label}
            </Link>
          ))}
        </nav>
      )}
    </header>
  );
}
