import { type LucideIcon } from 'lucide-react';

export interface NavItem {
  id: string;
  title: string;
  icon?: LucideIcon;
  path: string;
  badge?: string;
  // Raccourci « + » affiché au survol de l'entrée
  new?: {
    tooltip: string;
    path: string;
  };
}

// Section de la sidebar. Sans titre : entrées affichées à plat en tête de menu.
// Avec titre : groupe repliable (même rendu que la section Favoris du CRM Metronic).
export interface NavSection {
  id: string;
  title?: string;
  icon?: LucideIcon;
  items: NavItem[];
}

export type NavConfig = NavSection[];
