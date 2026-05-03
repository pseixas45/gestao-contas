'use client';

import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import MainLayout from '@/components/layout/MainLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { investmentsApi, type Asset } from '@/lib/api';
import { ArrowLeft, Edit2, X, Save, Search } from 'lucide-react';

export default function AtivosPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState('');
  const [classFilter, setClassFilter] = useState('');
  const [editing, setEditing] = useState<Asset | null>(null);

  const { data: assets = [], isLoading } = useQuery({
    queryKey: ['assets'],
    queryFn: () => investmentsApi.listAssets({ active_only: false }),
  });

  const { data: assetClasses = [] } = useQuery({
    queryKey: ['asset-classes'],
    queryFn: () => investmentsApi.listAssetClasses(),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<Asset> }) => investmentsApi.updateAsset(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['assets'] });
      setEditing(null);
    },
  });

  const filtered = useMemo(() => {
    let list = assets;
    if (search) {
      const s = search.toLowerCase();
      list = list.filter((a) => a.name.toLowerCase().includes(s) || (a.issuer || '').toLowerCase().includes(s));
    }
    if (classFilter) list = list.filter((a) => a.asset_class_id === parseInt(classFilter));
    return list;
  }, [assets, search, classFilter]);

  const handleSave = () => {
    if (!editing) return;
    updateMutation.mutate({
      id: editing.id,
      data: {
        name: editing.name,
        asset_class_id: editing.asset_class_id,
        issuer: editing.issuer,
        sector: editing.sector,
        liquidity_days: editing.liquidity_days,
        risk_level: editing.risk_level,
        is_active: editing.is_active,
      },
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
            <h1 className="text-2xl font-bold text-slate-900">Ativos</h1>
            <p className="text-slate-500 text-sm">Cadastro e ajuste de classe, liquidez e risco</p>
          </div>
        </div>

        {/* Filtros */}
        <Card>
          <CardContent>
            <div className="flex flex-wrap gap-3">
              <div className="flex-1 min-w-[240px]">
                <label className="text-xs text-slate-500 mb-1 block">Buscar</label>
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                  <input
                    type="text"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Nome ou emissor..."
                    className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-slate-200"
                  />
                </div>
              </div>
              <div>
                <label className="text-xs text-slate-500 mb-1 block">Classe</label>
                <select
                  value={classFilter}
                  onChange={(e) => setClassFilter(e.target.value)}
                  className="px-3 py-2 text-sm rounded-lg border border-slate-200 bg-white min-w-[180px]"
                >
                  <option value="">Todas</option>
                  {assetClasses.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Tabela */}
        <Card>
          <CardHeader>
            <CardTitle>{filtered.length} ativo{filtered.length !== 1 ? 's' : ''}</CardTitle>
          </CardHeader>
          <CardContent className="!p-0">
            {isLoading ? (
              <div className="py-12 text-center text-slate-400">Carregando…</div>
            ) : filtered.length === 0 ? (
              <div className="py-12 text-center text-slate-400">Nenhum ativo encontrado</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 border-b border-slate-200">
                    <tr>
                      <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase">Nome</th>
                      <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase">Classe</th>
                      <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase">Emissor</th>
                      <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase">Setor</th>
                      <th className="text-right px-4 py-3 text-xs font-semibold text-slate-500 uppercase">Liquidez</th>
                      <th className="text-right px-4 py-3 text-xs font-semibold text-slate-500 uppercase">Risco</th>
                      <th className="text-right px-4 py-3 text-xs font-semibold text-slate-500 uppercase"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((a) => (
                      <tr key={a.id} className="border-b border-slate-100 hover:bg-slate-50">
                        <td className="px-4 py-3 text-slate-800 font-medium">{a.name}</td>
                        <td className="px-4 py-3 text-slate-600 text-xs">{a.asset_class_name || '—'}</td>
                        <td className="px-4 py-3 text-slate-600 text-xs">{a.issuer || '—'}</td>
                        <td className="px-4 py-3 text-slate-600 text-xs">{a.sector || '—'}</td>
                        <td className="px-4 py-3 text-right text-slate-600 tabular-nums">{a.liquidity_days != null ? `D+${a.liquidity_days}` : '—'}</td>
                        <td className="px-4 py-3 text-right text-slate-600 tabular-nums">{a.risk_level || '—'}</td>
                        <td className="px-4 py-3 text-right">
                          <button
                            onClick={() => setEditing(a)}
                            className="p-1.5 rounded-lg hover:bg-primary-50 text-primary-600"
                          >
                            <Edit2 className="h-3.5 w-3.5" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Modal de edição */}
        {editing && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
            <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg mx-4">
              <div className="flex items-center justify-between p-4 border-b border-slate-200">
                <h3 className="font-semibold text-slate-800">Editar Ativo</h3>
                <button onClick={() => setEditing(null)} className="p-1 hover:bg-slate-100 rounded-lg">
                  <X className="h-4 w-4 text-slate-500" />
                </button>
              </div>
              <div className="p-4 space-y-3">
                <div>
                  <label className="text-xs text-slate-500 mb-1 block">Nome</label>
                  <input
                    type="text"
                    value={editing.name}
                    onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200"
                  />
                </div>
                <div>
                  <label className="text-xs text-slate-500 mb-1 block">Classe</label>
                  <select
                    value={editing.asset_class_id}
                    onChange={(e) => setEditing({ ...editing, asset_class_id: parseInt(e.target.value) })}
                    className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200 bg-white"
                  >
                    {assetClasses.map((c) => (
                      <option key={c.id} value={c.id}>{c.name}</option>
                    ))}
                  </select>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs text-slate-500 mb-1 block">Emissor</label>
                    <input
                      type="text"
                      value={editing.issuer || ''}
                      onChange={(e) => setEditing({ ...editing, issuer: e.target.value || null })}
                      className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-500 mb-1 block">Setor</label>
                    <input
                      type="text"
                      value={editing.sector || ''}
                      onChange={(e) => setEditing({ ...editing, sector: e.target.value || null })}
                      className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-500 mb-1 block">Liquidez (dias)</label>
                    <input
                      type="number"
                      value={editing.liquidity_days ?? ''}
                      onChange={(e) => setEditing({ ...editing, liquidity_days: e.target.value ? parseInt(e.target.value) : null })}
                      className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-500 mb-1 block">Risco (1-5)</label>
                    <input
                      type="number"
                      min={1}
                      max={5}
                      value={editing.risk_level ?? ''}
                      onChange={(e) => setEditing({ ...editing, risk_level: e.target.value ? parseInt(e.target.value) : null })}
                      className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200"
                    />
                  </div>
                </div>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={editing.is_active}
                    onChange={(e) => setEditing({ ...editing, is_active: e.target.checked })}
                  />
                  Ativo
                </label>
              </div>
              <div className="p-4 border-t border-slate-200 flex justify-end gap-2">
                <button onClick={() => setEditing(null)} className="px-4 py-2 text-sm rounded-lg border border-slate-200 hover:bg-slate-50">Cancelar</button>
                <button onClick={handleSave} disabled={updateMutation.isPending} className="px-4 py-2 text-sm rounded-lg bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50 flex items-center gap-1">
                  <Save className="h-3.5 w-3.5" />
                  {updateMutation.isPending ? 'Salvando…' : 'Salvar'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </MainLayout>
  );
}
