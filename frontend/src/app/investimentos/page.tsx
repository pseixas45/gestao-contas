'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import MainLayout from '@/components/layout/MainLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import StatCard from '@/components/ui/StatCard';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { investmentsApi } from '@/lib/api';
import { formatCurrency } from '@/lib/utils';
import {
  Wallet,
  TrendingUp,
  ArrowUpRight,
  ArrowDownRight,
  PiggyBank,
  Target,
  Activity,
  Shield,
  Droplets,
  LineChart as LineChartIcon,
} from 'lucide-react';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  PieChart,
  Pie,
  Cell,
  Legend,
  BarChart,
  Bar,
} from 'recharts';

const LIQUIDITY_LABELS: Record<string, string> = {
  imediato: 'Imediato (D+0)',
  d1: 'D+1',
  ate_30d: 'Até 30 dias',
  '31_a_60d': '31 a 60 dias',
  '61_a_360d': '61 a 360 dias',
  '361_a_720d': '1 a 2 anos',
  acima_720d: 'Acima de 2 anos',
};

function formatCompactCurrency(value: number): string {
  if (Math.abs(value) >= 1_000_000) return `R$ ${(value / 1_000_000).toFixed(2)}M`;
  if (Math.abs(value) >= 1000) return `R$ ${(value / 1000).toFixed(1)}k`;
  return formatCurrency(value);
}

function formatMonthYear(iso: string): string {
  const [y, m] = iso.split('-');
  const months = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
  return `${months[parseInt(m) - 1]}/${y.slice(2)}`;
}

