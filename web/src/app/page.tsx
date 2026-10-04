import { connection } from "next/server";
import { ShoppingChat } from "@/components/ShoppingChat";
import { query } from "@/lib/server/db";

const LETTER_SIZES = ["XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL"];

function sortSizes(a: string, b: string) {
  const ia = LETTER_SIZES.indexOf(a);
  const ib = LETTER_SIZES.indexOf(b);
  if (ia !== -1 || ib !== -1) return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
  const na = parseFloat(a);
  const nb = parseFloat(b);
  return Number.isNaN(na) || Number.isNaN(nb) ? a.localeCompare(b) : na - nb;
}

async function catalogOptions() {
  try {
    const [merchantRows, sizeRows, [count]] = await Promise.all([
      query<{ merchant: string }>(
        "SELECT DISTINCT merchant FROM catalog_search WHERE availability = 1 ORDER BY merchant",
      ),
      query<{ size: string }>(
        "SELECT DISTINCT size FROM catalog_search WHERE availability = 1 AND size IS NOT NULL",
      ),
      query<{ n: number }>("SELECT COUNT(*) AS n FROM catalog_search WHERE availability = 1"),
    ]);
    const merchants = merchantRows.map((r) => r.merchant);
    const sizes = [
      ...new Set(sizeRows.flatMap((r) => r.size.split(",").map((s) => s.trim()).filter(Boolean))),
    ].sort(sortSizes);
    return { merchants, sizes, productCount: count?.n ?? 0 };
  } catch (error) {
    console.error("Database non raggiungibile", error);
    return { merchants: [], sizes: [], productCount: 0 };
  }
}

export default async function Home() {
  await connection();
  return <ShoppingChat {...(await catalogOptions())} />;
}
