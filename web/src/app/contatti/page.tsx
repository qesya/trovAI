import type { Metadata } from "next";
import { connection } from "next/server";
import { Callout, IdentityWarning, InfoPage } from "@/components/InfoPage";
import { siteIdentity } from "@/lib/server/config";

export const metadata: Metadata = { title: "Contatti" };

export default async function Contatti() {
  await connection();
  const identity = siteIdentity();

  return (
    <InfoPage
      title="Contatti"
      intro={
        <>
          <IdentityWarning identity={identity} />
          <p className="mt-5">
            Puoi contattarci per assistenza sul funzionamento di TrovAI, segnalazioni relative ai
            risultati o richieste sulla privacy.
          </p>
        </>
      }
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="rounded-2xl border border-line/70 bg-white p-5">
          <p className="text-sm text-muted">Supporto generale</p>
          <p className="mt-1 font-medium text-ink">{identity.contactEmail ?? "[email da configurare]"}</p>
          {identity.contactEmail && (
            <a
              href={`mailto:${identity.contactEmail}`}
              className="mt-4 inline-block rounded-full bg-wine px-5 py-2.5 text-sm font-semibold text-cream hover:bg-wine-dark"
            >
              Scrivi al supporto
            </a>
          )}
        </div>
        <div className="rounded-2xl border border-line/70 bg-white p-5">
          <p className="text-sm text-muted">Richieste privacy</p>
          <p className="mt-1 font-medium text-ink">{identity.privacyEmail ?? "[email da configurare]"}</p>
        </div>
      </div>
      <Callout>
        Per problemi con un ordine, un pagamento, una consegna o un reso devi contattare direttamente
        il negozio presso cui hai effettuato l&apos;acquisto.
      </Callout>
    </InfoPage>
  );
}
