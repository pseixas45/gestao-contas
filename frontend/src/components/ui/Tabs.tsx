'use client';

import { cn } from '@/lib/utils';

interface Tab {
  id: string;
  label: string;
  count?: number;
}

interface TabsProps {
  tabs: Tab[];
  activeTab: string;
  onChange: (id: string) => void;
  className?: string;
}

export default function Tabs({ tabs, activeTab, onChange, className }: TabsProps) {
  return (
    <div className={cn('flex gap-1 p-1 bg-slate-100 rounded-xl', className)}>
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          className={cn(
            'flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-default',
            activeTab === tab.id
              ? 'bg-white text-slate-900 shadow-soft'
              : 'text-slate-500 hover:text-slate-700'
          )}
        >
          {tab.label}
          {tab.count !== undefined && (
            <span className={cn(
              'px-1.5 py-0.5 text-xs rounded-md font-medium',
              activeTab === tab.id
                ? 'bg-primary-100 text-primary-700'
                : 'bg-slate-200 text-slate-500'
            )}>
              {tab.count}
            </span>
          )}
        </button>
      ))}
    </div>
  );
}
