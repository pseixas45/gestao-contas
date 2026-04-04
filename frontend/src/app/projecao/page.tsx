'use client';

import React, { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import MainLayout from '@/components/layout/MainLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import Select from '@/components/ui/Select';
import Input from '@/components/ui/Input';
import Button from '@/components/ui/Button';
import StatCard from '@/components/ui/StatCard';
import Badge from '@/components/ui/Badge';
import { projectionsApi, accountsApi, categoriesApi } from '@/lib/api';
import type { MonthlyProjection, RecurringDetection, UncertainMatch } from '@/lib/api';
import type { Category } from '@/types';
import { formatCurrency } from '@/lib/utils';
import { useToast } from '@/components/ui/Toast';
import {
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Area,
  AreaChart,
} from 'recharts';
import {
  Wallet,
  TrendingUp,
  TrendingDown,
  Calendar,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  CheckCircle,
  Circle,
  Repeat,
  Plus,
  Pencil,
  Trash2,
  X,
  AlertTriangle,
  Check,
  XCircle,
} from 'lucide-react';

function formatCompactCurrency(value: number): string {
  if (Math.abs(value) >= 1000) {
    return `R$ ${(value / 1000).toFixed(1)}k`;
  }
  return formatCurrency(value);
}

// --- Modal de Criar/Editar Item ---
interface ItemFormData {
  description: string;
  amount_brl: string;
  date: string;
  category_id: string;
  is_recurring: boolean;
  recurring_day: string;
}

function ItemModal({
  isOpen,
  onClose,
  onSave,
  editItem,
  accountId,
  defaultDate,
  categories,
  isSaving,
}: {
  isOpen: boolean;
  onClose: () => void;
  onSave: (data: ItemFormData) => void;
  editItem?: { id: number; description: string; amount: number; date: string; category_id?: number | null; is_recurring?: boolean; recurring_day?: number | null } | null;
  accountId: number;
  defaultDate: string;
  categories: Category[];
  isSaving: boolean;
}) {
  const [form, setForm] = useState<ItemFormData>({
    description: '',
    amount_brl: '',
    date: defaultDate,
    category_id: '',
    is_recurring: false,
    recurring_day: '',
  });

  useEffect(() => {
    if (editItem) {
      setForm({
        description: editItem.description,
        amount_brl: String(editItem.amount),
        date: editItem.date,
        category_id: editItem.category_id ? String(editItem.category_id) : '',
        is_recurring: editItem.is_recurring || false,
        recurring_day: editItem.recurring_day ? String(editItem.recurring_day) : '',
      });
    } else {
      setForm({
        description: '',
        amount_brl: '',
        date: defaultDate,
        category_id: '',
        is_recurring: false,
        recurring_day: '',
      });
    }
  }, [editItem, defaultDate, isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <h3 className="text-lg font-bold text-slate-900">
            {editItem ? 'Editar Lancamento' : 'Novo Lancamento'}
          </h3>
          <button onClick={onClose} className="p-1 hover:bg-slate-100 rounded-lg transition-colors">
            <X className="h-5 w-5 text-slate-400" />
          </button>
        </div>
        <div className="p-6 space-y-4">
          <Input
            label="Descricao"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            placeholder="Ex: Salario, Aluguel..."
          />
          <div className="grid grid-cols-2 gap-4">
            <Input
              label="Valor (R$)"
              type="number"
              step="0.01"
              value={form.amount_brl}
              onChange={(e) => setForm({ ...form, amount_brl: e.target.value })}
              placeholder="-1500.00"
              hint="Negativo = despesa"
            />
            <Input
              label="Data"
              type="date"
              value={form.date}
              onChange={(e) => setForm({ ...form, date: e.target.value })}
            />
          </div>
          <Select
            label="Categoria"
            value={form.category_id}
            onChange={(e) => setForm({ ...form, category_id: e.target.value })}
            options={[
              { value: '', label: 'Sem categoria' },
              ...categories.map((c) => ({ value: c.id, label: c.name })),
            ]}
          />
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={form.is_recurring}
                onChange={(e) => setForm({ ...form, is_recurring: e.target.checked })}
                className="w-4 h-4 rounded border-slate-300 text-primary-600 focus:ring-primary-500"
              />
              <span className="text-sm text-slate-700">Recorrente</span>
            </label>
            {form.is_recurring && (
              <Input
                type="number"
                min="1"
                max="31"
                value={form.recurring_day}
                onChange={(e) => setForm({ ...form, recurring_day: e.target.value })}
                placeholder="Dia"
                className="w-20"
              />
            )}
          </div>
        </div>
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-100">
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button
            onClick={() => onSave(form)}
            isLoading={isSaving}
            disabled={!form.description || !form.amount_brl || !form.date}
          >
            {editItem ? 'Salvar' : 'Criar'}
          </Button>
        </div>
      </div>
    </div>
  );
}

// --- Pagina Principal ---
export default function ProjecaoPage() {
  const now = new Date();
  const [selectedAccount, setSelectedAccount] = useState('');
  const [month, setMonth] = useState(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`);
  const [showDetection, setShowDetection] = useState(false);
  const [selectedRecurring, setSelectedRecurring] = useState<Set<number>>(new Set());
  const [recurringEdits, setRecurringEdits] = useState<Record<number, { description: string; avg_amount: number; avg_day: number }>>({});

  // Modal state
  const [modalOpen, setModalOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<{
    id: number; description: string; amount: number; date: string;
    category_id?: number | null; is_recurring?: boolean; recurring_day?: number | null;
  } | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null);

  const queryClient = useQueryClient();
  const { addToast } = useToast();

  const { data: accounts = [] } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
  });

  const { data: categories = [] } = useQuery({
    queryKey: ['categories-flat'],
    queryFn: () => categoriesApi.list(true, true),
  });

  const accountId = selectedAccount ? parseInt(selectedAccount) : null;

  const { data: projection, isLoading: projLoading } = useQuery({
    queryKey: ['projection-monthly', accountId, month],
    queryFn: () => projectionsApi.getMonthly(accountId!, month),
    enabled: !!accountId,
  });

  const { data: recurring = [], isLoading: recurringLoading } = useQuery({
    queryKey: ['detect-recurring', accountId],
    queryFn: () => projectionsApi.detectRecurring(accountId!),
    enabled: !!accountId && showDetection,
  });

  // Reset recurring edits when detection data changes
  useEffect(() => {
    setRecurringEdits({});
  }, [recurring]);

  // Mutations
  const createMutation = useMutation({
    mutationFn: (data: { account_id: number; date: string; description: string; amount_brl: number; category_id?: number | null; is_recurring?: boolean; recurring_day?: number | null }) =>
      projectionsApi.createItem(data),
    onSuccess: () => {
      addToast('Lancamento criado', 'success');
      setModalOpen(false);
      queryClient.invalidateQueries({ queryKey: ['projection-monthly'] });
    },
    onError: () => addToast('Erro ao criar lancamento', 'error'),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, updates }: { id: number; updates: Record<string, unknown> }) =>
      projectionsApi.updateItem(id, updates),
    onSuccess: () => {
      addToast('Lancamento atualizado', 'success');
      setModalOpen(false);
      setEditingItem(null);
      queryClient.invalidateQueries({ queryKey: ['projection-monthly'] });
    },
    onError: () => addToast('Erro ao atualizar', 'error'),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => projectionsApi.deleteItem(id),
    onSuccess: () => {
      addToast('Lancamento removido', 'success');
      setDeleteConfirm(null);
      queryClient.invalidateQueries({ queryKey: ['projection-monthly'] });
    },
    onError: () => addToast('Erro ao remover', 'error'),
  });

  const confirmMatchMutation = useMutation({
    mutationFn: ({ projectedId, action }: { projectedId: number; action: 'confirm' | 'reject' }) =>
      projectionsApi.confirmMatch(projectedId, action),
    onSuccess: (data, variables) => {
      addToast(
        variables.action === 'confirm' ? 'Item marcado como realizado' : 'Match rejeitado',
        'success'
      );
      queryClient.invalidateQueries({ queryKey: ['projection-monthly'] });
    },
    onError: () => addToast('Erro ao processar match', 'error'),
  });

  const confirmMutation = useMutation({
    mutationFn: () => {
      const items = recurring
        .map((r, i) => ({ r, i }))
        .filter(({ i }) => selectedRecurring.has(i))
        .map(({ r, i }) => {
          const edits = recurringEdits[i];
          return {
            description: edits?.description ?? r.description,
            amount: edits?.avg_amount ?? r.avg_amount,
            recurring_day: Math.round(edits?.avg_day ?? r.avg_day),
            category_id: r.category_id,
          };
        });
      return projectionsApi.confirmRecurring(accountId!, items);
    },
    onSuccess: (data) => {
      addToast(`${data.created_count} itens criados`, 'success');
      setShowDetection(false);
      setSelectedRecurring(new Set());
      setRecurringEdits({});
      queryClient.invalidateQueries({ queryKey: ['projection-monthly'] });
    },
  });

  const handleSaveItem = (form: ItemFormData) => {
    const payload = {
      account_id: accountId!,
      date: form.date,
      description: form.description,
      amount_brl: parseFloat(form.amount_brl),
      category_id: form.category_id ? parseInt(form.category_id) : null,
      is_recurring: form.is_recurring,
      recurring_day: form.is_recurring && form.recurring_day ? parseInt(form.recurring_day) : null,
    };

    if (editingItem) {
      const { account_id, ...updates } = payload;
      updateMutation.mutate({ id: editingItem.id, updates });
    } else {
      createMutation.mutate(payload);
    }
  };

  const openEdit = (entry: MonthlyProjection['entries'][0]) => {
    setEditingItem({
      id: entry.id,
      description: entry.description,
      amount: entry.amount,
      date: entry.date,
      is_recurring: entry.is_recurring,
    });
    setModalOpen(true);
  };

  const openCreate = () => {
    setEditingItem(null);
    setModalOpen(true);
  };

  const navigateMonth = (direction: number) => {
    const [y, m] = month.split('-').map(Number);
    const d = new Date(y, m - 1 + direction, 1);
    setMonth(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`);
  };

  const monthLabel = (() => {
    const [y, m] = month.split('-').map(Number);
    const names = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
    return `${names[m - 1]} ${y}`;
  })();

  const todayStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;

  const defaultDate = `${month}-${String(now.getDate()).padStart(2, '0')}`;

  const chartData = projection?.daily_balances.map((d) => ({
    date: d.date.slice(8),
    balance: d.balance,
    isPast: d.is_past,
  })) || [];

  const toggleRecurring = (idx: number) => {
    const next = new Set(selectedRecurring);
    if (next.has(idx)) next.delete(idx);
    else next.add(idx);
    setSelectedRecurring(next);
  };

  const selectAllRecurring = () => {
    if (selectedRecurring.size === recurring.length) {
      setSelectedRecurring(new Set());
    } else {
      setSelectedRecurring(new Set(recurring.map((_, i) => i)));
    }
  };

  const getRecurringValue = (idx: number, field: 'description' | 'avg_amount' | 'avg_day') => {
    return recurringEdits[idx]?.[field] ?? recurring[idx][field];
  };

  const setRecurringEdit = (idx: number, field: string, value: string | number) => {
    setRecurringEdits((prev) => ({
      ...prev,
      [idx]: {
        description: prev[idx]?.description ?? recurring[idx].description,
        avg_amount: prev[idx]?.avg_amount ?? recurring[idx].avg_amount,
        avg_day: prev[idx]?.avg_day ?? recurring[idx].avg_day,
        [field]: value,
      },
    }));
  };

  return (
    <MainLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Projecao de Caixa</h1>
            <p className="text-slate-500">Visualize o saldo projetado dia a dia</p>
          </div>
          <div className="flex items-center gap-3">
            <Select
              value={selectedAccount}
              onChange={(e) => setSelectedAccount(e.target.value)}
              options={[
                { value: '', label: 'Selecione uma conta...' },
                ...accounts.map((a: { id: number; name: string; bank_name?: string }) => ({
                  value: a.id.toString(),
                  label: `${a.name}${a.bank_name ? ` (${a.bank_name})` : ''}`,
                })),
              ]}
            />
            {accountId && (
              <Button onClick={openCreate}>
                <Plus className="h-4 w-4 mr-1.5" />
                Novo Lancamento
              </Button>
            )}
          </div>
        </div>

        {!accountId && (
          <Card>
            <CardContent className="py-16 text-center">
              <Wallet className="h-12 w-12 text-slate-300 mx-auto mb-3" />
              <p className="text-slate-400">Selecione uma conta para ver a projecao</p>
            </CardContent>
          </Card>
        )}

        {accountId && (
          <>
            {/* Month navigation */}
            <div className="flex items-center justify-between">
              <button
                onClick={() => navigateMonth(-1)}
                className="p-2 rounded-lg hover:bg-slate-100 transition-colors"
              >
                <ChevronLeft className="h-5 w-5 text-slate-600" />
              </button>
              <h2 className="text-lg font-bold text-slate-900">{monthLabel}</h2>
              <button
                onClick={() => navigateMonth(1)}
                className="p-2 rounded-lg hover:bg-slate-100 transition-colors"
              >
                <ChevronRight className="h-5 w-5 text-slate-600" />
              </button>
            </div>

            {/* Stats */}
            {projection && (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <StatCard
                  title="Saldo Atual"
                  value={formatCurrency(projection.current_balance)}
                  icon={Wallet}
                  color="primary"
                />
                <StatCard
                  title="Inicio do Mes"
                  value={formatCurrency(projection.balance_at_month_start)}
                  icon={Calendar}
                  color="sky"
                />
                <StatCard
                  title="Projecao Fim do Mes"
                  value={formatCurrency(projection.projected_final_balance)}
                  icon={projection.projected_final_balance >= projection.balance_at_month_start ? TrendingUp : TrendingDown}
                  color={projection.projected_final_balance >= projection.balance_at_month_start ? 'emerald' : 'rose'}
                />
              </div>
            )}

            {/* Line chart */}
            <Card>
              <CardHeader>
                <CardTitle>Saldo Diario</CardTitle>
              </CardHeader>
              <CardContent>
                {projLoading ? (
                  <div className="h-64 flex items-center justify-center">
                    <div className="w-8 h-8 border-3 border-primary-200 border-t-primary-600 rounded-full animate-spin" />
                  </div>
                ) : chartData.length === 0 ? (
                  <div className="h-64 flex items-center justify-center text-slate-400">
                    Sem dados para este mes
                  </div>
                ) : (
                  <div className="h-72">
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={chartData}>
                        <defs>
                          <linearGradient id="balanceGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#6366f1" stopOpacity={0.15} />
                            <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                        <XAxis
                          dataKey="date"
                          tick={{ fontSize: 11, fill: '#94a3b8' }}
                          axisLine={false}
                          tickLine={false}
                        />
                        <YAxis
                          tick={{ fontSize: 11, fill: '#94a3b8' }}
                          tickFormatter={(v) => formatCompactCurrency(v)}
                          axisLine={false}
                          tickLine={false}
                          width={70}
                        />
                        <Tooltip
                          formatter={(value: number) => [formatCurrency(value), 'Saldo']}
                          labelFormatter={(label) => `Dia ${label}`}
                          contentStyle={{
                            borderRadius: '12px',
                            border: '1px solid #e2e8f0',
                            boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.05)',
                            fontSize: '13px',
                          }}
                        />
                        <ReferenceLine y={0} stroke="#e2e8f0" strokeDasharray="3 3" />
                        <Area
                          type="monotone"
                          dataKey="balance"
                          stroke="#6366f1"
                          strokeWidth={2}
                          fill="url(#balanceGrad)"
                          dot={false}
                          activeDot={{ r: 4, fill: '#6366f1' }}
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Entries table */}
            {projection && projection.entries.length > 0 && (
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle>
                      Lancamentos do Mes ({projection.real_count} reais, {projection.projected_count} projetados
                      {(projection.realized_count || 0) > 0 && `, ${projection.realized_count} realizado${projection.realized_count !== 1 ? 's' : ''}`}
                      {(projection.uncertain_matches?.length || 0) > 0 && `, ${projection.uncertain_matches.length} incerto${projection.uncertain_matches.length !== 1 ? 's' : ''}`})
                    </CardTitle>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="overflow-x-auto rounded-lg border border-slate-200 max-h-[500px] overflow-y-auto">
                    <table className="min-w-full text-sm">
                      <thead className="bg-slate-50 sticky top-0">
                        <tr>
                          <th className="px-3 py-2 text-left font-medium text-slate-500">Data</th>
                          <th className="px-3 py-2 text-left font-medium text-slate-500">Descricao</th>
                          <th className="px-3 py-2 text-right font-medium text-slate-500">Valor</th>
                          <th className="px-3 py-2 text-center font-medium text-slate-500">Status</th>
                          <th className="px-3 py-2 text-center font-medium text-slate-500 w-20">Acoes</th>
                        </tr>
                      </thead>
                      <tbody>
                        {projection.entries.map((entry, i) => {
                          const showTodaySep =
                            i > 0 &&
                            projection.entries[i - 1].date <= todayStr &&
                            entry.date > todayStr;

                          return (
                            <React.Fragment key={`${entry.type}-${entry.id}-${i}`}>
                              {showTodaySep && (
                                <tr>
                                  <td colSpan={5} className="px-3 py-1.5 bg-primary-50 text-center text-xs font-medium text-primary-600">
                                    Hoje
                                  </td>
                                </tr>
                              )}
                              <tr>
                              <td className="px-3 py-2 text-slate-600 whitespace-nowrap">{entry.date.slice(5)}</td>
                              <td className="px-3 py-2 text-slate-700">
                                <div className="flex items-center gap-2">
                                  {entry.category_color && (
                                    <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: entry.category_color }} />
                                  )}
                                  <span className="truncate max-w-xs">{entry.description}</span>
                                  {entry.is_recurring && (
                                    <Repeat className="h-3 w-3 text-violet-400 flex-shrink-0" />
                                  )}
                                </div>
                              </td>
                              <td className={`px-3 py-2 text-right tabular-nums font-medium ${
                                entry.amount >= 0 ? 'text-emerald-600' : 'text-rose-600'
                              }`}>
                                {formatCurrency(entry.amount)}
                              </td>
                              <td className="px-3 py-2 text-center">
                                {entry.type === 'real' ? (
                                  <Badge color="emerald" variant="soft" size="sm">Real</Badge>
                                ) : entry.type === 'uncertain' ? (
                                  <Badge color="amber" variant="soft" size="sm">
                                    <AlertTriangle className="h-3 w-3 mr-0.5 inline" />
                                    Incerto
                                  </Badge>
                                ) : (
                                  <Badge color="violet" variant="soft" size="sm">Previsto</Badge>
                                )}
                              </td>
                              <td className="px-3 py-2 text-center">
                                {entry.type === 'uncertain' && (() => {
                                  const match = projection.uncertain_matches?.find(m => m.projected_id === entry.id);
                                  return (
                                    <div className="flex items-center justify-center gap-1">
                                      <button
                                        onClick={() => confirmMatchMutation.mutate({ projectedId: entry.id, action: 'confirm' })}
                                        className="p-1 hover:bg-emerald-50 rounded-lg transition-colors text-slate-400 hover:text-emerald-600"
                                        title={match ? `Confirmar: ${match.matched_description} (${match.confidence}%)` : 'Confirmar'}
                                      >
                                        <Check className="h-3.5 w-3.5" />
                                      </button>
                                      <button
                                        onClick={() => confirmMatchMutation.mutate({ projectedId: entry.id, action: 'reject' })}
                                        className="p-1 hover:bg-rose-50 rounded-lg transition-colors text-slate-400 hover:text-rose-600"
                                        title="Rejeitar match"
                                      >
                                        <XCircle className="h-3.5 w-3.5" />
                                      </button>
                                    </div>
                                  );
                                })()}
                                {(entry.type === 'projected') && (
                                  <div className="flex items-center justify-center gap-1">
                                    <button
                                      onClick={() => openEdit(entry)}
                                      className="p-1 hover:bg-slate-100 rounded-lg transition-colors text-slate-400 hover:text-primary-600"
                                      title="Editar"
                                    >
                                      <Pencil className="h-3.5 w-3.5" />
                                    </button>
                                    {deleteConfirm === entry.id ? (
                                      <div className="flex items-center gap-1">
                                        <button
                                          onClick={() => deleteMutation.mutate(entry.id)}
                                          className="px-1.5 py-0.5 bg-rose-100 text-rose-600 rounded text-xs font-medium hover:bg-rose-200 transition-colors"
                                        >
                                          Sim
                                        </button>
                                        <button
                                          onClick={() => setDeleteConfirm(null)}
                                          className="px-1.5 py-0.5 bg-slate-100 text-slate-500 rounded text-xs hover:bg-slate-200 transition-colors"
                                        >
                                          Nao
                                        </button>
                                      </div>
                                    ) : (
                                      <button
                                        onClick={() => setDeleteConfirm(entry.id)}
                                        className="p-1 hover:bg-slate-100 rounded-lg transition-colors text-slate-400 hover:text-rose-600"
                                        title="Excluir"
                                      >
                                        <Trash2 className="h-3.5 w-3.5" />
                                      </button>
                                    )}
                                  </div>
                                )}
                              </td>
                              </tr>
                            </React.Fragment>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Uncertain matches detail */}
            {projection && projection.uncertain_matches && projection.uncertain_matches.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>
                    <AlertTriangle className="h-4 w-4 text-amber-500 inline mr-2" />
                    Matches Incertos ({projection.uncertain_matches.length})
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-xs text-slate-400 mb-3">
                    Itens projetados que podem corresponder a transacoes reais. Confirme ou rejeite cada match.
                  </p>
                  <div className="space-y-2">
                    {projection.uncertain_matches.map((m) => (
                      <div key={m.projected_id} className="flex items-center gap-3 p-3 bg-amber-50 rounded-xl border border-amber-100">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 text-sm">
                            <span className="font-medium text-slate-700 truncate">{m.projected_description}</span>
                            <span className="text-slate-400">→</span>
                            <span className="font-medium text-slate-700 truncate">{m.matched_description}</span>
                          </div>
                          <div className="flex items-center gap-3 text-xs text-slate-500 mt-1">
                            <span>Projetado: {formatCurrency(m.projected_amount)} em {m.projected_date?.slice(5)}</span>
                            <span>|</span>
                            <span>Real: {formatCurrency(m.matched_amount || 0)} em {m.matched_date?.slice(5)}</span>
                            <span>|</span>
                            <span className={`font-medium ${m.confidence >= 70 ? 'text-emerald-600' : 'text-amber-600'}`}>
                              {m.confidence}% confianca
                            </span>
                          </div>
                        </div>
                        <div className="flex items-center gap-1 flex-shrink-0">
                          <button
                            onClick={() => confirmMatchMutation.mutate({ projectedId: m.projected_id, action: 'confirm' })}
                            className="px-2.5 py-1 bg-emerald-100 text-emerald-700 rounded-lg text-xs font-medium hover:bg-emerald-200 transition-colors"
                          >
                            <Check className="h-3 w-3 inline mr-1" />
                            Confirmar
                          </button>
                          <button
                            onClick={() => confirmMatchMutation.mutate({ projectedId: m.projected_id, action: 'reject' })}
                            className="px-2.5 py-1 bg-slate-100 text-slate-600 rounded-lg text-xs font-medium hover:bg-slate-200 transition-colors"
                          >
                            <XCircle className="h-3 w-3 inline mr-1" />
                            Nao e
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Detect recurring section */}
            <div className="flex items-center gap-3">
              <Button
                variant="secondary"
                onClick={() => setShowDetection(!showDetection)}
              >
                <RefreshCw className="h-4 w-4 mr-1.5" />
                {showDetection ? 'Ocultar Deteccao' : 'Detectar Recorrentes'}
              </Button>
            </div>

            {showDetection && (
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle>Lancamentos Recorrentes Detectados</CardTitle>
                    {recurring.length > 0 && (
                      <div className="flex items-center gap-2">
                        <Button variant="secondary" size="sm" onClick={selectAllRecurring}>
                          {selectedRecurring.size === recurring.length ? 'Desmarcar todos' : 'Selecionar todos'}
                        </Button>
                        <Button
                          size="sm"
                          disabled={selectedRecurring.size === 0 || confirmMutation.isPending}
                          isLoading={confirmMutation.isPending}
                          onClick={() => confirmMutation.mutate()}
                        >
                          Confirmar {selectedRecurring.size} selecionado{selectedRecurring.size !== 1 ? 's' : ''}
                        </Button>
                      </div>
                    )}
                  </div>
                </CardHeader>
                <CardContent>
                  {recurringLoading ? (
                    <div className="py-8 text-center">
                      <div className="w-8 h-8 border-3 border-primary-200 border-t-primary-600 rounded-full animate-spin mx-auto" />
                      <p className="mt-3 text-sm text-slate-400">Analisando historico...</p>
                    </div>
                  ) : recurring.length === 0 ? (
                    <p className="text-sm text-slate-400 text-center py-8">
                      Nenhum lancamento recorrente detectado. Importe mais dados para melhorar a deteccao.
                    </p>
                  ) : (
                    <div className="space-y-1">
                      {recurring.map((r, i) => {
                        const isSelected = selectedRecurring.has(i);
                        const isEdited = !!recurringEdits[i];

                        return (
                          <div
                            key={i}
                            className={`flex items-center gap-3 p-3 rounded-xl transition-colors ${
                              isSelected
                                ? 'bg-primary-50 border border-primary-200'
                                : 'hover:bg-slate-50 border border-transparent'
                            }`}
                          >
                            {/* Checkbox */}
                            <button
                              onClick={() => toggleRecurring(i)}
                              className={`flex-shrink-0 ${isSelected ? 'text-primary-600' : 'text-slate-300'}`}
                            >
                              {isSelected ? <CheckCircle className="h-5 w-5" /> : <Circle className="h-5 w-5" />}
                            </button>

                            {/* Description - editable */}
                            <div className="flex-1 min-w-0">
                              <input
                                type="text"
                                value={getRecurringValue(i, 'description') as string}
                                onChange={(e) => setRecurringEdit(i, 'description', e.target.value)}
                                className="text-sm font-medium text-slate-700 bg-transparent border-0 border-b border-transparent hover:border-slate-300 focus:border-primary-500 focus:outline-none w-full truncate px-0 py-0.5"
                              />
                              <p className="text-xs text-slate-400">
                                {r.occurrences} ocorrencias
                                {r.category_name && ` | ${r.category_name}`}
                                {isEdited && <span className="text-amber-500 ml-1">(editado)</span>}
                              </p>
                            </div>

                            {/* Day - editable */}
                            <div className="flex items-center gap-1 flex-shrink-0">
                              <span className="text-xs text-slate-400">dia</span>
                              <input
                                type="number"
                                min="1"
                                max="31"
                                value={getRecurringValue(i, 'avg_day') as number}
                                onChange={(e) => setRecurringEdit(i, 'avg_day', parseInt(e.target.value) || 1)}
                                className="w-10 text-center text-xs font-medium text-slate-600 bg-transparent border border-slate-200 rounded-lg px-1 py-0.5 focus:border-primary-500 focus:outline-none"
                              />
                            </div>

                            {/* Amount - editable */}
                            <div className="flex-shrink-0 w-28 text-right">
                              <input
                                type="number"
                                step="0.01"
                                value={getRecurringValue(i, 'avg_amount') as number}
                                onChange={(e) => setRecurringEdit(i, 'avg_amount', parseFloat(e.target.value) || 0)}
                                className={`w-full text-right text-sm font-semibold tabular-nums bg-transparent border-0 border-b border-transparent hover:border-slate-300 focus:border-primary-500 focus:outline-none px-0 py-0.5 ${
                                  (getRecurringValue(i, 'avg_amount') as number) >= 0 ? 'text-emerald-600' : 'text-rose-600'
                                }`}
                              />
                              <p className="text-xs text-slate-400">CV: {(r.cv * 100).toFixed(0)}%</p>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </CardContent>
              </Card>
            )}
          </>
        )}
      </div>

      {/* Modal */}
      <ItemModal
        isOpen={modalOpen}
        onClose={() => { setModalOpen(false); setEditingItem(null); }}
        onSave={handleSaveItem}
        editItem={editingItem}
        accountId={accountId || 0}
        defaultDate={defaultDate}
        categories={categories}
        isSaving={createMutation.isPending || updateMutation.isPending}
      />
    </MainLayout>
  );
}
