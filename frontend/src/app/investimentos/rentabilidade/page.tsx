'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import MainLayout from '@/components/layout/MainLayout';
import InvestmentNav from '@/components/investments/InvestmentNav';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { investmentsApi, type AssetYieldSeries } from '@/lib/api';
import { formatCurrency } from '@/lib/utils';
import { ArrowLeft, ChevronDown, ChevronRight, AlertTriangle, Link2 } from 'lucide-react';

const fmtPct = (v: number) => `${v > 0 ? '+' : ''}${v.toFixed(2)}%`;
const fmtMonth = (ym: string) => {
  const [y, m] = ym.split('-');
  const meses = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];
  return `${meses[parseInt(m) - 1]}/${y.slice(2)}`;
};
const pctColor = (v: number) => (v > 0 ? 'text-emerald-600' : v < 0 ? 'text-rose-600' : 'text-slate-500');

function AssetRow({ a }: { a: AssetYieldSeries }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <tr className="border-b border-slate-100 hover:bg-slate-50 cursor-pointer" onClick={() => setOpen((o) => !o)}>
        <td className="px-3 py-3">
          <div className="flex items-center gap-2">
            {open ? <ChevronDown className="h-4 w-4 text-slate-400" /> : <ChevronRight className="h-4 w-4 text-slate-400" />}
            <div>
              <div className="font-medium text-slate-800">{a.asset_name}</div>
              <div className="text-xs text-slate-400">{a.ticker || a.asset_class || ''}</div>
            </div>
          </div>
        </td>
        <td className="px-3 py-3 text-right tabular-nums text-slate-700">{formatCurrency(a.current_value)}</td>
        <td className={`px-3 py-3 text-right tabular-nums font-medium ${pctColor(a.yield_total_value)}`}>{formatCurrency(a.yield_total_value)}</td>
        <td className={`px-3 py-3 text-right tabular-nums font-semibold ${pctColor(a.yield_accum_pct)}`}>{fmtPct(a.yield_accum_pct)}</td>
      </tr>
      {open && (
        <tr className="bg-slate-50/60">
          <td colSpan={4} className="px-3 py-2">
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-slate-400">
                    <th className="text-left py-1 px-2 font-medium">Mês</th>
                    <th className="text-right py-1 px-2 font-medium">Valor</th>
                    <th className="text-right py-1 px-2 font-medium">Aporte</th>
                    <th className="text-right py-1 px-2 font-medium">Cupom</th>
                    <th className="text-right py-1 px-2 font-medium">Rendimento</th>
                    <th className="text-right py-1 px-2 font-medium">Rentab.</th>
                  </tr>
                </thead>
                <tbody>
                  {a.months.map((m) => (
                    <tr key={m.date} className="border-t border-slate-100">
                      <td className="py-1 px-2 text-slate-600">{fmtMonth(m.date)}</td>
                      <td className="py-1 px-2 text-right tabular-nums text-slate-600">{formatCurrency(m.value)}</td>
                      <td className="py-1 px-2 text-right tabular-nums text-slate-500">{m.aporte ? formatCurrency(m.aporte) : '—'}</td>
                      <td className="py-1 px-2 text-right tabular-nums text-slate-500">{m.cupom ? formatCurrency(m.cupom) : '—'}</td>
                      <td className={`py-1 px-2 text-right tabular-nums ${pctColor(m.yield_value)}`}>{formatCurrency(m.yield_value)}</td>
                      <td className={`py-1 px-2 text-right tabular-nums ${pctColor(m.yield_pct)}`}>{fmtPct(m.yield_pct)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function AjustarVinculos() {
  const qc = useQueryClient();
  const { data: unmatched, isLoading } = useQuery({
    queryKey: ['asset-links-unmatched'],
    queryFn: () => investmentsApi.unmatchedAssetLinks(),
  });
  const { data: options = [] } = useQuery({
    queryKey: ['asset-link-options'],
    queryFn: () => investmentsApi.assetLinkOptions(),
  });
  const mutation = useMutation({
    mutationFn: ({ tid, aid }: { tid: number; aid: number | null }) => investmentsApi.setTransactionAsset(tid, aid),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['asset-links-unmatched'] });
      qc.invalidateQueries({ queryKey: ['asset-yield'] });
    },
  });
  const [picks, setPicks] = useState<Record<number, number | ''>>({});

  if (isLoading) return <div className="py-12 text-center text-slate-400">Carregando…</div>;
  if (!unmatched || unmatched.count === 0)
    return <div className="py-12 text-center text-slate-400">Nenhum lançamento pendente de vínculo. 🎉</div>;

  return (
    <div className="overflow-x-auto">
      <p className="text-sm text-slate-500 mb-3">
        {unmatched.count} lançamento(s) de Aplicação/Rendimento/Resgate ainda sem ativo. Confirme a sugestão ou escolha manualmente.
      </p>
      <table className="w-full text-sm">
        <thead className="bg-slate-50 border-b border-slate-200">
          <tr>
            <th className="text-left px-3 py-2 text-xs font-semibold text-slate-500 uppercase">Data</th>
            <th className="text-left px-3 py-2 text-xs font-semibold text-slate-500 uppercase">Lançamento</th>
            <th className="text-right px-3 py-2 text-xs font-semibold text-slate-500 uppercase">Valor</th>
            <th className="text-left px-3 py-2 text-xs font-semibold text-slate-500 uppercase">Vincular a</th>
            <th className="px-3 py-2"></th>
          </tr>
        </thead>
        <tbody>
          {unmatched.items.map((it) => {
            const pick = picks[it.transaction_id] ?? (it.suggestion ? it.suggestion.asset_id : '');
            return (
              <tr key={it.transaction_id} className="border-b border-slate-100">
                <td className="px-3 py-2 text-slate-500 whitespace-nowrap">{it.date}</td>
                <td className="px-3 py-2">
                  <div className="text-slate-700">{it.description}</div>
                  <div className="text-xs text-slate-400">
                    {it.category_name}
                    {it.suggestion && (
                      <span className="ml-2 text-amber-600">sugestão: {it.suggestion.asset_name} ({it.suggestion.confidence})</span>
                    )}
                  </div>
                </td>
                <td className="px-3 py-2 text-right tabular-nums text-slate-600 whitespace-nowrap">{formatCurrency(it.amount)}</td>
                <td className="px-3 py-2">
                  <select
                    value={pick}
                    onChange={(e) => setPicks((p) => ({ ...p, [it.transaction_id]: e.target.value ? parseInt(e.target.value) : '' }))}
                    className="px-2 py-1.5 text-xs rounded-lg border border-slate-200 bg-white min-w-[220px]"
                  >
                    <option value="">— escolher ativo —</option>
                    {options.map((o) => (
                      <option key={o.asset_id} value={o.asset_id}>{o.name}</option>
                    ))}
                  </select>
                </td>
                <td className="px-3 py-2">
                  <button
                    disabled={!pick || mutation.isPending}
                    onClick={() => pick && mutation.mutate({ tid: it.transaction_id, aid: pick as number })}
                    className="px-3 py-1.5 text-xs rounded-lg bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-40 flex items-center gap-1"
                  >
                    <Link2 className="h-3 w-3" /> Vincular
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function RentabilidadePage() {
  const [tab, setTab] = useState<'rentab' | 'ajustar'>('rentab');
  const { data, isLoading } = useQuery({
    queryKey: ['asset-yield'],
    queryFn: () => investmentsApi.assetYield(),
  });

  const alertMonths = (data?.reconciliation || []).filter((r) => r.unlinked_flow > 1000);

  return (
    <MainLayout>
      <div className="space-y-6">
        <InvestmentNav className="mb-1" />

        <div className="flex items-center gap-3">
          <Link href="/investimentos" className="p-2 rounded-lg hover:bg-slate-100">
            <ArrowLeft className="h-4 w-4 text-slate-500" />
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Rentabilidade por Ativo</h1>
            <p className="text-slate-500 text-sm">Marcação a mercado + cupons pagos, mês a mês e acumulado (carteira XP)</p>
          </div>
        </div>

        <div className="flex gap-2">
          <button
            onClick={() => setTab('rentab')}
            className={`text-sm px-4 py-2 rounded-lg font-medium border ${tab === 'rentab' ? 'bg-primary-600 text-white border-primary-600' : 'bg-white border-slate-200 text-slate-700'}`}
          >
            Rentabilidade
          </button>
          <button
            onClick={() => setTab('ajustar')}
            className={`text-sm px-4 py-2 rounded-lg font-medium border ${tab === 'ajustar' ? 'bg-primary-600 text-white border-primary-600' : 'bg-white border-slate-200 text-slate-700'}`}
          >
            Ajustar vínculos
          </button>
        </div>

        {tab === 'rentab' && alertMonths.length > 0 && (
          <Card>
            <CardContent>
              <div className="flex items-start gap-2 text-sm text-amber-700">
                <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
                <div>
                  <span className="font-medium">Atenção:</span> há fluxos não atribuídos a um ativo em{' '}
                  {alertMonths.map((m) => fmtMonth(m.date)).join(', ')}. A rentabilidade desses ativos pode estar distorcida —
                  resolva na aba <button className="underline" onClick={() => setTab('ajustar')}>Ajustar vínculos</button>.
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        <Card>
          {tab === 'ajustar' && (
            <CardHeader>
              <CardTitle>Vínculo de lançamentos a ativos</CardTitle>
            </CardHeader>
          )}
          <CardContent className={tab === 'rentab' ? '!p-0' : ''}>
            {tab === 'ajustar' ? (
              <AjustarVinculos />
            ) : isLoading ? (
              <div className="py-12 text-center text-slate-400">Carregando…</div>
            ) : !data || data.assets.length === 0 ? (
              <div className="py-12 text-center text-slate-400">Sem dados</div>
            ) : (
              <table className="w-full text-sm">
                <thead className="bg-slate-50 border-b border-slate-200">
                  <tr>
                    <th className="text-left px-3 py-3 text-xs font-semibold text-slate-500 uppercase">Ativo</th>
                    <th className="text-right px-3 py-3 text-xs font-semibold text-slate-500 uppercase">Valor atual</th>
                    <th className="text-right px-3 py-3 text-xs font-semibold text-slate-500 uppercase">Rend. total</th>
                    <th className="text-right px-3 py-3 text-xs font-semibold text-slate-500 uppercase">Acum.</th>
                  </tr>
                </thead>
                <tbody>
                  {data.assets.map((a) => (
                    <AssetRow key={a.asset_id} a={a} />
                  ))}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>
      </div>
    </MainLayout>
  );
}
