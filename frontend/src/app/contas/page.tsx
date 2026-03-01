'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import MainLayout from '@/components/layout/MainLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import Button from '@/components/ui/Button';
import Input from '@/components/ui/Input';
import Select from '@/components/ui/Select';
import { accountsApi, banksApi } from '@/lib/api';
import { formatCurrency, getAccountTypeLabel } from '@/lib/utils';
import { Plus, Edit2, Trash2 } from 'lucide-react';

export default function ContasPage() {
  const queryClient = useQueryClient();
  const router = useRouter();
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [editingAccount, setEditingAccount] = useState<any>(null);

  const [formData, setFormData] = useState({
    bank_id: '',
    name: '',
    account_number: '',
    account_type: 'checking',
    currency: 'BRL',
    initial_balance: '0',
  });

  // Buscar contas
  const { data: accounts = [], isLoading } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(false),
  });

  // Buscar bancos
  const { data: banks = [] } = useQuery({
    queryKey: ['banks'],
    queryFn: () => banksApi.list(),
  });

  // Criar conta
  const createMutation = useMutation({
    mutationFn: (data: any) => accountsApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accounts'] });
      resetForm();
    },
  });

  // Atualizar conta
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) => accountsApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accounts'] });
      resetForm();
    },
  });

  // Excluir conta
  const deleteMutation = useMutation({
    mutationFn: (id: number) => accountsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accounts'] });
    },
  });

  const resetForm = () => {
    setFormData({
      bank_id: '',
      name: '',
      account_number: '',
      account_type: 'checking',
      currency: 'BRL',
      initial_balance: '0',
    });
    setEditingAccount(null);
    setIsFormOpen(false);
  };

  const handleEdit = (account: any) => {
    setFormData({
      bank_id: account.bank_id.toString(),
      name: account.name,
      account_number: account.account_number || '',
      account_type: account.account_type,
      currency: account.currency || 'BRL',
      initial_balance: account.initial_balance.toString(),
    });
    setEditingAccount(account);
    setIsFormOpen(true);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const data = {
      bank_id: parseInt(formData.bank_id),
      name: formData.name,
      account_number: formData.account_number || null,
      account_type: formData.account_type,
      currency: formData.currency,
      initial_balance: parseFloat(formData.initial_balance),
    };

    if (editingAccount) {
      updateMutation.mutate({ id: editingAccount.id, data });
    } else {
      createMutation.mutate(data);
    }
  };

  const handleDelete = (id: number) => {
    if (confirm('Tem certeza que deseja desativar esta conta?')) {
      deleteMutation.mutate(id);
    }
  };

  const accountTypeOptions = [
    { value: 'checking', label: 'Conta Corrente' },
    { value: 'savings', label: 'Poupança' },
    { value: 'credit_card', label: 'Cartão de Crédito' },
    { value: 'investment', label: 'Investimentos' },
  ];

  const currencyOptions = [
    { value: 'BRL', label: 'R$ - Real Brasileiro' },
    { value: 'USD', label: '$ - Dólar Americano' },
    { value: 'EUR', label: '€ - Euro' },
  ];

  const getCurrencySymbol = (currency: string) => {
    switch (currency) {
      case 'USD': return '$';
      case 'EUR': return '€';
      default: return 'R$';
    }
  };

  const formatAccountCurrency = (value: number, currency: string) => {
    const symbol = getCurrencySymbol(currency);
    const formatted = Math.abs(value).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    return value < 0 ? `-${symbol} ${formatted}` : `${symbol} ${formatted}`;
  };

  return (
    <MainLayout>
      <div className="space-y-6">
        {/* Cabeçalho */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-800">Contas Bancárias</h1>
            <p className="text-gray-600">Gerencie suas contas bancárias</p>
          </div>
          <Button onClick={() => setIsFormOpen(true)}>
            <Plus size={20} className="mr-2" />
            Nova Conta
          </Button>
        </div>

        {/* Formulário */}
        {isFormOpen && (
          <Card>
            <CardHeader>
              <CardTitle>{editingAccount ? 'Editar Conta' : 'Nova Conta'}</CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <Select
                    label="Banco"
                    id="bank_id"
                    value={formData.bank_id}
                    onChange={(e) => setFormData({ ...formData, bank_id: e.target.value })}
                    options={banks.map((b) => ({ value: b.id, label: b.name }))}
                    placeholder="Selecione o banco"
                    required
                  />

                  <Input
                    label="Nome da Conta"
                    id="name"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    placeholder="Ex: Itaú CC Principal"
                    required
                  />

                  <Input
                    label="Número da Conta"
                    id="account_number"
                    value={formData.account_number}
                    onChange={(e) => setFormData({ ...formData, account_number: e.target.value })}
                    placeholder="Opcional"
                  />

                  <Select
                    label="Tipo de Conta"
                    id="account_type"
                    value={formData.account_type}
                    onChange={(e) => setFormData({ ...formData, account_type: e.target.value })}
                    options={accountTypeOptions}
                  />

                  <Select
                    label="Moeda"
                    id="currency"
                    value={formData.currency}
                    onChange={(e) => setFormData({ ...formData, currency: e.target.value })}
                    options={currencyOptions}
                  />

                  <Input
                    label="Saldo Inicial"
                    id="initial_balance"
                    type="number"
                    step="0.01"
                    value={formData.initial_balance}
                    onChange={(e) => setFormData({ ...formData, initial_balance: e.target.value })}
                  />
                </div>

                <div className="flex gap-2 justify-end">
                  <Button type="button" variant="secondary" onClick={resetForm}>
                    Cancelar
                  </Button>
                  <Button
                    type="submit"
                    isLoading={createMutation.isPending || updateMutation.isPending}
                  >
                    {editingAccount ? 'Salvar' : 'Criar Conta'}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        )}

        {/* Lista de Contas */}
        <Card>
          <CardContent className="p-0">
            {isLoading ? (
              <div className="text-center py-8 text-gray-500">Carregando...</div>
            ) : accounts.length === 0 ? (
              <div className="text-center py-8 text-gray-500">
                Nenhuma conta cadastrada
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        Conta
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        Banco
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        Tipo
                      </th>
                      <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase">
                        Moeda
                      </th>
                      <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                        Saldo
                      </th>
                      <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                        Saldo BRL
                      </th>
                      <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase">
                        Status
                      </th>
                      <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                        Ações
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200">
                    {accounts.map((account) => (
                      <tr key={account.id} className="hover:bg-gray-50">
                        <td className="px-6 py-4">
                          <button
                            onClick={() => router.push(`/transacoes?account_id=${account.id}`)}
                            className="text-left hover:text-primary-600 transition-colors"
                          >
                            <div className="font-medium text-gray-800 hover:text-primary-600">{account.name}</div>
                            {account.account_number && (
                              <div className="text-sm text-gray-500">{account.account_number}</div>
                            )}
                          </button>
                        </td>
                        <td className="px-6 py-4 text-gray-600">{account.bank_name}</td>
                        <td className="px-6 py-4 text-gray-600">
                          {getAccountTypeLabel(account.account_type)}
                        </td>
                        <td className="px-6 py-4 text-center">
                          <span className="px-2 py-1 text-xs font-medium rounded bg-gray-100 text-gray-700">
                            {account.currency || 'BRL'}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-right">
                          <span
                            className={`font-semibold ${
                              Number(account.current_balance) >= 0
                                ? 'text-green-600'
                                : 'text-red-600'
                            }`}
                          >
                            {formatAccountCurrency(Number(account.current_balance), account.currency || 'BRL')}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-right">
                          <span className={`text-sm ${Number(account.balance_brl) >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                            {formatAccountCurrency(Number(account.balance_brl || 0), 'BRL')}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-center">
                          <span
                            className={`px-2 py-1 text-xs rounded-full ${
                              account.is_active
                                ? 'bg-green-100 text-green-800'
                                : 'bg-gray-100 text-gray-800'
                            }`}
                          >
                            {account.is_active ? 'Ativa' : 'Inativa'}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-right">
                          <div className="flex justify-end gap-2">
                            <button
                              onClick={() => handleEdit(account)}
                              className="p-1 text-gray-500 hover:text-primary-600"
                            >
                              <Edit2 size={18} />
                            </button>
                            <button
                              onClick={() => handleDelete(account.id)}
                              className="p-1 text-gray-500 hover:text-red-600"
                            >
                              <Trash2 size={18} />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot className="bg-gray-100 border-t-2 border-gray-300">
                    <tr>
                      <td colSpan={5} className="px-6 py-3 text-right font-bold text-gray-700">
                        Total
                      </td>
                      <td className="px-6 py-3 text-right">
                        <span className={`font-bold ${
                          accounts.reduce((sum, a) => sum + Number(a.balance_brl || 0), 0) >= 0
                            ? 'text-green-700'
                            : 'text-red-700'
                        }`}>
                          {formatAccountCurrency(
                            accounts.reduce((sum, a) => sum + Number(a.balance_brl || 0), 0),
                            'BRL'
                          )}
                        </span>
                      </td>
                      <td colSpan={2}></td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </MainLayout>
  );
}
