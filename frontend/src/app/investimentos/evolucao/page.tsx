'use client';

import { useState, useMemo, useEffect, Fragment } from 'react';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { ArrowLeft, Download, ChevronDown, ChevronRight } from 'lucide-react';
import MainLayout from '@/components/layout/MainLayout';
import { investmentsApi, PositionEvolutionAsset } from '@/lib/api';

// Intervalo padrão: início do ano atual até o mês anterior ao atual
function defaultRange(): { from: string; to: string } {
  const now = new Date();
  const from = `${now.getFullYear()}-01`;
  const prev = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  const to = `${prev.getFullYear()}-${String(prev.getMonth() + 1).padStart(2, '0')}`;
  return { from, to };
}

function formatCurrency(value: number | null): string {
  if (value === null || value === undefined) return '—';
  return value.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatMonthShort(month: string): string {
  const [y, m] = month.split('-');
  const names = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
  return `${names[parseInt(m) - 1]}/${y.slice(2)}`;
}

function formatMonthLabel(month: string): string {
  const [y, m] = month.split('-');
  const names = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];
  return `${names[parseInt(m) - 1]} ${y}`;
}

export default function EvolucaoPage() {
  const initial = defaultRange();
  const [bankId, setBankId] = useState<number | undefined>();
  const [assetFilter, setAssetFilter] = useState<string>('');
  const [dateFrom, setDateFrom] = useState<string>(initial.from);
  const [dateTo, setDateTo] = useState<string>(initial.to);
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());

  const { data, isLoading } = useQuery({
    queryKey: ['position-evolution', bankId, dateFrom, dateTo],
    queryFn: () => investmentsApi.positionEvolution({
      bank_id: bankId,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
    }),
  });

  const months = data?.months || [];
  const allAssets = data?.assets || [];
  const banks = data?.banks || [];

  // Filter by asset name
  const filteredAssets = useMemo(() => {
    if (!assetFilter) return allAssets;
    const q = assetFilter.toLowerCase();
    return allAssets.filter(a => a.asset_name.toLowerCase().includes(q));
  }, [allAssets, assetFilter]);

  // Group by asset class
  const grouped = useMemo(() => {
    const groups: Record<string, { name: string; color: string | null; assets: PositionEvolutionAsset[]; totals: Record<string, number> }> = {};
    for (const asset of filteredAssets) {
      const cls = asset.asset_class || 'Sem classe';
      if (!groups[cls]) {
        groups[cls] = { name: cls, color: asset.asset_class_color, assets: [], totals: {} };
      }
      groups[cls].assets.push(asset);
      for (const m of months) {
        const v = asset.values[m];
        if (v !== null && v !== undefined) {
          groups[cls].totals[m] = (groups[cls].totals[m] || 0) + v;
        }
      }
    }
    return Object.values(groups).sort((a, b) => {
      const lastMonth = months[months.length - 1];
      return (b.totals[lastMonth] || 0) - (a.totals[lastMonth] || 0);
    });
  }, [filteredAssets, months]);

  // Expandir todas as classes por padrão quando os dados chegam (ativos visíveis)
  useEffect(() => {
    if (data?.assets) {
      const classes = new Set<string>();
      for (const a of data.assets) classes.add(a.asset_class || 'Sem classe');
      setExpandedGroups(classes);
    }
  }, [data]);

  // Grand totals
  const grandTotals = useMemo(() => {
    const totals: Record<string, number> = {};
    for (const asset of filteredAssets) {
      for (const m of months) {
        const v = asset.values[m];
        if (v !== null && v !== undefined) {
          totals[m] = (totals[m] || 0) + v;
        }
      }
    }
    return totals;
  }, [filteredAssets, months]);

  const toggleGroup = (name: string) => {
    setExpandedGroups(prev => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const expandAll = () => {
    setExpandedGroups(new Set(grouped.map(g => g.name)));
  };

  const collapseAll = () => {
    setExpandedGroups(new Set());
  };

  const exportCsv = () => {
    if (!data) return;
    const header = ['Classe', 'Ativo', 'Conta', ...months.map(formatMonthShort)];
    const rows: string[][] = [];
    for (const group of grouped) {
      for (const asset of group.assets) {
        rows.push([
          asset.asset_class || '',
          asset.asset_name,
          asset.account_name,
          ...months.map(m => asset.values[m] !== null && asset.values[m] !== undefined ? asset.values[m]!.toFixed(2) : ''),
        ]);
      }
    }
    const csv = [header, ...rows].map(r => r.map(c => `"${c}"`).join(';')).join('\n');
    const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `evolucao_investimentos_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <MainLayout>
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link href="/investimentos" className="p-1.5 rounded-lg hover:bg-slate-100">
            <ArrowLeft size={18} />
          </Link>
          <h1 className="text-xl font-bold text-slate-900">Evolucao da Carteira</h1>
        </div>
        <button
          onClick={exportCsv}
          disabled={!data || months.length === 0}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-slate-200 hover:bg-slate-50 disabled:opacity-40"
        >
          <Download size={14} />
          Exportar CSV
        </button>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-xl border border-slate-200 p-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div>
            <label className="text-xs font-medium text-slate-500 mb-1 block">Banco</label>
            <select
              value={bankId || ''}
              onChange={e => setBankId(e.target.value ? Number(e.target.value) : undefined)}
              className="w-full text-sm border border-slate-200 rounded-lg px-2.5 py-1.5"
            >
              <option value="">Todos</option>
              {banks.map(b => (
                <option key={b.id} value={b.id}>{b.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500 mb-1 block">De</label>
            <input
              type="month"
              value={dateFrom}
              onChange={e => setDateFrom(e.target.value)}
              className="w-full text-sm border border-slate-200 rounded-lg px-2.5 py-1.5"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500 mb-1 block">Ate</label>
            <input
              type="month"
              value={dateTo}
              onChange={e => setDateTo(e.target.value)}
              className="w-full text-sm border border-slate-200 rounded-lg px-2.5 py-1.5"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500 mb-1 block">Buscar Ativo</label>
            <input
              type="text"
              value={assetFilter}
              onChange={e => setAssetFilter(e.target.value)}
              placeholder="Nome do ativo..."
              className="w-full text-sm border border-slate-200 rounded-lg px-2.5 py-1.5"
            />
          </div>
        </div>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="bg-white rounded-xl border border-slate-200 p-8 text-center text-slate-400">
          Carregando...
        </div>
      ) : months.length === 0 ? (
        <div className="bg-white rounded-xl border border-slate-200 p-8 text-center text-slate-400">
          Nenhum dado encontrado para os filtros selecionados.
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-slate-200">
          {/* Controls */}
          <div className="flex items-center gap-2 px-4 py-2 border-b border-slate-100">
            <button onClick={expandAll} className="text-xs text-blue-600 hover:underline">Expandir tudo</button>
            <span className="text-slate-300">|</span>
            <button onClick={collapseAll} className="text-xs text-blue-600 hover:underline">Recolher tudo</button>
            <span className="text-xs text-slate-400 ml-auto">{filteredAssets.length} ativos em {grouped.length} classes</span>
          </div>

          <div className="overflow-x-auto">
            <table className="text-sm border-collapse">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200">
                  <th className="text-left px-4 py-2.5 font-semibold text-slate-600 sticky left-0 bg-slate-50 z-10 w-[300px] min-w-[300px] max-w-[300px]">
                    Ativo
                  </th>
                  {months.map(m => (
                    <th key={m} className="text-right px-3 py-2.5 font-semibold text-slate-600 whitespace-nowrap w-[110px] min-w-[110px]">
                      {formatMonthShort(m)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {/* Grand total row */}
                <tr className="bg-slate-100 font-bold border-b border-slate-300">
                  <td className="px-4 py-2 text-slate-800 sticky left-0 bg-slate-100 z-10 w-[300px] min-w-[300px] max-w-[300px]">
                    Total Geral
                  </td>
                  {months.map(m => (
                    <td key={m} className="text-right px-3 py-2 text-slate-800 whitespace-nowrap w-[110px] min-w-[110px]">
                      {formatCurrency(grandTotals[m] || 0)}
                    </td>
                  ))}
                </tr>

                {grouped.map(group => {
                  const isExpanded = expandedGroups.has(group.name);
                  return (
                    <Fragment key={group.name}>
                      {/* Group header */}
                      <tr
                        className="bg-slate-50 border-b border-slate-100 cursor-pointer hover:bg-slate-100"
                        onClick={() => toggleGroup(group.name)}
                      >
                        <td className="px-4 py-2 font-semibold text-slate-700 sticky left-0 bg-slate-50 z-10 w-[300px] min-w-[300px] max-w-[300px]">
                          <div className="flex items-center gap-2">
                            {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                            {group.color && (
                              <span className="w-2.5 h-2.5 rounded-full inline-block flex-shrink-0" style={{ backgroundColor: group.color }} />
                            )}
                            <span className="truncate">{group.name}</span>
                            <span className="text-xs font-normal text-slate-400 flex-shrink-0">({group.assets.length})</span>
                          </div>
                        </td>
                        {months.map(m => (
                          <td key={m} className="text-right px-3 py-2 font-semibold text-slate-700 whitespace-nowrap w-[110px] min-w-[110px]">
                            {group.totals[m] ? formatCurrency(group.totals[m]) : '—'}
                          </td>
                        ))}
                      </tr>

                      {/* Individual assets */}
                      {isExpanded && group.assets
                        .sort((a, b) => {
                          const lastMonth = months[months.length - 1];
                          return (b.values[lastMonth] || 0) - (a.values[lastMonth] || 0);
                        })
                        .map(asset => (
                          <tr key={asset.key} className="border-b border-slate-50 hover:bg-blue-50/30">
                            <td className="px-4 py-1.5 sticky left-0 bg-white z-10 w-[300px] min-w-[300px] max-w-[300px]">
                              <div className="pl-6">
                                <div className="text-slate-700 text-xs leading-tight truncate" title={asset.asset_name}>
                                  {asset.asset_name}
                                </div>
                                <div className="text-[10px] text-slate-400">{asset.account_name}</div>
                              </div>
                            </td>
                            {months.map(m => {
                              const val = asset.values[m];
                              return (
                                <td key={m} className="text-right px-3 py-1.5 text-xs text-slate-600 whitespace-nowrap w-[110px] min-w-[110px]">
                                  {val !== null && val !== undefined ? formatCurrency(val) : <span className="text-slate-300">—</span>}
                                </td>
                              );
                            })}
                          </tr>
                        ))}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
    </MainLayout>
  );
}
