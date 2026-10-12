/** The Awin hat feed uses zero where no customer-facing size is supplied. */
export function catalogSize(size: string | null, title: string): string | null {
  if (size?.trim() === "0" && /^cappell[oi]\b/i.test(title.trim())) return null;
  return size;
}

export function sizeLabel(size: string | null, title: string): string | null {
  const value = catalogSize(size, title);
  if (size && !value) return "Taglia non specificata";
  return value ? `Taglie ${value}` : null;
}
