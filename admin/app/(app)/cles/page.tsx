'use client';

import { FormEvent, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { type ColumnDef } from '@tanstack/react-table';
import { Copy, KeyRound, Plus, UserPlus, Users } from 'lucide-react';
import { toast } from 'sonner';
import { api } from '@/lib/api';
import { fmtAgo, fmtDate, fmtInt, KEY_ORIGINS, useKeys, useSettings, type KeyRow } from '@/lib/nm304';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Progress } from '@/components/ui/progress';
import { ColumnHeader, DataTable } from '@/components/nm304/data-table';
import { Page } from '@/components/nm304/page';
import { StatCard, StatGrid } from '@/components/nm304/stat-card';

const ORIGIN_VARIANT = {
  admin: 'primary',
  self: 'success',
  anonymous: 'secondary',
} as const;

export default function KeysPage() {
  const keys = useKeys();
  const settings = useSettings();
  const openOnLoad = useSearchParams().get('nouvelle') === '1';
  const [open, setOpen] = useState(false);
  useEffect(() => setOpen(openOnLoad), [openOnLoad]);
  const rows = keys.data ?? [];

  const columns = useMemo<ColumnDef<KeyRow>[]>(
    () => [
      {
        id: 'label',
        accessorFn: (r) => r.label,
        header: ({ column }) => <ColumnHeader title="Nom" column={column} />,
        cell: ({ row }) => (
          <div>
            <div className="font-medium text-mono">{row.original.label}</div>
            <div className="font-mono text-xs text-muted-foreground">
              {row.original.origin === 'anonymous' ? 'sans clé' : row.original.key}
            </div>
          </div>
        ),
        size: 240,
      },
      {
        id: 'origin',
        accessorFn: (r) => r.origin,
        header: ({ column }) => <ColumnHeader title="Origine" column={column} />,
        cell: ({ row }) => (
          <Badge variant={ORIGIN_VARIANT[row.original.origin]} appearance="light" size="sm">
            {KEY_ORIGINS[row.original.origin]}
          </Badge>
        ),
        size: 160,
      },
      {
        id: 'use_case',
        accessorFn: (r) => r.use_case ?? '',
        header: ({ column }) => <ColumnHeader title="Usage déclaré" column={column} />,
        cell: ({ row }) => <span className="line-clamp-2 max-w-sm">{row.original.use_case ?? '—'}</span>,
        size: 260,
      },
      {
        id: 'used',
        accessorFn: (r) => r.used,
        header: ({ column }) => <ColumnHeader title="Utilisation" column={column} />,
        cell: ({ row }) =>
          row.original.origin === 'anonymous' ? (
            <span className="tabular-nums">{fmtInt(row.original.used)} réponses</span>
          ) : (
            <div className="min-w-32 space-y-1">
              <Progress value={(row.original.used / row.original.quota) * 100} className="h-1.5" />
              <div className="text-xs text-muted-foreground tabular-nums">
                {fmtInt(row.original.used)} / {fmtInt(row.original.quota)}
              </div>
            </div>
          ),
        size: 160,
      },
      {
        id: 'last_used',
        accessorFn: (r) => r.last_used ?? 0,
        header: ({ column }) => <ColumnHeader title="Dernière activité" column={column} />,
        cell: ({ row }) => <span className="whitespace-nowrap">{fmtAgo(row.original.last_used)}</span>,
        size: 130,
      },
      {
        id: 'created_at',
        accessorFn: (r) => r.created_at,
        header: ({ column }) => <ColumnHeader title="Créée le" column={column} />,
        cell: ({ row }) => (
          <span className="whitespace-nowrap text-secondary-foreground">{fmtDate(row.original.created_at)}</span>
        ),
        size: 130,
      },
    ],
    [],
  );

  return (
    <Page
      title="Clés d'API"
      icon={KeyRound}
      actions={
        <Button onClick={() => setOpen(true)}>
          <Plus /> Nouvelle clé
        </Button>
      }
    >
      <StatGrid cols={3}>
        <StatCard
          icon={Users}
          label="Clés créées par vous"
          value={fmtInt(rows.filter((k) => k.origin === 'admin').length)}
          hint={`Quota par défaut : ${fmtInt(settings.data?.free_quota ?? 0)} réponses`}
        />
        <StatCard
          icon={UserPlus}
          label="Clés demandées par des agents"
          value={fmtInt(rows.filter((k) => k.origin === 'self').length)}
          hint={`Libre-service : ${fmtInt(settings.data?.self_service_quota ?? 0)} réponses par clé`}
          href="/agents"
        />
        <StatCard
          icon={KeyRound}
          label="Accès sans clé"
          value={`${fmtInt(settings.data?.anon_daily_limit ?? 0)} / jour`}
          hint="Questions par adresse IP, sans démarche"
        />
      </StatGrid>

      <DataTable
        title="Toutes les clés"
        description="Seul le début de chaque clé est affiché : la clé complète n'est montrée qu'à sa création."
        data={rows}
        columns={columns}
        isLoading={keys.isLoading}
        getRowId={(r) => r.key + r.created_at}
        searchText={(r) => [r.label, r.use_case, r.contact, KEY_ORIGINS[r.origin]]}
        emptyMessage="Aucune clé."
      />

      <NewKeyDialog open={open} onOpenChange={setOpen} defaultQuota={settings.data?.free_quota ?? 1000} />
    </Page>
  );
}

