import "server-only";
export class ConfigurationError extends Error {}

export function getSetting(name: string, fallback?: string): string | undefined {
  const value = process.env[name]?.trim();
  return value || fallback;
}

export function requireSetting(name: string): string {
  const value = getSetting(name);
  if (!value) {
    throw new ConfigurationError(
      `Configurazione obbligatoria mancante: ${name}. Impostala in web/.env.local.`,
    );
  }
  return value;
}

export function flag(name: string): boolean {
  return ["1", "true", "yes", "on"].includes((getSetting(name) ?? "").toLowerCase());
}

export interface SiteIdentity {
  name: string;
  owner?: string;
  contactEmail?: string;
  privacyEmail?: string;
  legalLastUpdated: string;
  isComplete: boolean;
}

export function siteIdentity(): SiteIdentity {
  const owner = getSetting("SITE_OWNER");
  const contactEmail = getSetting("CONTACT_EMAIL");
  const privacyEmail = getSetting("PRIVACY_EMAIL");
  return {
    name: getSetting("SITE_NAME", "TrovAI")!,
    owner,
    contactEmail,
    privacyEmail,
    legalLastUpdated: getSetting("LEGAL_LAST_UPDATED", "19 agosto 2026")!,
    isComplete: Boolean(owner && contactEmail && privacyEmail),
  };
}
