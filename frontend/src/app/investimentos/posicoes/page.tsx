'use client';

import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import MainLayout from '@/components/layout/MainLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { investmentsApi, accountsApi, type InvestmentPosition } from '@/lib/api';
import { formatCurrency, formatDate } from '@/lib/utils';
import { ArrowLeft, Filter, ChevronDown, ChevronRight } from 'lucide-react';

const ASSET_CLASS_LABELS: Record<string, string> = {
  RENDA_FIXA: 'Renda Fixa',
  POS_FIXADO: 'Pós-fixado',
  PRE_FIXADO: 'Pré-fixado',
  INFLACAO: 'Inflação',
  MULTIMERCADO: 'Multimercado',
  RENDA_VARIAVEL: 'Renda Variável',
  FII: 'FII',
  CRIPTO: 'Cripto',
  CAMBIAL: 'Cambial',
  PREVIDENCIA: 'Previdência',
  ALTERNATIVOS: 'Alternativos',
  CAIXA: 'Caixa',
  // o backend retorna o code em lowercase via .value (AssetClassCode é Enum string lowercase)
  renda_fixa: 'Renda Fixa',
  pos_fixado: 'Pós-fixado',
  pre_fixado: 'Pré-fixado',
  inflacao: 'Inflação',
  multimercado: 'Multimercado',
  renda_variavel: 'Renda Variável',
  fii: 'FII',
  cripto: 'Cripto',
  cambial: 'Cambial',
  previdencia: 'Previdência',
  alternativos: 'Alternativos',
  caixa: 'Caixa',
};

function classLabel(code: string | null): string {
  if (!code) return '—';
  return ASSET_CLASS_LABELS[code] || ASSET_CLASS_LABELS[code.toLowerCase()] || code;
}

interface AccountGroup {
  accountId: number | null;
  accountName: string;
  snapshotDate: string | null;
  positions: InvestmentPosition[];
  totalValue: number;
  totalInvested: number;
}