function NewKeyDialog({
  open,
  onOpenChange,
  defaultQuota,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  defaultQuota: number;
}) {
  const queryClient = useQueryClient();
  const [label, setLabel] = useState('');
  const [quota, setQuota] = useState(defaultQuota);
  const [created, setCreated] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function close(next: boolean) {
    if (!next) {
      setCreated(null);
      setLabel('');
    }
    onOpenChange(next);
  }

  async function create(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const res = await api.post<{ api_key: string }>('keys', {
        label: label.trim(),
        quota,
      });
      setCreated(res.api_key);
      await queryClient.invalidateQueries({ queryKey: ['keys'] });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Création impossible.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{created ? 'Clé créée' : 'Nouvelle clé'}</DialogTitle>
          <DialogDescription>
            {created
              ? 'Copiez cette clé maintenant : elle ne sera plus jamais affichée en entier.'
              : 'Pour un testeur, un partenaire ou un agent précis. Les questions sans réponse ne sont pas décomptées.'}
          </DialogDescription>
        </DialogHeader>
        {created ? (
          <>
            <DialogBody>
              <div className="flex items-center gap-2 rounded-md border border-dashed border-primary p-3">
                <code className="font-mono text-sm break-all grow">{created}</code>
                <Button
                  variant="outline"
                  size="sm"
                  mode="icon"
                  aria-label="Copier la clé"
                  onClick={() => navigator.clipboard?.writeText(created).then(() => toast.success('Clé copiée.'))}
                >
                  <Copy />
                </Button>
              </div>
            </DialogBody>
            <DialogFooter>
              <Button onClick={() => close(false)}>Terminé</Button>
            </DialogFooter>
          </>
        ) : (
          <form onSubmit={create}>
            <DialogBody className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="label">Nom (agent ou testeur)</Label>
                <Input
                  id="label"
                  required
                  maxLength={100}
                  autoFocus
                  value={label}
                  onChange={(e) => setLabel(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="quota">Quota de réponses</Label>
                <Input
                  id="quota"
                  type="number"
                  min={1}
                  value={quota}
                  onChange={(e) => setQuota(Number(e.target.value) || 1)}
                />
              </div>
            </DialogBody>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => close(false)}>
                Annuler
              </Button>
              <Button type="submit" disabled={busy || !label.trim()}>
                Créer la clé
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
