'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Sidebar from './Sidebar';
import { ToastProvider } from '@/components/ui/Toast';
import { transactionsApi } from '@/lib/api';

interface MainLayoutProps {
  children: React.ReactNode;
}

export default function MainLayout({ children }: MainLayoutProps) {
  const router = useRouter();
  const [pendingCount, setPendingCount] = useState(0);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

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
        <Sidebar pendingCount={pendingCount} onLogout={handleLogout} />
        <main className="flex-1 p-6 lg:p-8 overflow-x-hidden">
          <div className="max-w-7xl mx-auto animate-fade-in">
            {children}
          </div>
        </main>
      </div>
    </ToastProvider>
  );
}
