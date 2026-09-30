'use client';

import { Fragment, useMemo, useState } from 'react';
import { History } from 'lucide-react';
import { fmtDate, fmtEur, fmtInt, fmtPct, useRequests, type RequestRow } from '@/lib/nm304';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { EmptyState, Page } from '@/components/nm304/page';
import { FeedbackTag, OutcomeTag } from '@/components/nm304/tags';

export default function RequestsPage() {
  const requests = useRequests(500);
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState<string | null>(null);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const all = requests.data ?? [];
    if (!q) return all;
    return all.filter((r) =>
      [r.question, r.domain, r.client, r.context, r.key_label].some((v) => v?.toLowerCase().includes(q)),
    );
  }, [requests.data, query]);

  return (
    <Page
      title="Requêtes"
      icon={History}
      actions={
        <Input
          placeholder="Filtrer : question, domaine, agent…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="w-64"
        />
      }
    >
      <p className="text-sm text-muted-foreground">
        Les 500 dernières requêtes des agents. Cliquez sur une ligne pour voir la tâche de l&apos;agent et la réponse
        exacte qu&apos;il a reçue.
      </p>
      <Card>
        <CardContent className="p-0 overflow-x-auto">
          {requests.error && <p className="p-4 text-sm text-destructive">{requests.error.message}</p>}
          {rows.length ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Question</TableHead>
                  <TableHead>Domaine</TableHead>
                  <TableHead>Origine</TableHead>
                  <TableHead>Agent</TableHead>
                  <TableHead>Retour</TableHead>
                  <TableHead className="text-right">Durée</TableHead>
                  <TableHead className="text-right">Coût</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((r, i) => {
                  const id = r.request_id ?? String(i);
                  return (
                    <Fragment key={id}>
                      <TableRow className="cursor-pointer" onClick={() => setOpen(open === id ? null : id)}>
                        <TableCell className="whitespace-nowrap">{fmtDate(r.ts)}</TableCell>
                        <TableCell className="min-w-64">{r.question}</TableCell>
                        <TableCell>{r.domain ?? '—'}</TableCell>
                        <TableCell>
                          <OutcomeTag outcome={r.outcome} />
                        </TableCell>
                        <TableCell className="whitespace-nowrap">
                          <span className="text-muted-foreground">{r.channel === 'mcp' ? 'MCP' : 'API'} · </span>
                          {r.client ?? r.key_label}
                        </TableCell>
                        <TableCell>
                          <FeedbackTag
                            useful={r.feedback_useful === null ? null : Boolean(r.feedback_useful)}
                            issue={r.feedback_issue}
                          />
                        </TableCell>
                        <TableCell className="text-right tabular-nums whitespace-nowrap">
                          {fmtInt(r.latency_ms)} ms
                        </TableCell>
                        <TableCell className="text-right tabular-nums whitespace-nowrap">{fmtEur(r.cost_eur)}</TableCell>
                      </TableRow>
                      {open === id && <Detail row={r} />}
                    </Fragment>
                  );
                })}
              </TableBody>
            </Table>
          ) : (
            <EmptyState>{requests.isLoading ? 'Chargement…' : 'Aucune requête.'}</EmptyState>
          )}
        </CardContent>
      </Card>
    </Page>
  );
}

function Detail({ row }: { row: RequestRow }) {
  return (
    <TableRow className="bg-muted/40 hover:bg-muted/40">
      <TableCell colSpan={8} className="text-sm space-y-1.5 whitespace-pre-wrap break-words">
        <div>
          <b>Tâche de l&apos;agent : </b>
          {row.context ?? <span className="text-muted-foreground">non précisée</span>}
        </div>
        <div>
          <b>Réponse servie : </b>
          {row.answer ?? <span className="text-muted-foreground">aucune</span>}
          {row.confidence !== null && <span className="text-muted-foreground"> (confiance {fmtPct(row.confidence)})</span>}
        </div>
        <div className="text-xs text-muted-foreground">
          Requête {row.request_id ?? '?'} · clé {row.key_label}
        </div>
      </TableCell>
    </TableRow>
  );
}
