'use client';

import { useMemo } from 'react';
import { type ColumnDef } from '@tanstack/react-table';
import { Bot, Globe, Plug, UserPlus } from 'lucide-react';
import { downloadCsv, fmtAgo, fmtDate, fmtInt, useKeys, useStats, type KeyRow } from '@/lib/nm304';
import { Progress } from '@/components/ui/progress';
import { ColumnHeader, DataTable } from '@/components/nm304/data-table';
import { Page } from '@/components/nm304/page';
import { PeriodFilter, usePeriod } from '@/components/nm304/period-filter';
import { StatCard, StatGrid } from '@/components/nm304/stat-card';

interface ClientRow {
  client: string;
  requests: number;
  share: number;
}

export default function AgentsPage() {
  const [days, setDays] = usePeriod();
  const stats = useStats(days);
  const keys = useKeys();
  const s = stats.data;
  const channels = s?.channels ?? {};
  const total = s?.requests ?? 0;
  const registered = (keys.data ?? []).filter((k) => k.origin === 'self');

  const clients: ClientRow[] = (s?.clients ?? []).map((c) => ({
    ...c,
    share: total ? c.requests / total : 0,
  }));

  const clientColumns = useMemo<ColumnDef<ClientRow>[]>(
    () => [
      {
        id: 'client',
        accessorFn: (r) => r.client,
        header: ({ column }) => <ColumnHeader title="Agent (nom et version annoncés)" column={column} />,
        cell: ({ row }) => <span className="font-medium text-mono">{row.original.client}</span>,
        size: 320,
      },
      {
        id: 'requests',
        accessorFn: (r) => r.requests,
        header: ({ column }) => <ColumnHeader title="Requêtes" column={column} />,
        cell: ({ row }) => <span className="tabular-nums">{fmtInt(row.original.requests)}</span>,
        size: 110,
      },
      {
        id: 'share',
        accessorFn: (r) => r.share,
        header: ({ column }) => <ColumnHeader title="Part du trafic" column={column} />,
        cell: ({ row }) => (
          <div className="flex items-center gap-2 min-w-40">
            <Progress value={row.original.share * 100} className="h-1.5" />
            <span className="text-xs tabular-nums w-10 text-right">{Math.round(row.original.share * 100)} %</span>
          </div>
        ),
        size: 200,
      },
    ],
    [],
  );

  const registeredColumns = useMemo<ColumnDef<KeyRow>[]>(
    () => [
      {
        id: 'label',
        accessorFn: (r) => r.label,
        header: ({ column }) => <ColumnHeader title="Agent" column={column} />,
        cell: ({ row }) => (
          <div>
            <div className="font-medium text-mono">{row.original.label}</div>
            <div className="text-xs text-muted-foreground">inscrit le {fmtDate(row.original.created_at)}</div>
          </div>
        ),
        size: 220,
      },
      {
        id: 'use_case',
        accessorFn: (r) => r.use_case ?? '',
        header: ({ column }) => <ColumnHeader title="Usage déclaré" column={column} />,
        cell: ({ row }) =>
          row.original.use_case ? (
            <span className="line-clamp-2 max-w-md">{row.original.use_case}</span>
          ) : (
            <span className="text-muted-foreground">non précisé</span>
          ),
        size: 320,
      },
      {
        id: 'contact',
        accessorFn: (r) => r.contact ?? '',
        header: ({ column }) => <ColumnHeader title="Contact" column={column} />,
        cell: ({ row }) => <span className="break-all">{row.original.contact ?? '—'}</span>,
        size: 180,
      },
      {
        id: 'used',
        accessorFn: (r) => r.used,
        header: ({ column }) => <ColumnHeader title="Utilisation" column={column} />,
        cell: ({ row }) => (
          <div className="min-w-32 space-y-1">
            <Progress value={(row.original.used / row.original.quota) * 100} className="h-1.5" />
            <div className="text-xs text-muted-foreground tabular-nums">
              {fmtInt(row.original.used)} / {fmtInt(row.original.quota)}
            </div>
          </div>
        ),
        size: 150,
      },
      {
        id: 'last_used',
        accessorFn: (r) => r.last_used ?? 0,
        header: ({ column }) => <ColumnHeader title="Dernière activité" column={column} />,
        cell: ({ row }) => <span className="whitespace-nowrap">{fmtAgo(row.original.last_used)}</span>,
        size: 130,
      },
    ],
    [],
  );

  return (
    <Page title="Agents" icon={Bot} actions={<PeriodFilter days={days} onChange={setDays} />}>
      <StatGrid cols={4}>
        <StatCard
          icon={Bot}
          label="Agents différents"
          value={s && s.clients.length >= 20 ? '20 et plus' : fmtInt(s?.clients.length ?? 0)}
          hint="Nom annoncé par l'agent ou son outil"
        />
        <StatCard
          icon={Plug}
          label="Par le serveur MCP"
          value={fmtInt(channels.mcp ?? 0)}
          hint="Requêtes sur la période"
        />
        <StatCard
          icon={Globe}
          label="Par l'API HTTP"
          value={fmtInt(channels.http ?? 0)}
          hint="Requêtes sur la période"
        />
        <StatCard
          icon={UserPlus}
          label="Inscrits d'eux-mêmes"
          value={fmtInt(registered.length)}
          hint="Clés gratuites demandées par des agents"
        />
      </StatGrid>

      <DataTable
        title="Agents actifs sur la période"
        description="Les 20 agents les plus actifs, avec leur part du trafic."
        data={clients}
        columns={clientColumns}
        isLoading={stats.isLoading}
        getRowId={(r) => r.client}
        initialSort={[{ id: 'requests', desc: true }]}
        searchText={(r) => [r.client]}
        emptyMessage="Aucun agent sur cette période. Partagez l'adresse MCP ou le llms.txt pour en attirer."
        csv={{
          filename: 'agents.csv',
          export: (list) =>
            downloadCsv(
              'agents.csv',
              ['Agent', 'Requêtes'],
              list.map((r) => [r.client, r.requests]),
            ),
        }}
      />

      <DataTable
        title="Agents inscrits"
        description="Ce que chaque agent a déclaré en demandant sa clé gratuite (POST /v1/keys)."
        data={registered}
        columns={registeredColumns}
        isLoading={keys.isLoading}
        getRowId={(r) => r.key + r.created_at}
        searchText={(r) => [r.label, r.use_case, r.contact]}
        emptyMessage="Aucun agent inscrit pour le moment."
        csv={{
          filename: 'agents-inscrits.csv',
          export: (list) =>
            downloadCsv(
              'agents-inscrits.csv',
              ['Agent', 'Usage déclaré', 'Contact', 'Utilisé', 'Quota', 'Inscrit le', 'Dernière activité'],
              list.map((k) => [
                k.label,
                k.use_case,
                k.contact,
                k.used,
                k.quota,
                fmtDate(k.created_at),
                fmtAgo(k.last_used),
              ]),
            ),
        }}
      />
    </Page>
  );
}
