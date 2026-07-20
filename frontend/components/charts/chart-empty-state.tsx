export function ChartEmptyState({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-md border border-dashed border-slate-300 p-6 text-center dark:border-slate-700">
      <p className="text-sm font-medium text-slate-800 dark:text-slate-100">{title}</p>
      <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">{children}</p>
    </div>
  );
}
