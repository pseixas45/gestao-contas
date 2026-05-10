'use client';

import { useState, useMemo, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import MainLayout from '@/components/layout/MainLayout';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card';
import Button from '@/components/ui/Button';
import Badge from '@/components/ui/Badge';
import {
  expenseReportsApi,
  transactionsApi,
  accountsApi,
  categoriesApi,
  type ExpenseReportSummary,
  type ExpenseReportDetail,
  type UnreportedTransaction,
  type ExpectedItemsResponse,
} from '@/lib/api';
import { formatCurrency, formatDate } from '@/lib/utils';
import {
  Plus,
  ArrowLeft,
  Download,
  Trash2,
  Send,
  CheckCircle,
  RotateCcw,
  CheckSquare,
  Square,
  AlertTriangle,
  ShieldCheck,
  RefreshCw,
  X,
  PlusCircle,
} from 'lucide-react';

type View = 'list' | 'new' | 'detail';

const STATUS_CONFIG: Record<string, { label: string; color: string }> = {
  draft: { label: 'Rascunho', color: '#eab308' },
  submitted: { label: 'Enviado', color: '#3b82f6' },
  reimbursed: { label: 'Reembolsado', color: '#22c55e' },
};

function formatMonthLabel(ym: string): string {
  const months: Record<string, string> = {
    '01': 'Jan', '02': 'Fev', '03': 'Mar', '04': 'Abr',
    '05': 'Mai', '06': 'Jun', '07': 'Jul', '08': 'Ago',
    '09': 'Set', '10': 'Out', '11': 'Nov', '12': 'Dez',
  };
  const [year, month] = ym.split('-');
  return `${months[month] || month}/${year}`;
}

function getCurrentMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

export default function ReembolsosPage() {
  const queryClient = useQueryClient();
  const [view, setView] = useState<View>('list');
  const [selectedReportId, setSelectedReportId] = useState<number | null>(null);
  const [referenceMonth, setReferenceMonth] = useState(getCurrentMonth());
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [notes, setNotes] = useState('');

  const [showValidation, setShowValidation] = useState(true);
  const [showAddPanel, setShowAddPanel] = useState(false);
  const [addIds, setAddIds] = useState<Set<number>>(new Set());

  // Manual transaction form state
  const [showManualForm, setShowManualForm] = useState(false);
  const [manualDate, setManualDate] = useState('');
  const [manualDescription, setManualDescription] = useState('');
  const [manualAmount, setManualAmount] = useState('');
  const [manualAccountId, setManualAccountId] = useState<number | ''>('');

  // Queries
  const { data: reports = [], isLoading: loadingReports } = useQuery({
    queryKey: ['expense-reports'],
    queryFn: () => expenseReportsApi.list(),
    enabled: view === 'list',
  });

  const { data: reportDetail, isLoading: loadingDetail } = useQuery({
    queryKey: ['expense-reports', selectedReportId],
    queryFn: () => expenseReportsApi.get(selectedReportId!),
    enabled: view === 'detail' && selectedReportId !== null,
  });

  const isDraftDetail = view === 'detail' && reportDetail?.status === 'draft';

  const { data: unreported = [], isLoading: loadingUnreported } = useQuery({
    queryKey: ['unreported-transactions'],
    queryFn: () => expenseReportsApi.getUnreported(),
    enabled: view === 'new' || isDraftDetail,
  });

  const { data: expectedItems } = useQuery({
    queryKey: ['expected-items'],
    queryFn: () => expenseReportsApi.getExpectedItems(),
    enabled: view === 'new',
  });

  const { data: accounts = [] } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
    enabled: showManualForm || view === 'new' || isDraftDetail,
  });

  const { data: categories = [] } = useQuery({
    queryKey: ['categories-flat'],
    queryFn: () => categoriesApi.list(true, true),
    enabled: showManualForm || view === 'new' || isDraftDetail,
  });

  const workExpenseCategoryId = useMemo(() => {
    const cat = categories.find(c => c.name === 'Despesas Trabalho');
    return cat?.id ?? null;
  }, [categories]);

  // Mutations
  const createMutation = useMutation({
    mutationFn: expenseReportsApi.create,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['expense-reports'] });
      queryClient.invalidateQueries({ queryKey: ['unreported-transactions'] });
      setSelectedReportId(data.id);
      setView('detail');
      setSelectedIds(new Set());
      setNotes('');
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Parameters<typeof expenseReportsApi.update>[1] }) =>
      expenseReportsApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['expense-reports'] });
      if (selectedReportId) {
        queryClient.invalidateQueries({ queryKey: ['expense-reports', selectedReportId] });
      }
    },
  });

  const deleteMutation = useMutation({
    mutationFn: expenseReportsApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['expense-reports'] });
      queryClient.invalidateQueries({ queryKey: ['unreported-transactions'] });
      setView('list');
      setSelectedReportId(null);
    },
  });

  const selectedAccountCurrency = useMemo((): 'BRL' | 'USD' | 'EUR' => {
    if (!manualAccountId) return 'BRL';
    const acct = accounts.find(a => a.id === manualAccountId);
    return (acct?.currency as 'BRL' | 'USD' | 'EUR') || 'BRL';
  }, [manualAccountId, accounts]);

  const createTransactionMutation = useMutation({
    mutationFn: (data: { date: string; description: string; amount: number; account_id: number; category_id: number; currency: 'BRL' | 'USD' | 'EUR' }) =>
      transactionsApi.create({
        date: data.date,
        description: data.description,
        amount: -Math.abs(data.amount),
        account_id: data.account_id,
        category_id: data.category_id,
        original_currency: data.currency,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['unreported-transactions'] });
      setManualDate('');
      setManualDescription('');
      setManualAmount('');
      setManualAccountId('');
      setShowManualForm(false);
    },
  });

  // Handlers
  const handleOpenReport = useCallback((id: number) => {
    setSelectedReportId(id);
    setView('detail');
  }, []);

  const handleNewReport = useCallback(() => {
    setReferenceMonth(getCurrentMonth());
    setSelectedIds(new Set());
    setNotes('');
    setView('new');
  }, []);

  const handleBack = useCallback(() => {
    setView('list');
    setSelectedReportId(null);
  }, []);

  const toggleTransaction = useCallback((id: number) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const toggleAll = useCallback(() => {
    if (selectedIds.size === unreported.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(unreported.map(t => t.id)));
    }
  }, [selectedIds.size, unreported]);

  const handleCreate = useCallback(() => {
    if (selectedIds.size === 0) return;
    createMutation.mutate({
      reference_month: referenceMonth,
      transaction_ids: Array.from(selectedIds),
      notes: notes || undefined,
    });
  }, [selectedIds, referenceMonth, notes, createMutation]);

  const handleStatusChange = useCallback((reportId: number, newStatus: string) => {
    updateMutation.mutate({ id: reportId, data: { status: newStatus } });
  }, [updateMutation]);

  const handleDelete = useCallback((reportId: number) => {
    if (confirm('Excluir este relatório rascunho? As transações ficarão disponíveis para futuros relatórios.')) {
      deleteMutation.mutate(reportId);
    }
  }, [deleteMutation]);

  const handleRefreshReport = useCallback((reportId: number) => {
    if (unreported.length === 0) return;
    const allIds = unreported.map(t => t.id);
    updateMutation.mutate(
      { id: reportId, data: { add_transaction_ids: allIds } },
      {
        onSuccess: () => {
          queryClient.invalidateQueries({ queryKey: ['unreported-transactions'] });
        },
      }
    );
  }, [unreported, updateMutation, queryClient]);

  const handleRemoveFromReport = useCallback((reportId: number, transactionId: number) => {
    updateMutation.mutate(
      { id: reportId, data: { remove_transaction_ids: [transactionId] } },
      {
        onSuccess: () => {
          queryClient.invalidateQueries({ queryKey: ['unreported-transactions'] });
        },
      }
    );
  }, [updateMutation, queryClient]);

  const handleAddToReport = useCallback((reportId: number) => {
    if (addIds.size === 0) return;
    updateMutation.mutate(
      { id: reportId, data: { add_transaction_ids: Array.from(addIds) } },
      {
        onSuccess: () => {
          setAddIds(new Set());
          setShowAddPanel(false);
          queryClient.invalidateQueries({ queryKey: ['unreported-transactions'] });
        },
      }
    );
  }, [addIds, updateMutation, queryClient]);

  const toggleAddId = useCallback((id: number) => {
    setAddIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const handleCreateManualTransaction = useCallback(() => {
    if (!manualDate || !manualDescription || !manualAmount || !manualAccountId || !workExpenseCategoryId) return;
    createTransactionMutation.mutate({
      date: manualDate,
      description: manualDescription,
      amount: parseFloat(manualAmount),
      account_id: manualAccountId as number,
      category_id: workExpenseCategoryId,
      currency: selectedAccountCurrency,
    });
  }, [manualDate, manualDescription, manualAmount, manualAccountId, workExpenseCategoryId, createTransactionMutation]);

  const handleExport = useCallback((reportId: number) => {
    const url = expenseReportsApi.getExportUrl(reportId);
    const token = localStorage.getItem('token');
    // Fetch with auth header then download as blob
    fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      .then(res => res.blob())
      .then(blob => {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `reembolso_${reportDetail?.reference_month || 'report'}.xlsx`;
        a.click();
        URL.revokeObjectURL(a.href);
      });
  }, [reportDetail]);

  // Computed
  const selectedTotal = useMemo(() => {
    return unreported
      .filter(t => selectedIds.has(t.id))
      .reduce((sum, t) => sum + t.amount_brl, 0);
  }, [unreported, selectedIds]);

  // ===== RENDER =====

  if (view === 'new') {
    return (
      <MainLayout>
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <button onClick={handleBack} className="p-1.5 hover:bg-slate-100 rounded-lg transition-colors">
                  <ArrowLeft size={18} className="text-slate-500" />
                </button>
                <CardTitle>Novo Relatório de Reembolso</CardTitle>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {/* Mês de referência */}
            <div className="flex items-center gap-4 mb-6">
              <label className="text-sm font-medium text-slate-700">Mês de Referência:</label>
              <input
                type="month"
                value={referenceMonth}
                onChange={e => setReferenceMonth(e.target.value)}
                className="px-3 py-1.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>

            {/* Validação de itens esperados */}
            {expectedItems && expectedItems.expected.length > 0 && (
              <div className="mb-6">
                <button
                  onClick={() => setShowValidation(!showValidation)}
                  className="flex items-center gap-2 text-sm font-semibold text-slate-700 mb-2 hover:text-slate-900"
                >
                  {expectedItems.missing_count > 0 ? (
                    <AlertTriangle size={16} className="text-amber-500" />
                  ) : (
                    <ShieldCheck size={16} className="text-emerald-500" />
                  )}
                  Validação de Itens Recorrentes
                  <span className="font-normal text-slate-500">
                    ({expectedItems.found_count} encontrados, {expectedItems.missing_count} faltando)
                  </span>
                  <span className="text-xs text-slate-400">{showValidation ? '▼' : '▶'}</span>
                </button>

                {showValidation && (
                  <div className="border border-slate-200 rounded-xl overflow-hidden">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="bg-slate-50 border-b border-slate-200">
                          <th className="w-10 px-3 py-2 text-center font-medium text-slate-600">Status</th>
                          <th className="px-3 py-2 text-left font-medium text-slate-600">Item</th>
                          <th className="px-3 py-2 text-center font-medium text-slate-600">Frequência</th>
                          <th className="px-3 py-2 text-right font-medium text-slate-600">Valor Médio</th>
                        </tr>
                      </thead>
                      <tbody>
                        {expectedItems.expected.map((item, idx) => (
                          <tr
                            key={idx}
                            className={`border-b border-slate-100 ${
                              item.found ? '' : 'bg-amber-50'
                            }`}
                          >
                            <td className="px-3 py-2 text-center">
                              {item.found ? (
                                <CheckCircle size={16} className="text-emerald-500 inline" />
                              ) : (
                                <AlertTriangle size={16} className="text-amber-500 inline" />
                              )}
                            </td>
                            <td className="px-3 py-2 text-slate-800">
                              {item.sample_description}
                              {item.found && item.matched_transaction_ids.length > 0 && (
                                <button
                                  className="ml-2 text-xs text-primary-600 hover:text-primary-800"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setSelectedIds(prev => {
                                      const next = new Set(prev);
                                      item.matched_transaction_ids.forEach(id => next.add(id));
                                      return next;
                                    });
                                  }}
                                >
                                  + selecionar
                                </button>
                              )}
                            </td>
                            <td className="px-3 py-2 text-center text-slate-500">
                              {item.frequency}/{item.total_reports} meses
                            </td>
                            <td className="px-3 py-2 text-right text-slate-600">
                              {formatCurrency(item.avg_amount)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}

            {/* Criar transação manual */}
            <div className="mb-6">
              <button
                onClick={() => setShowManualForm(!showManualForm)}
                className="flex items-center gap-2 text-sm font-medium text-primary-600 hover:text-primary-800 mb-3"
              >
                <PlusCircle size={16} />
                Criar Nova Transação Manual
                <span className="text-xs text-slate-400">{showManualForm ? '▼' : '▶'}</span>
              </button>

              {showManualForm && (
                <div className="p-4 border border-slate-200 rounded-xl bg-slate-50 space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-xs font-medium text-slate-600">Data</label>
                      <input
                        type="date"
                        value={manualDate}
                        onChange={e => setManualDate(e.target.value)}
                        className="mt-1 w-full px-3 py-1.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                      />
                    </div>
                    <div>
                      <label className="text-xs font-medium text-slate-600">Conta</label>
                      <select
                        value={manualAccountId}
                        onChange={e => setManualAccountId(e.target.value ? Number(e.target.value) : '')}
                        className="mt-1 w-full px-3 py-1.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 bg-white"
                      >
                        <option value="">Selecione...</option>
                        {accounts.map(a => (
                          <option key={a.id} value={a.id}>{a.name}</option>
                        ))}
                      </select>
                    </div>
                  </div>
                  <div>
                    <label className="text-xs font-medium text-slate-600">Descrição</label>
                    <input
                      type="text"
                      value={manualDescription}
                      onChange={e => setManualDescription(e.target.value)}
                      placeholder="Ex: Uber para reunião cliente"
                      className="mt-1 w-full px-3 py-1.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                    />
                  </div>
                  <div className="flex items-end gap-3">
                    <div className="flex-1">
                      <label className="text-xs font-medium text-slate-600">Valor ({selectedAccountCurrency === 'BRL' ? 'R$' : selectedAccountCurrency})</label>
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        value={manualAmount}
                        onChange={e => setManualAmount(e.target.value)}
                        placeholder="0,00"
                        className="mt-1 w-full px-3 py-1.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                      />
                    </div>
                    <Button
                      size="sm"
                      onClick={handleCreateManualTransaction}
                      isLoading={createTransactionMutation.isPending}
                      disabled={!manualDate || !manualDescription || !manualAmount || !manualAccountId || !workExpenseCategoryId}
                    >
                      <Plus size={14} /> Criar
                    </Button>
                  </div>
                  {createTransactionMutation.isError && (
                    <p className="text-xs text-rose-600">
                      Erro ao criar transação: {(createTransactionMutation.error as Error).message}
                    </p>
                  )}
                </div>
              )}
            </div>

            {/* Transações não reportadas */}
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-slate-700">
                Transações Disponíveis ({unreported.length})
              </h3>
              <Button variant="ghost" size="sm" onClick={toggleAll}>
                {selectedIds.size === unreported.length ? (
                  <><Square size={14} /> Limpar Seleção</>
                ) : (
                  <><CheckSquare size={14} /> Selecionar Todos</>
                )}
              </Button>
            </div>

            {loadingUnreported ? (
              <p className="text-sm text-slate-500 py-8 text-center">Carregando...</p>
            ) : unreported.length === 0 ? (
              <p className="text-sm text-slate-500 py-8 text-center">
                Nenhuma transação de despesas de trabalho pendente de relatório.
              </p>
            ) : (
              <div className="border border-slate-200 rounded-xl overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-200">
                      <th className="w-10 px-3 py-2"></th>
                      <th className="px-3 py-2 text-left font-medium text-slate-600">Data</th>
                      <th className="px-3 py-2 text-left font-medium text-slate-600">Descrição</th>
                      <th className="px-3 py-2 text-left font-medium text-slate-600">Conta</th>
                      <th className="px-3 py-2 text-right font-medium text-slate-600">Valor (R$)</th>
                      <th className="px-3 py-2 text-center font-medium text-slate-600">Parcela</th>
                    </tr>
                  </thead>
                  <tbody>
                    {unreported.map(t => (
                      <tr
                        key={t.id}
                        className={`border-b border-slate-100 cursor-pointer transition-colors ${
                          selectedIds.has(t.id) ? 'bg-primary-50' : 'hover:bg-slate-50'
                        }`}
                        onClick={() => toggleTransaction(t.id)}
                      >
                        <td className="px-3 py-2 text-center">
                          <input
                            type="checkbox"
                            checked={selectedIds.has(t.id)}
                            onChange={() => toggleTransaction(t.id)}
                            className="rounded"
                            onClick={e => e.stopPropagation()}
                          />
                        </td>
                        <td className="px-3 py-2 text-slate-600 whitespace-nowrap">{formatDate(t.date)}</td>
                        <td className="px-3 py-2 text-slate-800">{t.description}</td>
                        <td className="px-3 py-2 text-slate-500 whitespace-nowrap">{t.account_name}</td>
                        <td className="px-3 py-2 text-right font-medium text-slate-800">
                          {formatCurrency(t.amount_brl)}
                        </td>
                        <td className="px-3 py-2 text-center text-slate-500">{t.installment_info || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Observações */}
            <div className="mt-4">
              <label className="text-sm font-medium text-slate-700">Observações (opcional):</label>
              <textarea
                value={notes}
                onChange={e => setNotes(e.target.value)}
                rows={2}
                className="mt-1 w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 resize-none"
                placeholder="Notas adicionais para o relatório..."
              />
            </div>

            {/* Footer fixo com total */}
            {selectedIds.size > 0 && (
              <div className="mt-4 flex items-center justify-between p-4 bg-primary-50 rounded-xl border border-primary-200">
                <div className="text-sm">
                  <span className="font-medium text-primary-700">{selectedIds.size}</span>
                  <span className="text-primary-600"> transação(ões) selecionada(s)</span>
                  <span className="mx-2 text-primary-400">|</span>
                  <span className="font-semibold text-primary-800">{formatCurrency(selectedTotal)}</span>
                </div>
                <Button
                  onClick={handleCreate}
                  isLoading={createMutation.isPending}
                  disabled={selectedIds.size === 0}
                >
                  <Plus size={16} /> Criar Relatório
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      </MainLayout>
    );
  }

  if (view === 'detail' && reportDetail) {
    const status = STATUS_CONFIG[reportDetail.status] || STATUS_CONFIG.draft;
    return (
      <MainLayout>
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <button onClick={handleBack} className="p-1.5 hover:bg-slate-100 rounded-lg transition-colors">
                  <ArrowLeft size={18} className="text-slate-500" />
                </button>
                <div>
                  <div className="flex items-center gap-2">
                    <CardTitle>Reembolso {formatMonthLabel(reportDetail.reference_month)}</CardTitle>
                    <Badge color={status.color} variant="soft">{status.label}</Badge>
                  </div>
                  {reportDetail.notes && (
                    <p className="text-xs text-slate-500 mt-1">{reportDetail.notes}</p>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2">
                {reportDetail.status === 'draft' && (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => handleRefreshReport(reportDetail.id)}
                    isLoading={updateMutation.isPending}
                    disabled={unreported.length === 0}
                    title={unreported.length === 0 ? 'Nenhuma transação nova disponível' : `Adicionar ${unreported.length} transação(ões)`}
                  >
                    <RefreshCw size={14} /> Atualizar{unreported.length > 0 ? ` (${unreported.length})` : ''}
                  </Button>
                )}
                <Button variant="secondary" size="sm" onClick={() => handleExport(reportDetail.id)}>
                  <Download size={14} /> Excel
                </Button>
                {reportDetail.status === 'draft' && (
                  <>
                    <Button variant="primary" size="sm" onClick={() => handleStatusChange(reportDetail.id, 'submitted')}>
                      <Send size={14} /> Marcar Enviado
                    </Button>
                    <Button variant="danger" size="sm" onClick={() => handleDelete(reportDetail.id)}>
                      <Trash2 size={14} />
                    </Button>
                  </>
                )}
                {reportDetail.status === 'submitted' && (
                  <>
                    <Button variant="success" size="sm" onClick={() => handleStatusChange(reportDetail.id, 'reimbursed')}>
                      <CheckCircle size={14} /> Reembolsado
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => handleStatusChange(reportDetail.id, 'draft')}>
                      <RotateCcw size={14} /> Voltar Rascunho
                    </Button>
                  </>
                )}
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="border border-slate-200 rounded-xl overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-200">
                    {reportDetail.status === 'draft' && <th className="w-10 px-3 py-2"></th>}
                    <th className="px-3 py-2 text-left font-medium text-slate-600">Data</th>
                    <th className="px-3 py-2 text-left font-medium text-slate-600">Descrição</th>
                    <th className="px-3 py-2 text-left font-medium text-slate-600">Conta</th>
                    <th className="px-3 py-2 text-right font-medium text-slate-600">Valor (R$)</th>
                    <th className="px-3 py-2 text-center font-medium text-slate-600">Moeda Orig.</th>
                    <th className="px-3 py-2 text-right font-medium text-slate-600">Valor Orig.</th>
                    <th className="px-3 py-2 text-center font-medium text-slate-600">Parcela</th>
                  </tr>
                </thead>
                <tbody>
                  {reportDetail.items.map(item => (
                    <tr key={item.transaction_id} className="border-b border-slate-100 group">
                      {reportDetail.status === 'draft' && (
                        <td className="px-3 py-2 text-center">
                          <button
                            onClick={() => handleRemoveFromReport(reportDetail.id, item.transaction_id)}
                            className="opacity-0 group-hover:opacity-100 p-1 hover:bg-rose-50 rounded transition-all"
                            title="Remover do relatório"
                          >
                            <X size={14} className="text-rose-500" />
                          </button>
                        </td>
                      )}
                      <td className="px-3 py-2 text-slate-600 whitespace-nowrap">{formatDate(item.date)}</td>
                      <td className="px-3 py-2 text-slate-800">{item.description}</td>
                      <td className="px-3 py-2 text-slate-500 whitespace-nowrap">{item.account_name}</td>
                      <td className="px-3 py-2 text-right font-medium text-slate-800">
                        {formatCurrency(item.amount_brl)}
                      </td>
                      <td className="px-3 py-2 text-center text-slate-500">{item.original_currency}</td>
                      <td className="px-3 py-2 text-right text-slate-600">
                        {item.original_currency !== 'BRL'
                          ? formatCurrency(item.original_amount, item.original_currency as 'USD' | 'EUR')
                          : '-'}
                      </td>
                      <td className="px-3 py-2 text-center text-slate-500">{item.installment_info || '-'}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="bg-slate-50 border-t border-slate-200">
                    <td colSpan={reportDetail.status === 'draft' ? 4 : 3} className="px-3 py-2 text-right font-semibold text-slate-700">TOTAL</td>
                    <td className="px-3 py-2 text-right font-bold text-slate-900">
                      {formatCurrency(reportDetail.total_brl)}
                    </td>
                    <td colSpan={3}></td>
                  </tr>
                </tfoot>
              </table>
            </div>
            <p className="text-xs text-slate-400 mt-3">
              {reportDetail.item_count} transação(ões) — Criado em {formatDate(reportDetail.created_at)}
            </p>

            {/* Adicionar transações ao rascunho */}
            {reportDetail.status === 'draft' && (
              <div className="mt-6">
                <button
                  onClick={() => { setShowAddPanel(!showAddPanel); setAddIds(new Set()); }}
                  className="flex items-center gap-2 text-sm font-medium text-primary-600 hover:text-primary-800"
                >
                  <Plus size={16} />
                  Adicionar Transações
                  <span className="text-xs text-slate-400">{showAddPanel ? '▼' : '▶'}</span>
                </button>

                {showAddPanel && (
                  <div className="mt-3">
                    {/* Criar transação manual */}
                    <button
                      onClick={() => setShowManualForm(!showManualForm)}
                      className="flex items-center gap-2 text-sm font-medium text-primary-600 hover:text-primary-800 mb-3"
                    >
                      <PlusCircle size={16} />
                      Criar Nova Transação Manual
                      <span className="text-xs text-slate-400">{showManualForm ? '▼' : '▶'}</span>
                    </button>

                    {showManualForm && (
                      <div className="p-4 border border-slate-200 rounded-xl bg-slate-50 space-y-3 mb-4">
                        <div className="grid grid-cols-2 gap-3">
                          <div>
                            <label className="text-xs font-medium text-slate-600">Data</label>
                            <input
                              type="date"
                              value={manualDate}
                              onChange={e => setManualDate(e.target.value)}
                              className="mt-1 w-full px-3 py-1.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                            />
                          </div>
                          <div>
                            <label className="text-xs font-medium text-slate-600">Conta</label>
                            <select
                              value={manualAccountId}
                              onChange={e => setManualAccountId(e.target.value ? Number(e.target.value) : '')}
                              className="mt-1 w-full px-3 py-1.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 bg-white"
                            >
                              <option value="">Selecione...</option>
                              {accounts.map(a => (
                                <option key={a.id} value={a.id}>{a.name}</option>
                              ))}
                            </select>
                          </div>
                        </div>
                        <div>
                          <label className="text-xs font-medium text-slate-600">Descrição</label>
                          <input
                            type="text"
                            value={manualDescription}
                            onChange={e => setManualDescription(e.target.value)}
                            placeholder="Ex: Uber para reunião cliente"
                            className="mt-1 w-full px-3 py-1.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                          />
                        </div>
                        <div className="flex items-end gap-3">
                          <div className="flex-1">
                            <label className="text-xs font-medium text-slate-600">Valor ({selectedAccountCurrency === 'BRL' ? 'R$' : selectedAccountCurrency})</label>
                            <input
                              type="number"
                              step="0.01"
                              min="0"
                              value={manualAmount}
                              onChange={e => setManualAmount(e.target.value)}
                              placeholder="0,00"
                              className="mt-1 w-full px-3 py-1.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                            />
                          </div>
                          <Button
                            size="sm"
                            onClick={handleCreateManualTransaction}
                            isLoading={createTransactionMutation.isPending}
                            disabled={!manualDate || !manualDescription || !manualAmount || !manualAccountId || !workExpenseCategoryId}
                          >
                            <Plus size={14} /> Criar
                          </Button>
                        </div>
                        {createTransactionMutation.isError && (
                          <p className="text-xs text-rose-600">
                            Erro ao criar transação: {(createTransactionMutation.error as Error).message}
                          </p>
                        )}
                      </div>
                    )}

                    {/* Transações existentes não reportadas */}
                    {loadingUnreported ? (
                      <p className="text-sm text-slate-500 py-4 text-center">Carregando...</p>
                    ) : unreported.length === 0 ? (
                      <p className="text-sm text-slate-500 py-4 text-center">
                        Nenhuma transação disponível para adicionar.
                      </p>
                    ) : (
                      <>
                        <div className="border border-slate-200 rounded-xl overflow-hidden">
                          <table className="w-full text-sm">
                            <thead>
                              <tr className="bg-slate-50 border-b border-slate-200">
                                <th className="w-10 px-3 py-2"></th>
                                <th className="px-3 py-2 text-left font-medium text-slate-600">Data</th>
                                <th className="px-3 py-2 text-left font-medium text-slate-600">Descrição</th>
                                <th className="px-3 py-2 text-left font-medium text-slate-600">Conta</th>
                                <th className="px-3 py-2 text-right font-medium text-slate-600">Valor (R$)</th>
                                <th className="px-3 py-2 text-center font-medium text-slate-600">Parcela</th>
                              </tr>
                            </thead>
                            <tbody>
                              {unreported.map(t => (
                                <tr
                                  key={t.id}
                                  className={`border-b border-slate-100 cursor-pointer transition-colors ${
                                    addIds.has(t.id) ? 'bg-primary-50' : 'hover:bg-slate-50'
                                  }`}
                                  onClick={() => toggleAddId(t.id)}
                                >
                                  <td className="px-3 py-2 text-center">
                                    <input
                                      type="checkbox"
                                      checked={addIds.has(t.id)}
                                      onChange={() => toggleAddId(t.id)}
                                      className="rounded"
                                      onClick={e => e.stopPropagation()}
                                    />
                                  </td>
                                  <td className="px-3 py-2 text-slate-600 whitespace-nowrap">{formatDate(t.date)}</td>
                                  <td className="px-3 py-2 text-slate-800">{t.description}</td>
                                  <td className="px-3 py-2 text-slate-500 whitespace-nowrap">{t.account_name}</td>
                                  <td className="px-3 py-2 text-right font-medium text-slate-800">
                                    {formatCurrency(t.amount_brl)}
                                  </td>
                                  <td className="px-3 py-2 text-center text-slate-500">{t.installment_info || '-'}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                        {addIds.size > 0 && (
                          <div className="mt-3 flex items-center justify-between p-3 bg-primary-50 rounded-xl border border-primary-200">
                            <span className="text-sm text-primary-700">
                              <span className="font-medium">{addIds.size}</span> transação(ões) para adicionar
                            </span>
                            <Button
                              size="sm"
                              onClick={() => handleAddToReport(reportDetail.id)}
                              isLoading={updateMutation.isPending}
                            >
                              <Plus size={14} /> Adicionar ao Relatório
                            </Button>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </MainLayout>
    );
  }

  // ===== LIST VIEW =====
  return (
    <MainLayout>
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Relatórios de Reembolso</CardTitle>
            <Button onClick={handleNewReport}>
              <Plus size={16} /> Novo Relatório
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {loadingReports ? (
            <p className="text-sm text-slate-500 py-8 text-center">Carregando...</p>
          ) : reports.length === 0 ? (
            <p className="text-sm text-slate-500 py-8 text-center">
              Nenhum relatório de reembolso criado. Clique em &quot;Novo Relatório&quot; para começar.
            </p>
          ) : (
            <div className="border border-slate-200 rounded-xl overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-200">
                    <th className="px-4 py-2.5 text-left font-medium text-slate-600">Mês Referência</th>
                    <th className="px-4 py-2.5 text-left font-medium text-slate-600">Status</th>
                    <th className="px-4 py-2.5 text-center font-medium text-slate-600">Itens</th>
                    <th className="px-4 py-2.5 text-right font-medium text-slate-600">Total (R$)</th>
                    <th className="px-4 py-2.5 text-left font-medium text-slate-600">Criado em</th>
                    <th className="w-10 px-4 py-2.5"></th>
                  </tr>
                </thead>
                <tbody>
                  {reports.map(r => {
                    const status = STATUS_CONFIG[r.status] || STATUS_CONFIG.draft;
                    return (
                      <tr
                        key={r.id}
                        className="border-b border-slate-100 hover:bg-slate-50 cursor-pointer transition-colors group"
                        onClick={() => handleOpenReport(r.id)}
                      >
                        <td className="px-4 py-3 font-medium text-slate-800">
                          {formatMonthLabel(r.reference_month)}
                        </td>
                        <td className="px-4 py-3">
                          <Badge color={status.color} variant="soft" dot>{status.label}</Badge>
                        </td>
                        <td className="px-4 py-3 text-center text-slate-600">{r.item_count}</td>
                        <td className="px-4 py-3 text-right font-medium text-slate-800">
                          {formatCurrency(r.total_brl)}
                        </td>
                        <td className="px-4 py-3 text-slate-500">{formatDate(r.created_at)}</td>
                        <td className="px-4 py-3 text-center">
                          {r.status === 'draft' && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleDelete(r.id);
                              }}
                              className="opacity-0 group-hover:opacity-100 p-1 hover:bg-rose-50 rounded transition-all"
                              title="Excluir relatório"
                            >
                              <Trash2 size={14} className="text-rose-500" />
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </MainLayout>
  );
}
