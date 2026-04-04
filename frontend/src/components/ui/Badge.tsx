'use client';

import { cn } from '@/lib/utils';

interface BadgeProps {
  children: React.ReactNode;
  color?: string;
  variant?: 'solid' | 'outline' | 'soft';
  size?: 'sm' | 'md';
  className?: string;
  dot?: boolean;
}

export default function Badge({ children, color = '#6366f1', variant = 'solid', size = 'sm', className, dot = false }: BadgeProps) {
  const sizeClasses = {
    sm: 'px-2 py-0.5 text-xs',
    md: 'px-2.5 py-1 text-xs',
  };

  if (variant === 'outline') {
    return (
      <span
        className={cn(
          'inline-flex items-center gap-1.5 rounded-lg font-medium border',
          sizeClasses[size],
          className
        )}
        style={{ borderColor: color, color }}
      >
        {dot && <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: color }} />}
        {children}
      </span>
    );
  }

  if (variant === 'soft') {
    return (
      <span
        className={cn(
          'inline-flex items-center gap-1.5 rounded-lg font-medium',
          sizeClasses[size],
          className
        )}
        style={{ backgroundColor: `${color}18`, color }}
      >
        {dot && <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: color }} />}
        {children}
      </span>
    );
  }

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-lg font-medium text-white',
        sizeClasses[size],
        className
      )}
      style={{ backgroundColor: color }}
    >
      {dot && <span className="w-1.5 h-1.5 rounded-full bg-white/40" />}
      {children}
    </span>
  );
}
