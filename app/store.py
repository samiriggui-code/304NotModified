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
-- Idempotence de /v1/answer : une relance avec la même Idempotency-Key reçoit la réponse déjà
-- produite, sans nouvelle recherche ni nouveau décompte (fondation de la future facturation).
CREATE TABLE IF NOT EXISTS idempotency (
    scope TEXT NOT NULL,            -- clé d'API, ou « anonymous:<adresse IP> »
    idem_key TEXT NOT NULL,
    fingerprint TEXT NOT NULL,      -- empreinte de la demande : même clé, autre demande = refus
    response TEXT,                  -- NULL tant que la demande est en cours
    created_at REAL NOT NULL,
    PRIMARY KEY (scope, idem_key)
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
        "reason": "TEXT",  # cause d'une absence de réponse (voir resolver.REASONS)
    },
    "api_keys": {
        "origin": "TEXT",  # admin (créée depuis le tableau de bord) | self (demandée par l'agent)
        "use_case": "TEXT",  # ce que l'agent dit vouloir en faire
        "contact": "TEXT",  # facultatif, donné par l'agent
        "last_used": "REAL",
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

    def create_key(
        self,
        label: str,
        quota: int,
        *,
        origin: str = "admin",
        use_case: str | None = None,
        contact: str | None = None,
        key: str | None = None,
    ) -> str:
        key = key or "nm304_" + secrets.token_urlsafe(24)
        with self._lock:
            self._db.execute(
                """INSERT OR IGNORE INTO api_keys (key, label, quota, created_at, origin, use_case, contact)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (key, label, quota, time.time(), origin, use_case, contact),
            )
            self._db.commit()
        return key

    # --- idempotence ---------------------------------------------------------

    def idempotency_begin(
        self, scope: str, idem_key: str, fingerprint: str, now: float, ttl: float
    ) -> tuple[str, dict | None]:
        """Réserve la clé. Renvoie ("new", None), ("replay", réponse), ("pending", None) ou ("conflict", None)."""
        with self._lock:
            self._db.execute("DELETE FROM idempotency WHERE created_at < ?", (now - ttl,))
            row = self._db.execute(
                "SELECT fingerprint, response FROM idempotency WHERE scope = ? AND idem_key = ?", (scope, idem_key)
            ).fetchone()
            if row is None:
                self._db.execute(
                    "INSERT INTO idempotency (scope, idem_key, fingerprint, created_at) VALUES (?, ?, ?, ?)",
                    (scope, idem_key, fingerprint, now),
                )
                self._db.commit()
                return "new", None
            self._db.commit()
        if row["fingerprint"] != fingerprint:
            return "conflict", None
        if row["response"] is None:
            return "pending", None
        return "replay", json.loads(row["response"])

    def idempotency_finish(self, scope: str, idem_key: str, response: dict) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE idempotency SET response = ? WHERE scope = ? AND idem_key = ?",
                (json.dumps(response), scope, idem_key),
            )
            self._db.commit()

    def idempotency_abort(self, scope: str, idem_key: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM idempotency WHERE scope = ? AND idem_key = ?", (scope, idem_key))
            self._db.commit()

    def count_keys_since(self, origin: str, since: float) -> int:
        with self._lock:
            return self._db.execute(
                "SELECT COUNT(*) FROM api_keys WHERE origin = ? AND created_at >= ?", (origin, since)
            ).fetchone()[0]

    def get_key(self, key: str) -> sqlite3.Row | None:
        with self._lock:
            return self._db.execute("SELECT * FROM api_keys WHERE key = ?", (key,)).fetchone()

    def touch_key(self, key: str) -> None:
        with self._lock:
            self._db.execute("UPDATE api_keys SET last_used = ? WHERE key = ?", (time.time(), key))
            self._db.commit()

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
                """SELECT key, label, quota, used, created_at, COALESCE(origin, 'admin') AS origin,
                          use_case, contact, last_used
                   FROM api_keys ORDER BY created_at DESC"""
            ).fetchall()
        # La clé complète n'est montrée qu'à sa création : ici, seulement son début.
        return [{**dict(r), "key": r["key"][:12] + "…"} for r in rows]

    # --- consultation pour le tableau de bord ------------------------------

    def recent_requests(self, limit: int, domain: str | None = None) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                """SELECT r.ts, r.request_id, r.question, r.domain, r.outcome, r.latency_ms, r.cost_eur,
                          COALESCE(k.label, '?') AS key_label, COALESCE(r.channel, 'http') AS channel,
                          r.client, r.context, r.reason, v.answer, v.confidence, v.sources,
                          f.useful AS feedback_useful, f.issue AS feedback_issue, f.comment AS feedback_comment
                   FROM requests r LEFT JOIN api_keys k ON k.key = r.api_key
                   LEFT JOIN answer_versions v ON v.id = r.answer_version_id
                   LEFT JOIN feedback f ON f.request_id = r.request_id
                   WHERE :domain IS NULL OR r.domain = :domain
                   ORDER BY r.id DESC LIMIT :limit""",
                {"domain": domain, "limit": limit},
            ).fetchall()
        return [{**dict(r), "sources": json.loads(r["sources"]) if r["sources"] else []} for r in rows]

    def list_answers(self, limit: int, domain: str | None = None) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM answers WHERE :domain IS NULL OR domain = :domain ORDER BY created_at DESC LIMIT :limit",
                {"domain": domain, "limit": limit},
            ).fetchall()
        return [{**asdict(_to_answer(r)), "hits": r["hits"]} for r in rows]

    def domain_overview(self, since: float, now: float) -> dict[str, dict]:
        """Par domaine : requêtes (depuis `since`), réponses en mémoire et retours des agents."""
        with self._lock:
            requests = self._db.execute(
                """SELECT domain, COUNT(*) AS requests, COUNT(DISTINCT key) AS distinct_questions,
                          SUM(outcome = 'hit') AS hit, SUM(outcome = 'miss') AS miss,
                          SUM(outcome = 'unanswered') AS unanswered, COALESCE(SUM(cost_eur), 0) AS cost_eur,
                          MAX(ts) AS last_ts
                   FROM requests WHERE ts >= ? AND domain IS NOT NULL GROUP BY domain""",
                (since,),
            ).fetchall()
            answers = self._db.execute(
                """SELECT domain, COUNT(*) AS answers, SUM(expires_at > ?) AS fresh_answers,
                          COALESCE(SUM(hits), 0) AS served
                   FROM answers GROUP BY domain""",
                (now,),
            ).fetchall()
            feedback = self._db.execute(
                """SELECT r.domain, COUNT(*) AS feedback, COALESCE(SUM(f.useful), 0) AS useful
                   FROM feedback f JOIN requests r ON r.request_id = f.request_id
                   WHERE f.ts >= ? AND r.domain IS NOT NULL GROUP BY r.domain""",
                (since,),
            ).fetchall()
        out: dict[str, dict] = {}
        for rows in (requests, answers, feedback):
            for r in rows:
                values = dict(r)
                out.setdefault(values.pop("domain"), {}).update(values)
        return out

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
        reason=None,
    ) -> str:
        request_id = request_id or "req_" + secrets.token_urlsafe(12)
        with self._lock:
            self._db.execute(
                """INSERT INTO requests
                   (ts, api_key, key, question, domain, outcome, latency_ms, cost_eur,
                    request_id, channel, client, context, answer_version_id, reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                    reason,
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

    def list_feedback(self, limit: int, domain: str | None = None) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                """SELECT f.ts, f.useful, f.issue, f.comment, r.question, r.domain, r.client, r.request_id,
                          v.answer
                   FROM feedback f JOIN requests r ON r.request_id = f.request_id
                   LEFT JOIN answer_versions v ON v.id = r.answer_version_id
                   WHERE :domain IS NULL OR r.domain = :domain
                   ORDER BY f.ts DESC LIMIT :limit""",
                {"domain": domain, "limit": limit},
            ).fetchall()
        return [{**dict(r), "useful": bool(r["useful"])} for r in rows]

    def timeseries(
        self, *, since: float, bucket_seconds: int, tz_offset_seconds: int = 0, domain: str | None = None
    ) -> list[dict]:
        """Requêtes par tranche de temps (heure ou jour, alignée sur le fuseau du lecteur)."""
        with self._lock:
            rows = self._db.execute(
                """SELECT CAST((ts + :tz) / :b AS INTEGER) * :b - :tz AS t,
                          SUM(outcome = 'hit') AS hit, SUM(outcome = 'miss') AS miss,
                          SUM(outcome = 'unanswered') AS unanswered,
                          COALESCE(SUM(cost_eur), 0) AS cost_eur,
                          CAST(AVG(latency_ms) AS INTEGER) AS avg_latency_ms
                   FROM requests WHERE ts >= :since AND (:domain IS NULL OR domain = :domain)
                   GROUP BY 1 ORDER BY 1""",
                {"tz": tz_offset_seconds, "b": bucket_seconds, "since": since, "domain": domain},
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

    def stats(self, price_per_request_eur: float, since: float = 0.0, domain: str | None = None) -> dict:
        """Statistiques sur les requêtes depuis `since` (horodatage Unix ; 0 = depuis le début),
        pour un seul domaine si `domain` est donné."""
        with self._lock:

            def q(sql):
                # Chaque sous-requête « depuis ? » est restreinte à la période et, au besoin, au domaine.
                sql = sql.replace(
                    "(SELECT * FROM requests WHERE ts >= ?)",
                    "(SELECT * FROM requests WHERE ts >= :since AND (:domain IS NULL OR domain = :domain))",
                ).replace(
                    "(SELECT * FROM feedback WHERE ts >= ?)",
                    """(SELECT f.* FROM feedback f JOIN requests r ON r.request_id = f.request_id
                        WHERE f.ts >= :since AND (:domain IS NULL OR r.domain = :domain))""",
                )
                return self._db.execute(sql, {"since": since, "domain": domain})

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
            unanswered_reasons = dict(
                q(
                    """SELECT COALESCE(reason, 'inconnue'), COUNT(*) FROM (SELECT * FROM requests WHERE ts >= ?) AS requests
                       WHERE outcome = 'unanswered' GROUP BY 1"""
                ).fetchall()
            )

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
            "unanswered_reasons": unanswered_reasons,
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
