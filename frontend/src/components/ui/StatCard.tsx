'use client';

import { cn } from '@/lib/utils';
import { LucideIcon, Info } from 'lucide-react';

interface StatCardProps {
  title: string;
  value: string;
  subtitle?: string;
  icon?: LucideIcon;
  trend?: { value: number; label: string };
  color?: 'primary' | 'emerald' | 'rose' | 'amber' | 'sky' | 'violet';
  info?: string;   // fórmula/explicação exibida em tooltip ao passar o mouse no ícone
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

export default function StatCard({ title, value, subtitle, icon: Icon, trend, color = 'primary', info, className }: StatCardProps) {
  const colors = colorMap[color];

  return (
    <div className={cn(
      'relative bg-white rounded-2xl shadow-card border border-slate-100/80 p-5 animate-fade-in hover:z-30',
      className
    )}>
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-1.5">
          <p className="text-sm font-medium text-slate-500">{title}</p>
          {info && (
            <span className="relative group/info inline-flex">
              <Info className="h-3.5 w-3.5 text-slate-300 hover:text-slate-500 cursor-help" aria-label="Fórmula" />
              <span
                role="tooltip"
                className="pointer-events-none absolute left-1/2 top-6 z-40 hidden w-60 -translate-x-1/2 rounded-lg bg-slate-800 px-3 py-2 text-xs font-normal leading-snug text-white shadow-lg group-hover/info:block"
              >
                {info}
                <span className="absolute -top-1 left-1/2 h-2 w-2 -translate-x-1/2 rotate-45 bg-slate-800" />
              </span>
            </span>
          )}
        </div>
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
