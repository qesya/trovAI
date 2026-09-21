import type { ManualFilters } from "@/lib/types";
import { ConfigurationError } from "@/lib/server/config";
import { runSearch } from "@/lib/server/search";
import {
  InputValidationError,
  buildFilterHistory,
  checkRateLimit,
  sanitizeQuery,
} from "@/lib/server/security";

function clientKey(request: Request): string {
  return (
    request.headers.get("x-forwarded-for")?.split(",")[0].trim() ||
    request.headers.get("x-real-ip") ||
    "local"
  );
}

function parseManual(value: unknown): ManualFilters | undefined {
  if (!value || typeof value !== "object") return undefined;
  const v = value as Record<string, unknown>;
  return {
    merchant: String(v.merchant ?? "Tutti"),
    gender: String(v.gender ?? "Tutti"),
    size: String(v.size ?? "Tutte"),
    maxPrice: Number.isFinite(Number(v.maxPrice)) ? Number(v.maxPrice) : 250,
    onSale: v.onSale === true,
  };
}

export async function POST(request: Request) {
  let body: Record<string, unknown>;
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "Richiesta non valida." }, { status: 400 });
  }

  let query: string;
  try {
    query = sanitizeQuery(body.query);
  } catch (error) {
    if (error instanceof InputValidationError) {
      return Response.json({ error: error.message }, { status: 400 });
    }
    throw error;
  }

  if (!checkRateLimit(clientKey(request))) {
    return Response.json(
      { error: "Hai effettuato troppe ricerche in poco tempo. Attendi un minuto e riprova." },
      { status: 429 },
    );
  }

  try {
    const result = await runSearch(
      query,
      buildFilterHistory(body.history),
      parseManual(body.manualFilters),
    );
    return Response.json(result);
  } catch (error) {
    console.error("Errore durante la ricerca", error);
    const message =
      error instanceof ConfigurationError
        ? error.message
        : "Si è verificato un errore durante la ricerca. Riprova più tardi.";
    return Response.json({ error: message }, { status: 500 });
  }
}
