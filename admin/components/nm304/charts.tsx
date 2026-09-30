'use client';

import { ReactNode, useState } from 'react';
import { Area, AreaChart, Bar, BarChart, CartesianGrid, XAxis, YAxis } from 'recharts';
import { fmtBucket, fmtEur, fmtInt, fmtPct, OUTCOMES, type Bucket, type Outcome } from '@/lib/nm304';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardHeading, CardTitle, CardToolbar } from '@/components/ui/card';
import { ChartContainer, ChartTooltip, type ChartConfig } from '@/components/ui/chart';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { EmptyState } from './page';
import { Swatch } from './tags';

// Règles de lecture : marques fines, arrondi 4 px côté donnée, grille discrète, un seul axe,
// infobulle au survol, légende pour plusieurs séries, et une vue tableau pour chaque graphique.

const OUTCOME_KEYS: Outcome[] = ['hit', 'miss', 'unanswered'];

const volumeConfig = Object.fromEntries(
  OUTCOME_KEYS.map((k) => [k, { label: OUTCOMES[k].label, color: OUTCOMES[k].color }]),
) satisfies ChartConfig;

// Graduation « ronde » (1, 2, 5 × 10ⁿ) : 0, 10, 20, 30… plutôt que 62,5.
function niceTicks(max: number, integer: boolean): number[] {
  if (max <= 0) return integer ? [0, 1, 2, 3, 4] : [0, 0.25, 0.5, 0.75, 1];
  const raw = max / 4;
  const p = 10 ** Math.floor(Math.log10(raw));
  let step = [1, 2, 5, 10].map((m) => m * p).find((v) => v >= raw) ?? 10 * p;
  if (integer) step = Math.max(1, Math.round(step));
  const top = Math.ceil(max / step - 1e-9) * step;
  return Array.from({ length: Math.round(top / step) + 1 }, (_, i) => +(i * step).toFixed(6));
}

interface TooltipRow {
  label: string;
  value: string;
  color?: string;
}

function Tip({ title, rows }: { title: string; rows: TooltipRow[] }) {
  return (
    <div className="rounded-lg border border-border bg-background px-3 py-2 text-xs shadow-md min-w-40">
      <div className="text-muted-foreground mb-1">{title}</div>
      {rows.map((r) => (
        <div key={r.label} className="flex items-center justify-between gap-4">
          <span className="inline-flex items-center gap-1.5 text-muted-foreground">
            {r.color && <i className="inline-block w-3 h-0.5 rounded-full" style={{ background: r.color }} />}
            {r.label}
          </span>
          <b className="text-foreground tabular-nums">{r.value}</b>
        </div>
      ))}
    </div>
  );
}

