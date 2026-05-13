'use client';

import { useState, useMemo, useCallback, useRef, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import MainLayout from '@/components/layout/MainLayout';
import { Card, CardContent } from '@/components/ui/Card';
import Select from '@/components/ui/Select';
import Button from '@/components/ui/Button';
import { budgetsApi } from '@/lib/api';
import type { BudgetGridResponse } from '@/lib/api';
import { formatCurrency } from '@/lib/utils';
import { Copy, Loader2 } from 'lucide-react';

const MONTH_NAMES: Record<string, string> = {
  '01': 'Jan', '02': 'Fev', '03': 'Mar', '04': 'Abr',
  '05': 'Mai', '06': 'Jun', '07': 'Jul', '08': 'Ago',
  '09': 'Set', '10': 'Out', '11': 'Nov', '12': 'Dez',
};

function formatMonth(ym: string): string {
  const [year, month] = ym.split('-');
  return `${MONTH_NAMES[month]}/${year.slice(2)}`;
}

function parseDisplayValue(text: string): number {
  // Accept both "1.234,56" (BR) and "1234.56" formats
  const cleaned = text.replace(/\s/g, '');
  if (cleaned.includes(',')) {
    // BR format: remove dots (thousands), replace comma with dot
    return parseFloat(cleaned.replace(/\./g, '').replace(',', '.')) || 0;
  }
  return parseFloat(cleaned) || 0;
}

interface EditingCell {
  categoryId: number;
  month: string;
}

export default function OrcamentoPage() {
  const queryClient = useQueryClient();
  const now = new Date();
  const currentYear = now.getFullYear();
  const currentMonth = `${currentYear}-01`;
  const endMonth = `${currentYear}-12`;

  const [startMonth, setStartMonth] = useState(currentMonth);
  const [endMonthState, setEndMonth] = useState(endMonth);
  const [currency, setCurrency] = useState('BRL');

  // Copy month state
  const [showCopyDialog, setShowCopyDialog] = useState(false);
  const [copySource, setCopySource] = useState('');
  const [copyTargetStart, setCopyTargetStart] = useState('');
  const [copyTargetEnd, setCopyTargetEnd] = useState('');

  // Editing state
  const [editingCell, setEditingCell] = useState<EditingCell | null>(null);
  const [editValue, setEditValue] = useState('');
  const [savingCell] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Focus input when editing starts
  useEffect(() => {
    if (editingCell && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editingCell]);

  // Fetch budget grid
  const { data: grid, isLoading } = useQuery({
    queryKey: ['budget-grid', startMonth, endMonthState, currency],
    queryFn: () => budgetsApi.getGrid({ start_month: startMonth, end_month: endMonthState, currency }),
    enabled: !!startMonth && !!endMonthState,
  });

  // Update cell mutation with optimistic update
  const updateCellMutation = useMutation({
    mutationFn: budgetsApi.updateCell,
  });

  // Copy month mutation — suporta intervalo de meses destino
  const copyMonthMutation = useMutation({
    mutationFn: async ({ source, targetStart, targetEnd }: { source: string; targetStart: string; targetEnd: string }) => {
      // Gerar lista de meses no intervalo
      const months: string[] = [];
      const [sy, sm] = targetStart.split('-').map(Number);
      const [ey, em] = targetEnd.split('-').map(Number);
      let y = sy, m = sm;
      while (y < ey || (y === ey && m <= em)) {
        months.push(`${y}-${String(m).padStart(2, '0')}`);
        m++;
        if (m > 12) { m = 1; y++; }
      }
      let totalCopied = 0;
      for (const target of months) {
        const result = await budgetsApi.copyMonth(source, target);
        totalCopied += result.copied_count;
      }
      return { copied_count: totalCopied, months_count: months.length };
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['budget-grid'] });
      setShowCopyDialog(false);
      alert(`${data.copied_count} orçamento(s) copiado(s) para ${data.months_count} mês(es).`);
    },
  });

  const handleCellClick = useCallback((categoryId: number, month: string, currentValue: number) => {
    if (editingCell?.categoryId === categoryId && editingCell?.month === month) return;
    setEditingCell({ categoryId, month });
    setEditValue(currentValue !== 0 ? currentValue.toFixed(2).replace('.', ',') : '');
  }, [editingCell]);

  const handleCellSave = useCallback(async () => {
    if (!editingCell) return;
    const amount = parseDisplayValue(editValue);
    const { categoryId, month } = editingCell;

    // Optimistic update: atualizar cache local imediatamente
    queryClient.setQueryData<BudgetGridResponse>(
      ['budget-grid', startMonth, endMonthState, currency],
      (old) => {
        if (!old) return old;
        const updateRows = (rows: BudgetGridResponse['expense_rows']) =>
          rows.map(row => {
            if (row.category_id !== categoryId) return row;
            const newValues = { ...row.values, [month]: amount };
            const newTotal = Object.values(newValues).reduce((s, v) => s + Number(v), 0);
            return { ...row, values: newValues, total: newTotal };
          });
        return {
          ...old,
          expense_rows: updateRows(old.expense_rows),
          income_rows: updateRows(old.income_rows),
          transfer_rows: updateRows(old.transfer_rows),
        };
      }
    );

    setEditingCell(null);
    setEditValue('');

    // Salvar no backend em background (sem bloquear a UI)
    updateCellMutation.mutate({
      month,
      category_id: categoryId,
      amount,
      currency,
    });
  }, [editingCell, editValue, currency, updateCellMutation, queryClient, startMonth, endMonthState]);

  const handleCellCancel = useCallback(() => {
    setEditingCell(null);
    setEditValue('');
  }, []);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleCellSave();
    } else if (e.key === 'Escape') {
      handleCellCancel();
    } else if (e.key === 'Tab') {
      e.preventDefault();
      handleCellSave();
    }
  }, [handleCellSave, handleCellCancel]);

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

  const currencyCode = (currency || 'BRL') as 'BRL' | 'USD' | 'EUR';

  const hasData = grid && (grid.expense_rows.length > 0 || grid.income_rows.length > 0 || grid.transfer_rows.length > 0);

  // Compute column totals (sum across all groups per month)
  const columnTotals = useMemo(() => {
    if (!grid) return {};
    const totals: Record<string, number> = {};
    for (const m of grid.months) {
      let sum = 0;
      for (const row of [...grid.expense_rows, ...grid.income_rows, ...grid.transfer_rows]) {
        sum += Number(row.values[m] || 0);
      }
      totals[m] = sum;
    }
    return totals;
  }, [grid]);

  // Render a single editable cell
  const renderCell = (categoryId: number, month: string, value: number) => {
    const isEditing = editingCell?.categoryId === categoryId && editingCell?.month === month;

    if (isEditing) {
      return (
        <td key={month} className="px-1 py-1 border border-gray-300">
          <input
            ref={inputRef}
            type="text"
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            onKeyDown={handleKeyDown}
            onBlur={handleCellSave}
            disabled={savingCell}
            className="w-full px-2 py-1 text-right text-sm border-2 border-blue-500 rounded outline-none bg-blue-50"
            placeholder="0,00"
          />
        </td>
      );
    }

    return (
      <td
        key={month}
        className="px-3 py-2 text-right cursor-pointer hover:bg-blue-50 transition-colors border border-gray-300"
        onClick={() => handleCellClick(categoryId, month, value)}
      >
        {value !== 0 ? (
          <span className="text-gray-700">{formatCurrency(value, currencyCode)}</span>
        ) : (
          <span className="text-gray-300">-</span>
        )}
      </td>
    );
  };

  // Render group rows
  const renderGroupRows = (
    rows: BudgetGridResponse['expense_rows'],
    groupTotal: number,
    label: string,
    colorClass: string,
    bgClass: string,
  ) => {
    if (rows.length === 0) return null;

    // Compute group subtotals per month
    const groupMonthTotals: Record<string, number> = {};
    if (grid) {
      for (const m of grid.months) {
        let sum = 0;
        for (const row of rows) {
          sum += Number(row.values[m] || 0);
        }
        groupMonthTotals[m] = sum;
      }
    }

    return (
      <>
        {/* Group header */}
        <tr className={bgClass}>
          <td colSpan={(grid?.months.length || 0) + 3} className={`px-4 py-2 font-bold ${colorClass} sticky left-0 z-10 ${bgClass} border border-gray-300`}>
            {label}
          </td>
        </tr>
        {/* Category rows */}
        {rows.map((row) => (
          <tr key={row.category_id} className="hover:bg-gray-50">
            <td className="px-4 py-2 pl-6 sticky left-0 bg-white z-10 border border-gray-300">
              <div className="flex items-center gap-1.5">
                {row.category_color && (
                  <span className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: row.category_color }} />
                )}
                <span className="text-gray-800">{row.category_name}</span>
              </div>
            </td>
            <td className="px-3 py-2 text-right text-xs text-amber-700 bg-amber-50/50 border border-gray-300">
              {row.avg_3m != null && Number(row.avg_3m) !== 0 ? formatCurrency(Number(row.avg_3m), currencyCode) : '-'}
            </td>
            {grid!.months.map((m) => renderCell(row.category_id, m, Number(row.values[m] || 0)))}
            <td className="px-4 py-2 text-right font-semibold bg-gray-50 text-gray-800 border border-gray-300">
              {Number(row.total) !== 0 ? formatCurrency(Number(row.total), currencyCode) : '-'}
            </td>
          </tr>
        ))}
        {/* Subtotal row */}
        <tr className="border-t border-gray-300">
          <td className={`px-4 py-2 font-bold ${colorClass} sticky left-0 bg-gray-50 z-10 border border-gray-300`}>
            Subtotal {label}
          </td>
          <td className={`px-3 py-2 text-right font-bold border border-gray-300 bg-amber-50/50 ${colorClass}`}>
            {(() => {
              const sum = rows.reduce((s, r) => s + Number(r.avg_3m || 0), 0);
              return sum !== 0 ? formatCurrency(sum, currencyCode) : '-';
            })()}
          </td>
          {grid!.months.map((m) => {
            const val = groupMonthTotals[m] || 0;
            return (
              <td key={m} className={`px-3 py-2 text-right font-bold ${colorClass} border border-gray-300`}>
                {val !== 0 ? formatCurrency(val, currencyCode) : '-'}
              </td>
            );
          })}
          <td className={`px-4 py-2 text-right font-bold ${colorClass} bg-gray-100 border border-gray-300`}>
            {formatCurrency(groupTotal, currencyCode)}
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
            <h1 className="text-2xl font-bold text-gray-800">Orçamento</h1>
            <p className="text-gray-600">Planejamento mensal por categoria — clique em uma célula para editar</p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              onClick={() => {
                setCopySource('');
                setCopyTargetStart('');
                setCopyTargetEnd('');
                setShowCopyDialog(true);
              }}
            >
              <Copy size={18} className="mr-1" />
              Copiar Mês
            </Button>
          </div>
        </div>

        {/* Filters */}
        <Card>
          <CardContent className="pt-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <Select
                label="Mês Inicial"
                id="start_month"
                value={startMonth}
                onChange={(e) => setStartMonth(e.target.value)}
                options={monthOptions}
              />
              <Select
                label="Mês Final"
                id="end_month"
                value={endMonthState}
                onChange={(e) => setEndMonth(e.target.value)}
                options={monthOptions}
              />
              <Select
                label="Moeda"
                id="currency"
                value={currency}
                onChange={(e) => setCurrency(e.target.value)}
                options={currencyOptions}
              />
            </div>
          </CardContent>
        </Card>

        {/* Budget Grid */}
        {isLoading ? (
          <div className="text-center py-8 text-gray-500">
            <Loader2 className="animate-spin inline-block mr-2" size={20} />
            Carregando orçamento...
          </div>
        ) : hasData ? (
          <Card>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm border-collapse border border-gray-400">
                  <thead className="bg-gray-50 sticky top-0">
                    <tr>
                      <th className="px-4 py-3 text-left font-medium text-gray-600 min-w-[250px] sticky left-0 bg-gray-50 z-10 border border-gray-300">
                        Categoria
                      </th>
                      <th className="px-3 py-3 text-right font-medium text-gray-600 min-w-[110px] border border-gray-300 bg-amber-50 text-amber-700">
                        Média 3M
                      </th>
                      {grid!.months.map((m) => (
                        <th key={m} className="px-3 py-3 text-right font-medium text-gray-600 min-w-[110px] border border-gray-300">
                          {formatMonth(m)}
                        </th>
                      ))}
                      <th className="px-4 py-3 text-right font-bold text-gray-700 min-w-[120px] bg-gray-100 border border-gray-300">
                        Total
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {renderGroupRows(grid!.expense_rows, Number(grid!.expense_total), 'Despesas', 'text-red-700', 'bg-red-50')}
                    {renderGroupRows(grid!.income_rows, Number(grid!.income_total), 'Receitas', 'text-green-700', 'bg-green-50')}
                    {renderGroupRows(grid!.transfer_rows, Number(grid!.transfer_total), 'Transferências', 'text-blue-700', 'bg-blue-50')}
                  </tbody>
                  <tfoot className="bg-gray-100 border-t-2 border-gray-300">
                    <tr>
                      <td className="px-4 py-3 font-bold text-gray-700 sticky left-0 bg-gray-100 z-10 border border-gray-400">
                        TOTAL GERAL
                      </td>
                      <td className={`px-3 py-3 text-right font-bold border border-gray-400 bg-gray-100 ${(() => {
                        const sum = [...grid!.expense_rows, ...grid!.income_rows, ...grid!.transfer_rows].reduce((s, r) => s + Number(r.avg_3m || 0), 0);
                        return sum >= 0 ? 'text-green-700' : 'text-red-700';
                      })()}`}>
                        {(() => {
                          const sum = [...grid!.expense_rows, ...grid!.income_rows, ...grid!.transfer_rows].reduce((s, r) => s + Number(r.avg_3m || 0), 0);
                          return sum !== 0 ? formatCurrency(sum, currencyCode) : '-';
                        })()}
                      </td>
                      {grid!.months.map((m) => {
                        const val = columnTotals[m] || 0;
                        return (
                          <td key={m} className={`px-3 py-3 text-right font-bold border border-gray-400 ${val >= 0 ? 'text-green-700' : 'text-red-700'}`}>
                            {formatCurrency(val, currencyCode)}
                          </td>
                        );
                      })}
                      <td className={`px-4 py-3 text-right font-bold bg-gray-200 border border-gray-400 ${Number(grid!.grand_total) >= 0 ? 'text-green-700' : 'text-red-700'}`}>
                        {formatCurrency(Number(grid!.grand_total), currencyCode)}
                      </td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            </CardContent>
          </Card>
        ) : grid ? (
          <Card>
            <CardContent className="py-12 text-center">
              <p className="text-gray-500">Nenhuma categoria ativa encontrada. Crie categorias primeiro.</p>
            </CardContent>
          </Card>
        ) : null}
      </div>

      {/* Copy Month Dialog */}
      {showCopyDialog && (
        <>
          <div className="fixed inset-0 bg-black/40 z-50" onClick={() => setShowCopyDialog(false)} />
          <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-white rounded-lg shadow-xl z-50 w-96 p-6">
            <h3 className="text-lg font-bold text-gray-800 mb-4">Copiar Orçamento</h3>
            <p className="text-sm text-gray-600 mb-4">
              Copiar todos os valores orçados de um mês para um intervalo de meses.
            </p>
            <div className="space-y-3">
              <Select
                label="Mês Origem"
                id="copy_source"
                value={copySource}
                onChange={(e) => setCopySource(e.target.value)}
                options={[{ value: '', label: 'Selecione...' }, ...monthOptions]}
              />
              <div className="grid grid-cols-2 gap-3">
                <Select
                  label="Destino Início"
                  id="copy_target_start"
                  value={copyTargetStart}
                  onChange={(e) => {
                    setCopyTargetStart(e.target.value);
                    if (!copyTargetEnd || e.target.value > copyTargetEnd) {
                      setCopyTargetEnd(e.target.value);
                    }
                  }}
                  options={[{ value: '', label: 'Selecione...' }, ...monthOptions]}
                />
                <Select
                  label="Destino Fim"
                  id="copy_target_end"
                  value={copyTargetEnd}
                  onChange={(e) => setCopyTargetEnd(e.target.value)}
                  options={[{ value: '', label: 'Selecione...' }, ...monthOptions.filter(o => !copyTargetStart || o.value >= copyTargetStart)]}
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <Button variant="secondary" onClick={() => setShowCopyDialog(false)}>
                Cancelar
              </Button>
              <Button
                onClick={() => {
                  if (copySource && copyTargetStart && copyTargetEnd) {
                    copyMonthMutation.mutate({ source: copySource, targetStart: copyTargetStart, targetEnd: copyTargetEnd });
                  }
                }}
                isLoading={copyMonthMutation.isPending}
                disabled={!copySource || !copyTargetStart || !copyTargetEnd}
              >
                Copiar
              </Button>
            </div>
          </div>
        </>
      )}
    </MainLayout>
  );
}
