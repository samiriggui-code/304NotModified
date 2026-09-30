import { Bot, Database, History, KeyRound, LayoutDashboard, MessageSquareReply } from 'lucide-react';
import { type NavConfig } from './types';

export const MAIN_NAV: NavConfig = [
  {
    id: 'pilotage',
    title: 'Pilotage',
    items: [{ id: 'dashboard', title: 'Tableau de bord', icon: LayoutDashboard, path: '/' }],
  },
  {
    id: 'activite',
    title: 'Activité des agents',
    items: [
      { id: 'requetes', title: 'Requêtes', icon: History, path: '/requetes' },
      { id: 'retours', title: 'Retours des agents', icon: MessageSquareReply, path: '/retours' },
      { id: 'agents', title: 'Agents', icon: Bot, path: '/agents' },
    ],
  },
  {
    id: 'service',
    title: 'Service',
    items: [
      { id: 'reponses', title: 'Réponses en mémoire', icon: Database, path: '/reponses' },
      {
        id: 'cles',
        title: "Clés d'API",
        icon: KeyRound,
        path: '/cles',
        new: { tooltip: 'Nouvelle clé', path: '/cles?nouvelle=1' },
      },
    ],
  },
];

// Entrée de menu correspondant exactement à pathname.
export function findNavItem(pathname: string) {
  for (const section of MAIN_NAV) {
    const item = section.items.find((entry) => entry.path === pathname);
    if (item) return { section, item };
  }
  return undefined;
}
