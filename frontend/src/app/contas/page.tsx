'use client';

import { useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import MainLayout from '@/components/layout/MainLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import Button from '@/components/ui/Button';
import Input from '@/components/ui/Input';
import Select from '@/components/ui/Select';
import { accountsApi, banksApi } from '@/lib/api';
import { formatCurrency, getAccountTypeLabel } from '@/lib/utils';
import { BankAccount } from '@/types';
import {
  Plus,
  Edit2,
  Trash2,
  CreditCard,
  Building2,
  TrendingUp,
  Wallet,
  ArrowRight,
  X,
} from 'lucide-react';

const ACCOUNT_TYPE_ICON: Record<string, React.ReactNode> = {
  checking: <Building2 size={18} />,
  savings: <Wallet size={18} />,
  credit_card: <CreditCard size={18} />,
  investment: <TrendingUp size={18} />,
};

const CURRENCY_SYMBOL: Record<string, string> = {
  BRL: 'R$',
  USD: '$',
  EUR: '€',
};

export default function ContasPage() {
  const queryClient = useQueryClient();
  const router = useRouter();
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [editingAccount, setEditingAccount] = useState<BankAccount | null>(null);

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

  const handleEdit = (account: BankAccount) => {
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

  // Agrupar contas por tipo
  const bankAccounts = useMemo(
    () => accounts.filter((a) => a.account_type === 'checking' || a.account_type === 'savings'),
    [accounts]
  );
  const creditCards = useMemo(
    () => accounts.filter((a) => a.account_type === 'credit_card'),
    [accounts]
  );
  const investments = useMemo(
    () => accounts.filter((a) => a.account_type === 'investment'),
    [accounts]
  );

  const totalBrl = accounts.reduce((sum, a) => sum + Number(a.balance_brl || 0), 0);
  const totalBankBrl = bankAccounts.reduce((sum, a) => sum + Number(a.balance_brl || 0), 0);
  const totalCardBrl = creditCards.reduce((sum, a) => sum + Number(a.balance_brl || 0), 0);
  const totalInvestBrl = investments.reduce((sum, a) => sum + Number(a.balance_brl || 0), 0);

  const getBankColor = (account: BankAccount) => {
    const bank = banks.find((b) => b.id === account.bank_id);
    return bank?.color || '#6366f1';
  };

  const formatAccountBalance = (value: number, currency: string) => {
    const symbol = CURRENCY_SYMBOL[currency] || 'R$';
    const formatted = Math.abs(value).toLocaleString('pt-BR', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
    return value < 0 ? `-${symbol} ${formatted}` : `${symbol} ${formatted}`;
  };

  const accountTypeOptions = [
    { value: 'checking', label: 'Conta Corrente' },
    { value: 'savings', label: 'Poupanca' },
    { value: 'credit_card', label: 'Cartao de Credito' },
    { value: 'investment', label: 'Investimentos' },
  ];

  const currencyOptions = [
    { value: 'BRL', label: 'R$ - Real Brasileiro' },
    { value: 'USD', label: '$ - Dolar Americano' },
    { value: 'EUR', label: 'Euro' },
  ];

  const renderAccountCard = (account: BankAccount) => {
    const color = getBankColor(account);
    const balance = Number(account.current_balance);
    const balanceBrl = Number(account.balance_brl || 0);
    const isMultiCurrency = account.currency !== 'BRL';

    return (
      <div
        key={account.id}
        className="group relative bg-white rounded-2xl border border-slate-200 p-5 hover:shadow-lg hover:-translate-y-0.5 transition-all duration-200 cursor-pointer"
        onClick={() => router.push(`/transacoes?account_id=${account.id}`)}
      >
        {/* Color bar */}
        <div
          className="absolute top-0 left-0 right-0 h-1 rounded-t-2xl"
          style={{ backgroundColor: color }}
        />

        {/* Header */}
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            <div
              className="w-10 h-10 rounded-xl flex items-center justify-center text-white"
              style={{ backgroundColor: color }}
            >
              {ACCOUNT_TYPE_ICON[account.account_type] || <Wallet size={18} />}
            </div>
            <div>
              <h3 className="font-semibold text-slate-800 text-sm">{account.name}</h3>
              <p className="text-xs text-slate-400">
                {account.bank_name} {account.account_number ? `- ${account.account_number}` : ''}
              </p>
            </div>
          </div>

          {/* Actions (hover) */}
          <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
            <button
              onClick={(e) => {
                e.stopPropagation();
                handleEdit(account);
              }}
              className="p-1.5 rounded-lg text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 transition-colors"
            >
              <Edit2 size={14} />
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation();
                handleDelete(account.id);
              }}
              className="p-1.5 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors"
            >
              <Trash2 size={14} />
            </button>
          </div>
        </div>

        {/* Balance */}
        <div>
          <p className="text-xs text-slate-400 mb-1">Saldo atual</p>
          <p
            className={`text-xl font-bold ${
              balance >= 0 ? 'text-slate-800' : 'text-rose-600'
            }`}
          >
            {formatAccountBalance(balance, account.currency || 'BRL')}
          </p>

          {/* BRL equivalent for foreign accounts */}
          {isMultiCurrency && (
            <p className="text-xs text-slate-400 mt-1">
              {formatAccountBalance(balanceBrl, 'BRL')}
            </p>
          )}
        </div>

        {/* Footer badges */}
        <div className="flex items-center gap-2 mt-4 pt-3 border-t border-slate-100">
          <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-500">
            {getAccountTypeLabel(account.account_type)}
          </span>
          <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-500">
            {account.currency || 'BRL'}
          </span>
          {!account.is_active && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-rose-100 text-rose-600">
              Inativa
            </span>
          )}
          <ArrowRight size={14} className="ml-auto text-slate-300 group-hover:text-indigo-500 transition-colors" />
        </div>
      </div>
    );
  };

  const renderSection = (title: string, items: BankAccount[], totalBrl: number) => {
    if (items.length === 0) return null;
    return (
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-slate-700">{title}</h2>
          <p className={`text-sm font-semibold ${totalBrl >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
            {formatAccountBalance(totalBrl, 'BRL')}
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {items.map(renderAccountCard)}
        </div>
      </div>
    );
  };

  return (
    <MainLayout>
      <div className="space-y-8">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-800">Contas</h1>
            <p className="text-slate-500">
              {accounts.length} conta(s) | Patrimonio total:{' '}
              <span className={`font-semibold ${totalBrl >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                {formatAccountBalance(totalBrl, 'BRL')}
              </span>
            </p>
          </div>
          <Button onClick={() => setIsFormOpen(true)}>
            <Plus size={18} className="mr-1.5" />
            Nova Conta
          </Button>
        </div>

        {/* Form modal */}
        {isFormOpen && (
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>{editingAccount ? 'Editar Conta' : 'Nova Conta'}</CardTitle>
                <button onClick={resetForm} className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100">
                  <X size={18} />
                </button>
              </div>
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
                    placeholder="Ex: Itau CC Principal"
                    required
                  />
                  <Input
                    label="Numero da Conta"
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
                  <Button type="submit" isLoading={createMutation.isPending || updateMutation.isPending}>
                    {editingAccount ? 'Salvar' : 'Criar Conta'}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        )}

        {/* Account cards */}
        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <div key={i} className="bg-white rounded-2xl border border-slate-200 p-5 animate-pulse">
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-10 h-10 rounded-xl bg-slate-200" />
                  <div className="space-y-2">
                    <div className="h-4 bg-slate-200 rounded w-24" />
                    <div className="h-3 bg-slate-200 rounded w-16" />
                  </div>
                </div>
                <div className="h-6 bg-slate-200 rounded w-32 mb-2" />
                <div className="h-3 bg-slate-200 rounded w-20" />
              </div>
            ))}
          </div>
        ) : accounts.length === 0 ? (
          <Card>
            <CardContent className="py-16 text-center">
              <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-slate-100 flex items-center justify-center">
                <Building2 size={32} className="text-slate-400" />
              </div>
              <h3 className="text-lg font-semibold text-slate-800">Nenhuma conta cadastrada</h3>
              <p className="text-slate-500 mt-1">Adicione sua primeira conta para comecar.</p>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-8">
            {renderSection('Contas Bancarias', bankAccounts, totalBankBrl)}
            {renderSection('Cartoes de Credito', creditCards, totalCardBrl)}
            {renderSection('Investimentos', investments, totalInvestBrl)}
          </div>
        )}
      </div>
    </MainLayout>
  );
}
