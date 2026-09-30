import { ReactNode } from 'react';
import Link from 'next/link';
import { type LucideIcon } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';

// Tuile de chiffre clé, façon Metronic : icône dans une pastille, valeur, libellé et précision.
export function StatCard({
  icon: Icon,
  label,
  value,
  hint,
  href,
  highlight,
}: {
  icon: LucideIcon;
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  href?: string;
  highlight?: boolean;
}) {
  const body = (
    <Card
      className={`h-full ${highlight ? 'border-primary/60' : ''} ${href ? 'hover:border-primary transition-colors' : ''}`}
    >
      <CardContent className="p-5 flex items-start gap-4">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Icon className="size-5" />
        </span>
        <div className="min-w-0 space-y-0.5">
          <div className="text-sm text-muted-foreground">{label}</div>
          <div className="text-2xl font-semibold text-mono leading-tight">{value}</div>
          {hint && <div className="text-xs text-muted-foreground">{hint}</div>}
        </div>
      </CardContent>
    </Card>
  );
  return href ? (
    <Link href={href} className="block h-full">
      {body}
    </Link>
  ) : (
    body
  );
}

export function StatGrid({ children, cols = 4 }: { children: ReactNode; cols?: 2 | 3 | 4 | 5 }) {
  const lg = {
    2: 'lg:grid-cols-2',
    3: 'lg:grid-cols-3',
    4: 'lg:grid-cols-4',
    5: 'lg:grid-cols-5',
  }[cols];
  return <div className={`grid gap-5 grid-cols-1 sm:grid-cols-2 ${lg}`}>{children}</div>;
}
