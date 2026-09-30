'use client';

import { Clock, History, Plug, Send, Timer } from 'lucide-react';
import { fmtAgo, fmtInt, useRequests } from '@/lib/nm304';
import { Page } from '@/components/nm304/page';
import { StatCard, StatGrid } from '@/components/nm304/stat-card';
import { RequestsTable } from '@/components/nm304/tables';

export default function RequestsPage() {
  const requests = useRequests(500);
  const rows = requests.data ?? [];
  const mcp = rows.filter((r) => r.channel === 'mcp').length;
  const withTask = rows.filter((r) => r.context).length;
  const avg = rows.length ? Math.round(rows.reduce((n, r) => n + r.latency_ms, 0) / rows.length) : 0;

  return (
    <Page title="Requêtes" icon={History}>
      <StatGrid cols={4}>
        <StatCard icon={Send} label="Requêtes affichées" value={fmtInt(rows.length)} hint="Les 500 plus récentes" />
        <StatCard
          icon={Clock}
          label="Dernière requête"
          value={rows.length ? fmtAgo(rows[0].ts) : '—'}
          hint={rows[0]?.client ?? ' '}
        />
        <StatCard
          icon={Plug}
          label="Par MCP"
          value={fmtInt(mcp)}
          hint={`${fmtInt(rows.length - mcp)} par l'API HTTP`}
        />
        <StatCard
          icon={Timer}
          label="Durée moyenne"
          value={rows.length ? `${fmtInt(avg)} ms` : '—'}
          hint={`${fmtInt(withTask)} requêtes avec la tâche de l'agent`}
        />
      </StatGrid>
      <RequestsTable rows={rows} isLoading={requests.isLoading} pageSize={25} />
    </Page>
  );
}
