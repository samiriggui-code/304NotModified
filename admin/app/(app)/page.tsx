'use client';

import Link from 'next/link';
import { LayoutDashboard } from 'lucide-react';
import { fmtInt, fmtPct, OUTCOMES, useStats, useTimeseries, type Outcome } from '@/lib/nm304';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { CacheRateChart, CostChart, RankBars, VolumeChart } from '@/components/nm304/charts';
import { KpiTiles } from '@/components/nm304/kpi-tiles';
import { EmptyState, Page } from '@/components/nm304/page';
import { PeriodFilter, usePeriod } from '@/components/nm304/period-filter';
import { Swatch } from '@/components/nm304/tags';

export default function DashboardPage() {
  const [days, setDays] = usePeriod();
  const stats = useStats(days);
  const series = useTimeseries(days);
  const s = stats.data;

  return (
    <Page title="Tableau de bord" icon={LayoutDashboard} actions={<PeriodFilter days={days} onChange={setDays} />}>
      {stats.error && <p className="text-sm text-destructive">{stats.error.message}</p>}
      {/* Pendant un rechargement, l'affichage précédent reste en place, un peu estompé. */}
      <div className={`space-y-5 transition-opacity ${stats.isFetching && s ? 'opacity-70' : ''}`}>
        {s && <KpiTiles stats={s} />}

        {series.data && <VolumeChart buckets={series.data} days={days} />}

        <div className="grid gap-5 lg:grid-cols-2">
          {series.data && <CacheRateChart buckets={series.data} days={days} />}
          {series.data && <CostChart buckets={series.data} days={days} />}
        </div>

        {s && (
          <>
            <Card>
              <CardHeader>
                <CardTitle>D&apos;où viennent les réponses</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <OutcomeShare stats={s.outcomes} />
                <p className="text-sm text-muted-foreground">
                  <b>Cache</b> : déjà en mémoire, servie immédiatement (coût quasi nul). <b>Recherche</b> : nouvelle
                  recherche sur le web (payante). <b>Sans réponse</b> : rien de fiable trouvé, ou clé Anthropic absente.
                </p>
              </CardContent>
            </Card>

            <div className="grid gap-5 lg:grid-cols-2">
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
              <Card>
                <CardHeader>
                  <CardTitle>
                    <Link href="/agents" className="hover:text-primary">
                      Agents les plus actifs
                    </Link>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <RankBars rows={s.clients.map((c) => ({ label: c.client, value: c.requests }))} />
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
      <div className="flex gap-0.5 h-3 rounded overflow-hidden" role="img" aria-label="Répartition des réponses par origine">
        {keys
          .filter((k) => stats[k])
          .map((k) => (
            <div key={k} style={{ width: `${((stats[k] ?? 0) / total) * 100}%`, background: OUTCOMES[k].color }} />
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

function QuestionList({
  title,
  rows,
  empty = 'Rien sur cette période.',
}: {
  title: string;
  rows: { question: string; requests: number }[];
  empty?: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
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
