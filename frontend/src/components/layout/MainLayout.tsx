'use client';

import { useEffect, useState } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { Menu, Wallet } from 'lucide-react';
import Sidebar from './Sidebar';
import { ToastProvider } from '@/components/ui/Toast';
import { transactionsApi } from '@/lib/api';

interface MainLayoutProps {
  children: React.ReactNode;
}

export default function MainLayout({ children }: MainLayoutProps) {
  const router = useRouter();
  const pathname = usePathname();
  const [pendingCount, setPendingCount] = useState(0);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Fechar sidebar mobile ao mudar de rota
  useEffect(() => {
    setSidebarOpen(false);
  }, [pathname]);

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) {
      router.push('/login');
      return;
    }

    setIsAuthenticated(true);
    setIsLoading(false);

    const fetchPendingCount = async () => {
      try {
        const count = await transactionsApi.getPendingCount();
        setPendingCount(count);
      } catch (error) {
        if ((error as any)?.response?.status === 401) {
          localStorage.removeItem('token');
          router.push('/login');
        }
      }
    };

    fetchPendingCount();
    const interval = setInterval(fetchPendingCount, 30000);
    return () => clearInterval(interval);
  }, [router]);

  const handleLogout = () => {
    localStorage.removeItem('token');
    router.push('/login');
  };

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <div className="text-center">
          <div className="w-10 h-10 border-3 border-primary-200 border-t-primary-600 rounded-full animate-spin mx-auto" />
          <p className="mt-3 text-sm text-slate-500">Carregando...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  return (
    <ToastProvider>
      <div className="flex min-h-screen bg-slate-50">
        <Sidebar
          pendingCount={pendingCount}
          onLogout={handleLogout}
          isOpen={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
        />
        <div className="flex-1 flex flex-col min-w-0">
          {/* Header mobile com botão hamburger (escondido em md+) */}
          <header className="md:hidden sticky top-0 z-20 bg-white border-b border-slate-200 px-4 py-3 flex items-center gap-3">
            <button
              onClick={() => setSidebarOpen(true)}
              className="p-1.5 -ml-1 hover:bg-slate-100 rounded-lg transition-colors"
              aria-label="Abrir menu"
            >
              <Menu className="h-5 w-5 text-slate-700" />
            </button>
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 bg-gradient-to-br from-primary-500 to-primary-700 rounded-lg flex items-center justify-center">
                <Wallet className="h-3.5 w-3.5 text-white" />
              </div>
              <span className="text-sm font-bold text-slate-800">Gestão de Contas</span>
            </div>
            {pendingCount > 0 && (
              <span className="ml-auto min-w-[20px] h-5 flex items-center justify-center bg-rose-500 text-white text-[10px] font-bold px-1.5 rounded-md">
                {pendingCount > 99 ? '99+' : pendingCount}
              </span>
            )}
          </header>

          <main className="flex-1 p-4 sm:p-6 lg:p-8 overflow-x-hidden">
            <div className="max-w-7xl mx-auto animate-fade-in">
              {children}
            </div>
          </main>
        </div>
      </div>
    </ToastProvider>
  );
}
