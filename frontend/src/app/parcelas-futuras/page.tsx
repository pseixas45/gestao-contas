'use client';

import { useState, useMemo, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import MainLayout from '@/components/layout/MainLayout';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card';
import Button from '@/components/ui/Button';
import {
  budgetsApi,
  type InstallmentProjectionRow,
} from '@/lib/api';
import { formatCurrency } from '@/lib/utils';
import {
  ChevronDown,
  ChevronRight,
  Copy,
  CheckCircle,
} from 'lucide-react';

function formatMonthLabel(ym: string): string {
  const months: Record<string, string> = {
    '01': 'Jan', '02': 'Fev', '03': 'Mar', '04': 'Abr',
    '05': 'Mai', '06': 'Jun', '07': 'Jul', '08': 'Ago',
    '09': 'Set', '10': 'Out', '11': 'Nov', '12': 'Dez',
  };
  const [year, month] = ym.split('-');
  return `${months[month]}/${year.slice(2)}`;
}

function getCurrentMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

export default function ParcelasFuturasPage() {
  const queryClient = useQueryClient();
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set());
  const [expandedDetails, setExpandedDetails] = useState<Set<string>>(new Set());
  const [selectedCategories, setSelectedCategories] = useState<Set<number>>(new Set());
  const [copySuccess, setCopySuccess] = useState(false);
  const [startMonth, setStartMonth] = useState(getCurrentMonth());

  const { data, isLoading } = useQuery({
    queryKey: ['installment-projections'],
    queryFn: () => budgetsApi.getInstallmentProjections(),
  });

  const copyMutation = useMutation({
    mutationFn: (items: { month: string; category_id: number; amount_brl: number }[]) =>
      budgetsApi.copyProjectionsToBudget(items),
    onSuccess: (data) => {
      setCopySuccess(true);
      setTimeout(() => setCopySuccess(false), 5000);
      queryClient.invalidateQueries({ queryKey: ['budget-grid'] });
    },
    onError: (error) => {
      alert(`Erro ao copiar: ${(error as Error).message}`);
    },
  });

  // Filter months >= startMonth
  const filteredMonths = useMemo(() => {
    if (!data) return [];
    return data.months.filter(m => m >= startMonth);
  }, [data, startMonth]);

  const filteredRows = useMemo(() => {
    if (!data) return [];
    return data.rows
      .map(row => {
        const filteredMonthValues: Record<string, number> = {};
        let total = 0;
        for (const m of filteredMonths) {
          const v = row.months[m] || 0;
          if (v > 0) {
            filteredMonthValues[m] = v;
            total += v;
          }
        }
        if (total === 0) return null;
        return { ...row, months: filteredMonthValues, total };
      })
      .filter(Boolean) as InstallmentProjectionRow[];
  }, [data, filteredMonths]);

  const filteredTotals = useMemo(() => {
    const totals: Record<string, number> = {};
    for (const m of filteredMonths) {
      totals[m] = filteredRows.reduce((s, r) => s + (r.months[m] || 0), 0);
    }
    return totals;
  }, [filteredMonths, filteredRows]);

  const grandTotal = useMemo(() => {
    return Object.values(filteredTotals).reduce((s, v) => s + v, 0);
  }, [filteredTotals]);

  const toggleCategory = useCallback((name: string) => {
    setExpandedCategories(prev => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }, []);

  const toggleDetail = useCallback((key: string) => {
    setExpandedDetails(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const toggleSelectCategory = useCallback((categoryId: number) => {
    setSelectedCategories(prev => {
      const next = new Set(prev);
      if (next.has(categoryId)) next.delete(categoryId);
      else next.add(categoryId);
      return next;
    });
  }, []);

  const toggleSelectAll = useCallback(() => {
    setSelectedCategories(prev => {
      const allIds = filteredRows.filter(r => r.category_id).map(r => r.category_id!);
      if (prev.size === allIds.length) return new Set();
      return new Set(allIds);
    });
  }, [filteredRows]);

  const handleCopyToBudget = useCallback(() => {
    // Se nenhuma categoria selecionada, copiar todas
    const selected = selectedCategories.size > 0
      ? selectedCategories
      : new Set(filteredRows.filter(r => r.category_id).map(r => r.category_id!));

    const items: { month: string; category_id: number; amount_brl: number }[] = [];
    for (const row of filteredRows) {
      if (!row.category_id || !selected.has(row.category_id)) continue;
      for (const month of filteredMonths) {
        const amount = row.months[month] || 0;
        items.push({ month, category_id: row.category_id, amount_brl: -amount });
      }
    }
    if (items.length > 0) {
      copyMutation.mutate(items);
    }
  }, [filteredRows, filteredMonths, selectedCategories, copyMutation]);

  return (
    <MainLayout>
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Parcelas</CardTitle>
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2">
                <label className="text-sm text-slate-600">A partir de:</label>
                <input
                  type="month"
                  value={startMonth}
                  onChange={e => setStartMonth(e.target.value)}
                  className="px-3 py-1.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>
              <Button
                onClick={handleCopyToBudget}
                isLoading={copyMutation.isPending}
                disabled={!filteredRows.length || copySuccess}
              >
                {copySuccess ? (
                  <><CheckCircle size={16} /> Copiado!</>
                ) : (
                  <><Copy size={16} /> Copiar {selectedCategories.size > 0 ? `(${selectedCategories.size})` : ''} para Orçamento</>
                )}
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="text-sm text-slate-500 py-8 text-center">Carregando...</p>
          ) : !data || filteredRows.length === 0 ? (
            <p className="text-sm text-slate-500 py-8 text-center">
              Nenhuma parcela futura encontrada.
            </p>
          ) : (
            <div className="border border-slate-200 rounded-xl overflow-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-200">
                    <th className="px-3 py-2 text-left font-medium text-slate-600 sticky left-0 bg-slate-50 min-w-[280px]">
                      <div className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={selectedCategories.size > 0 && selectedCategories.size === filteredRows.filter(r => r.category_id).length}
                          onChange={toggleSelectAll}
                          className="rounded border-slate-300 text-primary-600 focus:ring-primary-500"
                        />
                        Categoria / Descrição
                      </div>
                    </th>
                    {filteredMonths.map(m => (
                      <th key={m} className="px-3 py-2 text-right font-medium text-slate-600 min-w-[100px]">
                        {formatMonthLabel(m)}
                      </th>
                    ))}
                    <th className="px-3 py-2 text-right font-semibold text-slate-700 min-w-[110px] bg-slate-100">
                      Total
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRows.map(row => {
                    const isExpanded = expandedCategories.has(row.category_name);
                    return (
                      <CategoryBlock
                        key={row.category_name}
                        row={row}
                        months={filteredMonths}
                        isExpanded={isExpanded}
                        isSelected={row.category_id ? selectedCategories.has(row.category_id) : false}
                        expandedDetails={expandedDetails}
                        onToggle={() => toggleCategory(row.category_name)}
                        onToggleDetail={toggleDetail}
                        onToggleSelect={() => row.category_id && toggleSelectCategory(row.category_id)}
                      />
                    );
                  })}
                </tbody>
                <tfoot>
                  <tr className="bg-slate-100 border-t-2 border-slate-300">
                    <td className="px-3 py-2 font-bold text-slate-800 sticky left-0 bg-slate-100">
                      TOTAL
                    </td>
                    {filteredMonths.map(m => (
                      <td key={m} className="px-3 py-2 text-right font-bold text-slate-800">
                        {formatCurrency(filteredTotals[m] || 0)}
                      </td>
                    ))}
                    <td className="px-3 py-2 text-right font-bold text-slate-900 bg-slate-200">
                      {formatCurrency(grandTotal)}
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          )}

          {copyMutation.isError && (
            <p className="text-sm text-rose-600 mt-3">
              Erro ao copiar: {(copyMutation.error as Error).message}
            </p>
          )}
          {copySuccess && copyMutation.data && (
            <p className="text-sm text-emerald-600 mt-3">
              {copyMutation.data.created} criados, {copyMutation.data.updated} atualizados no orçamento.
            </p>
          )}
        </CardContent>
      </Card>
    </MainLayout>
  );
}

function CategoryBlock({
  row,
  months,
  isExpanded,
  isSelected,
  expandedDetails,
  onToggle,
  onToggleDetail,
  onToggleSelect,
}: {
  row: InstallmentProjectionRow;
  months: string[];
  isExpanded: boolean;
  isSelected: boolean;
  expandedDetails: Set<string>;
  onToggle: () => void;
  onToggleDetail: (key: string) => void;
  onToggleSelect: () => void;
}) {
  return (
    <>
      {/* Category row */}
      <tr
        className="border-b border-slate-200 cursor-pointer hover:bg-slate-50 transition-colors"
        onClick={onToggle}
      >
        <td className="px-3 py-2 sticky left-0 bg-white">
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={isSelected}
              onChange={(e) => { e.stopPropagation(); onToggleSelect(); }}
              onClick={(e) => e.stopPropagation()}
              className="rounded border-slate-300 text-primary-600 focus:ring-primary-500"
            />
            {isExpanded ? <ChevronDown size={14} className="text-slate-400" /> : <ChevronRight size={14} className="text-slate-400" />}
            {row.category_color && (
              <span
                className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                style={{ backgroundColor: row.category_color }}
              />
            )}
            <span className="font-medium text-slate-800">{row.category_name}</span>
            <span className="text-xs text-slate-400">({row.details.length})</span>
          </div>
        </td>
        {months.map(m => (
          <td key={m} className="px-3 py-2 text-right font-medium text-slate-700">
            {row.months[m] ? formatCurrency(row.months[m]) : <span className="text-slate-300">-</span>}
          </td>
        ))}
        <td className="px-3 py-2 text-right font-semibold text-slate-800 bg-slate-50">
          {formatCurrency(row.total)}
        </td>
      </tr>

      {/* Detail rows */}
      {isExpanded && row.details.map(detail => {
        const detailKey = `${row.category_name}|${detail.description}|${detail.account_name}`;
        const isDetailExpanded = expandedDetails.has(detailKey);

        return (
          <DetailBlock
            key={detailKey}
            detail={detail}
            months={months}
            detailKey={detailKey}
            isExpanded={isDetailExpanded}
            onToggle={() => onToggleDetail(detailKey)}
          />
        );
      })}
    </>
  );
}

function DetailBlock({
  detail,
  months,
  detailKey,
  isExpanded,
  onToggle,
}: {
  detail: InstallmentProjectionRow['details'][0];
  months: string[];
  detailKey: string;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  return (
    <>
      <tr
        className="border-b border-slate-100 cursor-pointer hover:bg-blue-50/30 transition-colors"
        onClick={onToggle}
      >
        <td className="px-3 py-1.5 sticky left-0 bg-white">
          <div className="flex items-center gap-2 pl-6">
            {isExpanded ? <ChevronDown size={12} className="text-slate-300" /> : <ChevronRight size={12} className="text-slate-300" />}
            <span className="text-slate-600 text-xs">{detail.description}</span>
            {detail.account_name && (
              <span className="text-slate-400 text-xs">({detail.account_name})</span>
            )}
          </div>
        </td>
        {months.map(m => (
          <td key={m} className="px-3 py-1.5 text-right text-xs text-slate-600">
            {detail.months[m] ? formatCurrency(detail.months[m]) : <span className="text-slate-200">-</span>}
          </td>
        ))}
        <td className="px-3 py-1.5 text-right text-xs font-medium text-slate-700 bg-slate-50">
          {formatCurrency(detail.total)}
        </td>
      </tr>

      {/* Installment detail rows */}
      {isExpanded && detail.items
        .filter(item => months.includes(item.month))
        .map((item, idx) => {
        const isRealized = item.status === 'realized';
        const textClass = isRealized ? 'text-slate-500' : 'text-blue-400 italic';
        const dotClass = isRealized ? 'bg-emerald-400' : 'bg-blue-300';
        return (
        <tr key={`${detailKey}-${idx}`} className="border-b border-slate-50">
          <td className="px-3 py-1 sticky left-0 bg-white">
            <div className={`pl-12 text-xs flex items-center gap-1.5 ${textClass}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${dotClass}`} />
              Parcela {item.installment_info}
            </div>
          </td>
          {months.map(m => (
            <td key={m} className={`px-3 py-1 text-right text-xs ${textClass}`}>
              {m === item.month ? formatCurrency(item.amount_brl) : ''}
            </td>
          ))}
          <td className="px-3 py-1 bg-slate-50"></td>
        </tr>
        );
      })}
    </>
  );
}
