// Types et lectures des données du tableau de bord (routes /internal/* de l'API).
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';

export type Outcome = 'hit' | 'miss' | 'unanswered';

export const OUTCOMES: Record<Outcome, { label: string; color: string }> = {
  hit: { label: 'Cache', color: 'var(--nm-cache)' },
  miss: { label: 'Recherche', color: 'var(--nm-search)' },
  unanswered: { label: 'Sans réponse', color: 'var(--nm-none)' },
};

export const ISSUES: Record<string, string> = {
  wrong: 'fausse',
  outdated: 'périmée',
  incomplete: 'incomplète',
  bad_source: 'mauvaise source',
  other: 'autre',
};

export interface Source {
  url: string;
  title: string;
}

export interface Stats {
  requests: number;
  distinct_questions: number;
  repeat_rate: number;
  cache_hit_rate: number;
  outcomes: Partial<Record<Outcome, number>>;
  avg_latency_ms: Partial<Record<Outcome, number>>;
  estimated_revenue_eur: number;
  estimated_cost_eur: number;
  estimated_margin_eur: number;
  price_per_request_eur: number;
  domains: { domain: string; requests: number; hits: number | null }[];
  top_repeated_questions: { key: string; question: string; requests: number }[];
  top_unanswered_questions: { question: string; requests: number }[];
  channels: Record<string, number>;
  clients: { client: string; requests: number }[];
  feedback: {
    count: number;
    useful_rate: number;
    issues: Record<string, number>;
  };
}

export interface Bucket {
  t: number;
  hit: number;
  miss: number;
  unanswered: number;
  cost_eur: number;
  avg_latency_ms: number | null;
}

export interface RequestRow {
  ts: number;
  request_id: string | null;
  question: string;
  domain: string | null;
  outcome: Outcome;
  latency_ms: number;
  cost_eur: number;
  key_label: string;
  channel: string;
  client: string | null;
  context: string | null;
  answer: string | null;
  confidence: number | null;
  sources: Source[];
  feedback_useful: number | null;
  feedback_issue: string | null;
  feedback_comment: string | null;
}

export interface AnswerRow {
  key: string;
  question: string;
  domain: string;
  answer: string;
  sources: Source[];
  confidence: number;
  created_at: number;
  expires_at: number;
  hits: number;
}

export interface FeedbackRow {
  ts: number;
  useful: boolean;
  issue: string | null;
  comment: string | null;
  question: string;
  domain: string | null;
  client: string | null;
  request_id: string;
  answer: string | null;
}

export interface KeyRow {
  key: string;
  label: string;
  quota: number;
  used: number;
  created_at: number;
  origin: 'admin' | 'self' | 'anonymous';
  use_case: string | null;
  contact: string | null;
  last_used: number | null;
}

export interface DomainRow {
  domain: string;
  label: string;
  description: string;
  ttl_seconds: number;
  specialty: boolean;
  requests: number;
  distinct_questions: number;
  hit: number;
  miss: number;
  unanswered: number;
  cache_hit_rate: number;
  cost_eur: number;
  last_ts: number | null;
  answers: number;
  fresh_answers: number;
  served: number;
  feedback: number;
  useful: number;
}

export interface Settings {
  public_url: string;
  mcp_url: string;
  resolver: string;
  search_enabled: boolean;
  anon_daily_limit: number;
  self_service_quota: number;
  free_quota: number;
  price_per_request_eur: number;
  log_retention_days: number;
  max_question_chars: number;
}

export const KEY_ORIGINS: Record<KeyRow['origin'], string> = {
  admin: 'Créée par vous',
  self: "Demandée par l'agent",
  anonymous: 'Accès sans clé',
};

// --- période -----------------------------------------------------------------

export const PERIODS = [
  { days: 1, label: '24 h' },
  { days: 7, label: '7 jours' },
  { days: 30, label: '30 jours' },
  { days: 90, label: '90 jours' },
  { days: 3650, label: 'Tout' },
] as const;

export const bucketKind = (days: number): 'hour' | 'day' => (days <= 1 ? 'hour' : 'day');

// Rafraîchissement automatique : les chiffres restent à jour sans recharger la page.
// Pendant un rechargement, on garde l'affichage précédent (pas de page qui clignote).
const LIVE = { refetchInterval: 30_000, placeholderData: keepPreviousData };

const withDomain = (path: string, domain?: string) =>
  domain ? `${path}${path.includes('?') ? '&' : '?'}domain=${encodeURIComponent(domain)}` : path;

export function useStats(days: number, domain?: string) {
  return useQuery({
    queryKey: ['stats', days, domain],
    queryFn: () => api.get<Stats>(withDomain(`stats?days=${days}`, domain)),
    ...LIVE,
  });
}

