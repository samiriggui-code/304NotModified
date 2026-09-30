'use client';

import Link from 'next/link';
import { Bot, Coins, Database, LayoutDashboard, Repeat, Send, ThumbsUp, Zap } from 'lucide-react';
import {
  fmtEur,
  fmtInt,
  fmtPct,
  OUTCOMES,
  useDomains,
  useSettings,
  useStats,
  useTimeseries,
  type Outcome,
} from '@/lib/nm304';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardHeading, CardTitle, CardToolbar } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { CacheRateChart, CostChart, RankBars, VolumeChart } from '@/components/nm304/charts';
import { EmptyState, Page } from '@/components/nm304/page';
import { PeriodFilter, usePeriod } from '@/components/nm304/period-filter';
import { ServiceStatus } from '@/components/nm304/service-status';
import { StatCard, StatGrid } from '@/components/nm304/stat-card';
import { Swatch } from '@/components/nm304/tags';

export default function DashboardPage() {
  const [days, setDays] = usePeriod();
  const stats = useStats(days);
  const series = useTimeseries(days);
  const domains = useDomains(days);
  const s = stats.data;
  const agents = s ? s.clients.length : 0;

  return (
    <Page title="Tableau de bord" icon={LayoutDashboard} actions={<PeriodFilter days={days} onChange={setDays} />}>
      <ServiceStatus />
      {stats.error && <p className="text-sm text-destructive">{stats.error.message}</p>}
      {/* Pendant un rechargement, l'affichage précédent reste en place, un peu estompé. */}
      <div className={`space-y-5 transition-opacity ${stats.isFetching && s ? 'opacity-70' : ''}`}>
        {s && (
          <StatGrid cols={4}>
            <StatCard
              icon={Send}
              label="Requêtes"
              value={fmtInt(s.requests)}
              hint={`${fmtInt(s.distinct_questions)} questions distinctes`}
              href="/requetes"
            />
            <StatCard
              icon={Repeat}
              label="Taux de répétition"
              value={fmtPct(s.repeat_rate)}
              hint="Questions déjà posées : le chiffre clé du modèle"
              highlight
            />
            <StatCard
              icon={Zap}
              label="Taux de cache"
              value={fmtPct(s.cache_hit_rate)}
              hint="Réponses servies depuis la mémoire"
              highlight
            />
            <StatCard
              icon={Bot}
              label="Agents"
              value={agents >= 20 ? '20 et plus' : fmtInt(agents)}
              hint={`MCP ${fmtInt(s.channels.mcp ?? 0)} · API ${fmtInt(s.channels.http ?? 0)}`}
              href="/agents"
            />
            <StatCard
              icon={Coins}
              label="Marge estimée"
              value={fmtEur(s.estimated_margin_eur)}
              hint={`Revenu ${fmtEur(s.estimated_revenue_eur)} · coût ${fmtEur(s.estimated_cost_eur)}`}
            />
            <StatCard
              icon={Database}
              label="Réponses en mémoire"
              value={fmtInt((domains.data ?? []).reduce((n, d) => n + d.answers, 0))}
              hint={`${fmtInt((domains.data ?? []).reduce((n, d) => n + d.fresh_answers, 0))} encore fraîches`}
              href="/reponses"
            />
            <StatCard
              icon={ThumbsUp}
              label="Retours utiles"
              value={s.feedback.count ? fmtPct(s.feedback.useful_rate) : '—'}
              hint={
                s.feedback.count ? `sur ${fmtInt(s.feedback.count)} retours d'agents` : 'Aucun retour sur la période'
              }
              href="/retours"
            />
            <StatCard
              icon={Zap}
              label="Temps de réponse"
              value={s.avg_latency_ms.hit !== undefined ? `${fmtInt(s.avg_latency_ms.hit)} ms` : '—'}
              hint={
                s.avg_latency_ms.miss !== undefined
                  ? `depuis le cache · ${fmtInt(s.avg_latency_ms.miss)} ms avec recherche`
                  : 'depuis le cache'
              }
            />
          </StatGrid>
        )}

        {series.data && <VolumeChart buckets={series.data} days={days} />}

        {s && (
          <Card>
            <CardHeader>
              <CardTitle>D&apos;où viennent les réponses</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <OutcomeShare stats={s.outcomes} />
              <p className="text-sm text-muted-foreground">
                <b>Cache</b> : déjà en mémoire, servie immédiatement (coût quasi nul). <b>Recherche</b> : nouvelle
                recherche sur le web (payante). <b>Sans réponse</b> : jamais décomptée ; la cause est ci-dessous.
              </p>
              <UnansweredReasons counts={s.unanswered_reasons} />
            </CardContent>
          </Card>
        )}

        <Card>
          <CardHeader>
            <CardHeading>
              <CardTitle>Spécialités</CardTitle>
              <div className="text-sm text-muted-foreground">Activité par domaine sur la période.</div>
            </CardHeading>
            <CardToolbar>
              <Button variant="outline" size="sm" asChild>
                <Link href="/specialites">Tout voir</Link>
              </Button>
            </CardToolbar>
          </CardHeader>
          <CardContent className="p-0 overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Domaine</TableHead>
                  <TableHead className="text-right">Requêtes</TableHead>
                  <TableHead className="text-right">Cache</TableHead>
                  <TableHead className="text-right">Sans réponse</TableHead>
                  <TableHead className="text-right">En mémoire</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(domains.data ?? [])
                  .filter((d) => d.specialty || d.requests)
                  .map((d) => (
                    <TableRow key={d.domain}>
                      <TableCell>
                        <Link href={`/specialites/${d.domain}`} className="font-medium text-mono hover:text-primary">
                          {d.label}
                        </Link>
                        <div className="text-xs text-muted-foreground">{d.description}</div>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{fmtInt(d.requests)}</TableCell>
                      <TableCell className="text-right tabular-nums">
                        {d.hit + d.miss ? fmtPct(d.cache_hit_rate) : '—'}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{fmtInt(d.unanswered)}</TableCell>
                      <TableCell className="text-right tabular-nums">{fmtInt(d.answers)}</TableCell>
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <div className="grid gap-5 lg:grid-cols-2">
          {series.data && <CacheRateChart buckets={series.data} days={days} />}
          {series.data && <CostChart buckets={series.data} days={days} />}
        </div>

        {s && (
          <>
            <div className="grid gap-5 lg:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle>Agents les plus actifs</CardTitle>
                </CardHeader>
                <CardContent>
                  <RankBars
                    rows={s.clients.map((c) => ({
                      label: c.client,
                      value: c.requests,
                    }))}
                  />
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>Domaines les plus demandés</CardTitle>
                </CardHeader>
                <CardContent>
                  <RankBars
                    rows={s.domains.map((d) => ({
                      label: d.domain,
                      value: d.requests,
                      note: d.requests ? `${Math.round(((d.hits ?? 0) / d.requests) * 100)} % cache` : undefined,
                    }))}
                  />
                </CardContent>
              </Card>
            </div>

            <div className="grid gap-5 lg:grid-cols-2">
              <QuestionList title="Questions les plus répétées" rows={s.top_repeated_questions} />
              <QuestionList
                title="Questions sans réponse"
                rows={s.top_unanswered_questions}
                empty="Aucune : toutes les questions ont trouvé une réponse."
              />
            </div>
          </>
        )}
      </div>
    </Page>
  );
}

function OutcomeShare({ stats }: { stats: Partial<Record<Outcome, number>> }) {
  const keys = Object.keys(OUTCOMES) as Outcome[];
  const total = keys.reduce((sum, k) => sum + (stats[k] ?? 0), 0);
  if (!total) return <EmptyState>Pas encore de requêtes sur cette période.</EmptyState>;
  return (
    <>
      <div
        className="flex gap-0.5 h-3 rounded overflow-hidden"
        role="img"
        aria-label="Répartition des réponses par origine"
      >
        {keys
          .filter((k) => stats[k])
          .map((k) => (
            <div
              key={k}
              style={{
                width: `${((stats[k] ?? 0) / total) * 100}%`,
                background: OUTCOMES[k].color,
              }}
            />
          ))}
      </div>
      <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
        {keys.map((k) => (
          <span key={k} className="inline-flex items-center gap-1.5">
            <Swatch color={OUTCOMES[k].color} />
            {OUTCOMES[k].label} : <b className="tabular-nums">{fmtInt(stats[k] ?? 0)}</b>
            <span className="text-muted-foreground">({fmtPct((stats[k] ?? 0) / total)})</span>
          </span>
        ))}
      </div>
    </>
  );
}

// Causes des absences de réponse, avec les libellés fournis par l'API.
function UnansweredReasons({ counts }: { counts: Record<string, number> }) {
  const reasons = useSettings().data?.reasons ?? {};
  const rows = Object.entries(counts ?? {}).sort((a, b) => b[1] - a[1]);
  if (!rows.length) return null;
  return (
    <div className="space-y-1.5 text-sm">
      <div className="font-medium">Causes des absences de réponse</div>
      {rows.map(([reason, n]) => (
        <div key={reason} className="flex items-center justify-between gap-4">
          <span>
            <code className="text-xs">{reason}</code>{' '}
            <span className="text-muted-foreground">{reasons[reason] ?? ''}</span>
          </span>
          <b className="tabular-nums">{fmtInt(n)}</b>
        </div>
      ))}
    </div>
  );
}

function QuestionList({
  title,
  rows,
  empty = 'Rien sur cette période.',
  href,
}: {
  title: string;
  rows: { question: string; requests: number }[];
  empty?: string;
  href?: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {href && (
          <CardToolbar>
            <Button variant="outline" size="sm" asChild>
              <Link href={href}>Traiter</Link>
            </Button>
          </CardToolbar>
        )}
      </CardHeader>
      <CardContent>
        {rows.length ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Question</TableHead>
                <TableHead className="text-right">Fois</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.question}>
                  <TableCell>{r.question}</TableCell>
                  <TableCell className="text-right tabular-nums">{fmtInt(r.requests)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <EmptyState>{empty}</EmptyState>
        )}
      </CardContent>
    </Card>
  );
}
