import "server-only";
import { query } from "./db";

/** Salva solo ID offerta, valore del feedback e data: nessun identificatore utente. */
export async function recordProductFeedback(productId: number, helpful: boolean): Promise<void> {
  await query(`
    CREATE TABLE IF NOT EXISTS product_feedback (
      id BIGSERIAL PRIMARY KEY,
      product_id BIGINT NOT NULL,
      helpful BOOLEAN NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )`);
  await query("INSERT INTO product_feedback (product_id, helpful) VALUES (?, ?)", [productId, helpful]);
}
