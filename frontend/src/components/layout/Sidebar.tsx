'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  Wallet,
  ArrowLeftRight,
  Upload,
  History,
  Tag,
  TrendingUp,
  LogOut,
  AlertCircle,
  BarChart3,
  PiggyBank,
} from 'lucide-react';
import { cn } from '@/lib/utils';

interface NavItem {
  href: string;
  label: string;
  icon: React.ReactNode;
  badge?: number;
}

interface SidebarProps {
  pendingCount?: number;
  onLogout: () => void;
}

export default function Sidebar({ pendingCount = 0, onLogout }: SidebarProps) {
  const pathname = usePathname();

  const navItems: NavItem[] = [
    {
      href: '/',
      label: 'Dashboard',
      icon: <LayoutDashboard size={20} />,
    },
    {
      href: '/contas',
      label: 'Contas',
      icon: <Wallet size={20} />,
    },
    {
      href: '/transacoes',
      label: 'Transações',
      icon: <ArrowLeftRight size={20} />,
    },
    {
      href: '/transacoes/pendentes',
      label: 'Pendentes',
      icon: <AlertCircle size={20} />,
      badge: pendingCount,
    },
    {
      href: '/importar',
      label: 'Importar',
      icon: <Upload size={20} />,
    },
    {
      href: '/importar/historico',
      label: 'Carga Histórico',
      icon: <History size={20} />,
    },
    {
      href: '/categorias',
      label: 'Categorias',
      icon: <Tag size={20} />,
    },
    {
      href: '/relatorios',
      label: 'Relatórios',
      icon: <BarChart3 size={20} />,
    },
    {
      href: '/orcamento',
      label: 'Orçamento',
      icon: <PiggyBank size={20} />,
    },
    {
      href: '/projecao',
      label: 'Projeção',
      icon: <TrendingUp size={20} />,
    },
  ];

  return (
    <aside className="w-64 bg-white border-r border-gray-200 min-h-screen flex flex-col">
      {/* Logo */}
      <div className="p-6 border-b border-gray-200">
        <h1 className="text-xl font-bold text-gray-800">
          Gestão de Contas
        </h1>
      </div>

      {/* Navegação */}
      <nav className="flex-1 p-4">
        <ul className="space-y-1">
          {navItems.map((item) => {
            const isActive = pathname === item.href ||
              (item.href !== '/' && pathname.startsWith(item.href));

            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className={cn(
                    'flex items-center gap-3 px-4 py-3 rounded-lg transition-colors',
                    isActive
                      ? 'bg-primary-50 text-primary-700 font-medium'
                      : 'text-gray-600 hover:bg-gray-100'
                  )}
                >
                  {item.icon}
                  <span>{item.label}</span>
                  {item.badge && item.badge > 0 && (
                    <span className="ml-auto bg-red-500 text-white text-xs px-2 py-0.5 rounded-full">
                      {item.badge}
                    </span>
                  )}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Logout */}
      <div className="p-4 border-t border-gray-200">
        <button
          onClick={onLogout}
          className="flex items-center gap-3 px-4 py-3 w-full text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
        >
          <LogOut size={20} />
          <span>Sair</span>
        </button>
      </div>
    </aside>
  );
}
