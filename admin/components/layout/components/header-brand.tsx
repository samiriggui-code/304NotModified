'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Menu } from 'lucide-react';
import { useIsMobile } from '@/hooks/use-mobile';
import { Button } from '@/components/ui/button';
import { Sheet, SheetBody, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet';
import { BrandMark, BrandName } from './brand';
import { SidebarContent } from './sidebar-content';

export function HeaderBrand() {
  const pathname = usePathname();
  const isMobile = useIsMobile();
  const [isSheetOpen, setIsSheetOpen] = useState(false);

  // Ferme le menu mobile à chaque changement de page.
  useEffect(() => {
    setIsSheetOpen(false);
  }, [pathname]);

  return (
    <div className="flex items-center -ms-1 gap-1">
      <Link href="/" className="flex items-center gap-1.5 text-white text-sm">
        <BrandMark />
        <BrandName />
      </Link>
      {isMobile && (
        <Sheet open={isSheetOpen} onOpenChange={setIsSheetOpen}>
          <SheetTrigger asChild>
            <Button variant="dim" mode="icon" className="hover:text-white" aria-label="Ouvrir le menu">
              <Menu />
            </Button>
          </SheetTrigger>
          <SheetContent className="p-0 gap-0 w-(--sidebar-width)" side="left" close={false}>
            <SheetHeader className="p-0 space-y-0">
              <SheetTitle className="sr-only">Navigation</SheetTitle>
            </SheetHeader>
            <SheetBody className="flex flex-col grow p-0 [--sidebar-space-x:calc(var(--spacing)*2.5)]">
              <SidebarContent />
            </SheetBody>
          </SheetContent>
        </Sheet>
      )}
    </div>
  );
}
