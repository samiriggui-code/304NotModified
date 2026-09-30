import Link from 'next/link';
import { CirclePlus } from 'lucide-react';
import { MAIN_NAV } from '@/config/menu.config';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

// Raccourcis de création déclarés dans le menu (champ `new`)
const CREATE_ACTIONS = MAIN_NAV.flatMap((section) => section.items).filter(
  (item) => item.new,
);

export function HeaderNew() {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className="text-white hover:text-white hover:bg-zinc-800 hover:border-zinc-800 data-[state=open]:bg-zinc-800"
        >
          <CirclePlus className="size-4 text-white" />
          Nouveau
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-52">
        {CREATE_ACTIONS.map((item) => (
          <DropdownMenuItem key={item.id} asChild>
            <Link href={item.new!.path}>
              {item.icon && <item.icon />}
              {item.new!.tooltip}
            </Link>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
