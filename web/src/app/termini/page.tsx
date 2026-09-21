import type { Metadata } from "next";
import { connection } from "next/server";
import { IdentityWarning, InfoPage, Section } from "@/components/InfoPage";
import { AFFILIATE_DISCLOSURE, RANKING_DISCLOSURE } from "@/lib/disclosures";
import { siteIdentity } from "@/lib/server/config";

export const metadata: Metadata = { title: "Termini d'uso" };

export default async function Termini() {
  await connection();
  const identity = siteIdentity();

  return (
    <InfoPage
      title="Termini d'uso"
      updated={identity.legalLastUpdated}
      intro={<IdentityWarning identity={identity} />}
    >
      <Section title="Natura del servizio">
        <p>
          TrovAI è uno strumento informativo di ricerca e confronto. Non è il venditore, non conclude
          il contratto di acquisto e non incassa il pagamento.
        </p>
      </Section>
      <Section title="Accuratezza delle informazioni">
        <p>
          Cerchiamo di mostrare dati aggiornati, ma prezzi, disponibilità, immagini e condizioni
          possono contenere ritardi o errori. Prima dell&apos;ordine fanno fede le informazioni
          pubblicate dal negozio.
        </p>
      </Section>
      <Section title="Risposte generate con AI">
        <p>
          L&apos;intelligenza artificiale può interpretare in modo inesatto una richiesta. I risultati
          non costituiscono consulenza professionale né garanzia di idoneità di un prodotto.
        </p>
      </Section>
      <Section title="Acquisti e assistenza">
        <p>
          Ordini, pagamenti, spedizioni, garanzie, resi e rimborsi sono disciplinati dai termini del
          negozio scelto e devono essere gestiti con quel negozio.
        </p>
      </Section>
      <Section title="Uso consentito">
        <p>
          Non è consentito utilizzare il servizio per attività illecite, tentare di comprometterne la
          sicurezza o effettuare interrogazioni automatizzate che ne pregiudichino il funzionamento.
        </p>
      </Section>
      <Section title="Affiliazioni">
        <p>{AFFILIATE_DISCLOSURE}</p>
        <p>{RANKING_DISCLOSURE}</p>
      </Section>
    </InfoPage>
  );
}
