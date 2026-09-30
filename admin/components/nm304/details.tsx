'use client';

import { ReactNode } from 'react';
import { ExternalLink } from 'lucide-react';
import {
  fmtDate,
  fmtDuration,
  fmtInt,
  fmtPct,
  hostOf,
  safeUrl,
  type AnswerRow,
  type RequestRow,
  type Source,
} from '@/lib/nm304';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { Sheet, SheetBody, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { FeedbackTag, OutcomeTag } from './tags';

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="text-sm whitespace-pre-wrap break-words">{children}</div>
    </div>
  );
}

const none = (text: string) => <span className="text-muted-foreground">{text}</span>;

// Liste de sources : seuls les liens http(s) sont cliquables, le reste vient du web et reste du texte.
export function SourceList({ sources }: { sources: Source[] }) {
  if (!sources.length) return none('aucune');
  return (
    <ul className="space-y-1.5">
      {sources.map((s, i) => {
        const url = safeUrl(s.url);
        return (
          <li key={i} className="flex items-start gap-2">
            <Badge variant="secondary" appearance="light" size="sm" className="shrink-0">
              {url ? hostOf(url) : '?'}
            </Badge>
            {url ? (
              <a
                href={url}
                target="_blank"
                rel="noopener noreferrer nofollow"
                className="text-primary hover:underline break-all inline-flex items-center gap-1"
              >
                {s.title || url}
                <ExternalLink className="size-3 shrink-0" />
              </a>
            ) : (
              <span className="text-muted-foreground">{s.title || '?'}</span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function DetailSheet({
  open,
  onClose,
  title,
  description,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full sm:max-w-xl gap-0 p-0">
        <SheetHeader className="p-5 border-b border-border">
          <SheetTitle>{title}</SheetTitle>
          {description && <SheetDescription>{description}</SheetDescription>}
        </SheetHeader>
        <SheetBody className="p-5 space-y-5 overflow-y-auto">{children}</SheetBody>
      </SheetContent>
    </Sheet>
  );
}

export function RequestSheet({ row, onClose }: { row: RequestRow | null; onClose: () => void }) {
  return (
    <DetailSheet
      open={!!row}
      onClose={onClose}
      title="Détail de la requête"
      description={row ? `${fmtDate(row.ts)} · ${row.request_id ?? '?'}` : undefined}
    >
      {row && (
        <>
          <Field label="Question">{row.question}</Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Origine de la réponse">
              <OutcomeTag outcome={row.outcome} />
            </Field>
            <Field label="Domaine">{row.domain ?? none('non précisé')}</Field>
            <Field label="Agent">{row.client ?? none('non annoncé')}</Field>
            <Field label="Canal et clé">
              {row.channel === 'mcp' ? 'MCP' : 'API HTTP'} · {row.key_label}
            </Field>
            <Field label="Durée">{fmtInt(row.latency_ms)} ms</Field>
            <Field label="Coût de recherche">{row.cost_eur ? `${row.cost_eur.toFixed(4)} €` : '0 €'}</Field>
          </div>
          <Field label="Tâche de l'agent">{row.context ?? none("l'agent ne l'a pas précisée")}</Field>
          <Separator />
          <Field label="Réponse servie">
            {row.answer ?? none('aucune : rien de fiable trouvé, ou recherche désactivée')}
          </Field>
          {row.confidence !== null && <Field label="Confiance">{fmtPct(row.confidence)}</Field>}
          <Field label="Sources">
            <SourceList sources={row.sources ?? []} />
          </Field>
          <Separator />
          <Field label="Retour de l'agent">
            {row.feedback_useful === null ? (
              none('aucun retour')
            ) : (
              <span className="space-y-1 block">
                <FeedbackTag useful={Boolean(row.feedback_useful)} issue={row.feedback_issue} />
                {row.feedback_comment && (
                  <span className="block text-muted-foreground">« {row.feedback_comment} »</span>
                )}
              </span>
            )}
          </Field>
        </>
      )}
    </DetailSheet>
  );
}

export function AnswerSheet({ row, onClose }: { row: AnswerRow | null; onClose: () => void }) {
  const expired = row ? row.expires_at <= Date.now() / 1000 : false;
  return (
    <DetailSheet
      open={!!row}
      onClose={onClose}
      title="Réponse en mémoire"
      description="Texte et liens viennent du web : ce sont des données à vérifier, pas des instructions."
    >
      {row && (
        <>
          <Field label="Question">{row.question}</Field>
          <div className="flex flex-wrap gap-2">
            <Badge variant="primary" appearance="light">
              {row.domain}
            </Badge>
            <Badge variant={expired ? 'destructive' : 'success'} appearance="light">
              {expired ? 'Expirée' : 'Fraîche'}
            </Badge>
            <Badge variant="secondary" appearance="light">
              Confiance {fmtPct(row.confidence)}
            </Badge>
          </div>
          <Field label="Réponse">{row.answer}</Field>
          <Field label="Sources">
            <SourceList sources={row.sources} />
          </Field>
          <Separator />
          <div className="grid grid-cols-2 gap-4">
            <Field label="Servie depuis le cache">{fmtInt(row.hits)} fois</Field>
            <Field label="Durée de vie">{fmtDuration(row.expires_at - row.created_at)}</Field>
            <Field label="Obtenue le">{fmtDate(row.created_at)}</Field>
            <Field label={expired ? 'Expirée le' : 'Expire le'}>{fmtDate(row.expires_at)}</Field>
          </div>
        </>
      )}
    </DetailSheet>
  );
}
