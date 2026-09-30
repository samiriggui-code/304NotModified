import { ReactNode, Suspense } from 'react';
import { Metadata } from 'next';
import { Inter } from 'next/font/google';
import { ThemeProvider } from 'next-themes';
import { cn } from '@/lib/utils';
import { QueryProvider } from '@/components/query-provider';
import { Toaster } from '@/components/ui/sonner';
import { TooltipProvider } from '@/components/ui/tooltip';

import '@/styles/globals.css';
import '@/styles/nm304.css';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: {
    template: '%s | 304NotModified',
    default: '304NotModified',
  },
  robots: { index: false, follow: false },
};

export default async function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="fr" className="h-full" data-scroll-behavior="smooth" suppressHydrationWarning>
      <body className={cn('antialiased flex h-full text-base text-foreground bg-background', inter.className)}>
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          storageKey="nm304-theme"
          enableSystem
          disableTransitionOnChange
          enableColorScheme
        >
          <TooltipProvider delayDuration={0}>
            <QueryProvider>
              <Suspense>{children}</Suspense>
            </QueryProvider>
            <Toaster />
          </TooltipProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