export function useTimeseries(days: number, domain?: string) {
  const tz = -new Date().getTimezoneOffset();
  return useQuery({
    queryKey: ['timeseries', days, tz, domain],
    queryFn: () =>
      api.get<Bucket[]>(withDomain(`timeseries?days=${days}&bucket=${bucketKind(days)}&tz_offset_min=${tz}`, domain)),
    select: (rows) => fillBuckets(rows, days),
    ...LIVE,
  });
}

export const useRequests = (limit = 100, domain?: string) =>
  useQuery({
    queryKey: ['requests', limit, domain],
    queryFn: () => api.get<RequestRow[]>(withDomain(`requests?limit=${limit}`, domain)),
    ...LIVE,
  });
export const useAnswers = (limit = 200, domain?: string) =>
  useQuery({
    queryKey: ['answers', limit, domain],
    queryFn: () => api.get<AnswerRow[]>(withDomain(`answers?limit=${limit}`, domain)),
    ...LIVE,
  });
export const useFeedback = (limit = 200, domain?: string) =>
  useQuery({
    queryKey: ['feedback', limit, domain],
    queryFn: () => api.get<FeedbackRow[]>(withDomain(`feedback?limit=${limit}`, domain)),
    ...LIVE,
  });
export const useKeys = () =>
  useQuery({
    queryKey: ['keys'],
    queryFn: () => api.get<KeyRow[]>('keys'),
    ...LIVE,
  });
export const useDomains = (days: number) =>
  useQuery({
    queryKey: ['domains', days],
    queryFn: () => api.get<DomainRow[]>(`domains?days=${days}`),
    ...LIVE,
  });
export const useSettings = () =>
  useQuery({
    queryKey: ['settings'],
    queryFn: () => api.get<Settings>('settings'),
    staleTime: 60_000,
  });

// Complète les tranches vides pour que l'axe du temps soit continu (même alignement que l'API).
export function fillBuckets(rows: Bucket[], days: number): Bucket[] {
  const size = bucketKind(days) === 'hour' ? 3600 : 86400;
  const tz = -new Date().getTimezoneOffset() * 60;
  const now = Date.now() / 1000;
  const from = days > 90 && rows.length ? rows[0].t : now - days * 86400;
  const start = Math.floor((from + tz) / size) * size - tz;
  const byT = new Map(rows.map((r) => [r.t, r]));
  const out: Bucket[] = [];
  for (let t = start; t <= now; t += size) {
    out.push(
      byT.get(t) ?? {
        t,
        hit: 0,
        miss: 0,
        unanswered: 0,
        cost_eur: 0,
        avg_latency_ms: null,
      },
    );
  }
  return out;
}

// --- mise en forme ---------------------------------------------------------------

export const fmtInt = (n: number) => n.toLocaleString('fr-FR');
export const fmtPct = (x: number) => `${(x * 100).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} %`;
export const fmtEur = (x: number) =>
  x.toLocaleString('fr-FR', {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: x && Math.abs(x) < 1 ? 3 : 2,
  });
export const fmtDate = (ts: number) =>
  new Date(ts * 1000).toLocaleString('fr-FR', {
    dateStyle: 'short',
    timeStyle: 'short',
  });

export function fmtAgo(ts: number | null | undefined) {
  if (!ts) return 'jamais';
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 60) return "à l'instant";
  if (s < 3600) return `il y a ${Math.floor(s / 60)} min`;
  if (s < 86400) return `il y a ${Math.floor(s / 3600)} h`;
  return `il y a ${Math.floor(s / 86400)} j`;
}

export function fmtDuration(seconds: number) {
  if (seconds < 86400) return `${Math.round(seconds / 3600)} h`;
  const d = Math.round(seconds / 86400);
  return `${d} jour${d > 1 ? 's' : ''}`;
}

export function fmtBucket(t: number, days: number, long = false) {
  const d = new Date(t * 1000);
  if (bucketKind(days) === 'hour') {
    return long
      ? d.toLocaleString('fr-FR', {
          weekday: 'short',
          hour: '2-digit',
          minute: '2-digit',
        })
      : `${String(d.getHours()).padStart(2, '0')} h`;
  }
  return d.toLocaleDateString(
    'fr-FR',
    long ? { weekday: 'short', day: 'numeric', month: 'short' } : { day: 'numeric', month: 'short' },
  );
}

// Seuls les liens http(s) deviennent cliquables : le reste vient du web et reste du texte.
export const safeUrl = (url: unknown) => (typeof url === 'string' && /^https?:\/\//i.test(url) ? url : null);

export function hostOf(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

// Export CSV (séparateur « ; », lisible par Excel en français).
export function downloadCsv(filename: string, headers: string[], rows: (string | number | null | undefined)[][]) {
  const cell = (v: string | number | null | undefined) => `"${String(v ?? '').replace(/"/g, '""')}"`;
  const text = [headers, ...rows].map((r) => r.map(cell).join(';')).join('\r\n');
  const url = URL.createObjectURL(new Blob(['﻿' + text], { type: 'text/csv;charset=utf-8' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
