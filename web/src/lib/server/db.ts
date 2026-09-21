import "server-only";
import Database from "better-sqlite3";
import { databasePath } from "./config";

let db: Database.Database | null = null;

/** Connessione condivisa allo stesso shop_database.db usato dagli script Python. */
export function getDb(): Database.Database {
  if (!db) {
    db = new Database(databasePath(), { fileMustExist: true });
    db.pragma("busy_timeout = 5000");
  }
  return db;
}
