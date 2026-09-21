import type { Metadata } from "next";
import { Callout, InfoPage, Section } from "@/components/InfoPage";
import {
  AFFILIATE_DISCLOSURE,
  AFFILIATE_DISCLOSURE_TITLE,
  AI_DISCLOSURE,
  MERCHANT_DISCLOSURE,
  RANKING_DISCLOSURE,
} from "@/lib/disclosures";

export const metadata: Metadata = { title: "Trasparenza e affiliazioni" };

export default function Trasparenza() {
  return (
    <InfoPage
      title="Trasparenza e affiliazioni"
      intro={
        <Callout>
          <strong>{AFFILIATE_DISCLOSURE_TITLE}:</strong> {AFFILIATE_DISCLOSURE} {RANKING_DISCLOSURE}
        </Callout>
      }
    >
      <Section title="Che cosa significa">
        <p>
          Un link affiliato consente di attribuire al nostro servizio una visita o un eventuale
          acquisto. La commissione viene riconosciuta dal negozio o dal network di affiliazione e non
          aggiunge un costo specifico al tuo ordine.
        </p>
      </Section>
      <Section title="Come ordiniamo i risultati">
        <p>{RANKING_DISCLOSURE}</p>
        <p>
          I fattori considerati sono marca, tipologia, sottocategoria, colore, materiale, genere,
          taglia, negozio e corrispondenza delle parole chiave. A parità di punteggio viene mantenuto
          un ordine stabile.
        </p>
      </Section>
      <Section title="Ruolo dell'intelligenza artificiale">
        <p>{AI_DISCLOSURE}</p>
      </Section>
      <Section title="Rapporto con negozi e network">
        <p>
          La presenza di un link non implica che il negozio, Awin o un altro network abbia
          sponsorizzato, approvato o realizzato TrovAI. Eventuali marchi appartengono ai rispettivi
          titolari.
        </p>
      </Section>
      <Section title="Dati commerciali">
        <p>
          Prezzi, sconti e disponibilità possono cambiare. Fanno fede esclusivamente le condizioni
          mostrate dal negozio prima dell&apos;acquisto.
        </p>
      </Section>
      <Section title="Chi conclude la vendita">
        <p>{MERCHANT_DISCLOSURE}</p>
      </Section>
    </InfoPage>
  );
}
