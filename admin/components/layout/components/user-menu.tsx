import { ReactNode } from 'react';
import { toAbsoluteUrl } from '@/lib/helpers';
import { useCurrentUser } from '@/hooks/use-current-user';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DropdownMenu, DropdownMenuContent, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';

export function UserAvatar({ className }: { className?: string }) {
  const { data: user } = useCurrentUser();
  const initial = (user?.email ?? '?').charAt(0).toUpperCase();
  return (
    <span
      className={`inline-flex items-center justify-center rounded-full bg-primary text-primary-foreground font-semibold ${className ?? ''}`}
      aria-hidden
    >
      {initial}
    </span>
  );
}

export function UserDropdownMenu({ trigger }: { trigger: ReactNode }) {
  const { data: user } = useCurrentUser();

  async function logout() {
    await fetch(toAbsoluteUrl('/api/auth/logout'), { method: 'POST' });
    window.location.href = toAbsoluteUrl('/signin');
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>{trigger}</DropdownMenuTrigger>
      <DropdownMenuContent className="w-72" side="bottom" align="end">
        <div className="flex items-center justify-between gap-2 p-3">
          <div className="flex items-center gap-2 min-w-0">
            <UserAvatar className="size-9 shrink-0 text-sm" />
            <div className="flex flex-col min-w-0">
              <span className="text-sm text-mono font-semibold truncate">Propriétaire</span>
              <span className="text-xs text-muted-foreground truncate">{user?.email}</span>
            </div>
          </div>
          <Badge variant="primary" appearance="light" size="sm">
            Admin
          </Badge>
        </div>

        <DropdownMenuSeparator />

        <div className="p-2 mt-1">
          <Button variant="outline" size="sm" className="w-full" onClick={logout}>
            Déconnexion
          </Button>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
