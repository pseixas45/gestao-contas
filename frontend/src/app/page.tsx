'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import MainLayout from '@/components/layout/MainLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import StatCard from '@/components/ui/StatCard';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { reportsApi, projectionsApi, accountsApi, importsApi, investmentsApi } from '@/lib/api';
import { formatCurrency, getAccountTypeLabel } from '@/lib/utils';
import {
  Wallet,
  TrendingUp,
  TrendingDown,
  AlertCircle,
  ArrowUpRight,
  ArrowDownRight,
  ChevronLeft,
  ChevronRight,
  PiggyBank,
} from 'lucide-react';
import Link from 'next/link';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  AreaChart,
  Area,
  ReferenceLine,
} from 'recharts';

const MONTH_LABELS: Record<string, string> = {
  '01': 'Jan', '02': 'Fev', '03': 'Mar', '04': 'Abr',
  '05': 'Mai', '06': 'Jun', '07': 'Jul', '08': 'Ago',
  '09': 'Set', '10': 'Out', '11': 'Nov', '12': 'Dez',
};

function formatMonthLabel(month: string): string {
  const [, m] = month.split('-');
  return MONTH_LABELS[m] || m;
}

function formatCompactCurrency(value: number): string {
  if (Math.abs(value) >= 1000) {
    return `R$ ${(value / 1000).toFixed(1)}k`;
  }
  return formatCurrency(value);
}

