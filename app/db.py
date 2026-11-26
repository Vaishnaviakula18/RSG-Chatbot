"""Data layer: clean the CSV, store it in SQLite, and open read-only connections."""
import json
import os
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = Path(os.getenv("BI_CSV_PATH", ROOT / "data" / "ai_bi_assistant_sales_data.csv"))
DB_PATH = Path(os.getenv("BI_DB_PATH", ROOT / "data" / "sales.db"))
REQUIRED_TEXT = ["transaction_id", "product", "category", "region", "sales_channel", "status"]

SCHEMA = """
CREATE TABLE sales (
    transaction_id  TEXT PRIMARY KEY,
    order_date      TEXT NOT NULL,            -- ISO YYYY-MM-DD
    order_month     TEXT NOT NULL,            -- YYYY-MM
    product         TEXT NOT NULL,
    category        TEXT NOT NULL,
    region          TEXT NOT NULL,
    sales_channel   TEXT NOT NULL,
    quantity        INTEGER NOT NULL CHECK (quantity > 0),
    unit_price      REAL NOT NULL CHECK (unit_price > 0),
    discount_amount REAL NOT NULL CHECK (discount_amount >= 0),
    revenue         REAL NOT NULL,            -- quantity * unit_price - discount_amount
    status          TEXT NOT NULL
);
CREATE INDEX idx_sales_month ON sales(order_month);
CREATE TABLE rejected_records (
    csv_line       INTEGER,
    transaction_id TEXT,
    reason         TEXT NOT NULL,
    raw_values     TEXT NOT NULL
);
"""


def clean_csv(csv_path):
    """Return (valid_rows, rejected_rows). Nothing is dropped silently."""
    raw = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    raw.columns = [c.strip().lower() for c in raw.columns]
    good, bad, seen = [], [], set()
    for i, row in raw.iterrows():
        r = {k: str(v).strip() for k, v in row.items()}
        reasons = [f"missing {c}" for c in REQUIRED_TEXT if not r.get(c)]
        tid = r.get("transaction_id", "")
        if tid in seen:
            reasons.append("duplicate transaction_id")
        date = pd.to_datetime(r.get("order_date", ""), format="%d-%m-%Y", errors="coerce")
        if pd.isna(date):
            reasons.append("invalid order_date (expected DD-MM-YYYY)")
        qty = pd.to_numeric(r.get("quantity", ""), errors="coerce")
        price = pd.to_numeric(r.get("unit_price", ""), errors="coerce")
        disc = pd.to_numeric(r.get("discount_amount") or "0", errors="coerce")
        if pd.isna(qty) or qty <= 0 or qty != int(qty):
            reasons.append("quantity missing, non-integer or <= 0")
        if pd.isna(price) or price <= 0:
            reasons.append("unit_price missing or <= 0")
        if pd.isna(disc) or disc < 0:
            reasons.append("invalid discount_amount")
        elif not pd.isna(qty) and not pd.isna(price) and disc > qty * price:
            reasons.append("discount exceeds gross amount")
        if r.get("status") and r["status"].lower() != "completed":
            reasons.append(f"status is '{r['status']}', not Completed")

        if reasons:
            bad.append({"csv_line": i + 2, "transaction_id": tid, "reason": "; ".join(reasons),
                        "raw_values": json.dumps(r)})
            continue
        seen.add(tid)
        good.append((tid, date.strftime("%Y-%m-%d"), date.strftime("%Y-%m"),
                     r["product"].title(), r["category"].title(), r["region"].title(),
                     r["sales_channel"].title(), int(qty), float(price), float(disc),
                     float(qty * price - disc), "Completed"))
    return good, bad


def build_database(csv_path=CSV_PATH, db_path=DB_PATH):
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    good, bad = clean_csv(csv_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.executemany("INSERT INTO sales VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", good)
        conn.executemany("INSERT INTO rejected_records VALUES (:csv_line,:transaction_id,:reason,:raw_values)", bad)
        conn.commit()
    finally:
        conn.close()
    return len(good), len(bad)


def connect_readonly(db_path=DB_PATH):
    """Read-only connection: any INSERT/UPDATE/DELETE/DROP raises an error."""
    uri = f"{Path(db_path).resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def get_catalog(conn):
    """Distinct values the user may refer to; used to validate every plan."""
    def col(c):
        return [r[0] for r in conn.execute(f"SELECT DISTINCT {c} FROM sales ORDER BY {c}")]
    return {"months": col("order_month"), "products": col("product"), "regions": col("region"),
            "categories": col("category"), "channels": col("sales_channel")}


def get_rejected(conn):
    return [dict(r) for r in conn.execute(
        "SELECT csv_line, transaction_id, reason FROM rejected_records ORDER BY csv_line")]