export default function PosicoesPage() {
  const [accountId, setAccountId] = useState<number | undefined>(undefined);
  const [classFilter, setClassFilter] = useState<string>('');
  const [sortBy, setSortBy] = useState<'value' | 'name' | 'class'>('value');
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());

  const { data: accounts = [] } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
  });

  const investmentAccounts = accounts.filter((a) => a.account_type === 'investment');

  const { data: positions = [], isLoading, error } = useQuery({
    queryKey: ['investment-positions', accountId],
    queryFn: () => investmentsApi.listCurrentPositions(accountId),
  });

  // Aplicar filtro de classe
  const filteredPositions = useMemo(() => {
    if (!classFilter) return positions;
    return positions.filter((p) => p.asset_class_code === classFilter);
  }, [positions, classFilter]);

  // Agrupar por conta
  const groups: AccountGroup[] = useMemo(() => {
    const map = new Map<string, AccountGroup>();
    for (const p of filteredPositions) {
      const key = `${p.account_id ?? 'na'}_${p.snapshot_date ?? 'na'}`;
      if (!map.has(key)) {
        map.set(key, {
          accountId: p.account_id,
          accountName: p.account_name || 'Sem conta',
          snapshotDate: p.snapshot_date,
          positions: [],
          totalValue: 0,
          totalInvested: 0,
        });
      }
      const g = map.get(key)!;
      g.positions.push(p);
      g.totalValue += Number(p.value) || 0;
      g.totalInvested += Number(p.value_invested) || 0;
    }
    // Ordenar posições internas + ordenar grupos
    const list = Array.from(map.values());
    for (const g of list) {
      g.positions.sort((a: InvestmentPosition, b: InvestmentPosition) => {
        if (sortBy === 'value') return (Number(b.value) || 0) - (Number(a.value) || 0);
        if (sortBy === 'class') return classLabel(a.asset_class_code).localeCompare(classLabel(b.asset_class_code));
        return (a.asset_name || '').localeCompare(b.asset_name || '');
      });
    }
    return list.sort((a, b) => b.totalValue - a.totalValue);
  }, [filteredPositions, sortBy]);

  // Total geral
  const grandTotal = groups.reduce((s, g) => s + g.totalValue, 0);
  const grandInvested = groups.reduce((s, g) => s + g.totalInvested, 0);

  const uniqueClasses = useMemo(
    () => Array.from(new Set(positions.map((p) => p.asset_class_code).filter(Boolean))) as string[],
    [positions]
  );

  const toggleCollapsed = (idx: number) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  return (
    <MainLayout>
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <Link href="/investimentos" className="p-2 rounded-lg hover:bg-slate-100">
            <ArrowLeft className="h-4 w-4 text-slate-500" />
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Posições</h1>
            <p className="text-slate-500 text-sm">Validação de saldos por conta — agrupado por banco</p>
          </div>
        </div>

        {/* Filtros + total geral */}
        <Card>
          <CardContent>
            <div className="flex flex-wrap gap-3 items-end">
              <div>
                <label className="text-xs text-slate-500 mb-1 block">Conta</label>
                <select
                  value={accountId || ''}
                  onChange={(e) => setAccountId(e.target.value ? parseInt(e.target.value) : undefined)}
                  className="px-3 py-2 text-sm rounded-lg border border-slate-200 bg-white min-w-[200px]"
                >
                  <option value="">Todas</option>
                  {investmentAccounts.map((a) => (
                    <option key={a.id} value={a.id}>{a.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-xs text-slate-500 mb-1 block">Classe</label>
                <select
                  value={classFilter}
                  onChange={(e) => setClassFilter(e.target.value)}
                  className="px-3 py-2 text-sm rounded-lg border border-slate-200 bg-white min-w-[160px]"
                >
                  <option value="">Todas</option>
                  {uniqueClasses.map((c) => (
                    <option key={c} value={c}>{classLabel(c)}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-xs text-slate-500 mb-1 block">Ordenar ativos por</label>
                <select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value as 'value' | 'name' | 'class')}
                  className="px-3 py-2 text-sm rounded-lg border border-slate-200 bg-white"
                >
                  <option value="value">Valor</option>
                  <option value="class">Classe</option>
                  <option value="name">Nome</option>
                </select>
              </div>
              <div className="ml-auto text-right">
                <p className="text-xs text-slate-500">Total geral</p>
                <p className="text-2xl font-bold text-slate-900 tabular-nums">{formatCurrency(grandTotal)}</p>
                {grandInvested > 0 && (
                  <p className="text-xs text-slate-500">
                    Aportado: <span className="tabular-nums">{formatCurrency(grandInvested)}</span>
                  </p>
                )}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Conteúdo */}
        {isLoading ? (
          <SkeletonCard />
        ) : error ? (
          <Card>
            <CardContent>
              <div className="py-8 text-center text-rose-600">
                <p className="text-sm font-medium">Erro ao carregar posições</p>
                <p className="text-xs mt-1">{(error as Error).message}</p>
              </div>
            </CardContent>
          </Card>
        ) : groups.length === 0 ? (
          <Card>
            <CardContent>
              <div className="flex flex-col items-center justify-center py-12 text-slate-400">
                <Filter className="h-10 w-10 mb-3 opacity-40" />
                <p className="text-sm">Nenhuma posição encontrada</p>
              </div>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-4">
            {groups.map((g, idx) => {
              const isCollapsed = collapsed.has(idx);
              const yieldValue = g.totalValue - g.totalInvested;
              const yieldPct = g.totalInvested > 0 ? (yieldValue / g.totalInvested) * 100 : null;
              return (
                <Card key={`${g.accountId}-${g.snapshotDate}-${idx}`}>
                  <button
                    onClick={() => toggleCollapsed(idx)}
                    className="w-full px-5 py-4 flex items-center gap-3 hover:bg-slate-50 transition-colors text-left rounded-t-2xl"
                  >
                    <span className="text-slate-400">
                      {isCollapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                    </span>
                    <div className="flex-1">
                      <p className="text-sm font-semibold text-slate-800">{g.accountName}</p>
                      <p className="text-xs text-slate-500">
                        Snapshot de {g.snapshotDate ? formatDate(g.snapshotDate) : '—'} ·{' '}
                        {g.positions.length} {g.positions.length === 1 ? 'posição' : 'posições'}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-lg font-bold text-slate-900 tabular-nums">{formatCurrency(g.totalValue)}</p>
                      {g.totalInvested > 0 && (
                        <p className={`text-xs tabular-nums ${yieldValue >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                          {yieldValue >= 0 ? '+' : ''}
                          {formatCurrency(yieldValue)}
                          {yieldPct !== null && (
                            <span className="ml-1 text-slate-400">({yieldPct >= 0 ? '+' : ''}{yieldPct.toFixed(2)}%)</span>
                          )}
                        </p>
                      )}
                    </div>
                  </button>

                  {!isCollapsed && (
                    <div className="border-t border-slate-100">
                      <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                          <thead className="bg-slate-50 border-b border-slate-200">
                            <tr>
                              <th className="text-left px-4 py-2.5 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Ativo</th>
                              <th className="text-left px-4 py-2.5 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Classe</th>
                              <th className="text-right px-4 py-2.5 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Valor (R$)</th>
                              <th className="text-right px-4 py-2.5 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Aportado</th>
                              <th className="text-right px-4 py-2.5 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Rent. (%)</th>
                              <th className="text-right px-4 py-2.5 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Aloc.</th>
                              <th className="text-left px-4 py-2.5 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Vencim.</th>
                              <th className="text-left px-4 py-2.5 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Taxa</th>
                            </tr>
                          </thead>
                          <tbody>
                            {g.positions.map((p) => {
                              const v = Number(p.value) || 0;
                              const vi = p.value_invested != null ? Number(p.value_invested) : null;
                              const yPct = p.yield_net_pct != null ? Number(p.yield_net_pct) : null;
                              const alloc = p.allocation_pct != null ? Number(p.allocation_pct) : null;
                              return (
                                <tr key={p.id} className="border-b border-slate-100 hover:bg-slate-50">
                                  <td className="px-4 py-2.5 text-slate-800 font-medium">{p.asset_name || '—'}</td>
                                  <td className="px-4 py-2.5 text-slate-600 text-xs">{classLabel(p.asset_class_code)}</td>
                                  <td className="px-4 py-2.5 text-right tabular-nums text-slate-800 font-medium">{formatCurrency(v)}</td>
                                  <td className="px-4 py-2.5 text-right tabular-nums text-slate-500">{vi != null ? formatCurrency(vi) : '—'}</td>
                                  <td className={`px-4 py-2.5 text-right tabular-nums ${(yPct || 0) >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                                    {yPct != null ? `${yPct >= 0 ? '+' : ''}${yPct.toFixed(2)}%` : '—'}
                                  </td>
                                  <td className="px-4 py-2.5 text-right tabular-nums text-slate-500">{alloc != null ? `${alloc.toFixed(2)}%` : '—'}</td>
                                  <td className="px-4 py-2.5 text-slate-500 text-xs">{p.maturity_date ? formatDate(p.maturity_date) : '—'}</td>
                                  <td className="px-4 py-2.5 text-slate-500 text-xs">{p.contracted_rate || '—'}</td>
                                </tr>
                              );
                            })}
                          </tbody>
                          <tfoot className="bg-slate-50">
                            <tr>
                              <td className="px-4 py-2.5 text-sm font-bold text-slate-700" colSpan={2}>
                                Subtotal {g.accountName}
                              </td>
                              <td className="px-4 py-2.5 text-right text-sm font-bold tabular-nums text-slate-900">{formatCurrency(g.totalValue)}</td>
                              <td className="px-4 py-2.5 text-right text-sm font-bold tabular-nums text-slate-700">
                                {g.totalInvested > 0 ? formatCurrency(g.totalInvested) : '—'}
                              </td>
                              <td className={`px-4 py-2.5 text-right text-sm font-bold tabular-nums ${yieldValue >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                                {yieldPct !== null ? `${yieldPct >= 0 ? '+' : ''}${yieldPct.toFixed(2)}%` : '—'}
                              </td>
                              <td colSpan={3}></td>
                            </tr>
                          </tfoot>
                        </table>
                      </div>
                    </div>
                  )}
                </Card>
              );
            })}
          </div>
        )}
      </div>
    </MainLayout>
  );
}
