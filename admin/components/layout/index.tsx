'use client';

import { ReactNode } from 'react';
import { Layout } from './components/layout';
import { LayoutProvider } from './components/layout-context';

// Layout applicatif, adapté du concept CRM de Metronic.
export function AppLayout({ children }: { children: ReactNode }) {
  return (
    <LayoutProvider>
      <Layout>{children}</Layout>
    </LayoutProvider>
  );
}