export default function DashboardPage() {
  const now = new Date();
  const todayMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  const monthNames = [
    'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
  ];
  const greeting = now.getHours() < 12 ? 'Bom dia' : now.getHours() < 18 ? 'Boa tarde' : 'Boa noite';

  const [selectedMonth, setSelectedMonth] = useState(todayMonth);
  const [projAccountId, setProjAccountId] = useState<number | null>(null);

  const navigateMonth = (direction: number) => {
    const [y, m] = selectedMonth.split('-').map(Number);
    const d = new Date(y, m - 1 + direction, 1);
    setSelectedMonth(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`);
  };

  const selectedMonthLabel = (() => {
    const [y, m] = selectedMonth.split('-').map(Number);
    return `${monthNames[m - 1]} ${y}`;
  })();

  const { data: summary, isLoading } = useQuery({
    queryKey: ['dashboard-summary', selectedMonth],
    queryFn: () => reportsApi.dashboardSummary(selectedMonth),
    refetchInterval: 60000,
  });

  const { data: pendingImports } = useQuery({
    queryKey: ['imports-pending-count'],
    queryFn: () => importsApi.pendingCount(),
    refetchInterval: 60000,
  });

  const { data: accounts = [] } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
  });

  const { data: monthInvestment } = useQuery({
    queryKey: ['investments-contribution-month', selectedMonth],
    queryFn: () => investmentsApi.contributionForMonth(selectedMonth),
  });

  // Auto-select Itaú (account_id=5) as default when accounts load
  const effectiveAccountId = projAccountId ?? (accounts.find(a => a.name?.toLowerCase().includes('itau') || a.name?.toLowerCase().includes('itaú'))?.id || accounts[0]?.id || null);

  const { data: projection, isLoading: projLoading } = useQuery({
    queryKey: ['dashboard-projection', effectiveAccountId, selectedMonth],
    queryFn: () => projectionsApi.getMonthly(effectiveAccountId!, selectedMonth),
    enabled: !!effectiveAccountId,
  });

  const projChartData = projection?.daily_balances.map((d) => ({
    date: d.date.slice(8),
    balance: d.balance,
    isPast: d.is_past,
  })) || [];

  if (isLoading || !summary) {
    return (
      <MainLayout>
        <div className="space-y-6">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">{greeting}</h1>
            <p className="text-slate-500">{selectedMonthLabel}</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <SkeletonCard />
            <SkeletonCard />
          </div>
        </div>
      </MainLayout>
    );
  }

  const monthBalance = summary.month_income - summary.month_expenses;

  // Separate accounts by type
  const bankAccounts = summary.accounts.filter(a => a.account_type !== 'credit_card');
  const creditCards = summary.accounts.filter(a => a.account_type === 'credit_card');

  // Evolution chart data
  const evolutionData = summary.monthly_evolution.map((m) => ({
    month: formatMonthLabel(m.month),
    Receitas: Number(m.income),
    Despesas: Number(m.expense),
    Saldo: Number(m.balance),
  }));

  return (
    <MainLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">{greeting}</h1>
            <div className="flex items-center gap-2 mt-1">
              <button
                onClick={() => navigateMonth(-1)}
                className="p-1 rounded-lg hover:bg-slate-100 transition-colors"
              >
                <ChevronLeft className="h-4 w-4 text-slate-400" />
              </button>
              <span className="text-sm font-medium text-slate-600 min-w-[120px] text-center">
                {selectedMonthLabel}
              </span>
              <button
                onClick={() => navigateMonth(1)}
                className="p-1 rounded-lg hover:bg-slate-100 transition-colors"
              >
                <ChevronRight className="h-4 w-4 text-slate-400" />
              </button>
              {selectedMonth !== todayMonth && (
                <button
                  onClick={() => setSelectedMonth(todayMonth)}
                  className="text-xs text-primary-600 hover:text-primary-700 font-medium ml-1"
                >
                  Hoje
                </button>
              )}
            </div>
          </div>
          {summary.pending_count > 0 && (
            <Link
              href="/transacoes/pendentes"
              className="inline-flex items-center gap-2 px-4 py-2 bg-amber-50 text-amber-700 rounded-xl text-sm font-medium hover:bg-amber-100 transition-colors"
            >
              <AlertCircle className="h-4 w-4" />
              {summary.pending_count} pendente{summary.pending_count > 1 ? 's' : ''}
            </Link>
          )}
        </div>

        {/* Pending imports warning */}
        {pendingImports && pendingImports.pending_count > 0 && (
          <Link
            href="/importar/historico"
            className="flex items-center gap-3 p-4 bg-amber-50 border border-amber-200 rounded-xl hover:bg-amber-100 transition-colors"
          >
            <AlertCircle className="h-5 w-5 text-amber-600 flex-shrink-0" />
            <div className="flex-1">
              <p className="text-sm font-medium text-amber-900">
                {pendingImports.pending_count} importação{pendingImports.pending_count !== 1 ? 'ões' : ''} pendente{pendingImports.pending_count !== 1 ? 's' : ''}
              </p>
              <p className="text-xs text-amber-700">
                Você fez upload mas não concluiu o processamento. Clique para ver e finalizar.
              </p>
            </div>
            <span className="text-xs text-amber-700 font-medium">Ver →</span>
          </Link>
        )}

        {/* StatCards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            title="Receitas do Mes"
            value={formatCurrency(Number(summary.month_income))}
            subtitle={selectedMonthLabel}
            icon={TrendingUp}
            color="emerald"
          />
          <StatCard
            title="Despesas do Mes"
            value={formatCurrency(Number(summary.month_expenses))}
            subtitle={selectedMonthLabel}
            icon={TrendingDown}
            color="rose"
          />
          <StatCard
            title="Balanco do Mes"
            value={formatCurrency(monthBalance)}
            subtitle={monthBalance >= 0 ? 'Positivo' : 'Negativo'}
            icon={monthBalance >= 0 ? ArrowUpRight : ArrowDownRight}
            color={monthBalance >= 0 ? 'sky' : 'amber'}
          />
          <StatCard
            title="Aplicacoes do Mes"
            value={monthInvestment?.contribution != null ? formatCurrency(monthInvestment.contribution) : '—'}
            subtitle={monthInvestment?.snapshot_date ? `Snapshot ${monthInvestment.snapshot_date}` : 'Sem snapshot'}
            icon={PiggyBank}
            color="primary"
          />
        </div>

        {/* Charts row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Projection Chart */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Projecao de Caixa</CardTitle>
                <select
                  value={effectiveAccountId || ''}
                  onChange={(e) => setProjAccountId(e.target.value ? parseInt(e.target.value) : null)}
                  className="px-2.5 py-1.5 text-xs rounded-lg border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400"
                >
                  {accounts.map((a: { id: number; name: string; bank_name?: string }) => (
                    <option key={a.id} value={a.id}>
                      {a.name}{a.bank_name ? ` (${a.bank_name})` : ''}
                    </option>
                  ))}
                </select>
              </div>
            </CardHeader>
            <CardContent>
              {projLoading ? (
                <div className="h-64 flex items-center justify-center">
                  <div className="w-8 h-8 border-3 border-primary-200 border-t-primary-600 rounded-full animate-spin" />
                </div>
              ) : projChartData.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12 text-slate-400">
                  <TrendingUp className="h-10 w-10 mb-3 opacity-40" />
                  <p className="text-sm">Sem dados de projecao</p>
                </div>
              ) : (
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={projChartData}>
                      <defs>
                        <linearGradient id="dashBalanceGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#6366f1" stopOpacity={0.15} />
                          <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                      <XAxis
                        dataKey="date"
                        tick={{ fontSize: 11, fill: '#94a3b8' }}
                        axisLine={false}
                        tickLine={false}
                      />
                      <YAxis
                        tick={{ fontSize: 11, fill: '#94a3b8' }}
                        tickFormatter={(v) => formatCompactCurrency(v)}
                        axisLine={false}
                        tickLine={false}
                        width={70}
                      />
                      <Tooltip
                        formatter={(value: number) => [formatCurrency(value), 'Saldo']}
                        labelFormatter={(label) => `Dia ${label}`}
                        contentStyle={{
                          borderRadius: '12px',
                          border: '1px solid #e2e8f0',
                          boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.05)',
                          fontSize: '13px',
                        }}
                      />
                      <ReferenceLine y={0} stroke="#e2e8f0" strokeDasharray="3 3" />
                      <Area
                        type="monotone"
                        dataKey="balance"
                        stroke="#6366f1"
                        strokeWidth={2}
                        fill="url(#dashBalanceGrad)"
                        dot={false}
                        activeDot={{ r: 4, fill: '#6366f1' }}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                  {projection && (
                    <div className="flex items-center justify-between mt-3 text-xs text-slate-500">
                      <span>Saldo fim do mes: <strong className={projection.projected_final_balance >= 0 ? 'text-emerald-600' : 'text-rose-600'}>{formatCurrency(projection.projected_final_balance)}</strong></span>
                      <Link href="/projecao" className="text-primary-600 hover:text-primary-700 font-medium">
                        Ver detalhes
                      </Link>
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Bar Chart: Monthly Evolution */}
          <Card>
            <CardHeader>
              <CardTitle>Evolucao Mensal</CardTitle>
            </CardHeader>
            <CardContent>
              {evolutionData.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12 text-slate-400">
                  <TrendingUp className="h-10 w-10 mb-3 opacity-40" />
                  <p className="text-sm">Sem dados de evolucao</p>
                </div>
              ) : (
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={evolutionData} barCategoryGap="20%">
                      <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                      <XAxis
                        dataKey="month"
                        tick={{ fontSize: 12, fill: '#64748b' }}
                        axisLine={false}
                        tickLine={false}
                      />
                      <YAxis
                        tick={{ fontSize: 11, fill: '#94a3b8' }}
                        tickFormatter={(v) => formatCompactCurrency(v)}
                        axisLine={false}
                        tickLine={false}
                        width={70}
                      />
                      <Tooltip
                        formatter={(value: number, name: string) => [formatCurrency(value), name]}
                        contentStyle={{
                          borderRadius: '12px',
                          border: '1px solid #e2e8f0',
                          boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.05)',
                          fontSize: '13px',
                        }}
                      />
                      <Legend
                        iconType="circle"
                        iconSize={8}
                        wrapperStyle={{ fontSize: '12px', paddingTop: '8px' }}
                      />
                      <Bar dataKey="Receitas" fill="#10b981" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="Despesas" fill="#f43f5e" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Accounts */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Bank Accounts */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Contas Bancarias</CardTitle>
                <Link
                  href="/contas"
                  className="text-xs text-primary-600 hover:text-primary-700 font-medium"
                >
                  Ver todas
                </Link>
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-1">
                {bankAccounts.map((acc) => (
                  <div
                    key={acc.account_id}
                    className="flex items-center gap-3 p-3 rounded-xl hover:bg-slate-50 transition-colors"
                  >
                    <div
                      className="w-9 h-9 rounded-lg flex items-center justify-center text-white text-xs font-bold flex-shrink-0"
                      style={{ backgroundColor: acc.bank_color || '#6366f1' }}
                    >
                      {acc.bank_name.slice(0, 2).toUpperCase()}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-slate-900 truncate">
                        {acc.account_name}
                      </p>
                      <p className="text-xs text-slate-400">
                        {acc.bank_name} &middot; {getAccountTypeLabel(acc.account_type)}
                      </p>
                    </div>
                    <div className="text-right flex-shrink-0">
                      <p className={`text-sm font-semibold tabular-nums ${
                        Number(acc.balance) >= 0 ? 'text-slate-900' : 'text-rose-600'
                      }`}>
                        {formatCurrency(Number(acc.balance), acc.currency as 'BRL' | 'USD' | 'EUR')}
                      </p>
                      {acc.currency !== 'BRL' && (
                        <p className="text-xs text-slate-400 tabular-nums">
                          {formatCurrency(Number(acc.balance_brl))}
                        </p>
                      )}
                    </div>
                  </div>
                ))}

                {/* Total */}
                <div className="flex items-center justify-between pt-3 mt-2 border-t border-slate-100">
                  <span className="text-sm font-medium text-slate-500">Total em BRL</span>
                  <span className={`text-sm font-bold tabular-nums ${
                    bankAccounts.reduce((s, a) => s + Number(a.balance_brl), 0) >= 0
                      ? 'text-slate-900' : 'text-rose-600'
                  }`}>
                    {formatCurrency(bankAccounts.reduce((s, a) => s + Number(a.balance_brl), 0))}
                  </span>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Credit Cards */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Cartoes de Credito</CardTitle>
                <Link
                  href="/contas"
                  className="text-xs text-primary-600 hover:text-primary-700 font-medium"
                >
                  Ver todos
                </Link>
              </div>
            </CardHeader>
            <CardContent>
              {creditCards.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-8 text-slate-400">
                  <Wallet className="h-8 w-8 mb-2 opacity-40" />
                  <p className="text-sm">Nenhum cartao cadastrado</p>
                </div>
              ) : (
                <div className="space-y-1">
                  {creditCards.map((acc) => (
                    <div
                      key={acc.account_id}
                      className="flex items-center gap-3 p-3 rounded-xl hover:bg-slate-50 transition-colors"
                    >
                      <div
                        className="w-9 h-9 rounded-lg flex items-center justify-center text-white text-xs font-bold flex-shrink-0"
                        style={{ backgroundColor: acc.bank_color || '#6366f1' }}
                      >
                        {acc.account_name.slice(0, 2).toUpperCase()}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-slate-900 truncate">
                          {acc.account_name}
                        </p>
                        <p className="text-xs text-slate-400">{acc.bank_name}</p>
                      </div>
                      <div className="text-right flex-shrink-0">
                        <p className="text-sm font-semibold text-rose-600 tabular-nums">
                          {formatCurrency(Math.abs(Number(acc.balance)))}
                        </p>
                        <p className="text-xs text-slate-400">fatura atual</p>
                      </div>
                    </div>
                  ))}

                  {/* Total */}
                  <div className="flex items-center justify-between pt-3 mt-2 border-t border-slate-100">
                    <span className="text-sm font-medium text-slate-500">Total faturas</span>
                    <span className="text-sm font-bold text-rose-600 tabular-nums">
                      {formatCurrency(Math.abs(creditCards.reduce((s, a) => s + Number(a.balance_brl), 0)))}
                    </span>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </MainLayout>
  );
}
