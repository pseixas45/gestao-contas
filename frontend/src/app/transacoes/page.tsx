'use client';

import { useState, useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import MainLayout from '@/components/layout/MainLayout';
import { Card, CardContent } from '@/components/ui/Card';
import Button from '@/components/ui/Button';
import Input from '@/components/ui/Input';
import Select from '@/components/ui/Select';
import { transactionsApi, accountsApi, categoriesApi } from '@/lib/api';
import { formatCurrency, formatDate } from '@/lib/utils';
import { Search, ChevronLeft, ChevronRight, Pencil, Trash2, X, Save, Plus } from 'lucide-react';
import type { Transaction } from '@/types';

interface EditModalProps {
  transaction: Transaction;
  accounts: Array<{ id: number; name: string; currency?: string }>;
  categories: Array<{ id: number; name: string }>;
  onSave: (data: Partial<Transaction>) => void;
  onDelete: () => void;
  onClose: () => void;
  isLoading: boolean;
}

function EditModal({ transaction, accounts, categories, onSave, onDelete, onClose, isLoading }: EditModalProps) {
  const [formData, setFormData] = useState({
    date: transaction.date,
    description: transaction.description,
    amount: transaction.original_amount.toString(),
    account_id: transaction.account_id.toString(),
    category_id: transaction.category_id?.toString() || '',
  });

  const currencyLabel = (transaction.original_currency || 'BRL') as string;
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSave({
      date: formData.date,
      description: formData.description,
      amount: parseFloat(formData.amount),
      account_id: parseInt(formData.account_id),
      category_id: formData.category_id ? parseInt(formData.category_id) : null,
    });
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-lg mx-4">
        <div className="flex items-center justify-between p-4 border-b">
          <h2 className="text-lg font-semibold">Editar Transação</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-700">
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Data</label>
            <Input
              type="date"
              value={formData.date}
              onChange={(e) => setFormData({ ...formData, date: e.target.value })}
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Descrição</label>
            <Input
              type="text"
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Valor ({currencyLabel})</label>
            <Input
              type="number"
              step="0.01"
              value={formData.amount}
              onChange={(e) => setFormData({ ...formData, amount: e.target.value })}
              required
            />
            <p className="text-xs text-gray-500 mt-1">Use valores negativos para despesas</p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Conta</label>
            <Select
              value={formData.account_id}
              onChange={(e) => setFormData({ ...formData, account_id: e.target.value })}
              options={accounts.map((a) => ({ value: a.id, label: a.name }))}
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Categoria</label>
            <Select
              value={formData.category_id}
              onChange={(e) => setFormData({ ...formData, category_id: e.target.value })}
              options={[
                { value: '', label: 'Sem categoria' },
                ...categories.map((c) => ({ value: c.id, label: c.name })),
              ]}
            />
          </div>

          <div className="flex items-center justify-between pt-4 border-t">
            {!showDeleteConfirm ? (
              <Button
                type="button"
                variant="danger"
                onClick={() => setShowDeleteConfirm(true)}
                disabled={isLoading}
              >
                <Trash2 size={16} className="mr-1" />
                Excluir
              </Button>
            ) : (
              <div className="flex items-center gap-2">
                <span className="text-sm text-red-600">Confirmar exclusão?</span>
                <Button
                  type="button"
                  variant="danger"
                  size="sm"
                  onClick={onDelete}
                  disabled={isLoading}
                >
                  Sim
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => setShowDeleteConfirm(false)}
                  disabled={isLoading}
                >
                  Não
                </Button>
              </div>
            )}

            <div className="flex gap-2">
              <Button type="button" variant="secondary" onClick={onClose} disabled={isLoading}>
                Cancelar
              </Button>
              <Button type="submit" disabled={isLoading}>
                <Save size={16} className="mr-1" />
                {isLoading ? 'Salvando...' : 'Salvar'}
              </Button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}

interface CreateModalProps {
  accounts: Array<{ id: number; name: string; currency?: string }>;
  categories: Array<{ id: number; name: string }>;
  onSave: (data: any) => void;
  onClose: () => void;
  isLoading: boolean;
  isError: boolean;
  defaultAccountId?: string;
}

