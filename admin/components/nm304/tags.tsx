import { Check, X } from 'lucide-react';
import { ISSUES, OUTCOMES, type Outcome } from '@/lib/nm304';

// L'identité vient de la pastille de couleur ; le texte reste à l'encre normale (lisible partout).
export function Swatch({ color, className }: { color: string; className?: string }) {
  return <i className={`inline-block size-2.5 rounded-[3px] shrink-0 ${className ?? ''}`} style={{ background: color }} />;
}

export function OutcomeTag({ outcome }: { outcome: Outcome }) {
  const o = OUTCOMES[outcome] ?? { label: outcome, color: 'var(--muted-foreground)' };
  return (
    <span className="inline-flex items-center gap-1.5 text-sm whitespace-nowrap">
      <Swatch color={o.color} />
      {o.label}
    </span>
  );
}

// Statut : toujours icône + libellé, jamais la couleur seule.
export function FeedbackTag({ useful, issue }: { useful: boolean | null | undefined; issue?: string | null }) {
  if (useful === null || useful === undefined) return <span className="text-muted-foreground">—</span>;
  return (
    <span className="inline-flex items-center gap-1.5 text-sm whitespace-nowrap">
      {useful ? (
        <Check className="size-3.5" style={{ color: 'var(--nm-good)' }} />
      ) : (
        <X className="size-3.5" style={{ color: 'var(--nm-bad)' }} />
      )}
      {useful ? 'utile' : `pas utile${issue ? ` · ${ISSUES[issue] ?? issue}` : ''}`}
    </span>
  );
}
