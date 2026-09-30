'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { ArrowLeft, Database, Layers, MessageSquareReply, Repeat, Send, Zap } from 'lucide-react';
import {
  fmtDuration,
  fmtInt,
  fmtPct,
  useAnswers,
  useDomains,
  useFeedback,
  useRequests,
  useStats,
  useTimeseries,
} from '@/lib/nm304';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { VolumeChart } from '@/components/nm304/charts';
import { Page } from '@/components/nm304/page';
import { PeriodFilter, usePeriod } from '@/components/nm304/period-filter';
import { StatCard, StatGrid } from '@/components/nm304/stat-card';
import { AnswersTable, FeedbackTable, RequestsTable } from '@/components/nm304/tables';

export default function SpecialtyPage() {
  const { domain } = useParams<{ domain: string }>();
  const [days, setDays] = usePeriod();
  const domains = useDomains(days);
  const stats = useStats(days, domain);
  const series = useTimeseries(days, domain);
  const requests = useRequests(500, domain);
  const answers = useAnswers(500, domain);
  const feedback = useFeedback(500, domain);
  const d = domains.data?.find((x) => x.domain === domain);
  const s = stats.data;

  return (
    <Page
      title={d?.label ?? domain}
      icon={Layers}
      actions={
        <>
          <Button variant="outline" asChild>
            <Link href="/specialites">
              <ArrowLeft /> Spécialités
            </Link>
          </Button>
          <PeriodFilter days={days} onChange={setDays} />
        </>
      }
    >
      {d && (
        <p className="text-sm text-muted-foreground">
          {d.description}. Domaine <code>{d.domain}</code> · une réponse reste fraîche {fmtDuration(d.ttl_seconds)}
          {d.specialty ? ' · spécialité avec consignes de recherche et sources officielles propres.' : '.'}
        </p>
      )}
      <StatGrid cols={5}>
        <StatCard
          icon={Send}
          label="Requêtes"
          value={fmtInt(s?.requests ?? 0)}
          hint={`${fmtInt(s?.distinct_questions ?? 0)} questions distinctes`}
        />
        <StatCard
          icon={Repeat}
          label="Répétition"
          value={s ? fmtPct(s.repeat_rate) : '—'}
          hint="Questions déjà posées"
          highlight
        />
        <StatCard
          icon={Zap}
          label="Taux de cache"
          value={s ? fmtPct(s.cache_hit_rate) : '—'}
          hint="Servies depuis la mémoire"
        />
        <StatCard
          icon={Database}
          label="En mémoire"
          value={fmtInt(d?.answers ?? 0)}
          hint={`${fmtInt(d?.fresh_answers ?? 0)} fraîches`}
        />
        <StatCard
          icon={MessageSquareReply}
          label="Retours utiles"
          value={s?.feedback.count ? fmtPct(s.feedback.useful_rate) : '—'}
          hint={`${fmtInt(s?.feedback.count ?? 0)} retours`}
        />
      </StatGrid>

      {series.data && <VolumeChart buckets={series.data} days={days} />}

      <Tabs defaultValue="requetes">
        <TabsList variant="line">
          <TabsTrigger value="requetes">Questions ({fmtInt(requests.data?.length ?? 0)})</TabsTrigger>
          <TabsTrigger value="reponses">Réponses en mémoire ({fmtInt(answers.data?.length ?? 0)})</TabsTrigger>
          <TabsTrigger value="retours">Retours ({fmtInt(feedback.data?.length ?? 0)})</TabsTrigger>
        </TabsList>
        <TabsContent value="requetes" className="pt-5">
          <RequestsTable
            rows={requests.data ?? []}
            isLoading={requests.isLoading}
            showDomain={false}
            title="Questions posées dans ce domaine"
            emptyMessage="Aucune question dans ce domaine pour le moment."
          />
        </TabsContent>
        <TabsContent value="reponses" className="pt-5">
          <AnswersTable rows={answers.data ?? []} isLoading={answers.isLoading} showDomain={false} />
        </TabsContent>
        <TabsContent value="retours" className="pt-5">
          <FeedbackTable rows={feedback.data ?? []} isLoading={feedback.isLoading} />
        </TabsContent>
      </Tabs>
    </Page>
  );
}
