'use client';

import { MessageSquareReply, ThumbsDown, ThumbsUp } from 'lucide-react';
import { fmtInt, fmtPct, ISSUES, useFeedback, useStats } from '@/lib/nm304';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { RankBars } from '@/components/nm304/charts';
import { Page } from '@/components/nm304/page';
import { StatCard, StatGrid } from '@/components/nm304/stat-card';
import { FeedbackTable } from '@/components/nm304/tables';

export default function FeedbackPage() {
  const feedback = useFeedback(500);
  const stats = useStats(3650);
  const fb = stats.data?.feedback;
  const negative = (feedback.data ?? []).filter((f) => !f.useful).length;

  return (
    <Page title="Retours des agents" icon={MessageSquareReply}>
      <div className="grid gap-5 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <StatGrid cols={3}>
            <StatCard
              icon={MessageSquareReply}
              label="Retours reçus"
              value={fb ? fmtInt(fb.count) : '—'}
              hint="Depuis le début"
            />
            <StatCard
              icon={ThumbsUp}
              label="Jugées utiles"
              value={fb?.count ? fmtPct(fb.useful_rate) : '—'}
              hint="Part des réponses qui ont aidé l'agent"
              highlight
            />
            <StatCard
              icon={ThumbsDown}
              label="Pas utiles"
              value={fmtInt(negative)}
              hint="Voir le commentaire de l'agent ci-dessous"
            />
          </StatGrid>
        </div>
        <Card>
          <CardHeader>
            <CardTitle>Problèmes signalés</CardTitle>
          </CardHeader>
          <CardContent>
            <RankBars
              rows={Object.entries(fb?.issues ?? {}).map(([issue, n]) => ({
                label: ISSUES[issue] ?? issue,
                value: n,
              }))}
            />
          </CardContent>
        </Card>
      </div>
      <FeedbackTable rows={feedback.data ?? []} isLoading={feedback.isLoading} pageSize={25} />
    </Page>
  );
}
