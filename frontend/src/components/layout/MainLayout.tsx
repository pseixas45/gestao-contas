'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Sidebar from './Sidebar';
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
    // Verificar se está autenticado
    const token = localStorage.getItem('token');
    if (!token) {
      router.push('/login');
      return;
    }

    setIsAuthenticated(true);
    setIsLoading(false);

    // Buscar contagem de pendentes
    const fetchPendingCount = async () => {
      try {
        const count = await transactionsApi.getPendingCount();
        setPendingCount(count);
      } catch (error) {
        // Se erro 401, redirecionar para login
        if ((error as any)?.response?.status === 401) {
          localStorage.removeItem('token');
          router.push('/login');
        }
        console.error('Erro ao buscar pendentes:', error);
      }
    };

    fetchPendingCount();
    // Atualizar a cada 30 segundos
    const interval = setInterval(fetchPendingCount, 30000);
    return () => clearInterval(interval);
  }, [router]);

  const handleLogout = () => {
    localStorage.removeItem('token');
    router.push('/login');
  };

  // Mostrar loading enquanto verifica autenticação
  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Carregando...</p>
        </div>
      </div>
    );
  }

  // Não renderizar se não autenticado (vai redirecionar)
  if (!isAuthenticated) {
    return null;
  }

  return (
    <div className="flex min-h-screen bg-gray-50">
      <Sidebar pendingCount={pendingCount} onLogout={handleLogout} />
      <main className="flex-1 p-8">
        {children}
      </main>
    </div>
  );
}
