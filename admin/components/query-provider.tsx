'use client';

import { ReactNode, useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiError } from '@/lib/api';

// Pas de relance sur un refus de session (401/403) : la relance échouerait pareil et multiplierait
// les appels ; l'utilisateur est renvoyé vers la connexion. Les autres erreurs sont relancées 2 fois.
export function QueryProvider({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: (failures, error) =>
              !(error instanceof ApiError && (error.status === 401 || error.status === 403)) && failures < 2,
          },
        },
      }),
  );
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
