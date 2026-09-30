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
  feedback: { count: number; useful_rate: number; issues: Record<string, number> };
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
  feedback_useful: number | null;
  feedback_issue: string | null;
}

export interface AnswerRow {
  key: string;
  question: string;
  domain: string;
  answer: string;
  sources: { url: string; title: string }[];
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
}

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

export function useStats(days: number) {
  return useQuery({ queryKey: ['stats', days], queryFn: () => api.get<Stats>(`stats?days=${days}`), ...LIVE });
}

export function useTimeseries(days: number) {
  const tz = -new Date().getTimezoneOffset();
  return useQuery({
    queryKey: ['timeseries', days, tz],
    queryFn: () =>
      api.get<Bucket[]>(`timeseries?days=${days}&bucket=${bucketKind(days)}&tz_offset_min=${tz}`),
    select: (rows) => fillBuckets(rows, days),
    ...LIVE,
  });
}

export const useRequests = (limit = 100) =>
  useQuery({ queryKey: ['requests', limit], queryFn: () => api.get<RequestRow[]>(`requests?limit=${limit}`), ...LIVE });
export const useAnswers = (limit = 200) =>
  useQuery({ queryKey: ['answers', limit], queryFn: () => api.get<AnswerRow[]>(`answers?limit=${limit}`), ...LIVE });
export const useFeedback = (limit = 200) =>
  useQuery({ queryKey: ['feedback', limit], queryFn: () => api.get<FeedbackRow[]>(`feedback?limit=${limit}`), ...LIVE });
export const useKeys = () => useQuery({ queryKey: ['keys'], queryFn: () => api.get<KeyRow[]>('keys'), ...LIVE });

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
    out.push(byT.get(t) ?? { t, hit: 0, miss: 0, unanswered: 0, cost_eur: 0, avg_latency_ms: null });
  }
  return out;
}

// --- mise en forme ---------------------------------------------------------------

export const fmtInt = (n: number) => n.toLocaleString('fr-FR');
export const fmtPct = (x: number) => `${(x * 100).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} %`;
export const fmtEur = (x: number) =>
  x.toLocaleString('fr-FR', { style: 'currency', currency: 'EUR', maximumFractionDigits: x && Math.abs(x) < 1 ? 3 : 2 });
export const fmtDate = (ts: number) =>
  new Date(ts * 1000).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' });

export function fmtBucket(t: number, days: number, long = false) {
  const d = new Date(t * 1000);
  if (bucketKind(days) === 'hour') {
    return long
      ? d.toLocaleString('fr-FR', { weekday: 'short', hour: '2-digit', minute: '2-digit' })
      : `${String(d.getHours()).padStart(2, '0')} h`;
  }
  return d.toLocaleDateString('fr-FR', long ? { weekday: 'short', day: 'numeric', month: 'short' } : { day: 'numeric', month: 'short' });
}

// Seuls les liens http(s) deviennent cliquables : le reste vient du web et reste du texte.
export const safeUrl = (url: unknown) => (typeof url === 'string' && /^https?:\/\//i.test(url) ? url : null);
