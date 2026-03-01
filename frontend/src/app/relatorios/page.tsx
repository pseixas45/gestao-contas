'use client';

import { useState, useEffect, useMemo, useCallback, Fragment } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import MainLayout from '@/components/layout/MainLayout';
import { Card, CardContent } from '@/components/ui/Card';
import Select from '@/components/ui/Select';
import Input from '@/components/ui/Input';
import { reportsApi, accountsApi, categoriesApi } from '@/lib/api';
import type { PivotReport, SavedReportView, TransactionDetail } from '@/lib/api';
import { formatCurrency, formatDate } from '@/lib/utils';
import { Download, Save, FolderOpen, Trash2, FileSpreadsheet, ChevronRight, ChevronDown, Loader2 } from 'lucide-react';
import Button from '@/components/ui/Button';

const MONTH_NAMES: Record<string, string> = {
  '01': 'Jan', '02': 'Fev', '03': 'Mar', '04': 'Abr',
  '05': 'Mai', '06': 'Jun', '07': 'Jul', '08': 'Ago',
  '09': 'Set', '10': 'Out', '11': 'Nov', '12': 'Dez',
};

function formatMonth(ym: string): string {
  const [year, month] = ym.split('-');
  return `${MONTH_NAMES[month]}/${year.slice(2)}`;
}

function fmtCsv(val: number): string {
  return val.toFixed(2).replace('.', ',');
}

function txMonth(dateStr: string): string {
  return dateStr.slice(0, 7); // "2025-07-15" → "2025-07"
}

interface Filters {
  start_month: string;
  end_month: string;
  currency: string;
  account_ids: number[];
  category_ids: number[];
}