function CreateModal({ accounts, categories, onSave, onClose, isLoading, isError, defaultAccountId }: CreateModalProps) {
  const [formData, setFormData] = useState({
    date: new Date().toISOString().split('T')[0],
    description: '',
    amount: '',
    account_id: defaultAccountId || '',
    category_id: '',
  });

  const selectedAccount = formData.account_id
    ? accounts.find((a) => a.id === parseInt(formData.account_id))
    : null;
  const currencyLabel = selectedAccount?.currency || 'BRL';

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSave({
      date: formData.date,
      description: formData.description,
      amount: parseFloat(formData.amount),
      account_id: parseInt(formData.account_id),
      category_id: formData.category_id ? parseInt(formData.category_id) : null,
    });
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-lg mx-4">
        <div className="flex items-center justify-between p-4 border-b">
          <h2 className="text-lg font-semibold">Nova Transação</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-700">
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Conta</label>
            <Select
              value={formData.account_id}
              onChange={(e) => setFormData({ ...formData, account_id: e.target.value })}
              options={accounts.map((a) => ({ value: a.id, label: `${a.name} (${a.currency || 'BRL'})` }))}
              placeholder="Selecione a conta"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Data</label>
            <Input
              type="date"
              value={formData.date}
              onChange={(e) => setFormData({ ...formData, date: e.target.value })}
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Descrição</label>
            <Input
              type="text"
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              placeholder="Ex: Pagamento de aluguel"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Valor ({currencyLabel})</label>
            <Input
              type="number"
              step="0.01"
              value={formData.amount}
              onChange={(e) => setFormData({ ...formData, amount: e.target.value })}
              placeholder="0.00"
              required
            />
            <p className="text-xs text-gray-500 mt-1">Use valores negativos para despesas</p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Categoria</label>
            <Select
              value={formData.category_id}
              onChange={(e) => setFormData({ ...formData, category_id: e.target.value })}
              options={[
                { value: '', label: 'Sem categoria' },
                ...categories.map((c) => ({ value: c.id, label: c.name })),
              ]}
            />
          </div>

          {isError && (
            <div className="p-3 bg-red-50 text-red-700 rounded text-sm">
              Erro ao criar transação. Verifique os dados e tente novamente.
            </div>
          )}

          <div className="flex justify-end gap-2 pt-4 border-t">
            <Button type="button" variant="secondary" onClick={onClose} disabled={isLoading}>
              Cancelar
            </Button>
            <Button type="submit" disabled={isLoading || !formData.account_id || !formData.amount}>
              <Plus size={16} className="mr-1" />
              {isLoading ? 'Salvando...' : 'Criar Transação'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function TransacoesPage() {
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState({
    account_id: '',
    category_id: '',
    start_date: '',
    end_date: '',
    card_payment_start: '',
    card_payment_end: '',
    search: '',
  });
  const [editingTransaction, setEditingTransaction] = useState<Transaction | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);

  // Inicializar filtro de conta a partir da URL
  useEffect(() => {
    const accountId = searchParams.get('account_id');
    if (accountId) {
      setFilters((prev) => ({ ...prev, account_id: accountId }));
    }
  }, [searchParams]);

  // Buscar contas
  const { data: accounts = [] } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
  });

  // Buscar categorias
  const { data: categories = [] } = useQuery({
    queryKey: ['categories', 'flat'],
    queryFn: () => categoriesApi.list(true, true),
  });

  // Buscar transações
  const { data: transactionsResponse, isLoading } = useQuery({
    queryKey: ['transactions', filters, page],
    queryFn: () =>
      transactionsApi.list({
        account_id: filters.account_id ? parseInt(filters.account_id) : undefined,
        category_id: filters.category_id ? parseInt(filters.category_id) : undefined,
        start_date: filters.start_date || undefined,
        end_date: filters.end_date || undefined,
        card_payment_start: filters.card_payment_start || undefined,
        card_payment_end: filters.card_payment_end || undefined,
        search: filters.search || undefined,
        page,
        limit: 50,
      }),
  });

  const transactions = transactionsResponse?.items ?? [];
  const balanceBefore = transactionsResponse?.balance_before ?? null;

  // Moeda da conta selecionada (para saldo e formatação)
  const selectedAccount = filters.account_id
    ? accounts.find((a) => a.id === parseInt(filters.account_id))
    : null;
  const accountCurrency = (selectedAccount?.currency || 'BRL') as 'BRL' | 'USD' | 'EUR';

  // Calcular saldo acumulado para cada transação (usa original_amount na moeda da conta)
  const runningBalances = (() => {
    if (balanceBefore === null || transactions.length === 0) return new Map<number, number>();

    // Ordenar por data ASC, id ASC para acumular cronologicamente
    const sorted = [...transactions].sort((a, b) => {
      if (a.date < b.date) return -1;
      if (a.date > b.date) return 1;
      return a.id - b.id;
    });

    const map = new Map<number, number>();
    let running = balanceBefore;
    for (const t of sorted) {
      running += Number(t.original_amount);
      map.set(t.id, running);
    }
    return map;
  })();

  // Atualizar categoria (inline)
  const updateCategoryMutation = useMutation({
    mutationFn: ({ id, categoryId }: { id: number; categoryId: number }) =>
      transactionsApi.updateCategory(id, categoryId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['transactions'] });
      queryClient.invalidateQueries({ queryKey: ['accounts'] });
    },
  });

  // Atualizar transação completa
  const updateTransactionMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<Transaction> }) =>
      transactionsApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['transactions'] });
      queryClient.invalidateQueries({ queryKey: ['accounts'] });
      setEditingTransaction(null);
    },
  });

  // Excluir transação
  const deleteTransactionMutation = useMutation({
    mutationFn: (id: number) => transactionsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['transactions'] });
      queryClient.invalidateQueries({ queryKey: ['accounts'] });
      setEditingTransaction(null);
    },
  });

  // Criar transação
  const createTransactionMutation = useMutation({
    mutationFn: (data: any) => transactionsApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['transactions'] });
      queryClient.invalidateQueries({ queryKey: ['accounts'] });
      setShowCreateModal(false);
    },
  });

  const handleCategoryChange = (transactionId: number, categoryId: string) => {
    if (categoryId) {
      updateCategoryMutation.mutate({
        id: transactionId,
        categoryId: parseInt(categoryId),
      });
    }
  };

  const handleSaveTransaction = (data: Partial<Transaction>) => {
    if (editingTransaction) {
      updateTransactionMutation.mutate({ id: editingTransaction.id, data });
    }
  };

  const handleDeleteTransaction = () => {
    if (editingTransaction) {
      deleteTransactionMutation.mutate(editingTransaction.id);
    }
  };

  return (
    <MainLayout>
      <div className="space-y-6">
        {/* Cabeçalho */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-800">Transações</h1>
            <p className="text-gray-600">Visualize e gerencie seus lançamentos</p>
          </div>
          <Button onClick={() => setShowCreateModal(true)}>
            <Plus size={20} className="mr-2" />
            Nova Transação
          </Button>
        </div>

        {/* Filtros */}
        <Card>
          <CardContent className="py-4">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
              <Select
                placeholder="Todas as contas"
                value={filters.account_id}
                onChange={(e) => setFilters({ ...filters, account_id: e.target.value })}
                options={accounts.map((a) => ({ value: a.id, label: a.name }))}
              />

              <Select
                placeholder="Todas as categorias"
                value={filters.category_id}
                onChange={(e) => setFilters({ ...filters, category_id: e.target.value })}
                options={[
                  { value: 0, label: '⏳ Pendente (sem categoria)' },
                  ...categories.map((c) => ({ value: c.id, label: c.name })),
                ]}
              />

              <Input
                type="date"
                placeholder="Data inicial"
                value={filters.start_date}
                onChange={(e) => setFilters({ ...filters, start_date: e.target.value })}
              />

              <Input
                type="date"
                placeholder="Data final"
                value={filters.end_date}
                onChange={(e) => setFilters({ ...filters, end_date: e.target.value })}
              />

              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={18} />
                <Input
                  className="pl-10"
                  placeholder="Buscar..."
                  value={filters.search}
                  onChange={(e) => setFilters({ ...filters, search: e.target.value })}
                />
              </div>
            </div>

            {/* Filtros de data de pagamento */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 mt-3">
              <div className="lg:col-span-2" />
              <div>
                <label className="block text-xs text-gray-500 mb-1">Dt. Pagamento de</label>
                <Input
                  type="date"
                  value={filters.card_payment_start}
                  onChange={(e) => setFilters({ ...filters, card_payment_start: e.target.value })}
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Dt. Pagamento até</label>
                <Input
                  type="date"
                  value={filters.card_payment_end}
                  onChange={(e) => setFilters({ ...filters, card_payment_end: e.target.value })}
                />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Tabela de Transações */}
        <Card>
          <CardContent className="p-0">
            {isLoading ? (
              <div className="text-center py-8 text-gray-500">Carregando...</div>
            ) : transactions.length === 0 ? (
              <div className="text-center py-8 text-gray-500">
                Nenhuma transação encontrada
              </div>
            ) : (
              <>
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                          Data
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                          Descrição
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                          Dt. Pagto
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                          Conta
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                          Categoria
                        </th>
                        <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                          Valor
                        </th>
                        {balanceBefore !== null && (
                          <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                            Saldo
                          </th>
                        )}
                        <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">
                          Ações
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200">
                      {transactions.map((transaction) => (
                        <tr key={transaction.id} className="hover:bg-gray-50">
                          <td className="px-4 py-3 text-sm text-gray-600">
                            {formatDate(transaction.date)}
                          </td>
                          <td className="px-4 py-3">
                            <div className="text-sm font-medium text-gray-800">
                              {transaction.description}
                            </div>
                            {!transaction.is_validated && (
                              <span className="text-xs text-orange-500">Pendente</span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-sm text-gray-500">
                            {transaction.card_payment_date
                              ? formatDate(transaction.card_payment_date)
                              : ''}
                          </td>
                          <td className="px-4 py-3 text-sm text-gray-600">
                            {transaction.account_name}
                          </td>
                          <td className="px-4 py-3">
                            <select
                              value={transaction.category_id || ''}
                              onChange={(e) =>
                                handleCategoryChange(transaction.id, e.target.value)
                              }
                              className="text-sm border border-gray-300 rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-primary-500"
                            >
                              <option value="">Sem categoria</option>
                              {categories.map((cat) => (
                                <option key={cat.id} value={cat.id}>
                                  {cat.name}
                                </option>
                              ))}
                            </select>
                          </td>
                          <td className="px-4 py-3 text-right">
                            <span
                              className={`font-semibold ${
                                Number(transaction.original_amount) >= 0
                                  ? 'text-green-600'
                                  : 'text-red-600'
                              }`}
                            >
                              {formatCurrency(Number(transaction.original_amount), transaction.original_currency as 'BRL' | 'USD' | 'EUR')}
                            </span>
                          </td>
                          {balanceBefore !== null && (
                            <td className="px-4 py-3 text-right">
                              <span
                                className={`font-semibold ${
                                  (runningBalances.get(transaction.id) ?? 0) >= 0
                                    ? 'text-blue-600'
                                    : 'text-red-600'
                                }`}
                              >
                                {formatCurrency(runningBalances.get(transaction.id) ?? 0, accountCurrency)}
                              </span>
                            </td>
                          )}
                          <td className="px-4 py-3 text-center">
                            <button
                              onClick={() => setEditingTransaction(transaction)}
                              className="text-gray-500 hover:text-primary-600 p-1 rounded hover:bg-gray-100"
                              title="Editar transação"
                            >
                              <Pencil size={16} />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Paginação */}
                <div className="flex items-center justify-between px-6 py-4 border-t">
                  <p className="text-sm text-gray-500">
                    Página {page}
                  </p>
                  <div className="flex gap-2">
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                      disabled={page === 1}
                    >
                      <ChevronLeft size={16} />
                      Anterior
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => setPage((p) => p + 1)}
                      disabled={transactions.length < 50}
                    >
                      Próxima
                      <ChevronRight size={16} />
                    </Button>
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Modal de Edição */}
      {editingTransaction && (
        <EditModal
          transaction={editingTransaction}
          accounts={accounts}
          categories={categories}
          onSave={handleSaveTransaction}
          onDelete={handleDeleteTransaction}
          onClose={() => setEditingTransaction(null)}
          isLoading={updateTransactionMutation.isPending || deleteTransactionMutation.isPending}
        />
      )}

      {/* Modal de Criação */}
      {showCreateModal && (
        <CreateModal
          accounts={accounts}
          categories={categories}
          onSave={(data) => createTransactionMutation.mutate(data)}
          onClose={() => { setShowCreateModal(false); createTransactionMutation.reset(); }}
          isLoading={createTransactionMutation.isPending}
          isError={createTransactionMutation.isError}
          defaultAccountId={filters.account_id}
        />
      )}
    </MainLayout>
  );
}
