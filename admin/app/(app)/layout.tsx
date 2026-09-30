'use client';

import { ReactNode } from 'react';
import { AppLayout } from '@/components/layout';

export default function Layout({ children }: { children: ReactNode }) {
  return <AppLayout>{children}</AppLayout>;
}
