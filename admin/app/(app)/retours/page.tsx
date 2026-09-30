'use client';

import { MessageSquareReply } from 'lucide-react';
import { fmtDate, fmtInt, fmtPct, ISSUES, useFeedback, useStats } from '@/lib/nm304';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { RankBars } from '@/components/nm304/charts';
import { EmptyState, Page } from '@/components/nm304/page';
import { FeedbackTag } from '@/components/nm304/tags';

export default function FeedbackPage() {
  const feedback = useFeedback(500);
  const stats = useStats(3650);
  const fb = stats.data?.feedback;

  return (
    <Page title="Retours des agents" icon={MessageSquareReply}>
      <p className="text-sm text-muted-foreground">
        Ce que les agents disent des réponses reçues. Un retour est noté à part : il ne modifie jamais une réponse en
        mémoire. C&apos;est à vous de décider quoi en faire.
      </p>

      <div className="grid gap-5 lg:grid-cols-3">
        <Card>
          <CardContent className="p-4 space-y-1">
            <div className="text-sm text-muted-foreground">Retours reçus</div>
            <div className="text-2xl font-semibold text-mono">{fb ? fmtInt(fb.count) : '—'}</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 space-y-1">
            <div className="text-sm text-muted-foreground">Réponses jugées utiles</div>
            <div className="text-2xl font-semibold text-mono">{fb?.count ? fmtPct(fb.useful_rate) : '—'}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Problèmes signalés</CardTitle>
          </CardHeader>
          <CardContent>
            <RankBars
              rows={Object.entries(fb?.issues ?? {}).map(([issue, n]) => ({ label: ISSUES[issue] ?? issue, value: n }))}
            />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardContent className="p-0 overflow-x-auto">
          {feedback.data?.length ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Question</TableHead>
                  <TableHead>Retour</TableHead>
                  <TableHead>Commentaire de l&apos;agent</TableHead>
                  <TableHead>Réponse servie</TableHead>
                  <TableHead>Agent</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {feedback.data.map((f) => (
                  <TableRow key={f.request_id}>
                    <TableCell className="whitespace-nowrap">{fmtDate(f.ts)}</TableCell>
                    <TableCell className="min-w-56">{f.question}</TableCell>
                    <TableCell>
                      <FeedbackTag useful={f.useful} issue={f.issue} />
                    </TableCell>
                    <TableCell className="min-w-56 whitespace-pre-wrap">{f.comment ?? '—'}</TableCell>
                    <TableCell className="min-w-56 text-muted-foreground">{f.answer ?? '—'}</TableCell>
                    <TableCell className="whitespace-nowrap">{f.client ?? '?'}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <EmptyState>{feedback.isLoading ? 'Chargement…' : 'Aucun retour pour le moment.'}</EmptyState>
          )}
        </CardContent>
      </Card>
    </Page>
  );
}
