import { PanelRightOpen } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { BrandMark } from './brand';
import { useLayout } from './layout-context';

export function SidebarDefaultHeader() {
  const { sidebarCollapse, setSidebarCollapse } = useLayout();

  return (
    <div className="group flex justify-between items-center gap-2.5 border-b border-border h-11 lg:h-(--sidebar-header-height) shrink-0 px-2.5">
      <div className="flex items-center gap-2.5 px-1.5">
        <BrandMark className="shrink-0" />
        <span className="text-foreground text-sm font-medium in-data-[sidebar-collapsed]:hidden">Administration</span>
      </div>

      <Button
        variant="ghost"
        mode="icon"
        className="hidden lg:group-hover:flex lg:in-data-[sidebar-collapsed]:hidden!"
        onClick={() => setSidebarCollapse(!sidebarCollapse)}
        aria-label="Réduire la sidebar"
      >
        <PanelRightOpen className="size-4" />
      </Button>
    </div>
  );
}
