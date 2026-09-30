import { ReactNode } from 'react';
import { type LucideIcon } from 'lucide-react';
import { Content } from '@/components/layout/components/content';
import { ContentHeader } from '@/components/layout/components/content-header';

// Gabarit d'une page : en-tête de contenu CRM (titre + actions) puis le contenu.
export function Page({
  title,
  icon: Icon,
  actions,
  children,
}: {
  title: string;
  icon?: LucideIcon;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <>
      <ContentHeader>
        <h1 className="inline-flex items-center gap-2.5 text-sm font-semibold">
          {Icon && <Icon className="size-4 text-primary" />}
          {title}
        </h1>
        {actions && <div className="hidden lg:flex items-center gap-2">{actions}</div>}
      </ContentHeader>
      <Content className="block">
        <div className="container-fluid space-y-5">
          {/* Sur petit écran, les actions passent sous le titre pour ne pas déborder. */}
          {actions && <div className="lg:hidden flex flex-wrap items-center gap-2 overflow-x-auto">{actions}</div>}
          {children}
        </div>
      </Content>
    </>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <p className="text-sm text-muted-foreground py-6 text-center">{children}</p>;
}
