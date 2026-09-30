import { Moon, Sun } from 'lucide-react';
import { useTheme } from 'next-themes';
import { useMounted } from '@/hooks/use-mounted';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';

export function HeaderTheme() {
  const { resolvedTheme, setTheme } = useTheme();
  // Le thème n'est connu que dans le navigateur : avant, on rend l'état « clair » comme le serveur,
  // sinon React signale un écart d'hydratation en mode sombre.
  const mounted = useMounted();
  const dark = mounted && resolvedTheme === 'dark';

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          mode="icon"
          className="text-white hover:text-white hover:bg-zinc-800"
          onClick={() => setTheme(dark ? 'light' : 'dark')}
          aria-label={dark ? 'Passer en mode clair' : 'Passer en mode sombre'}
        >
          {dark ? <Sun className="size-4 text-white" /> : <Moon className="size-4 text-white" />}
        </Button>
      </TooltipTrigger>
      <TooltipContent side="bottom">{dark ? 'Mode clair' : 'Mode sombre'}</TooltipContent>
    </Tooltip>
  );
}
