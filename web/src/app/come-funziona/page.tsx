import type { Metadata } from "next";
import { Callout, InfoPage, Section } from "@/components/InfoPage";
import {
  AFFILIATE_DISCLOSURE,
  AFFILIATE_DISCLOSURE_TITLE,
  AI_DISCLOSURE,
  MERCHANT_DISCLOSURE,
  RANKING_DISCLOSURE,
} from "@/lib/disclosures";

export const metadata: Metadata = { title: "Come funziona" };

export default function ComeFunziona() {
  return (
    <InfoPage
      title="Come funziona TrovAI"
      intro="TrovAI aiuta a cercare prodotti in un catalogo di negozi terzi usando linguaggio naturale e filtri tradizionali. Non vende direttamente prodotti."
    >
      <Section step={1} title="Comprendiamo la richiesta">
        <p>
          Il testo inserito viene analizzato per individuare caratteristiche come categoria, marca,
          colore, taglia e fascia di prezzo.
        </p>
      </Section>
      <Section step={2} title="Interroghiamo il catalogo">
        <p>
          I filtri vengono applicati al catalogo disponibile. Prezzi, immagini, disponibilità e
          descrizioni provengono dai dati associati ai negozi.
        </p>
      </Section>
      <Section step={3} title="Ordiniamo i risultati">
        <p>{RANKING_DISCLOSURE}</p>
        <p>{AI_DISCLOSURE}</p>
      </Section>
      <Section step={4} title="Completi l'acquisto sul sito del negozio">
        <p>{MERCHANT_DISCLOSURE}</p>
      </Section>
      <Callout>
        <strong>{AFFILIATE_DISCLOSURE_TITLE}:</strong> {AFFILIATE_DISCLOSURE} {RANKING_DISCLOSURE}
      </Callout>
    </InfoPage>
  );
}
