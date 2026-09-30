import { fmtEur, fmtInt, fmtPct, type Stats } from '@/lib/nm304';
import { Card, CardContent } from '@/components/ui/card';

interface Tile {
  label: string;
  value: string;
  hint: string;
  key?: boolean;
}

export function KpiTiles({ stats }: { stats: Stats }) {
  const tiles: Tile[] = [
    { label: 'Requêtes', value: fmtInt(stats.requests), hint: `${fmtInt(stats.distinct_questions)} questions distinctes` },
    {
      label: 'Taux de répétition',
      value: fmtPct(stats.repeat_rate),
      hint: 'Questions déjà posées : le chiffre clé du modèle',
      key: true,
    },
    { label: 'Taux de cache', value: fmtPct(stats.cache_hit_rate), hint: 'Réponses servies depuis la mémoire', key: true },
    {
      label: 'Marge estimée',
      value: fmtEur(stats.estimated_margin_eur),
      hint: `Revenu ${fmtEur(stats.estimated_revenue_eur)} · coût ${fmtEur(stats.estimated_cost_eur)}`,
    },
    {
      label: 'Retours utiles',
      value: stats.feedback.count ? fmtPct(stats.feedback.useful_rate) : '—',
      hint: stats.feedback.count ? `sur ${fmtInt(stats.feedback.count)} retours d'agents` : 'Aucun retour sur la période',
    },
  ];
  return (
    <div className="grid gap-5 grid-cols-2 lg:grid-cols-5">
      {tiles.map((t) => (
        <Card key={t.label} className={t.key ? 'border-primary/60' : undefined}>
          <CardContent className="p-4 space-y-1">
            <div className="text-sm text-muted-foreground">{t.label}</div>
            <div className="text-2xl font-semibold text-mono">{t.value}</div>
            <div className="text-xs text-muted-foreground">{t.hint}</div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
