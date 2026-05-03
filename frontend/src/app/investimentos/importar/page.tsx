'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import MainLayout from '@/components/layout/MainLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { investmentsApi, accountsApi } from '@/lib/api';
import { formatCurrency } from '@/lib/utils';
import { ArrowLeft, Upload, FileCheck, AlertCircle } from 'lucide-react';

export default function ImportarInvestimentosPage() {
  const [file, setFile] = useState<File | null>(null);
  const [accountId, setAccountId] = useState<number | null>(null);
  const [provider, setProvider] = useState<'xp' | 'itau' | 'c6'>('xp');
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<{ snapshot_id: number; positions_count: number; total_value: number; snapshot_date: string; filename: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { data: accounts = [] } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
  });

  const investmentAccounts = accounts.filter((a) => a.account_type === 'investment');

  const handleUpload = async () => {
    if (!file || !accountId) return;
    setUploading(true);
    setError(null);
    setResult(null);
    try {
      const res = await investmentsApi.upload(file, accountId, provider);
      setResult(res);
      setFile(null);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      setError(err.response?.data?.detail || err.message || 'Erro ao importar');
    } finally {
      setUploading(false);
    }
  };

  return (
    <MainLayout>
      <div className="space-y-6 max-w-2xl">
        <div className="flex items-center gap-3">
          <Link href="/investimentos" className="p-2 rounded-lg hover:bg-slate-100">
            <ArrowLeft className="h-4 w-4 text-slate-500" />
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Importar Extrato</h1>
            <p className="text-slate-500 text-sm">Carregue um arquivo de posição do XP ou Itaú</p>
          </div>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Configurações</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <label className="text-xs text-slate-500 mb-1 block">Banco / Provedor</label>
              <select
                value={provider}
                onChange={(e) => setProvider(e.target.value as 'xp' | 'itau' | 'c6')}
                className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200 bg-white"
              >
                <option value="xp">XP — PosicaoDetalhadaHistorica (.xlsx)</option>
                <option value="itau">Itaú — Extrato Carteira (.pdf)</option>
                <option value="c6">C6 — Posição por produto (.pdf)</option>
              </select>
            </div>

            <div>
              <label className="text-xs text-slate-500 mb-1 block">Conta de Investimento</label>
              <select
                value={accountId || ''}
                onChange={(e) => setAccountId(e.target.value ? parseInt(e.target.value) : null)}
                className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200 bg-white"
              >
                <option value="">Selecione…</option>
                {investmentAccounts.map((a) => (
                  <option key={a.id} value={a.id}>{a.name} {a.bank_name ? `(${a.bank_name})` : ''}</option>
                ))}
              </select>
              {investmentAccounts.length === 0 && (
                <p className="text-xs text-amber-600 mt-1">
                  Nenhuma conta do tipo "Investimento" cadastrada. <Link href="/contas" className="underline">Criar agora</Link>.
                </p>
              )}
            </div>

            <div>
              <label className="text-xs text-slate-500 mb-1 block">Arquivo</label>
              <input
                type="file"
                accept={provider === 'itau' || provider === 'c6' ? '.pdf' : '.xlsx,.xls'}
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                className="w-full text-sm"
              />
              {file && (
                <p className="text-xs text-slate-500 mt-1">
                  <FileCheck className="h-3 w-3 inline mr-1" />
                  {file.name} ({(file.size / 1024).toFixed(1)} KB)
                </p>
              )}
            </div>

            <button
              onClick={handleUpload}
              disabled={!file || !accountId || uploading}
              className="w-full px-4 py-2.5 rounded-lg bg-primary-600 text-white font-medium hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              <Upload className="h-4 w-4" />
              {uploading ? 'Importando…' : 'Importar'}
            </button>
          </CardContent>
        </Card>

        {error && (
          <div className="p-4 bg-rose-50 border border-rose-200 rounded-lg flex gap-3">
            <AlertCircle className="h-5 w-5 text-rose-600 flex-shrink-0" />
            <div>
              <p className="text-sm font-medium text-rose-800">Erro na importação</p>
              <p className="text-xs text-rose-700 mt-1">{error}</p>
            </div>
          </div>
        )}

        {result && (
          <Card>
            <CardContent>
              <div className="flex items-start gap-3">
                <div className="p-2 bg-emerald-50 rounded-lg">
                  <FileCheck className="h-5 w-5 text-emerald-600" />
                </div>
                <div className="flex-1">
                  <p className="text-sm font-semibold text-slate-800">Importação concluída</p>
                  <p className="text-xs text-slate-500 mt-0.5">{result.filename}</p>
                  <div className="mt-3 grid grid-cols-3 gap-3 text-sm">
                    <div>
                      <p className="text-xs text-slate-500">Data</p>
                      <p className="font-semibold">{result.snapshot_date}</p>
                    </div>
                    <div>
                      <p className="text-xs text-slate-500">Patrimônio</p>
                      <p className="font-semibold tabular-nums">{formatCurrency(result.total_value)}</p>
                    </div>
                    <div>
                      <p className="text-xs text-slate-500">Posições</p>
                      <p className="font-semibold">{result.positions_count}</p>
                    </div>
                  </div>
                  <div className="mt-4 flex gap-2">
                    <Link href="/investimentos" className="text-xs px-3 py-1.5 rounded-lg bg-primary-600 text-white hover:bg-primary-700">
                      Ver dashboard
                    </Link>
                    <Link href="/investimentos/historico" className="text-xs px-3 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50">
                      Ver histórico
                    </Link>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        <Card>
          <CardContent>
            <p className="text-xs font-semibold text-slate-700 mb-2">Formatos esperados</p>
            <ul className="space-y-1 text-xs text-slate-500">
              <li>• <strong>XP:</strong> arquivo <code className="bg-slate-100 px-1 rounded">PosicaoDetalhadaHistorica_dd_mm_yyyy.xlsx</code> (data extraída do nome)</li>
              <li>• <strong>Itaú:</strong> arquivo <code className="bg-slate-100 px-1 rounded">ITAU EXTRATO-CARTEIRA-yyyy-mm.pdf</code></li>
              <li>• Importações são <strong>idempotentes</strong>: subir o mesmo arquivo novamente substitui a snapshot daquela data.</li>
            </ul>
          </CardContent>
        </Card>
      </div>
    </MainLayout>
  );
}
