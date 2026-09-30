'use client';

import Link from 'next/link';
import { Layers } from 'lucide-react';
import { fmtAgo, fmtDuration, fmtInt, fmtPct, useDomains } from '@/lib/nm304';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Page } from '@/components/nm304/page';
import { PeriodFilter, usePeriod } from '@/components/nm304/period-filter';

export default function SpecialtiesPage() {
  const [days, setDays] = usePeriod();
  const domains = useDomains(days);

  return (
    <Page title="Spécialités" icon={Layers} actions={<PeriodFilter days={days} onChange={setDays} />}>
      <p className="text-sm text-muted-foreground">
        Chaque domaine que les agents peuvent interroger : son activité sur la période, ses réponses en mémoire et la
        durée pendant laquelle une réponse reste fraîche. Les spécialités ont des consignes de recherche et des sources
        officielles propres.
      </p>
      <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
        {(domains.data ?? []).map((d) => (
          <Link key={d.domain} href={`/specialites/${d.domain}`} className="block">
            <Card className="h-full hover:border-primary transition-colors">
              <CardContent className="p-5 space-y-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-semibold text-mono">{d.label}</div>
                    <div className="text-sm text-muted-foreground">{d.description}</div>
                  </div>
                  {d.specialty && (
                    <Badge variant="primary" appearance="light" size="sm">
                      Spécialité
                    </Badge>
                  )}
                </div>
                <div className="grid grid-cols-3 gap-3 text-center">
                  <div>
                    <div className="text-lg font-semibold tabular-nums">{fmtInt(d.requests)}</div>
                    <div className="text-xs text-muted-foreground">requêtes</div>
                  </div>
                  <div>
                    <div className="text-lg font-semibold tabular-nums">{fmtInt(d.answers)}</div>
                    <div className="text-xs text-muted-foreground">en mémoire</div>
                  </div>
                  <div>
                    <div className="text-lg font-semibold tabular-nums">{fmtInt(d.unanswered)}</div>
                    <div className="text-xs text-muted-foreground">sans réponse</div>
                  </div>
                </div>
                <div className="space-y-1">
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>Taux de cache</span>
                    <span className="tabular-nums">{d.hit + d.miss ? fmtPct(d.cache_hit_rate) : '—'}</span>
                  </div>
                  <Progress value={d.cache_hit_rate * 100} className="h-1.5" />
                </div>
                <div className="text-xs text-muted-foreground">
                  <code>{d.domain}</code> · fraîcheur {fmtDuration(d.ttl_seconds)} · dernière question{' '}
                  {fmtAgo(d.last_ts)}
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </Page>
  );
}
