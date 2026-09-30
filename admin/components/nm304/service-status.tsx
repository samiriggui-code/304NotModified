'use client';

import { CircleAlert, CircleCheck, Plug } from 'lucide-react';
import { useSettings } from '@/lib/nm304';
import { Alert, AlertContent, AlertDescription, AlertIcon, AlertTitle } from '@/components/ui/alert';

// État du service tel que l'API le décrit : recherche active ou non, adresses pour les agents.
export function ServiceStatus() {
  const { data: s } = useSettings();
  if (!s) return null;
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Alert variant={s.search_enabled ? 'success' : 'warning'} appearance="light">
        <AlertIcon>{s.search_enabled ? <CircleCheck /> : <CircleAlert />}</AlertIcon>
        <AlertContent>
          <AlertTitle>{s.search_enabled ? 'Recherche web active' : 'Recherche web désactivée'}</AlertTitle>
          <AlertDescription>
            {s.search_enabled
              ? 'Une question nouvelle déclenche une recherche (payante), puis la réponse est gardée en mémoire.'
              : 'Aucune clé de fournisseur active : les questions sont enregistrées mais restent « sans réponse ». Ajoutez du crédit Anthropic puis réactivez la clé sur le serveur.'}
          </AlertDescription>
        </AlertContent>
      </Alert>
      <Alert variant="primary" appearance="light">
        <AlertIcon>
          <Plug />
        </AlertIcon>
        <AlertContent>
          <AlertTitle>
            Adresse des agents : <code className="font-mono">{s.mcp_url}</code>
          </AlertTitle>
          <AlertDescription>
            API : <code className="font-mono">POST {s.public_url}/v1/answer</code> · sans clé : {s.anon_daily_limit}{' '}
            questions par jour et par IP ·{' '}
            <a href={`${s.public_url}/llms.txt`} target="_blank" rel="noopener noreferrer" className="underline">
              guide pour les agents
            </a>
          </AlertDescription>
        </AlertContent>
      </Alert>
    </div>
  );
}
