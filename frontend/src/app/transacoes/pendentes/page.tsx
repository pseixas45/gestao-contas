'use client';

import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import MainLayout from '@/components/layout/MainLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import Button from '@/components/ui/Button';
import { transactionsApi, categoriesApi, accountsApi } from '@/lib/api';
import { formatCurrency, formatDate } from '@/lib/utils';
import { Transaction, Category, TransactionSuggestion } from '@/types';
import {
  Check,
  ChevronDown,
  ChevronRight,
  Layers,
  Filter,
  Zap,
  Tag,
  AlertCircle,
  Sparkles,
} from 'lucide-react';

// Normalizar descrição para agrupar transações similares
function normalizeDescription(desc: string): string {
  return desc
    .toLowerCase()
    .replace(/\d{2}\/\d{2}/g, '') // datas
    .replace(/\d{2}:\d{2}/g, '') // horários
    .replace(/\*+/g, '')         // asteriscos
    .replace(/\d{4,}/g, '')      // números longos
    .replace(/\s+/g, ' ')
    .trim();
}

interface TransactionGroup {
  key: string;
  normalizedDesc: string;
  transactions: Transaction[];
  totalAmount: number;
  suggestion: TransactionSuggestion | null;
}

export default function PendentesPage() {
  const queryClient = useQueryClient();
  const [filterAccountId, setFilterAccountId] = useState<number | undefined>(undefined);
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const [selectedGroupKey, setSelectedGroupKey] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'grouped' | 'flat'>('grouped');

  // Buscar transações pendentes
  const { data: transactions = [], isLoading } = useQuery({
    queryKey: ['transactions', 'pending', filterAccountId],
    queryFn: () => transactionsApi.getPending(filterAccountId),
  });

  // Buscar categorias
  const { data: categories = [] } = useQuery({
    queryKey: ['categories', 'flat'],
    queryFn: () => categoriesApi.list(true, true),
  });

  // Buscar contas para filtro
  const { data: accounts = [] } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
  });

  // Buscar sugestões para as primeiras transações de cada grupo
  const firstTransactionIds = useMemo(() => {
    if (viewMode !== 'grouped') return [];
    const groups = new Map<string, number>();
    transactions.forEach((t) => {
      const key = normalizeDescription(t.description);
      if (!groups.has(key)) groups.set(key, t.id);
    });
    return Array.from(groups.values()).slice(0, 20); // Limitar a 20
  }, [transactions, viewMode]);

  const { data: suggestions = {} } = useQuery({
    queryKey: ['suggestions', firstTransactionIds],
    queryFn: async () => {
      const results: Record<number, TransactionSuggestion> = {};
      await Promise.allSettled(
        firstTransactionIds.map(async (id) => {
          try {
            const s = await transactionsApi.getSuggestion(id);
            if (s && s.suggested_category_id) results[id] = s;
          } catch {}
        })
      );
      return results;
    },
    enabled: firstTransactionIds.length > 0,
    staleTime: 60000,
  });

  // Agrupar transações por descrição normalizada
  const groups = useMemo((): TransactionGroup[] => {
    const groupMap = new Map<string, Transaction[]>();
    transactions.forEach((t) => {
      const key = normalizeDescription(t.description);
      if (!groupMap.has(key)) groupMap.set(key, []);
      groupMap.get(key)!.push(t);
    });

    return Array.from(groupMap.entries())
      .map(([key, txns]) => {
        const firstId = txns[0].id;
        return {
          key,
          normalizedDesc: txns[0].description,
          transactions: txns,
          totalAmount: txns.reduce((sum, t) => sum + Number(t.amount_brl), 0),
          suggestion: suggestions[firstId] || null,
        };
      })
      .sort((a, b) => b.transactions.length - a.transactions.length);
  }, [transactions, suggestions]);

  // Atualizar categoria (single)
  const updateCategoryMutation = useMutation({
    mutationFn: ({ id, categoryId, createRule }: { id: number; categoryId: number; createRule: boolean }) =>
      transactionsApi.updateCategory(id, categoryId, createRule),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['transactions'] });
    },
  });

  // Bulk categorize
  const bulkCategorizeMutation = useMutation({
    mutationFn: ({ ids, categoryId }: { ids: number[]; categoryId: number }) =>
      transactionsApi.bulkCategorize(ids, categoryId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['transactions'] });
      setSelectedGroupKey(null);
    },
  });

  const handleCategorize = (transactionId: number, categoryId: number, createRule = false) => {
    updateCategoryMutation.mutate({ id: transactionId, categoryId, createRule });
  };

  const handleBulkCategorize = (group: TransactionGroup, categoryId: number) => {
    const ids = group.transactions.map((t) => t.id);
    bulkCategorizeMutation.mutate({ ids, categoryId });
  };

  const toggleGroup = (key: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  // Categorias por tipo
  const expenseCategories = categories.filter((c) => c.type === 'expense');
  const incomeCategories = categories.filter((c) => c.type === 'income');
  const transferCategories = categories.filter((c) => c.type === 'transfer');

  // Top 5 categorias mais usadas (baseado no que existe)
  const topCategories = useMemo(() => {
    const allCats = [...expenseCategories, ...incomeCategories, ...transferCategories];
    return allCats.slice(0, 8);
  }, [expenseCategories, incomeCategories, transferCategories]);

  const confidenceBadge = (confidence: number) => {
    if (confidence >= 0.9) return <span className="text-xs px-1.5 py-0.5 rounded-full bg-emerald-100 text-emerald-700">{Math.round(confidence * 100)}%</span>;
    if (confidence >= 0.7) return <span className="text-xs px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700">{Math.round(confidence * 100)}%</span>;
    return <span className="text-xs px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-600">{Math.round(confidence * 100)}%</span>;
  };

  return (
    <MainLayout>
      <div className="space-y-6">
        {/* Cabeçalho */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-slate-800">Transações Pendentes</h1>
            <p className="text-slate-500">
              {transactions.length} transação(ões) aguardando categorização
              {viewMode === 'grouped' && groups.length > 0 && (
                <span className="ml-1">({groups.length} grupo(s))</span>
              )}
            </p>
          </div>

          <div className="flex items-center gap-3">
            {/* Filtro por conta */}
            <select
              value={filterAccountId || ''}
              onChange={(e) => setFilterAccountId(e.target.value ? parseInt(e.target.value) : undefined)}
              className="px-3 py-2 text-sm rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400"
            >
              <option value="">Todas as contas</option>
              {accounts.map((acc) => (
                <option key={acc.id} value={acc.id}>{acc.name}</option>
              ))}
            </select>

            {/* Toggle modo de visualização */}
            <div className="flex rounded-xl border border-slate-200 overflow-hidden">
              <button
                onClick={() => setViewMode('grouped')}
                className={`px-3 py-2 text-sm flex items-center gap-1.5 transition-colors ${
                  viewMode === 'grouped'
                    ? 'bg-indigo-50 text-indigo-700 font-medium'
                    : 'bg-white text-slate-500 hover:bg-slate-50'
                }`}
              >
                <Layers size={14} /> Agrupado
              </button>
              <button
                onClick={() => setViewMode('flat')}
                className={`px-3 py-2 text-sm flex items-center gap-1.5 transition-colors ${
                  viewMode === 'flat'
                    ? 'bg-indigo-50 text-indigo-700 font-medium'
                    : 'bg-white text-slate-500 hover:bg-slate-50'
                }`}
              >
                <Filter size={14} /> Lista
              </button>
            </div>
          </div>
        </div>

        {/* Estado vazio */}
        {isLoading ? (
          <div className="space-y-4">
            {[1, 2, 3].map((i) => (
              <Card key={i}>
                <CardContent className="py-6">
                  <div className="animate-pulse flex gap-4">
                    <div className="flex-1 space-y-3">
                      <div className="h-4 bg-slate-200 rounded w-1/4"></div>
                      <div className="h-5 bg-slate-200 rounded w-3/4"></div>
                    </div>
                    <div className="h-8 bg-slate-200 rounded w-24"></div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        ) : transactions.length === 0 ? (
          <Card>
            <CardContent className="py-16 text-center">
              <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-emerald-100 flex items-center justify-center">
                <Check size={32} className="text-emerald-600" />
              </div>
              <h3 className="text-lg font-semibold text-slate-800">Tudo categorizado!</h3>
              <p className="text-slate-500 mt-1">Não há transações pendentes no momento.</p>
            </CardContent>
          </Card>
        ) : viewMode === 'grouped' ? (
          /* ═══ MODO AGRUPADO ═══ */
          <div className="space-y-3">
            {groups.map((group) => {
              const isExpanded = expandedGroups.has(group.key);
              const isMultiple = group.transactions.length > 1;
              const firstTx = group.transactions[0];
              const isNegative = group.totalAmount < 0;

              return (
                <Card key={group.key} className="overflow-hidden">
                  {/* Header do grupo */}
                  <div
                    className={`px-5 py-4 flex items-center gap-4 cursor-pointer hover:bg-slate-50/80 transition-colors ${
                      isMultiple ? '' : ''
                    }`}
                    onClick={() => isMultiple && toggleGroup(group.key)}
                  >
                    {/* Expand icon (apenas para grupos) */}
                    {isMultiple ? (
                      <div className="text-slate-400">
                        {isExpanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                      </div>
                    ) : (
                      <div className="w-[18px]" />
                    )}

                    {/* Info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <p className="font-medium text-slate-800 truncate">{firstTx.description}</p>
                        {isMultiple && (
                          <span className="flex-shrink-0 text-xs px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-700 font-medium">
                            {group.transactions.length}x
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-3 text-xs text-slate-400">
                        <span>{firstTx.account_name}</span>
                        {isMultiple ? (
                          <span>
                            {formatDate(group.transactions[group.transactions.length - 1].date)} — {formatDate(firstTx.date)}
                          </span>
                        ) : (
                          <span>{formatDate(firstTx.date)}</span>
                        )}
                      </div>
                    </div>

                    {/* Valor */}
                    <div className="text-right flex-shrink-0">
                      <p className={`text-lg font-bold ${isNegative ? 'text-rose-600' : 'text-emerald-600'}`}>
                        {isMultiple
                          ? formatCurrency(group.totalAmount, 'BRL')
                          : formatCurrency(Number(firstTx.original_amount), firstTx.original_currency as 'BRL' | 'USD' | 'EUR')}
                      </p>
                      {isMultiple && (
                        <p className="text-xs text-slate-400">
                          média {formatCurrency(group.totalAmount / group.transactions.length, 'BRL')}
                        </p>
                      )}
                    </div>

                    {/* Sugestão de categoria (se houver) */}
                    {group.suggestion && (
                      <div className="flex-shrink-0 flex items-center gap-2">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            if (isMultiple) {
                              handleBulkCategorize(group, group.suggestion!.suggested_category_id!);
                            } else {
                              handleCategorize(firstTx.id, group.suggestion!.suggested_category_id!, true);
                            }
                          }}
                          className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-xl bg-violet-50 text-violet-700 hover:bg-violet-100 border border-violet-200 transition-colors"
                        >
                          <Sparkles size={14} />
                          {group.suggestion.suggested_category_name}
                          {confidenceBadge(group.suggestion.confidence)}
                        </button>
                      </div>
                    )}
                  </div>

                  {/* Botões de categorização rápida */}
                  <div className="px-5 py-3 bg-slate-50/50 border-t border-slate-100 flex flex-wrap gap-2">
                    {(isNegative ? expenseCategories : incomeCategories)
                      .slice(0, 8)
                      .map((cat) => (
                        <button
                          key={cat.id}
                          onClick={() => {
                            if (isMultiple) {
                              handleBulkCategorize(group, cat.id);
                            } else {
                              handleCategorize(firstTx.id, cat.id, true);
                            }
                          }}
                          className="px-3 py-1.5 text-xs rounded-xl border border-slate-200 bg-white hover:border-indigo-400 hover:bg-indigo-50 hover:text-indigo-700 transition-all"
                          style={{
                            borderLeftColor: cat.color,
                            borderLeftWidth: '3px',
                          }}
                        >
                          {cat.name}
                        </button>
                      ))}

                    {/* Dropdown para mais categorias */}
                    <select
                      onChange={(e) => {
                        if (e.target.value) {
                          const catId = parseInt(e.target.value);
                          if (isMultiple) {
                            handleBulkCategorize(group, catId);
                          } else {
                            handleCategorize(firstTx.id, catId, true);
                          }
                          e.target.value = '';
                        }
                      }}
                      className="px-3 py-1.5 text-xs rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
                    >
                      <option value="">Mais...</option>
                      <optgroup label="Despesas">
                        {expenseCategories.map((cat) => (
                          <option key={cat.id} value={cat.id}>{cat.name}</option>
                        ))}
                      </optgroup>
                      <optgroup label="Receitas">
                        {incomeCategories.map((cat) => (
                          <option key={cat.id} value={cat.id}>{cat.name}</option>
                        ))}
                      </optgroup>
                      <optgroup label="Transferências">
                        {transferCategories.map((cat) => (
                          <option key={cat.id} value={cat.id}>{cat.name}</option>
                        ))}
                      </optgroup>
                    </select>

                    {isMultiple && (
                      <span className="flex items-center text-xs text-slate-400 ml-2">
                        <Zap size={12} className="mr-1" />
                        Categoriza todas {group.transactions.length} de uma vez
                      </span>
                    )}
                  </div>

                  {/* Lista expandida de transações do grupo */}
                  {isExpanded && isMultiple && (
                    <div className="border-t border-slate-100">
                      {group.transactions.map((t, idx) => (
                        <div
                          key={t.id}
                          className={`px-5 py-3 flex items-center gap-4 text-sm ${
                            idx % 2 === 0 ? 'bg-white' : 'bg-slate-50/30'
                          }`}
                        >
                          <div className="w-[18px]" />
                          <span className="text-slate-400 w-20 flex-shrink-0">{formatDate(t.date)}</span>
                          <span className="flex-1 text-slate-600 truncate">{t.description}</span>
                          <span className="text-slate-400 text-xs flex-shrink-0">{t.account_name}</span>
                          <span
                            className={`font-medium flex-shrink-0 ${
                              Number(t.original_amount) < 0 ? 'text-rose-600' : 'text-emerald-600'
                            }`}
                          >
                            {formatCurrency(Number(t.original_amount), t.original_currency as 'BRL' | 'USD' | 'EUR')}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </Card>
              );
            })}
          </div>
        ) : (
          /* ═══ MODO LISTA FLAT ═══ */
          <div className="space-y-3">
            {transactions.map((transaction) => (
              <Card key={transaction.id}>
                <CardContent className="py-4">
                  <div className="flex flex-col lg:flex-row lg:items-center gap-4">
                    {/* Info da transação */}
                    <div className="flex-1">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs text-slate-400">
                          {formatDate(transaction.date)} — {transaction.account_name}
                        </span>
                        <span
                          className={`text-lg font-bold ${
                            Number(transaction.original_amount) >= 0 ? 'text-emerald-600' : 'text-rose-600'
                          }`}
                        >
                          {formatCurrency(Number(transaction.original_amount), transaction.original_currency as 'BRL' | 'USD' | 'EUR')}
                        </span>
                      </div>
                      <p className="font-medium text-slate-800">{transaction.description}</p>
                    </div>

                    {/* Seletor de categoria */}
                    <div className="flex flex-wrap gap-2">
                      {(Number(transaction.amount) < 0 ? expenseCategories : incomeCategories)
                        .slice(0, 6)
                        .map((cat) => (
                          <button
                            key={cat.id}
                            onClick={() => handleCategorize(transaction.id, cat.id, true)}
                            className="px-3 py-1.5 text-xs rounded-xl border border-slate-200 bg-white hover:border-indigo-400 hover:bg-indigo-50 hover:text-indigo-700 transition-all"
                            style={{
                              borderLeftColor: cat.color,
                              borderLeftWidth: '3px',
                            }}
                          >
                            {cat.name}
                          </button>
                        ))}

                      <select
                        onChange={(e) => {
                          if (e.target.value) {
                            handleCategorize(transaction.id, parseInt(e.target.value), true);
                            e.target.value = '';
                          }
                        }}
                        className="px-3 py-1.5 text-xs rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
                      >
                        <option value="">Mais...</option>
                        <optgroup label="Despesas">
                          {expenseCategories.map((cat) => (
                            <option key={cat.id} value={cat.id}>{cat.name}</option>
                          ))}
                        </optgroup>
                        <optgroup label="Receitas">
                          {incomeCategories.map((cat) => (
                            <option key={cat.id} value={cat.id}>{cat.name}</option>
                          ))}
                        </optgroup>
                        <optgroup label="Transferências">
                          {transferCategories.map((cat) => (
                            <option key={cat.id} value={cat.id}>{cat.name}</option>
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
