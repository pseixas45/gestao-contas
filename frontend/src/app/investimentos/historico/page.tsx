'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import MainLayout from '@/components/layout/MainLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { investmentsApi, accountsApi } from '@/lib/api';
import { formatCurrency } from '@/lib/utils';
import { ArrowLeft, Trash2 } from 'lucide-react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts';

function formatCompactCurrency(value: number): string {
  if (Math.abs(value) >= 1_000_000) return `R$ ${(value / 1_000_000).toFixed(2)}M`;
  if (Math.abs(value) >= 1000) return `R$ ${(value / 1000).toFixed(1)}k`;
  return formatCurrency(value);
}

export default function HistoricoPage() {
  const [accountId, setAccountId] = useState<number | undefined>(undefined);

  const { data: accounts = [] } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
  });

  const investmentAccounts = accounts.filter((a) => a.account_type === 'investment');

  const { data: history = [], isLoading } = useQuery({
    queryKey: ['investment-history', accountId],
    queryFn: () => investmentsApi.history(accountId),
  });

  const { data: snapshots = [] } = useQuery({
    queryKey: ['investment-snapshots', accountId],
    queryFn: () => investmentsApi.listSnapshots(accountId),
  });

  const handleDeleteSnapshot = async (id: number) => {
    if (!confirm('Remover esta snapshot? Os ativos não serão afetados.')) return;
    await investmentsApi.deleteSnapshot(id);
    window.location.reload();
  };

  const chartData = history.map((h) => ({
    date: h.date,
    Patrimonio: h.total_value,
    Aportado: h.total_invested,
    Rendimento: h.yield_value,
  }));

  return (
    <MainLayout>
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <Link href="/investimentos" className="p-2 rounded-lg hover:bg-slate-100">
            <ArrowLeft className="h-4 w-4 text-slate-500" />
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Histórico</h1>
            <p className="text-slate-500 text-sm">Evolução do patrimônio e snapshots</p>
          </div>
        </div>

        {/* Filtro */}
        <div className="flex items-center gap-3">
          <label className="text-xs text-slate-500">Conta:</label>
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

        {/* Gráfico */}
        <Card>
          <CardHeader>
            <CardTitle>Evolução do Patrimônio</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-80 flex items-center justify-center">
                <div className="w-8 h-8 border-3 border-primary-200 border-t-primary-600 rounded-full animate-spin" />
              </div>
            ) : chartData.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-slate-400">
                <p className="text-sm">Sem histórico disponível</p>
              </div>
            ) : (
              <div className="h-80">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                    <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} />
                    <YAxis tickFormatter={(v) => formatCompactCurrency(v)} tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} width={70} />
                    <Tooltip formatter={(v: number) => formatCurrency(v)} contentStyle={{ borderRadius: '12px', border: '1px solid #e2e8f0', fontSize: '13px' }} />
                    <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: '12px' }} />
                    <Line type="monotone" dataKey="Patrimonio" stroke="#6366f1" strokeWidth={2} dot={{ r: 3 }} />
                    <Line type="monotone" dataKey="Aportado" stroke="#10b981" strokeWidth={2} dot={{ r: 3 }} />
                    <Line type="monotone" dataKey="Rendimento" stroke="#f59e0b" strokeWidth={2} dot={{ r: 3 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Tabela de snapshots */}
        <Card>
          <CardHeader>
            <CardTitle>Snapshots ({snapshots.length})</CardTitle>
          </CardHeader>
          <CardContent className="!p-0">
            {snapshots.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-slate-400">
                <p className="text-sm">Nenhuma snapshot registrada</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 border-b border-slate-200">
                    <tr>
                      <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Data</th>
                      <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Conta</th>
                      <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Banco</th>
                      <th className="text-right px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Patrimônio</th>
                      <th className="text-right px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Aportado</th>
                      <th className="text-right px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Rendimento</th>
                      <th className="text-right px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Posições</th>
                      <th className="text-right px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {snapshots.map((s) => {
                      const yld = (s.total_value || 0) - (s.total_invested || 0);
                      return (
                        <tr key={s.id} className="border-b border-slate-100 hover:bg-slate-50">
                          <td className="px-4 py-3 text-slate-800 font-medium">{s.snapshot_date}</td>
                          <td className="px-4 py-3 text-slate-700">{s.account_name || '—'}</td>
                          <td className="px-4 py-3 text-slate-500 text-xs">{s.bank_name || '—'}</td>
                          <td className="px-4 py-3 text-right tabular-nums text-slate-800">{formatCurrency(s.total_value)}</td>
                          <td className="px-4 py-3 text-right tabular-nums text-slate-600">{s.total_invested != null ? formatCurrency(s.total_invested) : '—'}</td>
                          <td className={`px-4 py-3 text-right tabular-nums ${yld >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                            {formatCurrency(yld)}
                          </td>
                          <td className="px-4 py-3 text-right tabular-nums text-slate-500">{s.positions_count}</td>
                          <td className="px-4 py-3 text-right">
                            <button
                              onClick={() => handleDeleteSnapshot(s.id)}
                              className="p-1.5 rounded-lg hover:bg-rose-50 text-rose-500 transition-colors"
                              title="Remover snapshot"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
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
      </div>
    </MainLayout>
  );
}
