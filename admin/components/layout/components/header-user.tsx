import { UserAvatar, UserDropdownMenu } from './user-menu';

export function HeaderUser() {
  return (
    <UserDropdownMenu
      trigger={
        <button type="button" className="cursor-pointer" aria-label="Menu utilisateur">
          <UserAvatar className="size-7 text-xs border-2 border-zinc-950" />
        </button>
      }
    />
  );
}
