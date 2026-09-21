import type { ReactNode } from "react";
import type { SiteIdentity } from "@/lib/server/config";

export function InfoPage({
  title,
  intro,
  updated,
  children,
}: {
  title: string;
  intro?: ReactNode;
  updated?: string;
  children: ReactNode;
}) {
  return (
    <article className="mx-auto max-w-3xl px-4 py-12 sm:px-6 sm:py-16">
      <h1 className="font-display text-4xl font-semibold tracking-tight text-wine sm:text-5xl">{title}</h1>
      {updated && <p className="mt-3 text-sm text-muted">Ultimo aggiornamento: {updated}</p>}
      {intro && <div className="mt-5 text-lg leading-relaxed text-ink/90">{intro}</div>}
      <div className="mt-10 space-y-10">{children}</div>
    </article>
  );
}

export function Section({ title, step, children }: { title: string; step?: number; children: ReactNode }) {
  return (
    <section className="flex gap-4">
      {step != null && (
        <span className="grid size-9 shrink-0 place-items-center rounded-full bg-peach font-display font-semibold text-wine-dark">
          {step}
        </span>
      )}
      <div>
        <h2 className="font-display text-2xl font-semibold text-ink">{title}</h2>
        <div className="mt-3 space-y-3 leading-relaxed text-ink/85">{children}</div>
      </div>
    </section>
  );
}

export function Callout({ children, tone = "peach" }: { children: ReactNode; tone?: "peach" | "warn" }) {
  return (
    <div
      className={`rounded-2xl p-4 text-sm leading-relaxed ${
        tone === "warn"
          ? "border border-amber-300 bg-amber-50 text-amber-950"
          : "border border-peach/60 bg-peach-soft/70 text-wine-dark"
      }`}
    >
      {children}
    </div>
  );
}

export function IdentityWarning({ identity }: { identity: SiteIdentity }) {
  if (identity.isComplete) return null;
  return (
    <Callout tone="warn">
      Questa pagina contiene informazioni legali da completare prima della pubblicazione. Configura
      SITE_OWNER, CONTACT_EMAIL e PRIVACY_EMAIL.
    </Callout>
  );
}
