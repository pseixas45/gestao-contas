'use client';

import { cn } from '@/lib/utils';
import { LucideIcon } from 'lucide-react';

interface StatCardProps {
  title: string;
  value: string;
  subtitle?: string;
  icon?: LucideIcon;
  trend?: { value: number; label: string };
  color?: 'primary' | 'emerald' | 'rose' | 'amber' | 'sky' | 'violet';
  className?: string;
}

const colorMap = {
  primary: {
    bg: 'bg-primary-50',
    icon: 'text-primary-600',
    trend: 'text-primary-600',
  },
  emerald: {
    bg: 'bg-emerald-50',
    icon: 'text-emerald-600',
    trend: 'text-emerald-600',
  },
  rose: {
    bg: 'bg-rose-50',
    icon: 'text-rose-600',
    trend: 'text-rose-600',
  },
  amber: {
    bg: 'bg-amber-50',
    icon: 'text-amber-600',
    trend: 'text-amber-600',
  },
  sky: {
    bg: 'bg-sky-50',
    icon: 'text-sky-600',
    trend: 'text-sky-600',
  },
  violet: {
    bg: 'bg-violet-50',
    icon: 'text-violet-600',
    trend: 'text-violet-600',
  },
};

export default function StatCard({ title, value, subtitle, icon: Icon, trend, color = 'primary', className }: StatCardProps) {
  const colors = colorMap[color];

  return (
    <div className={cn(
      'bg-white rounded-2xl shadow-card border border-slate-100/80 p-5 animate-fade-in',
      className
    )}>
      <div className="flex items-start justify-between mb-3">
        <p className="text-sm font-medium text-slate-500">{title}</p>
        {Icon && (
          <div className={cn('p-2 rounded-xl', colors.bg)}>
            <Icon className={cn('h-4 w-4', colors.icon)} />
          </div>
        )}
      </div>
      <p className="text-2xl font-bold text-slate-900 tracking-tight">{value}</p>
      {(subtitle || trend) && (
        <div className="mt-1.5 flex items-center gap-2">
          {trend && (
            <span className={cn(
              'inline-flex items-center text-xs font-medium',
              trend.value >= 0 ? 'text-emerald-600' : 'text-rose-600'
            )}>
              {trend.value >= 0 ? '+' : ''}{trend.value.toFixed(1)}%
            </span>
          )}
          {subtitle && (
            <span className="text-xs text-slate-400">{subtitle}</span>
          )}
        </div>
      )}
    </div>
  );
}
