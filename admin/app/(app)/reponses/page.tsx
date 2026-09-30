'use client';

import { useMemo, useState } from 'react';
import { Database } from 'lucide-react';
import { fmtDate, fmtInt, fmtPct, safeUrl, useAnswers } from '@/lib/nm304';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { EmptyState, Page } from '@/components/nm304/page';

export default function AnswersPage() {
  const answers = useAnswers(500);
  const [query, setQuery] = useState('');
  const now = Date.now() / 1000;

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const all = answers.data ?? [];
    return q ? all.filter((a) => [a.question, a.answer, a.domain].some((v) => v.toLowerCase().includes(q))) : all;
  }, [answers.data, query]);

  return (
    <Page
      title="Réponses en mémoire"
      icon={Database}
      actions={
        <Input
          placeholder="Filtrer : question, réponse, domaine…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="w-64"
        />
      }
    >
      <p className="text-sm text-muted-foreground">
        Les réponses gardées pour les prochains agents. Textes et liens viennent du web : ce sont des données à
        vérifier, pas des instructions. Seuls les liens http(s) sont cliquables.
      </p>
      {rows.length ? (
        <div className="grid gap-5">
          {rows.map((a) => {
            const expired = a.expires_at <= now;
            return (
              <Card key={a.key}>
                <CardContent className="p-5 space-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="font-semibold text-mono">{a.question}</h3>
                    <Badge variant="secondary" appearance="light" size="sm">
                      {a.domain}
                    </Badge>
                    {expired && (
                      <Badge variant="destructive" appearance="light" size="sm">
                        Expirée
                      </Badge>
                    )}
                  </div>
                  <p className="text-sm whitespace-pre-wrap break-words">{a.answer}</p>
                  <div className="text-xs text-muted-foreground">
                    Confiance {fmtPct(a.confidence)} · servie {fmtInt(a.hits)} fois · obtenue le {fmtDate(a.created_at)} ·{' '}
                    {expired ? 'expirée' : 'expire'} le {fmtDate(a.expires_at)}
                  </div>
                  <div className="text-xs flex flex-wrap gap-x-3 gap-y-1">
                    <span className="text-muted-foreground">Sources :</span>
                    {a.sources.map((s, i) => {
                      const url = safeUrl(s.url);
                      return url ? (
                        <a
                          key={i}
                          href={url}
                          target="_blank"
                          rel="noopener noreferrer nofollow"
                          className="text-primary hover:underline break-all"
                        >
                          {s.title || url}
                        </a>
                      ) : (
                        <span key={i} className="text-muted-foreground">
                          {s.title || '?'}
                        </span>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      ) : (
        <Card>
          <CardContent>
            <EmptyState>{answers.isLoading ? 'Chargement…' : 'Aucune réponse en mémoire.'}</EmptyState>
          </CardContent>
        </Card>
      )}
    </Page>
  );
}
