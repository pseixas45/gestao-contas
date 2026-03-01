'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import MainLayout from '@/components/layout/MainLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import Button from '@/components/ui/Button';
import { transactionsApi, categoriesApi } from '@/lib/api';
import { formatCurrency, formatDate } from '@/lib/utils';
import { Check, ChevronRight } from 'lucide-react';

export default function PendentesPage() {
  const queryClient = useQueryClient();

  // Buscar transações pendentes
  const { data: transactions = [], isLoading } = useQuery({
    queryKey: ['transactions', 'pending'],
    queryFn: () => transactionsApi.getPending(),
  });

  // Buscar categorias
  const { data: categories = [] } = useQuery({
    queryKey: ['categories', 'flat'],
    queryFn: () => categoriesApi.list(true, true),
  });

  // Atualizar categoria
  const updateCategoryMutation = useMutation({
    mutationFn: ({ id, categoryId, createRule }: { id: number; categoryId: number; createRule: boolean }) =>
      transactionsApi.updateCategory(id, categoryId, createRule),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['transactions'] });
    },
  });

  const handleCategorize = (transactionId: number, categoryId: number, createRule = false) => {
    updateCategoryMutation.mutate({ id: transactionId, categoryId, createRule });
  };

  // Agrupar categorias por tipo
  const expenseCategories = categories.filter((c) => c.type === 'expense');
  const incomeCategories = categories.filter((c) => c.type === 'income');
  const transferCategories = categories.filter((c) => c.type === 'transfer');

  return (
    <MainLayout>
      <div className="space-y-6">
        {/* Cabeçalho */}
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Transações Pendentes</h1>
          <p className="text-gray-600">
            {transactions.length} transação(ões) aguardando categorização
          </p>
        </div>

        {/* Lista de Pendentes */}
        {isLoading ? (
          <div className="text-center py-8 text-gray-500">Carregando...</div>
        ) : transactions.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center">
              <div className="text-green-500 mb-4">
                <Check size={48} className="mx-auto" />
              </div>
              <h3 className="text-lg font-medium text-gray-800">Tudo categorizado!</h3>
              <p className="text-gray-500">Não há transações pendentes no momento.</p>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-4">
            {transactions.map((transaction) => (
              <Card key={transaction.id}>
                <CardContent className="py-4">
                  <div className="flex flex-col lg:flex-row lg:items-center gap-4">
                    {/* Info da transação */}
                    <div className="flex-1">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-sm text-gray-500">
                          {formatDate(transaction.date)} - {transaction.account_name}
                        </span>
                        <span
                          className={`text-lg font-bold ${
                            Number(transaction.original_amount) >= 0 ? 'text-green-600' : 'text-red-600'
                          }`}
                        >
                          {formatCurrency(Number(transaction.original_amount), transaction.original_currency as 'BRL' | 'USD' | 'EUR')}
                        </span>
                      </div>
                      <p className="font-medium text-gray-800">{transaction.description}</p>
                    </div>

                    {/* Seletor de categoria */}
                    <div className="flex flex-wrap gap-2">
                      {/* Mostrar categorias relevantes baseado no valor */}
                      {(Number(transaction.amount) < 0 ? expenseCategories : incomeCategories)
                        .slice(0, 6)
                        .map((cat) => (
                          <button
                            key={cat.id}
                            onClick={() => handleCategorize(transaction.id, cat.id)}
                            className="px-3 py-1.5 text-sm rounded-lg border border-gray-200 hover:border-primary-500 hover:bg-primary-50 transition-colors"
                            style={{ borderColor: cat.color + '40' }}
                          >
                            {cat.name}
                          </button>
                        ))}

                      {/* Dropdown para mais categorias */}
                      <select
                        onChange={(e) => {
                          if (e.target.value) {
                            handleCategorize(transaction.id, parseInt(e.target.value));
                            e.target.value = '';
                          }
                        }}
                        className="px-3 py-1.5 text-sm rounded-lg border border-gray-200 focus:outline-none focus:ring-1 focus:ring-primary-500"
                      >
                        <option value="">Mais...</option>
                        <optgroup label="Despesas">
                          {expenseCategories.map((cat) => (
                            <option key={cat.id} value={cat.id}>
                              {cat.name}
                            </option>
                          ))}
                        </optgroup>
                        <optgroup label="Receitas">
                          {incomeCategories.map((cat) => (
                            <option key={cat.id} value={cat.id}>
                              {cat.name}
                            </option>
                          ))}
                        </optgroup>
                        <optgroup label="Transferências">
                          {transferCategories.map((cat) => (
                            <option key={cat.id} value={cat.id}>
                              {cat.name}
                            </option>
                          ))}
                        </optgroup>
                      </select>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    </MainLayout>
  );
}
