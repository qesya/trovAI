import "server-only";
import { getDb } from "./db";

/** Salva solo ID prodotto, valore del feedback e data: nessun identificatore utente. */
export function recordProductFeedback(productId: number, helpful: boolean): void {
  const db = getDb();
  db.exec(`
    CREATE TABLE IF NOT EXISTS product_feedback (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      product_id INTEGER NOT NULL,
      helpful INTEGER NOT NULL CHECK (helpful IN (0, 1)),
      created_at TEXT NOT NULL
    )`);
  db.prepare(
    "INSERT INTO product_feedback (product_id, helpful, created_at) VALUES (?, ?, ?)",
  ).run(productId, helpful ? 1 : 0, new Date().toISOString().replace("Z", "+00:00"));
}
