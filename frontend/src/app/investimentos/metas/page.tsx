'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import MainLayout from '@/components/layout/MainLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { investmentsApi, type InvestmentGoal } from '@/lib/api';
import { formatCurrency } from '@/lib/utils';
import { ArrowLeft, Plus, Trash2, Target } from 'lucide-react';

const GOAL_TYPES = [
  { value: 'PORTFOLIO_TOTAL', label: 'Patrimônio Total (R$)' },
  { value: 'MONTHLY_CONTRIBUTION', label: 'Aporte Mensal (R$)' },
  { value: 'MIN_YIELD', label: 'Rentabilidade Mínima (%)' },
  { value: 'ALLOCATION_BY_CLASS', label: 'Alocação por Classe (%)' },
];

export default function MetasPage() {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    type: 'MONTHLY_CONTRIBUTION',
    name: '',
    description: '',
    target_value: '',
    target_class_id: '',
  });

  const { data: goals = [] } = useQuery({
    queryKey: ['investment-goals'],
    queryFn: () => investmentsApi.listGoals(false),
  });

  const { data: progress = [] } = useQuery({
    queryKey: ['investment-goals-progress'],
    queryFn: () => investmentsApi.goalsProgress(),
  });

  const { data: assetClasses = [] } = useQuery({
    queryKey: ['asset-classes'],
    queryFn: () => investmentsApi.listAssetClasses(),
  });

  const createMutation = useMutation({
    mutationFn: (data: Partial<InvestmentGoal>) => investmentsApi.createGoal(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['investment-goals'] });
      qc.invalidateQueries({ queryKey: ['investment-goals-progress'] });
      setShowForm(false);
      setForm({ type: 'MONTHLY_CONTRIBUTION', name: '', description: '', target_value: '', target_class_id: '' });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => investmentsApi.deleteGoal(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['investment-goals'] });
      qc.invalidateQueries({ queryKey: ['investment-goals-progress'] });
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const data: Partial<InvestmentGoal> & { target_value?: number; target_class_id?: number | null } = {
      type: form.type,
      name: form.name,
      description: form.description || null,
      target_value: form.target_value ? parseFloat(form.target_value) : undefined,
      target_class_id: form.target_class_id ? parseInt(form.target_class_id) : null,
      is_active: true,
    };
    createMutation.mutate(data);
  };

  const progressMap = new Map(progress.map((p) => [p.id, p]));

  return (
    <MainLayout>
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <Link href="/investimentos" className="p-2 rounded-lg hover:bg-slate-100">
            <ArrowLeft className="h-4 w-4 text-slate-500" />
          </Link>
          <div className="flex-1">
            <h1 className="text-2xl font-bold text-slate-900">Metas</h1>
            <p className="text-slate-500 text-sm">Defina e acompanhe suas metas financeiras</p>
          </div>
          <button
            onClick={() => setShowForm(!showForm)}
            className="px-4 py-2 rounded-lg bg-primary-600 text-white text-sm font-medium hover:bg-primary-700 flex items-center gap-2"
          >
            <Plus className="h-4 w-4" /> Nova Meta
          </button>
        </div>

        {showForm && (
          <Card>
            <CardHeader>
              <CardTitle>Nova Meta</CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="text-xs text-slate-500 mb-1 block">Tipo</label>
                    <select
                      value={form.type}
                      onChange={(e) => setForm({ ...form, type: e.target.value })}
                      className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200 bg-white"
                    >
                      {GOAL_TYPES.map((t) => (
                        <option key={t.value} value={t.value}>{t.label}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="text-xs text-slate-500 mb-1 block">Nome</label>
                    <input
                      type="text"
                      value={form.name}
                      onChange={(e) => setForm({ ...form, name: e.target.value })}
                      required
                      placeholder="Ex: Aporte mensal de R$ 5.000"
                      className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-500 mb-1 block">
                      Valor alvo {form.type === 'MIN_YIELD' || form.type === 'ALLOCATION_BY_CLASS' ? '(%)' : '(R$)'}
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      value={form.target_value}
                      onChange={(e) => setForm({ ...form, target_value: e.target.value })}
                      required
                      className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200"
                    />
                  </div>
                  {form.type === 'ALLOCATION_BY_CLASS' && (
                    <div>
                      <label className="text-xs text-slate-500 mb-1 block">Classe alvo</label>
                      <select
                        value={form.target_class_id}
                        onChange={(e) => setForm({ ...form, target_class_id: e.target.value })}
                        required
                        className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200 bg-white"
                      >
                        <option value="">Selecione…</option>
                        {assetClasses.map((c) => (
                          <option key={c.id} value={c.id}>{c.name}</option>
                        ))}
                      </select>
                    </div>
                  )}
                </div>
                <div>
                  <label className="text-xs text-slate-500 mb-1 block">Descrição (opcional)</label>
                  <input
                    type="text"
                    value={form.description}
                    onChange={(e) => setForm({ ...form, description: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200"
                  />
                </div>
                <div className="flex gap-2 justify-end">
                  <button type="button" onClick={() => setShowForm(false)} className="px-4 py-2 text-sm rounded-lg border border-slate-200 hover:bg-slate-50">Cancelar</button>
                  <button type="submit" disabled={createMutation.isPending} className="px-4 py-2 text-sm rounded-lg bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50">
                    {createMutation.isPending ? 'Salvando…' : 'Salvar'}
                  </button>
                </div>
              </form>
            </CardContent>
          </Card>
        )}

        {goals.length === 0 ? (
          <Card>
            <CardContent>
              <div className="flex flex-col items-center justify-center py-12 text-slate-400">
                <Target className="h-12 w-12 mb-3 opacity-40" />
                <p className="text-sm">Nenhuma meta cadastrada</p>
                <p className="text-xs text-slate-400 mt-1">Cadastre uma meta para começar a acompanhar seu progresso.</p>
              </div>
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {goals.map((g) => {
              const prog = progressMap.get(g.id);
              const pct = prog ? Math.min(100, Math.max(0, prog.progress_pct)) : 0;
              const color = pct >= 100 ? 'bg-emerald-500' : pct >= 70 ? 'bg-sky-500' : 'bg-amber-500';
              const isPercent = g.type === 'MIN_YIELD' || g.type === 'ALLOCATION_BY_CLASS';
              return (
                <Card key={g.id}>
                  <CardContent>
                    <div className="flex items-start justify-between mb-3">
                      <div className="flex-1">
                        <p className="text-xs text-slate-400 uppercase tracking-wider mb-0.5">{GOAL_TYPES.find((t) => t.value === g.type)?.label || g.type}</p>
                        <p className="text-base font-semibold text-slate-800">{g.name}</p>
                        {g.description && <p className="text-xs text-slate-500 mt-1">{g.description}</p>}
                      </div>
                      <button
                        onClick={() => deleteMutation.mutate(g.id)}
                        className="p-1.5 rounded-lg hover:bg-rose-50 text-rose-500"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                    <div className="mb-2">
                      <div className="flex justify-between items-end mb-1.5">
                        <p className="text-xs text-slate-500">
                          Atual: <span className="font-semibold text-slate-700">
                            {prog ? (isPercent ? `${prog.current.toFixed(2)}%` : formatCurrency(prog.current)) : '—'}
                          </span>
                        </p>
                        <p className="text-xs text-slate-500">
                          Meta: <span className="font-semibold text-slate-700">
                            {isPercent ? `${(g.target_value || 0).toFixed(2)}%` : formatCurrency(g.target_value || 0)}
                          </span>
                        </p>
                      </div>
                      <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                        <div className={`${color} h-full rounded-full transition-all`} style={{ width: `${pct}%` }} />
                      </div>
                      <p className="text-xs text-right text-slate-500 mt-1">{prog ? prog.progress_pct.toFixed(1) : '0'}% atingido</p>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </div>
    </MainLayout>
  );
}
