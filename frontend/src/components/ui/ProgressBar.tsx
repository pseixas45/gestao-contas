'use client';

import { cn } from '@/lib/utils';

interface ProgressBarProps {
  value: number;
  max?: number;
  label?: string;
  showPercent?: boolean;
  color?: 'primary' | 'emerald' | 'rose' | 'amber';
  size?: 'sm' | 'md';
  className?: string;
}

const barColors = {
  primary: 'bg-primary-500',
  emerald: 'bg-emerald-500',
  rose: 'bg-rose-500',
  amber: 'bg-amber-500',
};

const trackColors = {
  primary: 'bg-primary-100',
  emerald: 'bg-emerald-100',
  rose: 'bg-rose-100',
  amber: 'bg-amber-100',
};

export default function ProgressBar({
  value,
  max = 100,
  label,
  showPercent = false,
  color = 'primary',
  size = 'md',
  className,
}: ProgressBarProps) {
  const percent = Math.min(100, Math.max(0, (value / max) * 100));

  return (
    <div className={cn('w-full', className)}>
      {(label || showPercent) && (
        <div className="flex items-center justify-between mb-1.5">
          {label && <span className="text-xs font-medium text-slate-600">{label}</span>}
          {showPercent && <span className="text-xs font-medium text-slate-500">{Math.round(percent)}%</span>}
        </div>
      )}
      <div className={cn(
        'w-full rounded-full overflow-hidden',
        trackColors[color],
        size === 'sm' ? 'h-1.5' : 'h-2.5'
      )}>
        <div
          className={cn(
            'h-full rounded-full transition-all duration-500 ease-out',
            barColors[color]
          )}
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}
