import { Separator } from '@/components/ui/separator';
import { HeaderBrand } from './header-brand';
import { HeaderNew } from './header-new';
import { HeaderTheme } from './header-theme';
import { HeaderUser } from './header-user';

export function Header() {
  return (
    <header className="fixed top-0 start-0 end-0 z-[10] flex items-center justify-between h-[var(--header-height)] bg-zinc-950 border-b border-zinc-950 dark:border-border transition-[start] duration-200 ease-in-out pe-[var(--removed-body-scroll-bar-size,0px)]">
      <div className="container-fluid flex justify-between items-stretch lg:gap-4">
        <div className="flex items-center gap-4">
          <HeaderBrand />
        </div>
        <div className="flex items-center gap-2">
          <HeaderNew />
          <Separator orientation="vertical" className="bg-zinc-600 h-4 mx-1" />
          <HeaderTheme />
          <HeaderUser />
        </div>
      </div>
    </header>
  );
}
