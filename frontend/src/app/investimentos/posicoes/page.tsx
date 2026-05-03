'use client';

import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import MainLayout from '@/components/layout/MainLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { investmentsApi, accountsApi } from '@/lib/api';
import { formatCurrency } from '@/lib/utils';
import { ArrowLeft, Filter } from 'lucide-react';

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
};

export default function PosicoesPage() {
  const [accountId, setAccountId] = useState<number | undefined>(undefined);
  const [classFilter, setClassFilter] = useState<string>('');
  const [sortBy, setSortBy] = useState<'value' | 'yield' | 'name'>('value');

  const { data: accounts = [] } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
  });

  const investmentAccounts = accounts.filter((a) => a.account_type === 'investment');

  const { data: positions = [], isLoading } = useQuery({
    queryKey: ['investment-positions', accountId],
    queryFn: () => investmentsApi.listCurrentPositions(accountId),
  });

  const filtered = useMemo(() => {
    let list = positions;
    if (classFilter) list = list.filter((p) => p.asset_class_code === classFilter);
    list = [...list].sort((a, b) => {
      if (sortBy === 'value') return (b.value || 0) - (a.value || 0);
      if (sortBy === 'yield') return (b.yield_net_pct || 0) - (a.yield_net_pct || 0);
      return (a.asset_name || '').localeCompare(b.asset_name || '');
    });
    return list;
  }, [positions, classFilter, sortBy]);

  const totalValue = filtered.reduce((s, p) => s + (p.value || 0), 0);
  const totalInvested = filtered.reduce((s, p) => s + (p.value_invested || 0), 0);
  const totalYield = totalValue - totalInvested;

  const uniqueClasses = Array.from(new Set(positions.map((p) => p.asset_class_code).filter(Boolean))) as string[];

  return (
    <MainLayout>
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <Link href="/investimentos" className="p-2 rounded-lg hover:bg-slate-100">
            <ArrowLeft className="h-4 w-4 text-slate-500" />
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Posições</h1>
            <p className="text-slate-500 text-sm">Detalhamento de cada ativo da carteira</p>
          </div>
        </div>

        {/* Filtros */}
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
                    <option key={c} value={c}>{ASSET_CLASS_LABELS[c] || c}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-xs text-slate-500 mb-1 block">Ordenar por</label>
                <select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value as 'value' | 'yield' | 'name')}
                  className="px-3 py-2 text-sm rounded-lg border border-slate-200 bg-white"
                >
                  <option value="value">Valor</option>
                  <option value="yield">Rentabilidade</option>
                  <option value="name">Nome</option>
                </select>
              </div>
              <div className="ml-auto text-right">
                <p className="text-xs text-slate-500">Total filtrado</p>
                <p className="text-lg font-bold text-slate-900">{formatCurrency(totalValue)}</p>
                <p className={`text-xs ${totalYield >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                  {totalYield >= 0 ? '+' : ''}{formatCurrency(totalYield)}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Tabela */}
        {isLoading ? (
          <SkeletonCard />
        ) : filtered.length === 0 ? (
          <Card>
            <CardContent>
              <div className="flex flex-col items-center justify-center py-12 text-slate-400">
                <Filter className="h-10 w-10 mb-3 opacity-40" />
                <p className="text-sm">Nenhuma posição encontrada</p>
              </div>
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardContent className="!p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 border-b border-slate-200">
                    <tr>
                      <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Ativo</th>
                      <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Classe</th>
                      <th className="text-right px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Valor</th>
                      <th className="text-right px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Aportado</th>
                      <th className="text-right px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Rent. (%)</th>
                      <th className="text-right px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Aloc.</th>
                      <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Vencim.</th>
                      <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Taxa</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((p) => (
                      <tr key={p.id} className="border-b border-slate-100 hover:bg-slate-50">
                        <td className="px-4 py-3 text-slate-800 font-medium">{p.asset_name || '—'}</td>
                        <td className="px-4 py-3 text-slate-600 text-xs">{p.asset_class_code ? (ASSET_CLASS_LABELS[p.asset_class_code] || p.asset_class_code) : '—'}</td>
                        <td className="px-4 py-3 text-right tabular-nums text-slate-800">{formatCurrency(p.value || 0)}</td>
                        <td className="px-4 py-3 text-right tabular-nums text-slate-500">{p.value_invested != null ? formatCurrency(p.value_invested) : '—'}</td>
                        <td className={`px-4 py-3 text-right tabular-nums ${(p.yield_net_pct || 0) >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                          {p.yield_net_pct != null ? `${p.yield_net_pct >= 0 ? '+' : ''}${p.yield_net_pct.toFixed(2)}%` : '—'}
                        </td>
                        <td className="px-4 py-3 text-right tabular-nums text-slate-500">
                          {p.allocation_pct != null ? `${p.allocation_pct.toFixed(2)}%` : '—'}
                        </td>
                        <td className="px-4 py-3 text-slate-500 text-xs">{p.maturity_date || '—'}</td>
                        <td className="px-4 py-3 text-slate-500 text-xs">{p.contracted_rate || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot className="bg-slate-50">
                    <tr>
                      <td className="px-4 py-3 text-sm font-bold text-slate-700" colSpan={2}>Total</td>
                      <td className="px-4 py-3 text-right text-sm font-bold tabular-nums text-slate-900">{formatCurrency(totalValue)}</td>
                      <td className="px-4 py-3 text-right text-sm font-bold tabular-nums text-slate-700">{formatCurrency(totalInvested)}</td>
                      <td className={`px-4 py-3 text-right text-sm font-bold tabular-nums ${totalYield >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                        {totalInvested > 0 ? `${(totalYield / totalInvested * 100).toFixed(2)}%` : '—'}
                      </td>
                      <td colSpan={3}></td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </MainLayout>
  );
}
