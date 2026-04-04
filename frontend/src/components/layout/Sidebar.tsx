'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  Wallet,
  ArrowLeftRight,
  Upload,
  Tag,
  TrendingUp,
  LogOut,
  AlertCircle,
  BarChart3,
  PiggyBank,
  Settings,
  BookOpen,
} from 'lucide-react';
import { cn } from '@/lib/utils';

interface NavItem {
  href: string;
  label: string;
  icon: React.ReactNode;
  badge?: number;
}

interface NavSection {
  title?: string;
  items: NavItem[];
}

interface SidebarProps {
  pendingCount?: number;
  onLogout: () => void;
}

export default function Sidebar({ pendingCount = 0, onLogout }: SidebarProps) {
  const pathname = usePathname();

  const sections: NavSection[] = [
    {
      items: [
        { href: '/', label: 'Dashboard', icon: <LayoutDashboard size={18} /> },
      ],
    },
    {
      title: 'Operações',
      items: [
        { href: '/importar', label: 'Importar', icon: <Upload size={18} /> },
        { href: '/transacoes', label: 'Transações', icon: <ArrowLeftRight size={18} /> },
        { href: '/transacoes/pendentes', label: 'Pendentes', icon: <AlertCircle size={18} />, badge: pendingCount },
      ],
    },
    {
      title: 'Análise',
      items: [
        { href: '/relatorios', label: 'Relatórios', icon: <BarChart3 size={18} /> },
        { href: '/orcamento', label: 'Orçamento', icon: <PiggyBank size={18} /> },
        { href: '/projecao', label: 'Projeção', icon: <TrendingUp size={18} /> },
      ],
    },
    {
      title: 'Configuração',
      items: [
        { href: '/contas', label: 'Contas', icon: <Wallet size={18} /> },
        { href: '/categorias', label: 'Categorias', icon: <Tag size={18} /> },
        { href: '/categorias/regras', label: 'Regras', icon: <BookOpen size={18} /> },
      ],
    },
  ];

  return (
    <aside className="w-[220px] bg-white border-r border-slate-200/80 min-h-screen flex flex-col">
      {/* Logo */}
      <div className="px-5 py-5 border-b border-slate-100">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 bg-gradient-to-br from-primary-500 to-primary-700 rounded-xl flex items-center justify-center">
            <Wallet className="h-4 w-4 text-white" />
          </div>
          <div>
            <h1 className="text-sm font-bold text-slate-800 leading-tight">Gestão</h1>
            <p className="text-[10px] font-medium text-slate-400 uppercase tracking-wider">de Contas</p>
          </div>
        </div>
      </div>

      {/* Navegação */}
      <nav className="flex-1 px-3 py-3 overflow-y-auto">
        {sections.map((section, sIdx) => (
          <div key={sIdx} className={sIdx > 0 ? 'mt-5' : ''}>
            {section.title && (
              <p className="px-3 mb-1.5 text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
                {section.title}
              </p>
            )}
            <ul className="space-y-0.5">
              {section.items.map((item) => {
                const isActive = pathname === item.href ||
                  (item.href !== '/' && pathname.startsWith(item.href));

                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      className={cn(
                        'flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm transition-default',
                        isActive
                          ? 'bg-primary-50 text-primary-700 font-medium'
                          : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                      )}
                    >
                      <span className={cn(
                        'flex-shrink-0',
                        isActive ? 'text-primary-600' : 'text-slate-400'
                      )}>
                        {item.icon}
                      </span>
                      <span className="flex-1 truncate">{item.label}</span>
                      {item.badge !== undefined && item.badge > 0 && (
                        <span className="flex-shrink-0 min-w-[20px] h-5 flex items-center justify-center bg-rose-500 text-white text-[10px] font-bold px-1.5 rounded-md">
                          {item.badge > 99 ? '99+' : item.badge}
                        </span>
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-3 py-3 border-t border-slate-100">
        <button
          onClick={onLogout}
          className="flex items-center gap-2.5 px-3 py-2 w-full text-sm text-slate-500 hover:text-slate-700 hover:bg-slate-50 rounded-xl transition-default"
        >
          <LogOut size={18} />
          <span>Sair</span>
        </button>
      </div>
    </aside>
  );
}
