'use client';

import { Bot } from 'lucide-react';
import { fmtInt, useStats } from '@/lib/nm304';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { RankBars } from '@/components/nm304/charts';
import { Page } from '@/components/nm304/page';
import { PeriodFilter, usePeriod } from '@/components/nm304/period-filter';

export default function AgentsPage() {
  const [days, setDays] = usePeriod();
  const stats = useStats(days);
  const s = stats.data;
  const channels = s?.channels ?? {};

  return (
    <Page title="Agents" icon={Bot} actions={<PeriodFilter days={days} onChange={setDays} />}>
      <p className="text-sm text-muted-foreground">
        Qui utilise le service : le nom et la version annoncés par chaque agent (ou son outil), et le canal utilisé.
      </p>
      <div className="grid gap-5 lg:grid-cols-3">
        <Card>
          <CardContent className="p-4 space-y-1">
            <div className="text-sm text-muted-foreground">Par le serveur MCP</div>
            <div className="text-2xl font-semibold text-mono">{fmtInt(channels.mcp ?? 0)}</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 space-y-1">
            <div className="text-sm text-muted-foreground">Par l&apos;API directe</div>
            <div className="text-2xl font-semibold text-mono">{fmtInt(channels.http ?? 0)}</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 space-y-1">
            <div className="text-sm text-muted-foreground">Agents différents</div>
            {/* L'API renvoie les 20 agents les plus actifs. */}
            <div className="text-2xl font-semibold text-mono">
              {s && s.clients.length >= 20 ? '20 et plus' : fmtInt(s?.clients.length ?? 0)}
            </div>
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Requêtes par agent</CardTitle>
        </CardHeader>
        <CardContent>
          <RankBars rows={(s?.clients ?? []).map((c) => ({ label: c.client, value: c.requests }))} />
        </CardContent>
      </Card>
    </Page>
  );
}
