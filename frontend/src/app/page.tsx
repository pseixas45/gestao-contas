'use client';

import { useQuery } from '@tanstack/react-query';
import MainLayout from '@/components/layout/MainLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { accountsApi, transactionsApi, categoriesApi } from '@/lib/api';
import { formatCurrency, formatDate } from '@/lib/utils';
import { Wallet, TrendingUp, TrendingDown, AlertCircle } from 'lucide-react';
import Link from 'next/link';

export default function DashboardPage() {
  // Calcular datas do mês atual
  const now = new Date();
  const startOfMonth = new Date(now.getFullYear(), now.getMonth(), 1).toISOString().split('T')[0];
  const endOfMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).toISOString().split('T')[0];

  // Buscar contas
  const { data: accounts = [] } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
  });

  // Buscar transações do mês atual
  const { data: monthResponse } = useQuery({
    queryKey: ['transactions', 'month', startOfMonth, endOfMonth],
    queryFn: () => transactionsApi.list({ start_date: startOfMonth, end_date: endOfMonth, limit: 10000 }),
  });
  const monthTransactions = monthResponse?.items ?? [];

  // Buscar transações recentes (para a lista)
  const { data: recentResponse } = useQuery({
    queryKey: ['transactions', 'recent'],
    queryFn: () => transactionsApi.list({ limit: 10 }),
  });
  const recentTransactions = recentResponse?.items ?? [];

  // Buscar contagem de pendentes
  const { data: pendingCount = 0 } = useQuery({
    queryKey: ['transactions', 'pending', 'count'],
    queryFn: () => transactionsApi.getPendingCount(),
  });

  // Calcular totais do mês (usar amount_brl para garantir valor em reais)
  const totalBalance = accounts.reduce((sum, acc) => sum + Number(acc.current_balance), 0);
  const totalIncome = monthTransactions
    .filter((t) => parseFloat(String(t.amount_brl)) > 0)
    .reduce((sum, t) => sum + parseFloat(String(t.amount_brl)), 0);
  const totalExpense = monthTransactions
    .filter((t) => parseFloat(String(t.amount_brl)) < 0)
    .reduce((sum, t) => sum + Math.abs(parseFloat(String(t.amount_brl))), 0);

  return (
    <MainLayout>
      <div className="space-y-6">
        {/* Cabeçalho */}
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Dashboard</h1>
          <p className="text-gray-600">Visão geral das suas finanças</p>
        </div>

        {/* Cards de resumo */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Saldo Total */}
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-500">Saldo Total</p>
                  <p className="text-2xl font-bold text-gray-800">
                    {formatCurrency(totalBalance)}
                  </p>
                </div>
                <div className="p-3 bg-primary-100 rounded-full">
                  <Wallet className="text-primary-600" size={24} />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Entradas do mês */}
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-500">Entradas (mês atual)</p>
                  <p className="text-2xl font-bold text-green-600">
                    {formatCurrency(totalIncome)}
                  </p>
                </div>
                <div className="p-3 bg-green-100 rounded-full">
                  <TrendingUp className="text-green-600" size={24} />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Saídas do mês */}
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-500">Saídas (mês atual)</p>
                  <p className="text-2xl font-bold text-red-600">
                    {formatCurrency(totalExpense)}
                  </p>
                </div>
                <div className="p-3 bg-red-100 rounded-full">
                  <TrendingDown className="text-red-600" size={24} />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Pendentes */}
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-500">Pendentes</p>
                  <p className="text-2xl font-bold text-orange-600">{pendingCount}</p>
                </div>
                <div className="p-3 bg-orange-100 rounded-full">
                  <AlertCircle className="text-orange-600" size={24} />
                </div>
              </div>
              {pendingCount > 0 && (
                <Link
                  href="/transacoes/pendentes"
                  className="text-sm text-primary-600 hover:underline mt-2 block"
                >
                  Categorizar agora
                </Link>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Contas e Transações Recentes */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Contas */}
          <Card>
            <CardHeader>
              <CardTitle>Contas Bancárias</CardTitle>
            </CardHeader>
            <CardContent>
              {accounts.length === 0 ? (
                <p className="text-gray-500 text-center py-4">
                  Nenhuma conta cadastrada.{' '}
                  <Link href="/contas" className="text-primary-600 hover:underline">
                    Criar conta
                  </Link>
                </p>
              ) : (
                <div className="space-y-3">
                  {accounts.map((account) => (
                    <div
                      key={account.id}
                      className="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
                    >
                      <div>
                        <p className="font-medium text-gray-800">{account.name}</p>
                        <p className="text-sm text-gray-500">{account.bank_name}</p>
                      </div>
                      <p
                        className={`font-semibold ${
                          Number(account.current_balance) >= 0
                            ? 'text-green-600'
                            : 'text-red-600'
                        }`}
                      >
                        {formatCurrency(Number(account.current_balance), (account.currency || 'BRL') as 'BRL' | 'USD' | 'EUR')}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Transações Recentes */}
          <Card>
            <CardHeader>
              <CardTitle>Transações Recentes</CardTitle>
            </CardHeader>
            <CardContent>
              {recentTransactions.length === 0 ? (
                <p className="text-gray-500 text-center py-4">
                  Nenhuma transação encontrada.{' '}
                  <Link href="/importar" className="text-primary-600 hover:underline">
                    Importar extrato
                  </Link>
                </p>
              ) : (
                <div className="space-y-2">
                  {recentTransactions.slice(0, 5).map((transaction) => (
                    <div
                      key={transaction.id}
                      className="flex items-center justify-between py-2 border-b last:border-0"
                    >
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-800 truncate">
                          {transaction.description}
                        </p>
                        <p className="text-xs text-gray-500">
                          {formatDate(transaction.date)}
                          {transaction.category_name && (
                            <span
                              className="ml-2 px-1.5 py-0.5 rounded text-xs"
                              style={{
                                backgroundColor: transaction.category_color + '20',
                                color: transaction.category_color,
                              }}
                            >
                              {transaction.category_name}
                            </span>
                          )}
                        </p>
                      </div>
                      <p
                        className={`font-semibold ml-4 ${
                          Number(transaction.original_amount) >= 0
                            ? 'text-green-600'
                            : 'text-red-600'
                        }`}
                      >
                        {formatCurrency(Number(transaction.original_amount), transaction.original_currency as 'BRL' | 'USD' | 'EUR')}
                      </p>
                    </div>
                  ))}
                </div>
              )}
              <Link
                href="/transacoes"
                className="text-sm text-primary-600 hover:underline mt-4 block text-center"
              >
                Ver todas as transações
              </Link>
            </CardContent>
          </Card>
        </div>
      </div>
    </MainLayout>
  );
}
