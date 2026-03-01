'use client';

import { cn } from '@/lib/utils';

interface BadgeProps {
  children: React.ReactNode;
  color?: string;
  variant?: 'solid' | 'outline';
  className?: string;
}

export default function Badge({ children, color = '#6B7280', variant = 'solid', className }: BadgeProps) {
  if (variant === 'outline') {
    return (
      <span
        className={cn(
          'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border',
          className
        )}
        style={{ borderColor: color, color }}
      >
        {children}
      </span>
    );
  }

  return (
    <span
      className={cn(
        'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium text-white',
        className
      )}
      style={{ backgroundColor: color }}
    >
      {children}
    </span>
  );
}
