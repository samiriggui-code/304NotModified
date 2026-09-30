"""Stockage SQLite : réponses en cache, journal des requêtes, clés d'API."""

import json
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass

SCHEMA = """
CREATE TABLE IF NOT EXISTS answers (
    key TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    domain TEXT NOT NULL,
    answer TEXT NOT NULL,
    sources TEXT NOT NULL,
    confidence REAL NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    hits INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    api_key TEXT NOT NULL,
    key TEXT NOT NULL,
    question TEXT NOT NULL,
    domain TEXT,
    outcome TEXT NOT NULL,          -- hit | miss | unanswered
    latency_ms INTEGER NOT NULL,
    cost_eur REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS requests_key ON requests(key);
CREATE TABLE IF NOT EXISTS api_keys (
    key TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    quota INTEGER NOT NULL,
    used INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
"""


@dataclass
class CachedAnswer:
    key: str
    question: str
    domain: str
    answer: str
    sources: list[dict]
    confidence: float
    created_at: float
    expires_at: float


class Store:
    def __init__(self, path: str):
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(SCHEMA)

    # --- clés d'API -------------------------------------------------------

    def create_key(self, label: str, quota: int) -> str:
        key = "nm304_" + secrets.token_urlsafe(24)
        with self._lock:
            self._db.execute(
                "INSERT INTO api_keys (key, label, quota, created_at) VALUES (?, ?, ?, ?)",
                (key, label, quota, time.time()),
            )
            self._db.commit()
        return key

    def get_key(self, key: str) -> sqlite3.Row | None:
        with self._lock:
            return self._db.execute("SELECT * FROM api_keys WHERE key = ?", (key,)).fetchone()

    def consume(self, key: str) -> None:
        with self._lock:
            self._db.execute("UPDATE api_keys SET used = used + 1 WHERE key = ?", (key,))
            self._db.commit()

    # --- cache ------------------------------------------------------------

    def get_fresh(self, key: str, now: float) -> CachedAnswer | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM answers WHERE key = ? AND expires_at > ?", (key, now)).fetchone()
            if row is None:
                return None
            self._db.execute("UPDATE answers SET hits = hits + 1 WHERE key = ?", (key,))
            self._db.commit()
        return _to_answer(row)

    def put(self, answer: CachedAnswer) -> None:
        with self._lock:
            self._db.execute(
                """INSERT OR REPLACE INTO answers
                   (key, question, domain, answer, sources, confidence, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    answer.key,
                    answer.question,
                    answer.domain,
                    answer.answer,
                    json.dumps(answer.sources, ensure_ascii=False),
                    answer.confidence,
                    answer.created_at,
                    answer.expires_at,
                ),
            )
            self._db.commit()

    # --- journal et statistiques -----------------------------------------

    def log(self, *, api_key, key, question, domain, outcome, latency_ms, cost_eur=0.0):
        with self._lock:
            self._db.execute(
                """INSERT INTO requests
                   (ts, api_key, key, question, domain, outcome, latency_ms, cost_eur)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (time.time(), api_key, key, question, domain, outcome, latency_ms, cost_eur),
            )
            self._db.commit()

    def stats(self, price_per_request_eur: float) -> dict:
        with self._lock:
            q = self._db.execute
            total = q("SELECT COUNT(*) FROM requests").fetchone()[0]
            distinct = q("SELECT COUNT(DISTINCT key) FROM requests").fetchone()[0]
            by_outcome = dict(q("SELECT outcome, COUNT(*) FROM requests GROUP BY outcome").fetchall())
            cost = q("SELECT COALESCE(SUM(cost_eur), 0) FROM requests").fetchone()[0]
            avg_latency = dict(
                q("SELECT outcome, CAST(AVG(latency_ms) AS INTEGER) FROM requests GROUP BY outcome").fetchall()
            )
            domains = [
                dict(r)
                for r in q(
                    """SELECT COALESCE(domain, 'inconnu') AS domain, COUNT(*) AS requests,
                              SUM(outcome = 'hit') AS hits
                       FROM requests GROUP BY 1 ORDER BY 2 DESC"""
                ).fetchall()
            ]
            top = [
                dict(r)
                for r in q(
                    """SELECT key, MIN(question) AS question, COUNT(*) AS requests
                       FROM requests GROUP BY key HAVING COUNT(*) > 1
                       ORDER BY 3 DESC LIMIT 20"""
                ).fetchall()
            ]
            unanswered = [
                dict(r)
                for r in q(
                    """SELECT MIN(question) AS question, COUNT(*) AS requests
                       FROM requests WHERE outcome = 'unanswered'
                       GROUP BY key ORDER BY 2 DESC LIMIT 20"""
                ).fetchall()
            ]

        answered = by_outcome.get("hit", 0) + by_outcome.get("miss", 0)
        revenue = answered * price_per_request_eur
        return {
            "requests": total,
            "distinct_questions": distinct,
            # Part des requêtes portant sur une question déjà posée : le chiffre clé du modèle.
            "repeat_rate": round((total - distinct) / total, 3) if total else 0.0,
            "cache_hit_rate": round(by_outcome.get("hit", 0) / answered, 3) if answered else 0.0,
            "outcomes": by_outcome,
            "avg_latency_ms": avg_latency,
            "estimated_revenue_eur": round(revenue, 4),
            "estimated_cost_eur": round(cost, 4),
            "estimated_margin_eur": round(revenue - cost, 4),
            "price_per_request_eur": price_per_request_eur,
            "domains": domains,
            "top_repeated_questions": top,
            "top_unanswered_questions": unanswered,
        }


def _to_answer(row: sqlite3.Row) -> CachedAnswer:
    return CachedAnswer(
        key=row["key"],
        question=row["question"],
        domain=row["domain"],
        answer=row["answer"],
        sources=json.loads(row["sources"]),
        confidence=row["confidence"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
    )
