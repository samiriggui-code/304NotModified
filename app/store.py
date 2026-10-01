"""Stockage SQLite : réponses en cache, journal des requêtes, clés d'API."""

import json
import secrets
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass, field

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
-- Calculs sur les données de l'agent (/v1/calc/*) : journal à part, pour ne pas fausser les mesures
-- des questions (taux de répétition, de cache, coût des recherches). Aucune bougie n'est gardée.
CREATE TABLE IF NOT EXISTS calc_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL UNIQUE,
    ts REAL NOT NULL,
    api_key TEXT NOT NULL,
    name TEXT NOT NULL,
    candles INTEGER NOT NULL,
    latency_ms INTEGER NOT NULL,
    client TEXT
);
-- Catalogue de services : devis (prix ferme jusqu'à expiration, lié à une clé et à des paramètres),
-- exécutions (coûts par étape, prix facturé, état final) et résultats réutilisables.
CREATE TABLE IF NOT EXISTS quotes (
    quote_id TEXT PRIMARY KEY,
    api_key TEXT NOT NULL,
    service TEXT NOT NULL,
    version TEXT NOT NULL,
    fingerprint TEXT NOT NULL,      -- empreinte des paramètres : un devis ne vaut que pour eux
    price_eur REAL NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    used_by TEXT                    -- run_id qui l'a consommé ; NULL tant qu'il est libre
);
CREATE TABLE IF NOT EXISTS service_runs (
    run_id TEXT PRIMARY KEY,
    ts REAL NOT NULL,
    api_key TEXT NOT NULL,
    service TEXT NOT NULL,
    version TEXT NOT NULL,
    quote_id TEXT,
    status TEXT NOT NULL,           -- completed | partial | failed
    billed INTEGER NOT NULL,        -- 1 seulement si le résultat a été livré complet
    price_eur REAL NOT NULL,        -- prix facturé (0 si non facturé)
    cost_collect_eur REAL NOT NULL DEFAULT 0,
    cost_classify_eur REAL NOT NULL DEFAULT 0,
    cost_llm_eur REAL NOT NULL DEFAULT 0,
    cost_other_eur REAL NOT NULL DEFAULT 0,
    latency_ms INTEGER NOT NULL,
    cached INTEGER NOT NULL DEFAULT 0,
    steps TEXT NOT NULL,            -- JSON : chaque étape, son fournisseur, son coût, son issue
    reason TEXT,
    channel TEXT,
    client TEXT
);
CREATE INDEX IF NOT EXISTS service_runs_key_ts ON service_runs(api_key, ts);
CREATE TABLE IF NOT EXISTS service_cache (
    cache_key TEXT PRIMARY KEY,     -- service + version + paramètres normalisés
    service TEXT NOT NULL,
    result TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL
);
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
_FACT_COLUMNS = {
    "claims": "TEXT",  # JSON : faits de la réponse, chacun avec les URL qui le justifient
    "valid_from": "TEXT",  # AAAA-MM-JJ : début d'application du fait décrit, si connu
    "valid_until": "TEXT",  # AAAA-MM-JJ : fin d'application connue, si connue
}
MIGRATIONS = {
    "answers": {"version_id": "INTEGER", **_FACT_COLUMNS},
    "answer_versions": dict(_FACT_COLUMNS),
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
    claims: list[dict] = field(default_factory=list)
    valid_from: str | None = None
    valid_until: str | None = None


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

    # --- catalogue de services : devis, exécutions, résultats réutilisables ---

    def create_quote(
        self, *, api_key: str, service: str, version: str, fingerprint: str, price_eur: float, now: float, ttl: float
    ) -> dict:
        quote = {
            "quote_id": "quo_" + secrets.token_urlsafe(12),
            "api_key": api_key,
            "service": service,
            "version": version,
            "fingerprint": fingerprint,
            "price_eur": price_eur,
            "created_at": now,
            "expires_at": now + ttl,
        }
        with self._lock:
            self._db.execute(
                """INSERT INTO quotes (quote_id, api_key, service, version, fingerprint, price_eur, created_at, expires_at)
                   VALUES (:quote_id, :api_key, :service, :version, :fingerprint, :price_eur, :created_at, :expires_at)""",
                quote,
            )
            self._db.commit()
        return quote

    def claim_quote(self, quote_id: str, api_key: str, run_id: str, now: float) -> tuple[str, dict | None]:
        """Réserve un devis pour une exécution. Renvoie ("ok", devis), ("unknown", None), ("expired", devis)
        ou ("used", devis). Un devis ne sert qu'une fois : pas de double exécution sur un même devis."""
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM quotes WHERE quote_id = ? AND api_key = ?", (quote_id, api_key)
            ).fetchone()
            if row is None:
                return "unknown", None
            quote = dict(row)
            if quote["used_by"]:
                return "used", quote
            if quote["expires_at"] <= now:
                return "expired", quote
            claimed = self._db.execute(
                "UPDATE quotes SET used_by = ? WHERE quote_id = ? AND used_by IS NULL", (run_id, quote_id)
            ).rowcount
            self._db.commit()
        return ("ok", quote) if claimed else ("used", quote)

    def release_quote(self, quote_id: str, run_id: str) -> None:
        """Rend un devis réutilisable quand l'exécution n'a rien facturé (échec passager, résultat partiel)."""
        with self._lock:
            self._db.execute("UPDATE quotes SET used_by = NULL WHERE quote_id = ? AND used_by = ?", (quote_id, run_id))
            self._db.commit()

    def billed_since(self, api_key: str, since: float) -> float:
        with self._lock:
            return self._db.execute(
                "SELECT COALESCE(SUM(price_eur), 0) FROM service_runs WHERE api_key = ? AND ts >= ? AND billed = 1",
                (api_key, since),
            ).fetchone()[0]

    def log_service_run(self, run: dict) -> None:
        with self._lock:
            self._db.execute(
                """INSERT INTO service_runs
                   (run_id, ts, api_key, service, version, quote_id, status, billed, price_eur, cost_collect_eur,
                    cost_classify_eur, cost_llm_eur, cost_other_eur, latency_ms, cached, steps, reason, channel, client)
                   VALUES (:run_id, :ts, :api_key, :service, :version, :quote_id, :status, :billed, :price_eur,
                           :cost_collect_eur, :cost_classify_eur, :cost_llm_eur, :cost_other_eur, :latency_ms, :cached,
                           :steps, :reason, :channel, :client)""",
                {**run, "steps": json.dumps(run["steps"], ensure_ascii=False)},
            )
            self._db.commit()

    def service_cache_get(self, cache_key: str, now: float) -> dict | None:
        with self._lock:
            row = self._db.execute(
                "SELECT result, created_at, expires_at FROM service_cache WHERE cache_key = ? AND expires_at > ?",
                (cache_key, now),
            ).fetchone()
        if row is None:
            return None
        return {"result": json.loads(row["result"]), "created_at": row["created_at"], "expires_at": row["expires_at"]}

    def service_cache_put(self, cache_key: str, service: str, result: dict, now: float, ttl: float) -> None:
        with self._lock:
            self._db.execute(
                """INSERT OR REPLACE INTO service_cache (cache_key, service, result, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (cache_key, service, json.dumps(result, ensure_ascii=False), now, now + ttl),
            )
            self._db.commit()

    def service_stats(self, since: float = 0.0) -> dict:
        """Par service : exécutions, issues, coûts par étape, prix facturé, marge, latence, part servie
        depuis la mémoire. Les montants sont ceux enregistrés (coûts réels lus chez les fournisseurs)."""
        with self._lock:
            rows = self._db.execute(
                """SELECT service, COUNT(*) AS runs, SUM(status = 'completed') AS completed,
                          SUM(status = 'partial') AS partial, SUM(status = 'failed') AS failed,
                          SUM(cached) AS cached, SUM(billed) AS billed,
                          COALESCE(SUM(price_eur), 0) AS revenue_eur,
                          COALESCE(SUM(cost_collect_eur), 0) AS cost_collect_eur,
                          COALESCE(SUM(cost_classify_eur), 0) AS cost_classify_eur,
                          COALESCE(SUM(cost_llm_eur), 0) AS cost_llm_eur,
                          COALESCE(SUM(cost_other_eur), 0) AS cost_other_eur,
                          CAST(AVG(latency_ms) AS INTEGER) AS avg_latency_ms
                   FROM service_runs WHERE ts >= ? GROUP BY service""",
                (since,),
            ).fetchall()
        out = {}
        for r in rows:
            row = dict(r)
            cost = row["cost_collect_eur"] + row["cost_classify_eur"] + row["cost_llm_eur"] + row["cost_other_eur"]
            row["cost_eur"] = round(cost, 6)
            row["margin_eur"] = round(row["revenue_eur"] - cost, 6)
            row["success_rate"] = round(row["completed"] / row["runs"], 3) if row["runs"] else 0.0
            out[row.pop("service")] = row
        return out

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
            json.dumps(answer.claims, ensure_ascii=False),
            answer.valid_from,
            answer.valid_until,
        )
        with self._lock:
            version_id = self._db.execute(
                """INSERT INTO answer_versions
                   (key, question, domain, answer, sources, confidence, created_at, expires_at,
                    claims, valid_from, valid_until)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                values,
            ).lastrowid
            self._db.execute(
                """INSERT OR REPLACE INTO answers
                   (key, question, domain, answer, sources, confidence, created_at, expires_at,
                    claims, valid_from, valid_until, version_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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

    def log_calc(self, *, api_key: str, name: str, candles: int, latency_ms: int, client: str | None) -> str:
        request_id = "calc_" + secrets.token_urlsafe(12)
        with self._lock:
            self._db.execute(
                """INSERT INTO calc_requests (request_id, ts, api_key, name, candles, latency_ms, client)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (request_id, time.time(), api_key, name, candles, latency_ms, client),
            )
            self._db.commit()
        return request_id

    def calc_stats(self, since: float = 0.0) -> dict:
        with self._lock:
            rows = self._db.execute(
                """SELECT name, COUNT(*) AS calls, COUNT(DISTINCT api_key) AS clients,
                          CAST(AVG(latency_ms) AS INTEGER) AS avg_latency_ms
                   FROM calc_requests WHERE ts >= ? GROUP BY name ORDER BY 2 DESC""",
                (since,),
            ).fetchall()
        return {r["name"]: dict(r) for r in rows}

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

            def latency_quantile(fraction: float) -> int | None:
                # Rang le plus proche : la moyenne cache les requêtes lentes, la médiane et le 95e centile non.
                if not total:
                    return None
                return q(
                    f"""SELECT latency_ms FROM (SELECT * FROM requests WHERE ts >= ?) AS requests
                        ORDER BY latency_ms LIMIT 1 OFFSET {int((total - 1) * fraction)}"""
                ).fetchone()[0]

            latency = {"p50": latency_quantile(0.5), "p95": latency_quantile(0.95)}
            # Coût par résultat : recherches abouties, recherches sans réponse (dépense perdue), et
            # recherches qui remplacent une réponse déjà produite pour la même question (rafraîchissement).
            cost_by_outcome = dict(
                q(
                    """SELECT outcome, COALESCE(SUM(cost_eur), 0) FROM (SELECT * FROM requests WHERE ts >= ?) AS requests
                       GROUP BY outcome"""
                ).fetchall()
            )
            refresh = q(
                """SELECT COUNT(*), COALESCE(SUM(cost_eur), 0) FROM (SELECT * FROM requests WHERE ts >= ?) AS requests
                   WHERE outcome = 'miss' AND EXISTS (
                       SELECT 1 FROM requests p WHERE p.key = requests.key AND p.outcome = 'miss' AND p.id < requests.id)"""
            ).fetchone()
            # Clients techniques (clés d'API, hors accès sans clé partagé) et ceux qui reviennent un autre jour.
            clients_activity = q(
                """SELECT COUNT(*) AS active, COALESCE(SUM(days >= 2), 0) AS returning_clients FROM (
                       SELECT COUNT(DISTINCT CAST(ts / 86400 AS INTEGER)) AS days
                       FROM (SELECT * FROM requests WHERE ts >= ?) AS requests
                       WHERE api_key NOT IN (SELECT key FROM api_keys WHERE origin = 'anonymous')
                       GROUP BY api_key)"""
            ).fetchone()
            # Réponses servies depuis la mémoire puis signalées fausses, périmées, hors sujet ou contredites :
            # la mesure des erreurs de réutilisation (un taux de cache élevé ne vaut rien sans elle).
            reuse_errors = q(
                """SELECT COUNT(*) FROM (SELECT * FROM feedback WHERE ts >= ?) AS feedback
                   JOIN requests r ON r.request_id = feedback.request_id
                   WHERE r.outcome = 'hit' AND feedback.useful = 0
                     AND feedback.issue IN ('wrong', 'outdated', 'off_topic', 'contradiction')"""
            ).fetchone()[0]

        answered = by_outcome.get("hit", 0) + by_outcome.get("miss", 0)
        revenue = answered * price_per_request_eur
        hits, misses = by_outcome.get("hit", 0), by_outcome.get("miss", 0)
        avg_search_cost = cost_by_outcome.get("miss", 0.0) / misses if misses else None
        economics = {
            "cost_per_answer_eur": round(cost / answered, 6) if answered else None,
            # Retours « utile » seulement : sans retour, pas de chiffre plutôt qu'un chiffre trompeur.
            "cost_per_useful_answer_eur": round(cost / fb["useful"], 6) if fb["useful"] else None,
            "avg_search_cost_eur": round(avg_search_cost, 6) if avg_search_cost is not None else None,
            "unanswered_cost_eur": round(cost_by_outcome.get("unanswered", 0.0), 4),
            "refresh_searches": refresh[0],
            "refresh_cost_eur": round(refresh[1], 4),
            "avoided_searches": hits,
            # Estimation : réponses servies depuis la mémoire × coût moyen observé d'une recherche aboutie.
            "estimated_avoided_cost_eur": round(hits * avg_search_cost, 4) if avg_search_cost is not None else None,
        }
        return {
            "requests": total,
            "distinct_questions": distinct,
            # Part des requêtes portant sur une question déjà posée : le chiffre clé du modèle.
            "repeat_rate": round((total - distinct) / total, 3) if total else 0.0,
            "cache_hit_rate": round(by_outcome.get("hit", 0) / answered, 3) if answered else 0.0,
            "outcomes": by_outcome,
            "avg_latency_ms": avg_latency,
            "latency_ms": latency,
            "economics": economics,
            "clients_activity": {
                "active": clients_activity["active"],
                "returning": clients_activity["returning_clients"],
            },
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
                "reuse_errors": reuse_errors,
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
        claims=json.loads(row["claims"]) if row["claims"] else [],
        valid_from=row["valid_from"],
        valid_until=row["valid_until"],
    )