function ChartCard({
  title,
  description,
  legend,
  table,
  children,
}: {
  title: string;
  description?: string;
  legend?: ReactNode;
  table: () => ReactNode;
  children: ReactNode;
}) {
  const [asTable, setAsTable] = useState(false);
  return (
    <Card>
      <CardHeader>
        <CardHeading>
          <CardTitle>{title}</CardTitle>
          {description && <p className="text-sm text-muted-foreground">{description}</p>}
        </CardHeading>
        <CardToolbar>
          <Button variant="outline" size="sm" onClick={() => setAsTable(!asTable)} aria-pressed={asTable}>
            {asTable ? 'Graphique' : 'Tableau'}
          </Button>
        </CardToolbar>
      </CardHeader>
      <CardContent>
        {legend && !asTable && <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm mb-3">{legend}</div>}
        {asTable ? <div className="max-h-80 overflow-auto">{table()}</div> : children}
      </CardContent>
    </Card>
  );
}

function SimpleTable({ headers, rows }: { headers: string[]; rows: (string | number)[][] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          {headers.map((h, i) => (
            <TableHead key={h} className={i ? 'text-right' : undefined}>
              {h}
            </TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((r, i) => (
          <TableRow key={i}>
            {r.map((c, j) => (
              <TableCell key={j} className={j ? 'text-right tabular-nums' : undefined}>
                {c}
              </TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

const hasData = (buckets: Bucket[], pick: (b: Bucket) => number | null) => buckets.some((b) => (pick(b) ?? 0) > 0);

// --- volume par origine (colonnes empilées) -------------------------------------

export function VolumeChart({ buckets, days }: { buckets: Bucket[]; days: number }) {
  const totals = buckets.map((b) => b.hit + b.miss + b.unanswered);
  const ticks = niceTicks(Math.max(0, ...totals), true);
  return (
    <ChartCard
      title="Volume de requêtes"
      description={days <= 1 ? 'Par heure, sur les dernières 24 heures.' : 'Par jour, sur la période choisie.'}
      legend={OUTCOME_KEYS.map((k) => (
        <span key={k} className="inline-flex items-center gap-1.5">
          <Swatch color={OUTCOMES[k].color} />
          {OUTCOMES[k].label}
        </span>
      ))}
      table={() => (
        <SimpleTable
          headers={['Période', 'Cache', 'Recherche', 'Sans réponse', 'Total']}
          rows={buckets.map((b, i) => [fmtBucket(b.t, days, true), b.hit, b.miss, b.unanswered, totals[i]])}
        />
      )}
    >
      {hasData(buckets, (b) => b.hit + b.miss + b.unanswered) ? (
        <ChartContainer config={volumeConfig} className="aspect-auto h-64 w-full">
          <BarChart data={buckets} margin={{ left: 0, right: 8, top: 8 }} barCategoryGap="30%">
            <CartesianGrid vertical={false} />
            <XAxis
              dataKey="t"
              tickLine={false}
              axisLine={false}
              minTickGap={24}
              tickFormatter={(t) => fmtBucket(t, days)}
            />
            <YAxis
              width={40}
              tickLine={false}
              axisLine={false}
              ticks={ticks}
              domain={[0, ticks[ticks.length - 1]]}
              tickFormatter={fmtInt}
              allowDecimals={false}
            />
            <ChartTooltip
              cursor={{ fillOpacity: 0.5 }}
              content={({ active, payload }) => {
                const b = payload?.[0]?.payload as Bucket | undefined;
                if (!active || !b) return null;
                return (
                  <Tip
                    title={fmtBucket(b.t, days, true)}
                    rows={[
                      ...OUTCOME_KEYS.map((k) => ({ label: OUTCOMES[k].label, value: fmtInt(b[k]), color: OUTCOMES[k].color })),
                      { label: 'Total', value: fmtInt(b.hit + b.miss + b.unanswered) },
                    ]}
                  />
                );
              }}
            />
            {OUTCOME_KEYS.map((k, i) => (
              <Bar
                key={k}
                dataKey={k}
                stackId="v"
                fill={`var(--color-${k})`}
                maxBarSize={24}
                // Liseré de la couleur du fond : sépare les segments empilés sans ajouter d'encre.
                stroke="var(--background)"
                strokeWidth={1}
                radius={i === OUTCOME_KEYS.length - 1 ? [4, 4, 0, 0] : 0}
                isAnimationActive={false}
              />
            ))}
          </BarChart>
        </ChartContainer>
      ) : (
        <EmptyState>Pas encore de requêtes sur cette période.</EmptyState>
      )}
    </ChartCard>
  );
}

// --- taux de cache (courbe) ---------------------------------------------------------

export function CacheRateChart({ buckets, days }: { buckets: Bucket[]; days: number }) {
  const data = buckets.map((b) => ({ t: b.t, rate: b.hit + b.miss ? b.hit / (b.hit + b.miss) : null }));
  const config = { rate: { label: 'Taux de cache', color: 'var(--nm-cache)' } } satisfies ChartConfig;
  return (
    <ChartCard
      title="Taux de cache"
      description="Part servie depuis la mémoire : plus il monte, plus la marge grossit."
      table={() => (
        <SimpleTable
          headers={['Période', 'Taux de cache']}
          rows={data.map((d) => [fmtBucket(d.t, days, true), d.rate === null ? '—' : fmtPct(d.rate)])}
        />
      )}
    >
      {data.some((d) => d.rate !== null) ? (
        <ChartContainer config={config} className="aspect-auto h-52 w-full">
          <AreaChart data={data} margin={{ left: 0, right: 12, top: 8 }}>
            <CartesianGrid vertical={false} />
            <XAxis dataKey="t" tickLine={false} axisLine={false} minTickGap={24} tickFormatter={(t) => fmtBucket(t, days)} />
            <YAxis
              width={44}
              tickLine={false}
              axisLine={false}
              domain={[0, 1]}
              ticks={[0, 0.25, 0.5, 0.75, 1]}
              tickFormatter={(v) => `${Math.round(v * 100)} %`}
            />
            <ChartTooltip
              cursor={{ stroke: 'var(--border)' }}
              content={({ active, payload }) => {
                const d = payload?.[0]?.payload as { t: number; rate: number | null } | undefined;
                if (!active || !d) return null;
                return (
                  <Tip
                    title={fmtBucket(d.t, days, true)}
                    rows={[{ label: 'Taux de cache', value: d.rate === null ? 'aucune réponse' : fmtPct(d.rate), color: 'var(--nm-cache)' }]}
                  />
                );
              }}
            />
            <Area
              dataKey="rate"
              type="linear"
              stroke="var(--color-rate)"
              strokeWidth={2}
              fill="var(--color-rate)"
              fillOpacity={0.1}
              connectNulls={false}
              dot={false}
              activeDot={{ r: 4, strokeWidth: 2, stroke: 'var(--background)' }}
              isAnimationActive={false}
            />
          </AreaChart>
        </ChartContainer>
      ) : (
        <EmptyState>Aucune réponse sur cette période.</EmptyState>
      )}
    </ChartCard>
  );
}

// --- coût des recherches (colonnes) ----------------------------------------------

export function CostChart({ buckets, days }: { buckets: Bucket[]; days: number }) {
  const config = { cost_eur: { label: 'Coût estimé', color: 'var(--nm-cache)' } } satisfies ChartConfig;
  const ticks = niceTicks(Math.max(0, ...buckets.map((b) => b.cost_eur)), false);
  return (
    <ChartCard
      title="Coût des recherches"
      description="Estimation, en euros, des nouvelles recherches sur le web."
      table={() => (
        <SimpleTable
          headers={['Période', 'Coût estimé']}
          rows={buckets.map((b) => [fmtBucket(b.t, days, true), fmtEur(b.cost_eur)])}
        />
      )}
    >
      {hasData(buckets, (b) => b.cost_eur) ? (
        <ChartContainer config={config} className="aspect-auto h-52 w-full">
          <BarChart data={buckets} margin={{ left: 0, right: 8, top: 8 }} barCategoryGap="30%">
            <CartesianGrid vertical={false} />
            <XAxis dataKey="t" tickLine={false} axisLine={false} minTickGap={24} tickFormatter={(t) => fmtBucket(t, days)} />
            <YAxis
              width={56}
              tickLine={false}
              axisLine={false}
              ticks={ticks}
              domain={[0, ticks[ticks.length - 1]]}
              tickFormatter={(v) => fmtEur(v)}
            />
            <ChartTooltip
              cursor={{ fillOpacity: 0.5 }}
              content={({ active, payload }) => {
                const b = payload?.[0]?.payload as Bucket | undefined;
                if (!active || !b) return null;
                return (
                  <Tip
                    title={fmtBucket(b.t, days, true)}
                    rows={[{ label: 'Coût estimé', value: fmtEur(b.cost_eur), color: 'var(--nm-cache)' }]}
                  />
                );
              }}
            />
            <Bar dataKey="cost_eur" fill="var(--color-cost_eur)" maxBarSize={24} radius={[4, 4, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ChartContainer>
      ) : (
        <EmptyState>Aucune recherche payante sur cette période.</EmptyState>
      )}
    </ChartCard>
  );
}

// --- classement en barres horizontales (domaines, agents) ------------------------

export function RankBars({ rows }: { rows: { label: string; value: number; note?: string }[] }) {
  if (!rows.length) return <EmptyState>Rien sur cette période.</EmptyState>;
  const max = Math.max(...rows.map((r) => r.value));
  return (
    <div className="grid grid-cols-[minmax(80px,38%)_1fr] gap-x-3 gap-y-2 items-center text-sm">
      {rows.slice(0, 10).map((r) => (
        <div key={r.label} className="contents">
          <span className="truncate" title={r.label}>
            {r.label}
          </span>
          <span className="flex items-center gap-2 min-w-0">
            <span
              className="h-3.5 rounded-e-[4px] shrink-0"
              style={{ width: `${Math.max(1, (r.value / max) * 55)}%`, background: 'var(--nm-cache)' }}
            />
            <span className="tabular-nums whitespace-nowrap">{fmtInt(r.value)}</span>
            {r.note && <span className="text-muted-foreground truncate min-w-0">{r.note}</span>}
          </span>
        </div>
      ))}
    </div>
  );
}
