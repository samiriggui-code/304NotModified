// Logo texte de 304NotModified : « 304 » en pastille + nom. Pas d'image à maintenir.
export function BrandMark({ className }: { className?: string }) {
  return (
    <span
      className={`inline-flex items-center justify-center rounded-md bg-primary text-primary-foreground text-[11px] font-bold tracking-tight px-1.5 h-5 ${className ?? ''}`}
      aria-hidden
    >
      304
    </span>
  );
}

export function BrandName({ className }: { className?: string }) {
  return <span className={`font-semibold ${className ?? ''}`}>NotModified</span>;
}
