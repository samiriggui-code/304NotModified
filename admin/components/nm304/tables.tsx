'use client';

import { ReactNode, useMemo, useState } from 'react';
import { type ColumnDef } from '@tanstack/react-table';
import {
  downloadCsv,
  fmtAgo,
  fmtDate,
  fmtInt,
  fmtPct,
  hostOf,
  ISSUES,
  OUTCOMES,
  type AnswerRow,
  type FeedbackRow,
  type Outcome,
  type RequestRow,
} from '@/lib/nm304';
import { Badge } from '@/components/ui/badge';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { ColumnHeader, DataTable } from './data-table';
import { AnswerSheet, RequestSheet } from './details';
import { FeedbackTag, OutcomeTag } from './tags';

const clamp = (text: string, className = 'max-w-md') => (
  <span className={`line-clamp-2 ${className}`} title={text}>
    {text}
  </span>
);

// --- requêtes -------------------------------------------------------------------------

export function RequestsTable({
  rows,
  isLoading,
  title = 'Requêtes des agents',
  description,
  showDomain = true,
  pageSize = 10,
  emptyMessage,
}: {
  rows: RequestRow[];
  isLoading?: boolean;
  title?: ReactNode;
  description?: ReactNode;
  showDomain?: boolean;
  pageSize?: number;
  emptyMessage?: ReactNode;
}) {
  const [open, setOpen] = useState<RequestRow | null>(null);
  const [outcome, setOutcome] = useState<Outcome | 'all'>('all');
  const data = useMemo(() => (outcome === 'all' ? rows : rows.filter((r) => r.outcome === outcome)), [rows, outcome]);

  const columns = useMemo<ColumnDef<RequestRow>[]>(
    () => [
      {
        id: 'ts',
        accessorFn: (r) => r.ts,
        header: ({ column }) => <ColumnHeader title="Date" column={column} />,
        cell: ({ row }) => (
          <span className="whitespace-nowrap text-secondary-foreground">{fmtDate(row.original.ts)}</span>
        ),
        size: 130,
      },
      {
        id: 'question',
        accessorFn: (r) => r.question,
        header: ({ column }) => <ColumnHeader title="Question" column={column} />,
        cell: ({ row }) => (
          <div className="space-y-0.5">
            <div className="font-medium text-mono">{clamp(row.original.question)}</div>
            {row.original.context && (
              <div className="text-xs text-muted-foreground">{clamp(`Tâche : ${row.original.context}`)}</div>
            )}
          </div>
        ),
        size: 380,
      },
      ...(showDomain
        ? [
            {
              id: 'domain',
              accessorFn: (r: RequestRow) => r.domain ?? '',
              header: ({ column }) => <ColumnHeader title="Domaine" column={column} />,
              cell: ({ row }) =>
                row.original.domain ? (
                  <Badge variant="secondary" appearance="light" size="sm">
                    {row.original.domain}
                  </Badge>
                ) : (
                  '—'
                ),
              size: 130,
            } satisfies ColumnDef<RequestRow>,
          ]
        : []),
      {
        id: 'outcome',
        accessorFn: (r) => r.outcome,
        header: ({ column }) => <ColumnHeader title="Origine" column={column} />,
        cell: ({ row }) => <OutcomeTag outcome={row.original.outcome} />,
        size: 130,
      },
      {
        id: 'agent',
        accessorFn: (r) => r.client ?? r.key_label,
        header: ({ column }) => <ColumnHeader title="Agent" column={column} />,
        cell: ({ row }) => (
          <div className="whitespace-nowrap">
            <div className="truncate max-w-48">{row.original.client ?? row.original.key_label}</div>
            <div className="text-xs text-muted-foreground">
              {row.original.channel === 'mcp' ? 'MCP' : 'API'} · {row.original.key_label}
            </div>
          </div>
        ),
        size: 190,
      },
      {
        id: 'feedback',
        accessorFn: (r) => r.feedback_useful ?? -1,
        header: ({ column }) => <ColumnHeader title="Retour" column={column} />,
        cell: ({ row }) => (
          <FeedbackTag
            useful={row.original.feedback_useful === null ? null : Boolean(row.original.feedback_useful)}
            issue={row.original.feedback_issue}
          />
        ),
        size: 140,
      },
      {
        id: 'latency',
        accessorFn: (r) => r.latency_ms,
        header: ({ column }) => <ColumnHeader title="Durée" column={column} />,
        cell: ({ row }) => <span className="tabular-nums whitespace-nowrap">{fmtInt(row.original.latency_ms)} ms</span>,
        size: 90,
      },
    ],
    [showDomain],
  );

  return (
    <>
      <DataTable
        title={title}
        description={description ?? 'Cliquez sur une ligne pour voir la tâche de l’agent et la réponse exacte reçue.'}
        data={data}
        columns={columns}
        isLoading={isLoading}
        pageSize={pageSize}
        onRowClick={setOpen}
        getRowId={(r, i) => r.request_id ?? String(i)}
        searchText={(r) => [r.question, r.domain, r.client, r.context, r.key_label, r.answer]}
        searchPlaceholder="Question, agent, tâche…"
        emptyMessage={emptyMessage ?? 'Aucune requête pour le moment.'}
        toolbar={
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            value={outcome}
            onValueChange={(v) => v && setOutcome(v as Outcome | 'all')}
          >
            <ToggleGroupItem value="all">Toutes</ToggleGroupItem>
            {(Object.keys(OUTCOMES) as Outcome[]).map((k) => (
              <ToggleGroupItem key={k} value={k}>
                {OUTCOMES[k].label}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        }
        csv={{
          filename: 'requetes.csv',
          export: (list) =>
            downloadCsv(
              'requetes.csv',
              [
                'Date',
                'Question',
                'Domaine',
                'Origine',
                'Agent',
                'Canal',
                'Clé',
                'Tâche',
                'Réponse',
                'Confiance',
                'Retour',
                'Durée (ms)',
              ],
              list.map((r) => [
                fmtDate(r.ts),
                r.question,
                r.domain,
                OUTCOMES[r.outcome]?.label ?? r.outcome,
                r.client,
                r.channel,
                r.key_label,
                r.context,
                r.answer,
                r.confidence === null ? '' : fmtPct(r.confidence),
                r.feedback_useful === null ? '' : r.feedback_useful ? 'utile' : `pas utile ${r.feedback_issue ?? ''}`,
                r.latency_ms,
              ]),
            ),
        }}
      />
      <RequestSheet row={open} onClose={() => setOpen(null)} />
    </>
  );
}

// --- réponses en mémoire ------------------------------------------------------------------

export function AnswersTable({
  rows,
  isLoading,
  title = 'Réponses en mémoire',
  description,
  showDomain = true,
  pageSize = 10,
  emptyMessage,
}: {
  rows: AnswerRow[];
  isLoading?: boolean;
  title?: ReactNode;
  description?: ReactNode;
  showDomain?: boolean;
  pageSize?: number;
  emptyMessage?: ReactNode;
}) {
  const [open, setOpen] = useState<AnswerRow | null>(null);
  const now = Date.now() / 1000;

  const columns = useMemo<ColumnDef<AnswerRow>[]>(
    () => [
      {
        id: 'question',
        accessorFn: (r) => r.question,
        header: ({ column }) => <ColumnHeader title="Question" column={column} />,
        cell: ({ row }) => (
          <div className="space-y-0.5">
            <div className="font-medium text-mono">{clamp(row.original.question)}</div>
            <div className="text-xs text-muted-foreground">{clamp(row.original.answer)}</div>
          </div>
        ),
        size: 420,
      },
      ...(showDomain
        ? [
            {
              id: 'domain',
              accessorFn: (r: AnswerRow) => r.domain,
              header: ({ column }) => <ColumnHeader title="Domaine" column={column} />,
              cell: ({ row }) => (
                <Badge variant="secondary" appearance="light" size="sm">
                  {row.original.domain}
                </Badge>
              ),
              size: 130,
            } satisfies ColumnDef<AnswerRow>,
          ]
        : []),
      {
        id: 'confidence',
        accessorFn: (r) => r.confidence,
        header: ({ column }) => <ColumnHeader title="Confiance" column={column} />,
        cell: ({ row }) => (
          <Badge
            variant={
              row.original.confidence >= 0.8 ? 'success' : row.original.confidence >= 0.6 ? 'warning' : 'destructive'
            }
            appearance="light"
            size="sm"
          >
            {fmtPct(row.original.confidence)}
          </Badge>
        ),
        size: 110,
      },
      {
        id: 'sources',
        accessorFn: (r) => r.sources.length,
        header: ({ column }) => <ColumnHeader title="Sources" column={column} />,
        cell: ({ row }) => (
          <span className="text-xs text-muted-foreground line-clamp-2 max-w-48">
            {row.original.sources.map((s) => hostOf(s.url)).join(', ') || '—'}
          </span>
        ),
        size: 190,
      },
      {
        id: 'hits',
        accessorFn: (r) => r.hits,
        header: ({ column }) => <ColumnHeader title="Servie" column={column} />,
        cell: ({ row }) => <span className="tabular-nums">{fmtInt(row.original.hits)} fois</span>,
        size: 90,
      },
      {
        id: 'expires',
        accessorFn: (r) => r.expires_at,
        header: ({ column }) => <ColumnHeader title="Fraîcheur" column={column} />,
        cell: ({ row }) =>
          row.original.expires_at <= now ? (
            <Badge variant="destructive" appearance="light" size="sm">
              Expirée
            </Badge>
          ) : (
            <span className="text-xs text-muted-foreground whitespace-nowrap">
              jusqu’au {fmtDate(row.original.expires_at)}
            </span>
          ),
        size: 150,
      },
    ],
    [showDomain, now],
  );

  return (
    <>
      <DataTable
        title={title}
        description={
          description ?? 'Les réponses gardées pour les prochains agents. Cliquez pour voir la réponse et ses sources.'
        }
        data={rows}
        columns={columns}
        isLoading={isLoading}
        pageSize={pageSize}
        onRowClick={setOpen}
        getRowId={(r) => r.key}
        searchText={(r) => [r.question, r.answer, r.domain, ...r.sources.map((s) => s.url)]}
        searchPlaceholder="Question, réponse, source…"
        emptyMessage={
          emptyMessage ??
          'Aucune réponse en mémoire : elles apparaissent dès que la recherche est active et qu’un agent pose une question.'
        }
        csv={{
          filename: 'reponses.csv',
          export: (list) =>
            downloadCsv(
              'reponses.csv',
              ['Question', 'Réponse', 'Domaine', 'Confiance', 'Sources', 'Servie', 'Obtenue le', 'Expire le'],
              list.map((r) => [
                r.question,
                r.answer,
                r.domain,
                fmtPct(r.confidence),
                r.sources.map((s) => s.url).join(' '),
                r.hits,
                fmtDate(r.created_at),
                fmtDate(r.expires_at),
              ]),
            ),
        }}
      />
      <AnswerSheet row={open} onClose={() => setOpen(null)} />
    </>
  );
}

// --- retours des agents ------------------------------------------------------------------

export function FeedbackTable({
  rows,
  isLoading,
  title = 'Retours des agents',
  pageSize = 10,
}: {
  rows: FeedbackRow[];
  isLoading?: boolean;
  title?: ReactNode;
  pageSize?: number;
}) {
  const columns = useMemo<ColumnDef<FeedbackRow>[]>(
    () => [
      {
        id: 'ts',
        accessorFn: (r) => r.ts,
        header: ({ column }) => <ColumnHeader title="Date" column={column} />,
        cell: ({ row }) => (
          <span className="whitespace-nowrap text-secondary-foreground">{fmtAgo(row.original.ts)}</span>
        ),
        size: 110,
      },
      {
        id: 'question',
        accessorFn: (r) => r.question,
        header: ({ column }) => <ColumnHeader title="Question" column={column} />,
        cell: ({ row }) => <span className="font-medium text-mono">{clamp(row.original.question)}</span>,
        size: 320,
      },
      {
        id: 'useful',
        accessorFn: (r) => (r.useful ? 1 : 0),
        header: ({ column }) => <ColumnHeader title="Retour" column={column} />,
        cell: ({ row }) => <FeedbackTag useful={row.original.useful} issue={row.original.issue} />,
        size: 170,
      },
      {
        id: 'comment',
        accessorFn: (r) => r.comment ?? '',
        header: ({ column }) => <ColumnHeader title="Commentaire" column={column} />,
        cell: ({ row }) =>
          row.original.comment ? clamp(row.original.comment) : <span className="text-muted-foreground">—</span>,
        size: 280,
      },
      {
        id: 'client',
        accessorFn: (r) => r.client ?? '',
        header: ({ column }) => <ColumnHeader title="Agent" column={column} />,
        cell: ({ row }) => <span className="whitespace-nowrap">{row.original.client ?? '?'}</span>,
        size: 160,
      },
    ],
    [],
  );
  return (
    <DataTable
      title={title}
      description="Un retour est noté à part : il ne modifie jamais une réponse. C’est à vous de décider quoi en faire."
      data={rows}
      columns={columns}
      isLoading={isLoading}
      pageSize={pageSize}
      getRowId={(r) => r.request_id}
      searchText={(r) => [r.question, r.comment, r.client, r.issue ? ISSUES[r.issue] : null]}
      searchPlaceholder="Question, commentaire, agent…"
      emptyMessage="Aucun retour pour le moment : les agents en envoient avec l’outil « feedback » ou POST /v1/feedback."
      csv={{
        filename: 'retours.csv',
        export: (list) =>
          downloadCsv(
            'retours.csv',
            ['Date', 'Question', 'Utile', 'Problème', 'Commentaire', 'Agent', 'Réponse servie'],
            list.map((r) => [
              fmtDate(r.ts),
              r.question,
              r.useful ? 'oui' : 'non',
              r.issue ? (ISSUES[r.issue] ?? r.issue) : '',
              r.comment,
              r.client,
              r.answer,
            ]),
          ),
      }}
    />
  );
}
