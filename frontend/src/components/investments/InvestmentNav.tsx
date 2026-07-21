'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';

const TABS = [
  { href: '/investimentos', label: 'Visão Geral' },
  { href: '/investimentos/posicoes', label: 'Posições' },
  { href: '/investimentos/historico', label: 'Histórico' },
  { href: '/investimentos/evolucao', label: 'Evolução' },
  { href: '/investimentos/rentabilidade', label: 'Rentab. Ativo' },
  { href: '/investimentos/metas', label: 'Metas' },
  { href: '/investimentos/ativos', label: 'Ativos' },
  { href: '/investimentos/importar', label: 'Importar' },
];

/** Barra de navegação entre as telas de investimentos (destaca a ativa). */
export default function InvestmentNav({ className }: { className?: string }) {
  const pathname = usePathname();
  return (
    <nav className={cn('flex flex-wrap items-center gap-2', className)}>
      {TABS.map((t) => {
        const active = t.href === '/investimentos'
          ? pathname === '/investimentos'
          : pathname.startsWith(t.href);
        return (
          <Link
            key={t.href}
            href={t.href}
            className={cn(
              'text-xs px-3 py-2 rounded-lg font-medium border transition-colors',
              active
                ? 'bg-primary-600 text-white border-primary-600'
                : 'bg-white border-slate-200 text-slate-700 hover:bg-slate-50'
            )}
          >
            {t.label}
          </Link>
        );
      })}
    </nav>
  );
}
