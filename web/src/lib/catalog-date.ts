/** Normalizza anche il timestamp PostgreSQL prima del parsing nel browser. */
export function catalogDate(value: string | null): { iso: string; label: string } | null {
  if (!value) return null;
  const normalized = value.trim().replace(" ", "T")
    .replace(/(\.\d{3})\d+/, "$1")
    .replace(/([+-]\d{2})$/, "$1:00");
  // Non interpretare date senza fuso secondo le impostazioni locali del browser.
  if (!/(Z|[+-]\d{2}:\d{2})$/i.test(normalized)) return null;
  const date = new Date(normalized);
  if (!Number.isFinite(date.getTime())) return null;
  return {
    iso: date.toISOString(),
    label: new Intl.DateTimeFormat("it-IT", {
      day: "2-digit", month: "2-digit", year: "numeric",
      hour: "2-digit", minute: "2-digit", timeZone: "Europe/Rome",
    }).format(date),
  };
}
