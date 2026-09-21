import type { Metadata } from "next";
import { connection } from "next/server";
import { IdentityWarning, InfoPage, Section } from "@/components/InfoPage";
import { siteIdentity } from "@/lib/server/config";

export const metadata: Metadata = { title: "Informativa privacy" };

export default async function Privacy() {
  await connection();
  const identity = siteIdentity();
  const owner = identity.owner ?? "[titolare da configurare]";
  const privacyEmail = identity.privacyEmail ?? "[email privacy da configurare]";

  return (
    <InfoPage
      title="Informativa privacy"
      updated={identity.legalLastUpdated}
      intro={<IdentityWarning identity={identity} />}
    >
      <Section title="Titolare e contatti">
        <p>
          Il titolare del trattamento è {owner}. Contatto privacy: {privacyEmail}.
        </p>
      </Section>
      <Section title="Dati trattati">
        <p>
          Il servizio tratta il testo delle ricerche, i filtri selezionati, le interazioni tecniche
          necessarie alla sessione e gli elementi aggiunti temporaneamente a preferiti o carrello. Non
          inserire dati personali, dati sensibili o informazioni di pagamento nella chat.
        </p>
      </Section>
      <Section title="Finalità">
        <p>
          I dati vengono utilizzati per interpretare la richiesta, cercare prodotti, mantenere la
          sessione e garantire sicurezza e funzionamento del servizio.
        </p>
      </Section>
      <Section title="Fornitori tecnologici">
        <p>
          Il testo della ricerca può essere trasmesso al fornitore del modello di intelligenza
          artificiale configurato dal gestore. Hosting, monitoraggio o analytics possono comportare
          ulteriori trattamenti e dovranno essere indicati qui prima della pubblicazione.
        </p>
      </Section>
      <Section title="Conservazione">
        <p>
          Nella versione attuale chat, preferiti e carrello sono conservati nello stato temporaneo
          della sessione del browser. Eventuali log tecnici del servizio pubblicato dovranno avere
          tempi di conservazione documentati e limitati.
        </p>
      </Section>
      <Section title="Link esterni">
        <p>
          Quando apri il sito di un negozio si applicano la sua informativa privacy e le tecnologie di
          tracciamento del network o del venditore.
        </p>
      </Section>
      <Section title="Diritti">
        <p>
          Per richieste relative ai tuoi dati puoi contattare {privacyEmail}. Prima della
          pubblicazione questa sezione deve essere verificata rispetto alla configurazione reale del
          servizio e alla normativa applicabile.
        </p>
      </Section>
    </InfoPage>
  );
}
