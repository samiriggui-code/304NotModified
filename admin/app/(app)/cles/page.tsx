'use client';

import { FormEvent, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { Copy, KeyRound } from 'lucide-react';
import { toast } from 'sonner';
import { api } from '@/lib/api';
import { fmtDate, fmtInt, useKeys } from '@/lib/nm304';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { EmptyState, Page } from '@/components/nm304/page';

export default function KeysPage() {
  const keys = useKeys();
  const queryClient = useQueryClient();
  const autoFocus = useSearchParams().get('nouvelle') === '1';
  const [label, setLabel] = useState('');
  const [quota, setQuota] = useState(1000);
  const [created, setCreated] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function create(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const res = await api.post<{ api_key: string }>('keys', { label: label.trim(), quota });
      setCreated(res.api_key);
      setLabel('');
      await queryClient.invalidateQueries({ queryKey: ['keys'] });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Création impossible.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Page title="Clés d'API" icon={KeyRound}>
      <Card>
        <CardHeader>
          <CardTitle>Nouvelle clé</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <form onSubmit={create} className="flex flex-wrap items-end gap-3">
            <div className="space-y-1.5 grow min-w-48">
              <Label htmlFor="label">Nom (agent ou testeur)</Label>
              <Input
                id="label"
                required
                maxLength={100}
                autoFocus={autoFocus}
                value={label}
                onChange={(e) => setLabel(e.target.value)}
              />
            </div>
            <div className="space-y-1.5 w-36">
              <Label htmlFor="quota">Quota de requêtes</Label>
              <Input
                id="quota"
                type="number"
                min={1}
                value={quota}
                onChange={(e) => setQuota(Number(e.target.value) || 1)}
              />
            </div>
            <Button type="submit" disabled={busy || !label.trim()}>
              Créer la clé
            </Button>
          </form>
          {created && (
            <div className="rounded-md border border-dashed border-primary p-3 text-sm space-y-2">
              <p>Copiez cette clé maintenant : elle ne sera plus jamais affichée en entier.</p>
              <div className="flex items-center gap-2">
                <code className="font-mono break-all">{created}</code>
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
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0 overflow-x-auto">
          {keys.data?.length ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nom</TableHead>
                  <TableHead>Clé</TableHead>
                  <TableHead className="text-right">Utilisé</TableHead>
                  <TableHead className="text-right">Quota</TableHead>
                  <TableHead>Créée le</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {keys.data.map((k) => (
                  <TableRow key={k.key + k.created_at}>
                    <TableCell>{k.label}</TableCell>
                    <TableCell className="font-mono text-xs">{k.key}</TableCell>
                    <TableCell className="text-right tabular-nums">{fmtInt(k.used)}</TableCell>
                    <TableCell className="text-right tabular-nums">{fmtInt(k.quota)}</TableCell>
                    <TableCell className="whitespace-nowrap">{fmtDate(k.created_at)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <EmptyState>{keys.isLoading ? 'Chargement…' : 'Aucune clé.'}</EmptyState>
          )}
        </CardContent>
      </Card>
    </Page>
  );
}
