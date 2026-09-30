'use client';

import { useEffect, useState } from 'react';
import { PERIODS } from '@/lib/nm304';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';

const STORAGE_KEY = 'nm304_period';

// Période choisie, retenue dans ce navigateur (confort seulement).
export function usePeriod(): [number, (days: number) => void] {
  const [days, setDays] = useState(7);
  useEffect(() => {
    try {
      const saved = Number(localStorage.getItem(STORAGE_KEY));
      if (PERIODS.some((p) => p.days === saved)) setDays(saved);
    } catch {
      /* stockage indisponible : on garde 7 jours */
    }
  }, []);
  const update = (value: number) => {
    setDays(value);
    try {
      localStorage.setItem(STORAGE_KEY, String(value));
    } catch {
      /* rien à faire */
    }
  };
  return [days, update];
}

export function PeriodFilter({ days, onChange }: { days: number; onChange: (days: number) => void }) {
  return (
    <ToggleGroup
      type="single"
      variant="outline"
      size="sm"
      value={String(days)}
      onValueChange={(value) => value && onChange(Number(value))}
      aria-label="Période"
    >
      {PERIODS.map((p) => (
        <ToggleGroupItem key={p.days} value={String(p.days)} className="px-3">
          {p.label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}
