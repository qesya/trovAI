import { connection } from "next/server";
import { ShoppingChat } from "@/components/ShoppingChat";
import { getDb } from "@/lib/server/db";

const LETTER_SIZES = ["XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL"];

function sortSizes(a: string, b: string) {
  const ia = LETTER_SIZES.indexOf(a);
  const ib = LETTER_SIZES.indexOf(b);
  if (ia !== -1 || ib !== -1) return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
  const na = parseFloat(a);
  const nb = parseFloat(b);
  return Number.isNaN(na) || Number.isNaN(nb) ? a.localeCompare(b) : na - nb;
}

function catalogOptions() {
  try {
    const db = getDb();
    const merchants = (
      db.prepare("SELECT DISTINCT merchant FROM prodotti WHERE availability = 1 ORDER BY merchant").all() as {
        merchant: string;
      }[]
    ).map((r) => r.merchant);
    const sizeRows = db
      .prepare("SELECT size FROM prodotti WHERE availability = 1 AND size IS NOT NULL")
      .all() as { size: string }[];
    const sizes = [
      ...new Set(sizeRows.flatMap((r) => r.size.split(",").map((s) => s.trim()).filter(Boolean))),
    ].sort(sortSizes);
    const { n } = db.prepare("SELECT COUNT(*) AS n FROM prodotti WHERE availability = 1").get() as {
      n: number;
    };
    return { merchants, sizes, productCount: n };
  } catch (error) {
    console.error("Database non raggiungibile", error);
    return { merchants: [], sizes: [], productCount: 0 };
  }
}

export default async function Home() {
  await connection();
  return <ShoppingChat {...catalogOptions()} />;
}
