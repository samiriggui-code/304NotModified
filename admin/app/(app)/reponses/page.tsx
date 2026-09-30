'use client';

import { CheckCircle2, Database, Gauge, Repeat } from 'lucide-react';
import { fmtInt, fmtPct, useAnswers } from '@/lib/nm304';
import { Page } from '@/components/nm304/page';
import { StatCard, StatGrid } from '@/components/nm304/stat-card';
import { AnswersTable } from '@/components/nm304/tables';

export default function AnswersPage() {
  const answers = useAnswers(500);
  const rows = answers.data ?? [];
  const now = Date.now() / 1000;
  const fresh = rows.filter((a) => a.expires_at > now).length;
  const served = rows.reduce((n, a) => n + a.hits, 0);
  const confidence = rows.length ? rows.reduce((n, a) => n + a.confidence, 0) / rows.length : 0;

  return (
    <Page title="Réponses en mémoire" icon={Database}>
      <StatGrid cols={4}>
        <StatCard
          icon={Database}
          label="Réponses en mémoire"
          value={fmtInt(rows.length)}
          hint="Chacune avec ses sources"
        />
        <StatCard
          icon={CheckCircle2}
          label="Encore fraîches"
          value={fmtInt(fresh)}
          hint={`${fmtInt(rows.length - fresh)} expirées : la prochaine question relancera une recherche`}
        />
        <StatCard icon={Repeat} label="Servies depuis le cache" value={fmtInt(served)} hint="Recherches économisées" />
        <StatCard
          icon={Gauge}
          label="Confiance moyenne"
          value={rows.length ? fmtPct(confidence) : '—'}
          hint="Estimée par le chercheur"
        />
      </StatGrid>
      <AnswersTable rows={rows} isLoading={answers.isLoading} pageSize={25} />
    </Page>
  );
}
