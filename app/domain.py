"""Tools implement policy; model output can never authorize a refund."""

import sqlite3
from pathlib import Path

from langchain_core.tools import tool

ORDERS = {
    "ORD-100": {"paid_cents": 12000, "delivered_days_ago": 4, "returned": True},
    "ORD-200": {"paid_cents": 5500, "delivered_days_ago": 45, "returned": True},
    "ORD-300": {"paid_cents": 8500, "delivered_days_ago": 3, "returned": False},
}


@tool
def lookup_order(order_id: str) -> dict:
    """Read an order from the synthetic business fixture. No external network calls."""
    if order_id not in ORDERS:
        raise ValueError("Order not found")
    return {"order_id": order_id, **ORDERS[order_id]}


@tool
def refund_policy(order_id: str) -> dict:
    """Calculate the policy cap using verified order data, not model-supplied amounts."""
    order = lookup_order.invoke({"order_id": order_id})
    eligible = order["returned"] and order["delivered_days_ago"] <= 30
    return {"eligible": eligible, "maximum_cents": order["paid_cents"] if eligible else 0}


class Ledger:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS refunds(
                order_id TEXT PRIMARY KEY, run_id TEXT UNIQUE, amount_cents INTEGER NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
            db.execute("""CREATE TABLE IF NOT EXISTS decisions(
                run_id TEXT PRIMARY KEY, proposal_hash TEXT, approved INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=10)

    def record_decision(self, run_id: str, digest: str, approved: bool) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO decisions(run_id,proposal_hash,approved) VALUES(?,?,?)",
                (run_id, digest, int(approved)),
            )

    def execute(self, run_id: str, order_id: str, amount: int, digest: str) -> dict:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            decision = db.execute(
                "SELECT proposal_hash,approved FROM decisions WHERE run_id=?", (run_id,)
            ).fetchone()
            if decision != (digest, 1):
                raise ValueError("Exact approval is required")
            existing = db.execute(
                "SELECT run_id,amount_cents FROM refunds WHERE order_id=?", (order_id,)
            ).fetchone()
            if existing:
                if existing != (run_id, amount):
                    raise ValueError("Order already refunded by another proposal")
                return {"status": "completed", "replayed": True}
            policy = refund_policy.invoke({"order_id": order_id})
            if amount <= 0 or amount > policy["maximum_cents"]:
                raise ValueError("Order no longer eligible")
            db.execute(
                "INSERT INTO refunds(order_id,run_id,amount_cents) VALUES(?,?,?)",
                (order_id, run_id, amount),
            )
        return {"status": "completed", "replayed": False}
