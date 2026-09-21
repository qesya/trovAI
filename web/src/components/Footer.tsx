import Link from "next/link";
import { connection } from "next/server";
import { siteIdentity } from "@/lib/server/config";
import { NAV_LINKS } from "@/lib/nav";

export async function Footer() {
  await connection();
  const identity = siteIdentity();
  return (
    <footer className="mt-16 border-t border-line/70 bg-blush/50">
      <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-8 text-sm text-muted sm:px-6 md:flex-row md:items-start md:justify-between">
        <p className="max-w-xl leading-relaxed">
          <span className="font-display font-semibold text-wine">{identity.name}</span> · Gestito da{" "}
          {identity.owner ?? "Titolare da configurare"} · Contatti:{" "}
          {identity.contactEmail ?? "Contatto da configurare"}. Acquisti, pagamenti, consegne e resi
          sono gestiti dai rispettivi negozi.
        </p>
        <nav className="flex flex-wrap gap-x-4 gap-y-2" aria-label="Pagine legali">
          {NAV_LINKS.map((l) => (
            <Link key={l.href} href={l.href} className="hover:text-wine hover:underline">
              {l.label}
            </Link>
          ))}
        </nav>
      </div>
    </footer>
  );
}
