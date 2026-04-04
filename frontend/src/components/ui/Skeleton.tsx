'use client';

import { cn } from '@/lib/utils';

interface SkeletonProps {
  className?: string;
  variant?: 'text' | 'circular' | 'rectangular';
  width?: string | number;
  height?: string | number;
}

export default function Skeleton({ className, variant = 'text', width, height }: SkeletonProps) {
  const variants = {
    text: 'rounded-lg h-4',
    circular: 'rounded-full',
    rectangular: 'rounded-xl',
  };

  return (
    <div
      className={cn(
        'animate-pulse bg-slate-200/70',
        variants[variant],
        className
      )}
      style={{ width, height }}
    />
  );
}

export function SkeletonCard() {
  return (
    <div className="bg-white rounded-2xl shadow-card border border-slate-100/80 p-5 space-y-3">
      <Skeleton width="40%" height={14} />
      <Skeleton width="60%" height={28} />
      <Skeleton width="30%" height={12} />
    </div>
  );
}

export function SkeletonRow() {
  return (
    <div className="flex items-center gap-4 py-3 px-4">
      <Skeleton variant="circular" width={36} height={36} />
      <div className="flex-1 space-y-2">
        <Skeleton width="50%" height={14} />
        <Skeleton width="30%" height={12} />
      </div>
      <Skeleton width={80} height={20} />
    </div>
  );
}