export default function RelatoriosPage() {
  const queryClient = useQueryClient();
  const now = new Date();
  const currentMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  const defaultStart = `${now.getFullYear() - 1}-${String(now.getMonth() + 1).padStart(2, '0')}`;

  const [filters, setFilters] = useState<Filters>({
    start_month: defaultStart,
    end_month: currentMonth,
    currency: 'BRL',
    account_ids: [],
    category_ids: [],
  });

  const [saveName, setSaveName] = useState('');
  const [showSaveInput, setShowSaveInput] = useState(false);
  const [showLoadMenu, setShowLoadMenu] = useState(false);
  const [exportingDetailed, setExportingDetailed] = useState(false);

  // Drill-down state: expanded categories and their loaded transactions
  const [expandedCategories, setExpandedCategories] = useState<Set<number>>(new Set());
  const [categoryTransactions, setCategoryTransactions] = useState<Record<number, TransactionDetail[]>>({});
  const [loadingCategory, setLoadingCategory] = useState<number | null>(null);

  // Fetch accounts
  const { data: accounts = [] } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(false),
  });

  // Fetch categories
  const { data: categories = [] } = useQuery({
    queryKey: ['categories', 'flat'],
    queryFn: () => categoriesApi.list(true, true),
  });

  // Fetch saved views
  const { data: savedViews = [] } = useQuery({
    queryKey: ['saved-report-views'],
    queryFn: () => reportsApi.listSavedViews(),
  });

  const allFilterableCategories = categories.filter((c) => c.type === 'expense' || c.type === 'income' || c.type === 'transfer');

  // Build query params
  const queryParams = useMemo(() => {
    const params: {
      start_month: string;
      end_month: string;
      currency?: string;
      account_ids?: string;
      category_ids?: string;
    } = {
      start_month: filters.start_month,
      end_month: filters.end_month,
      currency: filters.currency,
    };
    if (filters.account_ids.length > 0) params.account_ids = filters.account_ids.join(',');
    if (filters.category_ids.length > 0) params.category_ids = filters.category_ids.join(',');
    return params;
  }, [filters]);

  // Fetch report
  const { data: report, isLoading } = useQuery({
    queryKey: ['report', 'category-monthly-pivot', queryParams],
    queryFn: () => reportsApi.categoryMonthlyPivot(queryParams),
    enabled: !!filters.start_month && !!filters.end_month,
  });

  const currencyCode = (filters.currency || 'BRL') as 'BRL' | 'USD' | 'EUR';
  const amountField = filters.currency === 'USD' ? 'amount_usd' : filters.currency === 'EUR' ? 'amount_eur' : 'amount_brl';

  // --- Drill-down ---
  const handleToggleCategory = useCallback(async (categoryId: number) => {
    if (expandedCategories.has(categoryId)) {
      setExpandedCategories((prev) => {
        const next = new Set(prev);
        next.delete(categoryId);
        return next;
      });
      return;
    }

    // Load transactions for this category if not cached
    if (!categoryTransactions[categoryId]) {
      setLoadingCategory(categoryId);
      try {
        const txParams = { ...queryParams, category_ids: String(categoryId) };
        const details = await reportsApi.transactionDetails(txParams);
        setCategoryTransactions((prev) => ({ ...prev, [categoryId]: details }));
      } finally {
        setLoadingCategory(null);
      }
    }

    setExpandedCategories((prev) => new Set(prev).add(categoryId));
  }, [expandedCategories, categoryTransactions, queryParams]);

  // Reset drill-down cache when filters change
  useEffect(() => {
    setExpandedCategories(new Set());
    setCategoryTransactions({});
  }, [queryParams]);

  // --- Save/Load views ---
  const saveMutation = useMutation({
    mutationFn: (data: SavedReportView) => reportsApi.createSavedView(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['saved-report-views'] });
      setShowSaveInput(false);
      setSaveName('');
    },
  });

  const deleteSavedMutation = useMutation({
    mutationFn: (id: number) => reportsApi.deleteSavedView(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['saved-report-views'] }),
  });

  const handleSaveView = () => {
    if (!saveName.trim()) return;
    saveMutation.mutate({
      name: saveName.trim(),
      filters_json: JSON.stringify(filters),
    });
  };

  const handleLoadView = (view: SavedReportView) => {
    try {
      const parsed = JSON.parse(view.filters_json);
      // Backward compat: old views may have account_ids as string
      if (typeof parsed.account_ids === 'string') {
        parsed.account_ids = parsed.account_ids ? parsed.account_ids.split(',').map(Number) : [];
      }
      setFilters(parsed as Filters);
      setShowLoadMenu(false);
    } catch {}
  };

  // --- Toggles ---
  const handleCategoryToggle = (catId: number) => {
    setFilters((prev) => {
      const ids = prev.category_ids.includes(catId)
        ? prev.category_ids.filter((id) => id !== catId)
        : [...prev.category_ids, catId];
      return { ...prev, category_ids: ids };
    });
  };

  const handleAccountToggle = (accId: number) => {
    setFilters((prev) => {
      const ids = prev.account_ids.includes(accId)
        ? prev.account_ids.filter((id) => id !== accId)
        : [...prev.account_ids, accId];
      return { ...prev, account_ids: ids };
    });
  };

  // --- CSV Export (aggregated) ---
  const handleExportCSV = () => {
    if (!report) return;
    const sep = ';';
    const header = ['Tipo', 'Categoria', ...report.months.map(formatMonth), 'Total'].join(sep);
    const lines: string[] = [header];

    const addGroupRows = (label: string, rows: PivotReport['expense_rows'], totals: PivotReport['expense_totals']) => {
      for (const row of rows) {
        const vals = report.months.map((m) => fmtCsv(Number(row.values[m] || 0)));
        lines.push([label, row.category_name, ...vals, fmtCsv(Number(row.total))].join(sep));
      }
      const totVals = report.months.map((m) => fmtCsv(Number(totals.values[m] || 0)));
      lines.push([`TOTAL ${label}`, '', ...totVals, fmtCsv(Number(totals.total))].join(sep));
    };

    addGroupRows('Despesa', report.expense_rows, report.expense_totals);
    addGroupRows('Receita', report.income_rows, report.income_totals);
    if (report.transfer_rows.length > 0) {
      addGroupRows('Transferência', report.transfer_rows, report.transfer_totals);
    }

    const netVals = report.months.map((m) => fmtCsv(Number(report.column_totals[m] || 0)));
    lines.push(['SALDO (Despesa - Receita)', '', ...netVals, fmtCsv(Number(report.grand_total))].join(sep));

    downloadCSV(lines.join('\n'), `relatorio_${filters.start_month}_${filters.end_month}.csv`);
  };

  // --- CSV Export (detailed transactions) ---
  const handleExportDetailed = async () => {
    setExportingDetailed(true);
    try {
      const details = await reportsApi.transactionDetails(queryParams);
      const sep = ';';
      const header = ['Data', 'Descrição', 'Categoria', 'Tipo', 'Conta', 'Valor Original', 'Moeda', `Valor ${filters.currency}`].join(sep);
      const lines = [header];
      for (const t of details) {
        lines.push([
          t.date,
          `"${(t.description || '').replace(/"/g, '""')}"`,
          t.category_name || '',
          t.category_type || '',
          t.account_name || '',
          fmtCsv(Number(t.original_amount)),
          t.original_currency,
          fmtCsv(Number(t[amountField as keyof typeof t] as number)),
        ].join(sep));
      }
      downloadCSV(lines.join('\n'), `lancamentos_${filters.start_month}_${filters.end_month}.csv`);
    } finally {
      setExportingDetailed(false);
    }
  };

  function downloadCSV(content: string, filename: string) {
    const blob = new Blob(['\uFEFF' + content], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  // Month options
  const monthOptions = useMemo(() => {
    const options = [];
    for (let y = 2024; y <= now.getFullYear() + 1; y++) {
      for (let m = 1; m <= 12; m++) {
        const val = `${y}-${String(m).padStart(2, '0')}`;
        options.push({ value: val, label: formatMonth(val) });
      }
    }
    return options;
  }, []);

  const currencyOptions = [
    { value: 'BRL', label: 'R$ - Real' },
    { value: 'USD', label: '$ - Dólar' },
    { value: 'EUR', label: '€ - Euro' },
  ];

  const hasData = report && (report.expense_rows.length > 0 || report.income_rows.length > 0 || report.transfer_rows.length > 0);

  // --- Render transaction drill-down rows ---
  const renderTransactionRows = (categoryId: number) => {
    const txs = categoryTransactions[categoryId];
    if (!txs || txs.length === 0) {
      return (
        <tr>
          <td colSpan={(report?.months.length || 0) + 2} className="px-4 py-2 pl-12 text-sm text-gray-400 italic">
            Nenhuma transação encontrada
          </td>
        </tr>
      );
    }

    return txs.map((tx, idx) => {
      const month = txMonth(tx.date);
      const val = Number(tx[amountField as keyof typeof tx] as number);
      return (
        <tr key={`tx-${categoryId}-${idx}`} className="bg-gray-50/50 hover:bg-gray-100/50">
          <td className="px-4 py-1.5 pl-12 sticky left-0 bg-gray-50/80 z-10">
            <div className="flex items-center gap-2 text-xs text-gray-600">
              <span className="text-gray-400 w-[70px] flex-shrink-0">{formatDate(tx.date)}</span>
              <span className="truncate" title={tx.description}>{tx.description}</span>
              {tx.account_name && (
                <span className="text-gray-400 flex-shrink-0">({tx.account_name})</span>
              )}
            </div>
          </td>
          {report!.months.map((m) => (
            <td key={m} className={`px-3 py-1.5 text-right text-xs ${m === month && val > 0 ? 'text-green-600' : 'text-gray-500'}`}>
              {m === month ? formatCurrency(val, currencyCode) : ''}
            </td>
          ))}
          <td className={`px-4 py-1.5 text-right text-xs font-medium bg-gray-50 ${val > 0 ? 'text-green-600' : 'text-gray-600'}`}>
            {formatCurrency(val, currencyCode)}
          </td>
        </tr>
      );
    });
  };

  // --- Render group rows with drill-down ---
  const renderGroupRows = (
    rows: PivotReport['expense_rows'],
    totals: PivotReport['expense_totals'],
    label: string,
    colorClass: string,
    bgClass: string,
  ) => {
    if (rows.length === 0) return null;
    return (
      <>
        {/* Group header */}
        <tr className={bgClass}>
          <td colSpan={(report?.months.length || 0) + 2} className={`px-4 py-2 font-bold ${colorClass} sticky left-0 z-10 ${bgClass}`}>
            {label}
          </td>
        </tr>
        {/* Category rows */}
        {rows.map((row) => {
          const isExpanded = expandedCategories.has(row.category_id);
          const isLoadingThis = loadingCategory === row.category_id;
          return (
            <Fragment key={row.category_id}>
              <tr
                className="hover:bg-gray-50 cursor-pointer"
                onClick={() => handleToggleCategory(row.category_id)}
              >
                <td className="px-4 py-2 pl-6 sticky left-0 bg-white z-10">
                  <div className="flex items-center gap-1.5">
                    {isLoadingThis ? (
                      <Loader2 size={14} className="animate-spin text-gray-400 flex-shrink-0" />
                    ) : isExpanded ? (
                      <ChevronDown size={14} className="text-gray-400 flex-shrink-0" />
                    ) : (
                      <ChevronRight size={14} className="text-gray-400 flex-shrink-0" />
                    )}
                    {row.category_color && (
                      <span className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: row.category_color }} />
                    )}
                    <span className="text-gray-800">{row.category_name}</span>
                  </div>
                </td>
                {report!.months.map((m) => {
                  const val = Number(row.values[m] || 0);
                  return (
                    <td key={m} className={`px-3 py-2 text-right ${val > 0 ? 'text-green-700' : 'text-gray-700'}`}>
                      {val !== 0 ? formatCurrency(val, currencyCode) : '-'}
                    </td>
                  );
                })}
                <td className={`px-4 py-2 text-right font-semibold bg-gray-50 ${Number(row.total) > 0 ? 'text-green-700' : 'text-gray-800'}`}>
                  {formatCurrency(Number(row.total), currencyCode)}
                </td>
              </tr>
              {/* Drill-down rows */}
              {isExpanded && renderTransactionRows(row.category_id)}
            </Fragment>
          );
        })}
        {/* Subtotal row */}
        <tr className="border-t border-gray-300">
          <td className={`px-4 py-2 font-bold ${colorClass} sticky left-0 bg-gray-50 z-10`}>
            Subtotal {label}
          </td>
          {report!.months.map((m) => {
            const val = Number(totals.values[m] || 0);
            return (
              <td key={m} className={`px-3 py-2 text-right font-bold ${colorClass}`}>
                {val !== 0 ? formatCurrency(val, currencyCode) : '-'}
              </td>
            );
          })}
          <td className={`px-4 py-2 text-right font-bold ${colorClass} bg-gray-100`}>
            {formatCurrency(Number(totals.total), currencyCode)}
          </td>
        </tr>
      </>
    );
  };

  return (
    <MainLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-2xl font-bold text-gray-800">Relatório Mensal</h1>
            <p className="text-gray-600">Categorias × Meses (Despesas, Receitas e Transferências)</p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {/* Save view */}
            {showSaveInput ? (
              <div className="flex items-center gap-1">
                <Input
                  value={saveName}
                  onChange={(e) => setSaveName(e.target.value)}
                  placeholder="Nome da visão..."
                  className="w-40 text-sm"
                  onKeyDown={(e) => e.key === 'Enter' && handleSaveView()}
                />
                <Button size="sm" onClick={handleSaveView} isLoading={saveMutation.isPending}>
                  OK
                </Button>
                <Button size="sm" variant="secondary" onClick={() => { setShowSaveInput(false); setSaveName(''); }}>
                  X
                </Button>
              </div>
            ) : (
              <Button variant="secondary" onClick={() => setShowSaveInput(true)} title="Salvar visão">
                <Save size={18} className="mr-1" />
                Salvar
              </Button>
            )}

            {/* Load view */}
            <div className="relative">
              <Button variant="secondary" onClick={() => setShowLoadMenu(!showLoadMenu)} title="Carregar visão salva">
                <FolderOpen size={18} className="mr-1" />
                Visões
                {savedViews.length > 0 && (
                  <span className="ml-1 bg-primary-100 text-primary-700 text-xs px-1.5 py-0.5 rounded-full">
                    {savedViews.length}
                  </span>
                )}
              </Button>
              {showLoadMenu && (
                <div className="absolute right-0 top-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-50 w-64">
                  {savedViews.length === 0 ? (
                    <p className="p-3 text-sm text-gray-500">Nenhuma visão salva</p>
                  ) : (
                    <ul className="py-1 max-h-60 overflow-y-auto">
                      {savedViews.map((v) => (
                        <li key={v.id} className="flex items-center justify-between px-3 py-2 hover:bg-gray-50">
                          <button
                            className="flex-1 text-left text-sm text-gray-800 hover:text-primary-600"
                            onClick={() => handleLoadView(v)}
                          >
                            {v.name}
                          </button>
                          <button
                            className="text-gray-400 hover:text-red-500 ml-2 p-1"
                            onClick={(e) => {
                              e.stopPropagation();
                              if (v.id) deleteSavedMutation.mutate(v.id);
                            }}
                          >
                            <Trash2 size={14} />
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>

            {/* Export buttons */}
            {hasData && (
              <>
                <Button variant="secondary" onClick={handleExportCSV} title="Exportar agregado">
                  <Download size={18} className="mr-1" />
                  CSV Agregado
                </Button>
                <Button variant="secondary" onClick={handleExportDetailed} isLoading={exportingDetailed} title="Exportar lançamentos">
                  <FileSpreadsheet size={18} className="mr-1" />
                  CSV Lançamentos
                </Button>
              </>
            )}
          </div>
        </div>

        {/* Filters */}
        <Card>
          <CardContent className="pt-6">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              <Select
                label="Mês Inicial"
                id="start_month"
                value={filters.start_month}
                onChange={(e) => setFilters({ ...filters, start_month: e.target.value })}
                options={monthOptions}
              />
              <Select
                label="Mês Final"
                id="end_month"
                value={filters.end_month}
                onChange={(e) => setFilters({ ...filters, end_month: e.target.value })}
                options={monthOptions}
              />
              <Select
                label="Moeda"
                id="currency"
                value={filters.currency}
                onChange={(e) => setFilters({ ...filters, currency: e.target.value })}
                options={currencyOptions}
              />
            </div>

            {/* Multi-account filter chips */}
            {accounts.length > 0 && (
              <div className="mt-4">
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Contas
                  {filters.account_ids.length > 0 && (
                    <span className="text-xs text-gray-400 ml-2">({filters.account_ids.length} selecionada(s))</span>
                  )}
                </label>
                <div className="flex flex-wrap gap-2">
                  {filters.account_ids.length > 0 && (
                    <button
                      onClick={() => setFilters({ ...filters, account_ids: [] })}
                      className="px-3 py-1.5 text-xs rounded-full border border-gray-300 text-gray-600 hover:bg-gray-100"
                    >
                      Todas
                    </button>
                  )}
                  {accounts.map((acc) => {
                    const isSelected = filters.account_ids.includes(acc.id);
                    return (
                      <button
                        key={acc.id}
                        onClick={() => handleAccountToggle(acc.id)}
                        className={`px-3 py-1.5 text-xs rounded-full border transition-colors ${
                          isSelected
                            ? 'bg-primary-600 text-white border-primary-600 font-medium'
                            : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
                        }`}
                      >
                        {acc.name} ({acc.currency || 'BRL'})
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Category filter chips */}
            {allFilterableCategories.length > 0 && (
              <div className="mt-4">
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Categorias
                  {filters.category_ids.length > 0 && (
                    <span className="text-xs text-gray-400 ml-2">({filters.category_ids.length} selecionada(s))</span>
                  )}
                </label>
                <div className="flex flex-wrap gap-2">
                  {filters.category_ids.length > 0 && (
                    <button
                      onClick={() => setFilters({ ...filters, category_ids: [] })}
                      className="px-3 py-1.5 text-xs rounded-full border border-gray-300 text-gray-600 hover:bg-gray-100"
                    >
                      Limpar filtro
                    </button>
                  )}
                  {allFilterableCategories.map((cat) => {
                    const isSelected = filters.category_ids.includes(cat.id);
                    return (
                      <button
                        key={cat.id}
                        onClick={() => handleCategoryToggle(cat.id)}
                        className={`px-3 py-1.5 text-xs rounded-full border transition-colors ${
                          isSelected ? 'text-white font-medium' : 'bg-white text-gray-700 hover:bg-gray-50'
                        }`}
                        style={{
                          borderColor: cat.color,
                          backgroundColor: isSelected ? cat.color : undefined,
                        }}
                      >
                        {cat.name}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Report Table */}
        {isLoading ? (
          <div className="text-center py-8 text-gray-500">Carregando relatório...</div>
        ) : hasData ? (
          <Card>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 sticky top-0">
                    <tr>
                      <th className="px-4 py-3 text-left font-medium text-gray-600 min-w-[280px] sticky left-0 bg-gray-50 z-10">
                        Categoria
                      </th>
                      {report!.months.map((m) => (
                        <th key={m} className="px-3 py-3 text-right font-medium text-gray-600 min-w-[100px]">
                          {formatMonth(m)}
                        </th>
                      ))}
                      <th className="px-4 py-3 text-right font-bold text-gray-700 min-w-[120px] bg-gray-100">
                        Total
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {renderGroupRows(report!.expense_rows, report!.expense_totals, 'Despesas', 'text-red-700', 'bg-red-50')}
                    {renderGroupRows(report!.income_rows, report!.income_totals, 'Receitas', 'text-green-700', 'bg-green-50')}
                    {renderGroupRows(report!.transfer_rows, report!.transfer_totals, 'Transferências', 'text-blue-700', 'bg-blue-50')}
                  </tbody>
                  <tfoot className="bg-gray-100 border-t-2 border-gray-300">
                    <tr>
                      <td className="px-4 py-3 font-bold text-gray-700 sticky left-0 bg-gray-100 z-10">
                        SALDO LÍQUIDO
                      </td>
                      {report!.months.map((m) => {
                        const val = Number(report!.column_totals[m] || 0);
                        return (
                          <td key={m} className={`px-3 py-3 text-right font-bold ${val >= 0 ? 'text-green-700' : 'text-red-700'}`}>
                            {formatCurrency(val, currencyCode)}
                          </td>
                        );
                      })}
                      <td className={`px-4 py-3 text-right font-bold bg-gray-200 ${Number(report!.grand_total) >= 0 ? 'text-green-700' : 'text-red-700'}`}>
                        {formatCurrency(Number(report!.grand_total), currencyCode)}
                      </td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            </CardContent>
          </Card>
        ) : report ? (
          <Card>
            <CardContent className="py-12 text-center">
              <p className="text-gray-500">Nenhum dado encontrado para o período selecionado.</p>
            </CardContent>
          </Card>
        ) : null}
      </div>

      {/* Click outside to close load menu */}
      {showLoadMenu && (
        <div className="fixed inset-0 z-40" onClick={() => setShowLoadMenu(false)} />
      )}
    </MainLayout>
  );
}
