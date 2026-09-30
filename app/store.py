"""Stockage SQLite : réponses en cache, journal des requêtes, clés d'API."""

import json
import secrets
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass

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
-- Chaque réponse produite est gardée : on sait exactement ce qui a été servi à chaque requête,
-- même après un rafraîchissement.
CREATE TABLE IF NOT EXISTS answer_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL,
    question TEXT NOT NULL,
    domain TEXT NOT NULL,
    answer TEXT NOT NULL,
    sources TEXT NOT NULL,
    confidence REAL NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL
);
-- Retours des agents. Ils sont notés à part et ne modifient jamais les réponses en mémoire.
CREATE TABLE IF NOT EXISTS feedback (
    request_id TEXT PRIMARY KEY,
    ts REAL NOT NULL,
    api_key TEXT NOT NULL,
    useful INTEGER NOT NULL,
    issue TEXT,
    comment TEXT
);
CREATE TABLE IF NOT EXISTS api_keys (
    key TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    quota INTEGER NOT NULL,
    used INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
"""


# Colonnes ajoutées après la première version : créées au démarrage si la base est ancienne.
MIGRATIONS = {
    "answers": {"version_id": "INTEGER"},
    "requests": {
        "request_id": "TEXT",
        "channel": "TEXT",  # http | mcp
        "client": "TEXT",  # nom et version de l'agent ou de son outil
        "context": "TEXT",  # ce que l'agent était en train de faire, s'il l'a dit
        "answer_version_id": "INTEGER",
    },
}


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
    version_id: int | None = None


class Store:
    def __init__(self, path: str):
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(SCHEMA)
            for table, columns in MIGRATIONS.items():
                existing = {r["name"] for r in self._db.execute(f"PRAGMA table_info({table})")}
                for name, kind in columns.items():
                    if name not in existing:
                        self._db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")
            self._db.execute("CREATE UNIQUE INDEX IF NOT EXISTS requests_request_id ON requests(request_id)")
            self._db.commit()

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

    def put(self, answer: CachedAnswer) -> int:
        """Met la réponse en cache et en garde une version permanente ; renvoie l'identifiant de version."""
        values = (
            answer.key,
            answer.question,
            answer.domain,
            answer.answer,
            json.dumps(answer.sources, ensure_ascii=False),
            answer.confidence,
            answer.created_at,
            answer.expires_at,
        )
        with self._lock:
            version_id = self._db.execute(
                """INSERT INTO answer_versions
                   (key, question, domain, answer, sources, confidence, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                values,
            ).lastrowid
            self._db.execute(
                """INSERT OR REPLACE INTO answers
                   (key, question, domain, answer, sources, confidence, created_at, expires_at, version_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (*values, version_id),
            )
            self._db.commit()
        answer.version_id = version_id
        return version_id

    def list_keys(self) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT key, label, quota, used, created_at FROM api_keys ORDER BY created_at DESC"
            ).fetchall()
        # La clé complète n'est montrée qu'à sa création : ici, seulement son début.
        return [{**dict(r), "key": r["key"][:12] + "…"} for r in rows]

    # --- consultation pour le tableau de bord ------------------------------

    def recent_requests(self, limit: int) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                """SELECT r.ts, r.request_id, r.question, r.domain, r.outcome, r.latency_ms, r.cost_eur,
                          COALESCE(k.label, '?') AS key_label, COALESCE(r.channel, 'http') AS channel,
                          r.client, r.context, v.answer, v.confidence,
                          f.useful AS feedback_useful, f.issue AS feedback_issue
                   FROM requests r LEFT JOIN api_keys k ON k.key = r.api_key
                   LEFT JOIN answer_versions v ON v.id = r.answer_version_id
                   LEFT JOIN feedback f ON f.request_id = r.request_id
                   ORDER BY r.id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_answers(self, limit: int) -> list[dict]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM answers ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [{**asdict(_to_answer(r)), "hits": r["hits"]} for r in rows]

    # --- journal et statistiques -----------------------------------------

    def log(
        self,
        *,
        api_key,
        key,
        question,
        domain,
        outcome,
        latency_ms,
        cost_eur=0.0,
        request_id=None,
        channel="http",
        client=None,
        context=None,
        answer_version_id=None,
    ) -> str:
        request_id = request_id or "req_" + secrets.token_urlsafe(12)
        with self._lock:
            self._db.execute(
                """INSERT INTO requests
                   (ts, api_key, key, question, domain, outcome, latency_ms, cost_eur,
                    request_id, channel, client, context, answer_version_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    time.time(),
                    api_key,
                    key,
                    question,
                    domain,
                    outcome,
                    latency_ms,
                    cost_eur,
                    request_id,
                    channel,
                    client,
                    context,
                    answer_version_id,
                ),
            )
            self._db.commit()
        return request_id

    # --- retours des agents ------------------------------------------------

    def add_feedback(self, *, request_id, api_key, useful, issue=None, comment=None) -> bool:
        """Note le retour d'un agent sur une de SES requêtes. Ne touche jamais aux réponses."""
        with self._lock:
            owner = self._db.execute("SELECT api_key FROM requests WHERE request_id = ?", (request_id,)).fetchone()
            if owner is None or owner["api_key"] != api_key:
                return False
            self._db.execute(
                """INSERT OR REPLACE INTO feedback (request_id, ts, api_key, useful, issue, comment)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (request_id, time.time(), api_key, int(useful), issue, comment),
            )
            self._db.commit()
        return True

    def list_feedback(self, limit: int) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                """SELECT f.ts, f.useful, f.issue, f.comment, r.question, r.domain, r.client, r.request_id,
                          v.answer
                   FROM feedback f JOIN requests r ON r.request_id = f.request_id
                   LEFT JOIN answer_versions v ON v.id = r.answer_version_id
                   ORDER BY f.ts DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [{**dict(r), "useful": bool(r["useful"])} for r in rows]

    def timeseries(self, *, since: float, bucket_seconds: int, tz_offset_seconds: int = 0) -> list[dict]:
        """Requêtes par tranche de temps (heure ou jour, alignée sur le fuseau du lecteur)."""
        with self._lock:
            rows = self._db.execute(
                """SELECT CAST((ts + :tz) / :b AS INTEGER) * :b - :tz AS t,
                          SUM(outcome = 'hit') AS hit, SUM(outcome = 'miss') AS miss,
                          SUM(outcome = 'unanswered') AS unanswered,
                          COALESCE(SUM(cost_eur), 0) AS cost_eur,
                          CAST(AVG(latency_ms) AS INTEGER) AS avg_latency_ms
                   FROM requests WHERE ts >= :since GROUP BY 1 ORDER BY 1""",
                {"tz": tz_offset_seconds, "b": bucket_seconds, "since": since},
            ).fetchall()
        return [dict(r) for r in rows]

    def purge_older_than(self, days: int) -> None:
        """Efface le journal des requêtes (et leurs retours) plus ancien que `days` jours."""
        cutoff = time.time() - days * 86400
        with self._lock:
            self._db.execute(
                "DELETE FROM feedback WHERE request_id IN (SELECT request_id FROM requests WHERE ts < ?)", (cutoff,)
            )
            self._db.execute("DELETE FROM requests WHERE ts < ?", (cutoff,))
            self._db.commit()

    def stats(self, price_per_request_eur: float, since: float = 0.0) -> dict:
        """Statistiques sur les requêtes depuis `since` (horodatage Unix ; 0 = depuis le début)."""
        with self._lock:

            def q(sql):
                # Chaque « ? » de ces requêtes est la borne de début de période.
                return self._db.execute(sql, (since,) * sql.count("?"))

            total = q("SELECT COUNT(*) FROM (SELECT * FROM requests WHERE ts >= ?) AS requests").fetchone()[0]
            distinct = q(
                "SELECT COUNT(DISTINCT key) FROM (SELECT * FROM requests WHERE ts >= ?) AS requests"
            ).fetchone()[0]
            by_outcome = dict(
                q(
                    "SELECT outcome, COUNT(*) FROM (SELECT * FROM requests WHERE ts >= ?) AS requests GROUP BY outcome"
                ).fetchall()
            )
            cost = q(
                "SELECT COALESCE(SUM(cost_eur), 0) FROM (SELECT * FROM requests WHERE ts >= ?) AS requests"
            ).fetchone()[0]
            avg_latency = dict(
                q(
                    "SELECT outcome, CAST(AVG(latency_ms) AS INTEGER) FROM (SELECT * FROM requests WHERE ts >= ?) AS requests GROUP BY outcome"
                ).fetchall()
            )
            domains = [
                dict(r)
                for r in q(
                    """SELECT COALESCE(domain, 'inconnu') AS domain, COUNT(*) AS requests,
                              SUM(outcome = 'hit') AS hits
                       FROM (SELECT * FROM requests WHERE ts >= ?) AS requests GROUP BY 1 ORDER BY 2 DESC"""
                ).fetchall()
            ]
            top = [
                dict(r)
                for r in q(
                    """SELECT key, MIN(question) AS question, COUNT(*) AS requests
                       FROM (SELECT * FROM requests WHERE ts >= ?) AS requests GROUP BY key HAVING COUNT(*) > 1
                       ORDER BY 3 DESC LIMIT 20"""
                ).fetchall()
            ]
            unanswered = [
                dict(r)
                for r in q(
                    """SELECT MIN(question) AS question, COUNT(*) AS requests
                       FROM (SELECT * FROM requests WHERE ts >= ?) AS requests WHERE outcome = 'unanswered'
                       GROUP BY key ORDER BY 2 DESC LIMIT 20"""
                ).fetchall()
            ]

            channels = dict(
                q(
                    "SELECT COALESCE(channel, 'http'), COUNT(*) FROM (SELECT * FROM requests WHERE ts >= ?) AS requests GROUP BY 1"
                ).fetchall()
            )
            clients = [
                dict(r)
                for r in q(
                    """SELECT COALESCE(client, 'inconnu') AS client, COUNT(*) AS requests
                       FROM (SELECT * FROM requests WHERE ts >= ?) AS requests GROUP BY 1 ORDER BY 2 DESC LIMIT 20"""
                ).fetchall()
            ]
            fb = q(
                "SELECT COUNT(*) AS n, COALESCE(SUM(useful), 0) AS useful FROM (SELECT * FROM feedback WHERE ts >= ?) AS feedback"
            ).fetchone()
            fb_issues = dict(
                q(
                    "SELECT issue, COUNT(*) FROM (SELECT * FROM feedback WHERE ts >= ?) AS feedback WHERE issue IS NOT NULL GROUP BY issue"
                ).fetchall()
            )

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
            "channels": channels,
            "clients": clients,
            "feedback": {
                "count": fb["n"],
                "useful_rate": round(fb["useful"] / fb["n"], 3) if fb["n"] else 0.0,
                "issues": fb_issues,
            },
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
        version_id=row["version_id"],
    )