export default function InvestimentosDashboardPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['investments-dashboard'],
    queryFn: () => investmentsApi.dashboard(),
  });

  const { data: goalsProgress } = useQuery({
    queryKey: ['investments-goals-progress'],
    queryFn: () => investmentsApi.goalsProgress(),
  });

  if (isLoading || !data) {
    return (
      <MainLayout>
        <div className="space-y-6">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Investimentos</h1>
            <p className="text-slate-500">Visão geral da sua carteira</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {[1, 2, 3, 4].map((i) => <SkeletonCard key={i} />)}
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <SkeletonCard /><SkeletonCard />
          </div>
        </div>
      </MainLayout>
    );
  }

  const { overview, allocation_by_class, allocation_by_bank, history, exposure, risk, liquidity, contributions } = data;
  const hasData = overview.total_value > 0;

  const historyChart = history.map((h) => ({
    month: formatMonthYear(h.date),
    Patrimonio: h.total_value,
    Aportado: h.total_invested,
  }));

  const contribChart = contributions
    .filter((c) => c.contribution !== null)
    .map((c) => ({
      month: formatMonthYear(c.date),
      Aporte: c.contribution || 0,
    }));

  const allocByClass = allocation_by_class.map((a) => ({
    name: a.name,
    value: a.value,
    pct: a.allocation_pct,
    color: a.color || '#6366f1',
  }));

  const allocByBank = allocation_by_bank.map((a) => ({
    name: a.name,
    value: a.value,
    pct: a.allocation_pct,
    color: a.color || '#6366f1',
  }));

  const liquidityChart = liquidity.map((b) => ({
    bucket: LIQUIDITY_LABELS[b.bucket] || b.bucket,
    pct: b.pct,
    value: b.value,
  }));

  return (
    <MainLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Investimentos</h1>
            <p className="text-slate-500 text-sm">Visão geral da sua carteira</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link href="/investimentos/posicoes" className="text-xs px-3 py-2 rounded-lg bg-white border border-slate-200 hover:bg-slate-50 font-medium text-slate-700">Posições</Link>
            <Link href="/investimentos/historico" className="text-xs px-3 py-2 rounded-lg bg-white border border-slate-200 hover:bg-slate-50 font-medium text-slate-700">Histórico</Link>
            <Link href="/investimentos/metas" className="text-xs px-3 py-2 rounded-lg bg-white border border-slate-200 hover:bg-slate-50 font-medium text-slate-700">Metas</Link>
            <Link href="/investimentos/ativos" className="text-xs px-3 py-2 rounded-lg bg-white border border-slate-200 hover:bg-slate-50 font-medium text-slate-700">Ativos</Link>
            <Link href="/investimentos/importar" className="text-xs px-3 py-2 rounded-lg bg-primary-600 text-white hover:bg-primary-700 font-medium">Importar</Link>
          </div>
        </div>

        {!hasData && (
          <Card>
            <CardContent>
              <div className="flex flex-col items-center justify-center py-12 text-slate-500">
                <PiggyBank className="h-12 w-12 mb-3 opacity-40" />
                <p className="text-sm font-medium">Nenhum dado de investimento ainda</p>
                <p className="text-xs text-slate-400 mt-1 mb-4">Importe seus extratos para começar.</p>
                <Link href="/investimentos/importar" className="text-xs px-3 py-2 rounded-lg bg-primary-600 text-white hover:bg-primary-700 font-medium">
                  Importar extrato
                </Link>
              </div>
            </CardContent>
          </Card>
        )}

        {hasData && (
          <>
            {/* StatCards */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <StatCard
                title="Patrimônio Total"
                value={formatCurrency(overview.total_value)}
                subtitle={`${overview.accounts.length} conta${overview.accounts.length !== 1 ? 's' : ''}`}
                icon={Wallet}
                color="primary"
              />
              <StatCard
                title="Variação no Mês"
                value={overview.monthly_change != null ? formatCurrency(overview.monthly_change) : '—'}
                subtitle={overview.monthly_change_pct != null ? `${overview.monthly_change_pct >= 0 ? '+' : ''}${overview.monthly_change_pct.toFixed(2)}%` : 'Sem comparação'}
                icon={overview.monthly_change != null && overview.monthly_change >= 0 ? ArrowUpRight : ArrowDownRight}
                color={overview.monthly_change != null && overview.monthly_change >= 0 ? 'emerald' : 'rose'}
              />
              <StatCard
                title="Rentabilidade Total"
                value={`${overview.yield_pct >= 0 ? '+' : ''}${overview.yield_pct.toFixed(2)}%`}
                subtitle={formatCurrency(overview.yield_value)}
                icon={TrendingUp}
                color={overview.yield_pct >= 0 ? 'emerald' : 'rose'}
              />
              <StatCard
                title="Aporte do Mês"
                value={overview.monthly_contribution != null ? formatCurrency(overview.monthly_contribution) : '—'}
                subtitle="Líquido (capital)"
                icon={PiggyBank}
                color="sky"
              />
            </div>

            {/* Goals progress */}
            {goalsProgress && goalsProgress.length > 0 && (
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle>Progresso das Metas</CardTitle>
                    <Link href="/investimentos/metas" className="text-xs text-primary-600 hover:text-primary-700 font-medium">
                      Gerenciar
                    </Link>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    {goalsProgress.map((g) => {
                      const pct = Math.min(100, Math.max(0, g.progress_pct));
                      const color = pct >= 100 ? 'bg-emerald-500' : pct >= 70 ? 'bg-sky-500' : 'bg-amber-500';
                      return (
                        <div key={g.id}>
                          <div className="flex items-center justify-between mb-1.5">
                            <div>
                              <p className="text-sm font-medium text-slate-800">{g.name}</p>
                              <p className="text-xs text-slate-400">
                                {g.type === 'PORTFOLIO_TOTAL' && `Patrimônio alvo: ${formatCurrency(g.target_value || 0)}`}
                                {g.type === 'MONTHLY_CONTRIBUTION' && `Aporte mensal: ${formatCurrency(g.target_value || 0)}`}
                                {g.type === 'MIN_YIELD' && `Rentabilidade mínima: ${(g.target_value || 0).toFixed(2)}%`}
                                {g.type === 'ALLOCATION_BY_CLASS' && `${g.target_class_name}: ${(g.target_value || 0).toFixed(2)}%`}
                              </p>
                            </div>
                            <div className="text-right">
                              <p className="text-sm font-semibold text-slate-800">{g.progress_pct.toFixed(1)}%</p>
                              <p className="text-xs text-slate-400">
                                {g.type === 'MIN_YIELD' || g.type === 'ALLOCATION_BY_CLASS'
                                  ? `${g.current.toFixed(2)}%`
                                  : formatCurrency(g.current)}
                              </p>
                            </div>
                          </div>
                          <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                            <div className={`${color} h-full rounded-full transition-all`} style={{ width: `${pct}%` }} />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Histórico + Aportes */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <Card>
                <CardHeader>
                  <CardTitle>Evolução do Patrimônio</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="h-72">
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={historyChart}>
                        <defs>
                          <linearGradient id="patrGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#6366f1" stopOpacity={0.25} />
                            <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                          </linearGradient>
                          <linearGradient id="aportGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#10b981" stopOpacity={0.2} />
                            <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                        <XAxis dataKey="month" tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} />
                        <YAxis tickFormatter={(v) => formatCompactCurrency(v)} tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} width={70} />
                        <Tooltip formatter={(v: number) => formatCurrency(v)} contentStyle={{ borderRadius: '12px', border: '1px solid #e2e8f0', fontSize: '13px' }} />
                        <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: '12px', paddingTop: '8px' }} />
                        <Area type="monotone" dataKey="Aportado" stroke="#10b981" strokeWidth={2} fill="url(#aportGrad)" />
                        <Area type="monotone" dataKey="Patrimonio" stroke="#6366f1" strokeWidth={2} fill="url(#patrGrad)" />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Aportes Mensais</CardTitle>
                </CardHeader>
                <CardContent>
                  {contribChart.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-12 text-slate-400">
                      <PiggyBank className="h-10 w-10 mb-3 opacity-40" />
                      <p className="text-sm">Sem aportes registrados</p>
                    </div>
                  ) : (
                    <div className="h-72">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={contribChart}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                          <XAxis dataKey="month" tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} />
                          <YAxis tickFormatter={(v) => formatCompactCurrency(v)} tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} width={70} />
                          <Tooltip formatter={(v: number) => formatCurrency(v)} contentStyle={{ borderRadius: '12px', border: '1px solid #e2e8f0', fontSize: '13px' }} />
                          <Bar dataKey="Aporte" radius={[4, 4, 0, 0]}>
                            {contribChart.map((c, i) => (
                              <Cell key={i} fill={c.Aporte >= 0 ? '#10b981' : '#f43f5e'} />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>

            {/* Alocação */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <Card>
                <CardHeader>
                  <CardTitle>Alocação por Classe</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="h-72">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie data={allocByClass} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={60} outerRadius={100} paddingAngle={2}>
                          {allocByClass.map((d, i) => <Cell key={i} fill={d.color} />)}
                        </Pie>
                        <Tooltip formatter={(v: number) => formatCurrency(v)} contentStyle={{ borderRadius: '12px', border: '1px solid #e2e8f0', fontSize: '13px' }} />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                  <div className="mt-3 space-y-1.5">
                    {allocByClass.slice(0, 6).map((a, i) => (
                      <div key={i} className="flex items-center justify-between text-xs">
                        <div className="flex items-center gap-2">
                          <span className="w-3 h-3 rounded" style={{ backgroundColor: a.color }} />
                          <span className="text-slate-700">{a.name}</span>
                        </div>
                        <span className="text-slate-500 tabular-nums">{a.pct.toFixed(1)}%</span>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Alocação por Banco</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="h-72">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie data={allocByBank} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={60} outerRadius={100} paddingAngle={2}>
                          {allocByBank.map((d, i) => <Cell key={i} fill={d.color} />)}
                        </Pie>
                        <Tooltip formatter={(v: number) => formatCurrency(v)} contentStyle={{ borderRadius: '12px', border: '1px solid #e2e8f0', fontSize: '13px' }} />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                  <div className="mt-3 space-y-1.5">
                    {allocByBank.map((a, i) => (
                      <div key={i} className="flex items-center justify-between text-xs">
                        <div className="flex items-center gap-2">
                          <span className="w-3 h-3 rounded" style={{ backgroundColor: a.color }} />
                          <span className="text-slate-700">{a.name}</span>
                        </div>
                        <span className="text-slate-500 tabular-nums">{a.pct.toFixed(1)}%</span>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Risco / Liquidez / Exposição */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Shield className="h-4 w-4 text-amber-600" /> Risco
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-center mb-4">
                    <p className="text-3xl font-bold text-slate-900">{risk.weighted_avg.toFixed(2)}</p>
                    <p className="text-xs text-slate-500">Risco médio (1-5)</p>
                  </div>
                  <div className="space-y-2">
                    {Object.entries(risk.distribution).sort().map(([k, v]) => {
                      const lvl = k.replace('level_', '');
                      const colors = ['', 'bg-emerald-500', 'bg-sky-500', 'bg-amber-500', 'bg-orange-500', 'bg-rose-500'];
                      return (
                        <div key={k}>
                          <div className="flex justify-between text-xs mb-1">
                            <span className="text-slate-600">Nível {lvl}</span>
                            <span className="text-slate-500 tabular-nums">{v.toFixed(1)}%</span>
                          </div>
                          <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                            <div className={`${colors[parseInt(lvl)] || 'bg-slate-500'} h-full rounded-full`} style={{ width: `${v}%` }} />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Droplets className="h-4 w-4 text-sky-600" /> Liquidez
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    {liquidityChart.filter((b) => b.pct > 0).map((b, i) => (
                      <div key={i}>
                        <div className="flex justify-between text-xs mb-1">
                          <span className="text-slate-600">{b.bucket}</span>
                          <span className="text-slate-500 tabular-nums">{b.pct.toFixed(1)}%</span>
                        </div>
                        <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                          <div className="bg-sky-500 h-full rounded-full" style={{ width: `${b.pct}%` }} />
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Activity className="h-4 w-4 text-violet-600" /> Exposição
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    {[
                      { label: 'Inflação', pct: exposure.inflation_pct, color: 'bg-orange-500' },
                      { label: 'Câmbio', pct: exposure.currency_pct, color: 'bg-emerald-500' },
                      { label: 'Renda Variável', pct: exposure.equity_pct, color: 'bg-rose-500' },
                      { label: 'Renda Fixa', pct: exposure.fixed_income_pct, color: 'bg-sky-500' },
                      { label: 'Cripto', pct: exposure.crypto_pct, color: 'bg-amber-500' },
                      { label: 'Alternativos', pct: exposure.private_equity_pct, color: 'bg-violet-500' },
                    ].map((e, i) => (
                      <div key={i}>
                        <div className="flex justify-between text-xs mb-1">
                          <span className="text-slate-600">{e.label}</span>
                          <span className="text-slate-500 tabular-nums">{e.pct.toFixed(1)}%</span>
                        </div>
                        <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                          <div className={`${e.color} h-full rounded-full`} style={{ width: `${Math.min(100, e.pct)}%` }} />
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </div>
          </>
        )}
      </div>
    </MainLayout>
  );
}
