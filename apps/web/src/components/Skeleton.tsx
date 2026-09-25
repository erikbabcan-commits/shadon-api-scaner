import React from "react";

export const Skeleton: React.FC<{ className?: string }> = ({ className = "h-4 w-full" }) => {
  return (
    <div
      className={`animate-pulse rounded bg-slate-800/80 ${className}`}
      aria-hidden="true"
    />
  );
};

export const SkeletonCard: React.FC = () => {
  return (
    <div className="rounded-xl border border-slate-800/70 bg-slate-900/40 p-4 shadow-sm">
      <div className="flex items-center justify-between mb-3">
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-4 w-12 rounded-full" />
      </div>
      <Skeleton className="h-4 w-48 mb-4" />
      <div className="flex items-center gap-4 pt-2 border-t border-slate-800/50">
        <Skeleton className="h-4 w-16" />
        <Skeleton className="h-4 w-20" />
        <Skeleton className="h-4 w-16" />
      </div>
    </div>
  );
};

export const SkeletonTable: React.FC<{ rows?: number }> = ({ rows = 5 }) => {
  return (
    <div className="rounded-xl border border-slate-800/70 bg-slate-900/40 overflow-hidden">
      <div className="p-4 border-b border-slate-800/70 flex gap-4">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-4 w-20" />
      </div>
      <div className="divide-y divide-slate-800/40">
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="p-4 flex items-center justify-between gap-4">
            <div className="flex items-center gap-3 flex-1">
              <Skeleton className="h-3 w-3 rounded-full" />
              <div className="flex-1 space-y-2">
                <Skeleton className="h-4 w-48" />
                <Skeleton className="h-3 w-32" />
              </div>
            </div>
            <Skeleton className="h-6 w-20 rounded-md" />
          </div>
        ))}
      </div>
    </div>
  );
};

export const SkeletonMetric: React.FC = () => {
  return (
    <div className="rounded-xl border border-slate-800/70 bg-slate-900/40 p-4 space-y-2">
      <Skeleton className="h-3 w-20" />
      <Skeleton className="h-8 w-16" />
      <Skeleton className="h-2.5 w-28" />
    </div>
  );
};
