'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ChevronRight, Plus } from 'lucide-react';
import { MAIN_NAV } from '@/config/menu.config';
import type { NavItem, NavSection } from '@/config/types';
import {
  AccordionMenu,
  AccordionMenuItem,
} from '@/components/ui/accordion-menu';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { useLayout } from './layout-context';

function NavEntry({ item }: { item: NavItem }) {
  return (
    <>
      <Link
        href={item.path}
        className="flex items-center grow gap-2.5 font-medium"
      >
        {item.icon && <item.icon />}
        <span>{item.title}</span>
      </Link>
      {item.new && (
        <div className="opacity-0 flex items-center gap-1 group-hover:opacity-100">
          <Tooltip delayDuration={500}>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                className="size-6 hover:bg-input"
                size="icon"
                asChild
              >
                <Link href={item.new.path}>
                  <Plus className="size-3.5 opacity-100" />
                </Link>
              </Button>
            </TooltipTrigger>
            <TooltipContent align="center" side="right" sideOffset={28}>
              {item.new.tooltip}
            </TooltipContent>
          </Tooltip>
        </div>
      )}
      {item.badge && (
        <Badge
          size="xs"
          variant="primary"
          className="text-[11px] group-hover:hidden me-1"
        >
          {item.badge}
        </Badge>
      )}
    </>
  );
}

function NavEntryCollapsed({ item }: { item: NavItem }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Link href={item.path}>{item.icon && <item.icon />}</Link>
      </TooltipTrigger>
      <TooltipContent align="center" side="right" sideOffset={28}>
        {item.title}
      </TooltipContent>
    </Tooltip>
  );
}

function NavItems({ items }: { items: NavItem[] }) {
  const pathname = usePathname();
  const { sidebarCollapse } = useLayout();

  const matchPath = (path: string) =>
    path === pathname || (path.length > 1 && pathname.startsWith(path));

  return (
    <AccordionMenu
      type="single"
      matchPath={matchPath}
      classNames={{
        root: 'grow space-y-0.5 shrink-0',
        item: 'group py-0 h-8 [&:has([data-state=open])]:bg-accent justify-between cursor-pointer',
      }}
      collapsible
    >
      {items.map((item) => (
        <AccordionMenuItem key={item.id} asChild value={item.path}>
          <div>
            {sidebarCollapse ? (
              <NavEntryCollapsed item={item} />
            ) : (
              <NavEntry item={item} />
            )}
          </div>
        </AccordionMenuItem>
      ))}
    </AccordionMenu>
  );
}

function NavGroup({ section }: { section: NavSection }) {
  const [isOpen, setIsOpen] = useState(true);
  const { sidebarCollapse } = useLayout();

  // Sidebar repliée : on garde uniquement les icônes des entrées
  if (sidebarCollapse) {
    return (
      <div className="px-(--sidebar-space-x) border-t border-border pt-3.5">
        <NavItems items={section.items} />
      </div>
    );
  }

  return (
    <Collapsible
      open={isOpen}
      onOpenChange={setIsOpen}
      className="px-(--sidebar-space-x)"
    >
      <CollapsibleTrigger className="flex w-full items-center justify-start h-8 px-2 gap-2.5 text-sm text-muted-foreground hover:text-foreground">
        <ChevronRight className="ms-0.25 size-3.5 in-data-[state=open]:rotate-90" />
        <span>{section.title}</span>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <NavItems items={section.items} />
      </CollapsibleContent>
    </Collapsible>
  );
}

export function SidebarDefaultNav() {
  return (
    <div className="space-y-3.5">
      {MAIN_NAV.map((section) =>
        section.title ? (
          <NavGroup key={section.id} section={section} />
        ) : (
          <div key={section.id} className="px-(--sidebar-space-x)">
            <NavItems items={section.items} />
          </div>
        ),
      )}
    </div>
  );
}
