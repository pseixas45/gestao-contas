'use client';

import { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useDropzone } from 'react-dropzone';
import MainLayout from '@/components/layout/MainLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import Button from '@/components/ui/Button';
import Input from '@/components/ui/Input';
import Select from '@/components/ui/Select';
import Badge from '@/components/ui/Badge';
import { importsApi, accountsApi } from '@/lib/api';
import { formatCurrency, formatDate, getImportStatusLabel, getImportStatusColor } from '@/lib/utils';
import {
  Upload,
  CheckCircle,
  AlertCircle,
  AlertTriangle,
  Trash2,
  ArrowRight,
  ArrowLeft,
  ChevronDown,
  ChevronUp,
  FileSpreadsheet,
  Settings2,
  RotateCcw,
  X,
} from 'lucide-react';
import type { ImportPreview, ImportResult, ImportAnalysis, ColumnMapping } from '@/types';

type Step = 'upload' | 'analysis' | 'result';

export default function ImportarPage() {
  const [step, setStep] = useState<Step>('upload');
  const [selectedAccount, setSelectedAccount] = useState('');
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [columnMapping, setColumnMapping] = useState<ColumnMapping | null>(null);
  const [analysis, setAnalysis] = useState<ImportAnalysis | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [validateBalance, setValidateBalance] = useState(true);
  const [expectedBalance, setExpectedBalance] = useState('');
  const [deletingBatchId, setDeletingBatchId] = useState<number | null>(null);
  const [cardPaymentDate, setCardPaymentDate] = useState('');
  const [showMapping, setShowMapping] = useState(false);
  const [showTransactions, setShowTransactions] = useState(false);

  const queryClient = useQueryClient();

  const { data: accounts = [] } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
  });

  const { data: batches = [] } = useQuery({
    queryKey: ['import-batches'],
    queryFn: () => importsApi.listBatches(),
  });

  const selectedAccountObj = accounts.find((a) => a.id === parseInt(selectedAccount));
  const isCreditCard = selectedAccountObj?.account_type === 'credit_card';

  // Upload → detect/template → auto-analyze
  const uploadMutation = useMutation({
    mutationFn: (file: File) => importsApi.upload(file, parseInt(selectedAccount)),
    onSuccess: async (data) => {
      setPreview(data);
      setColumnMapping(data.detected_mapping);

      // If has template, auto-analyze immediately
      if (data.has_template) {
        try {
          const analysisResult = await importsApi.analyze({
            batch_id: data.batch_id,
            column_mapping: data.detected_mapping,
            account_id: parseInt(selectedAccount),
            card_payment_date: cardPaymentDate || undefined,
          });
          setAnalysis(analysisResult);
          setStep('analysis');
        } catch {
          // Template mapping failed, show mapping panel
          setShowMapping(true);
          setStep('analysis');
        }
      } else {
        // No template, show mapping
        setShowMapping(true);
        setStep('analysis');
      }
    },
  });

  const analyzeMutation = useMutation({
    mutationFn: () =>
      importsApi.analyze({
        batch_id: preview!.batch_id,
        column_mapping: columnMapping!,
        account_id: parseInt(selectedAccount),
        card_payment_date: cardPaymentDate || undefined,
      }),
    onSuccess: (data) => {
      setAnalysis(data);
      setShowMapping(false);
    },
  });

  const processMutation = useMutation({
    mutationFn: () =>
      importsApi.process({
        batch_id: preview!.batch_id,
        column_mapping: columnMapping!,
        account_id: parseInt(selectedAccount),
        validate_balance: validateBalance && !!expectedBalance,
        expected_final_balance: validateBalance && expectedBalance ? parseFloat(expectedBalance) : undefined,
        skip_duplicates: true,
        card_payment_date: cardPaymentDate || undefined,
      }),
    onSuccess: (data) => {
      setResult(data);
      setStep('result');
      queryClient.invalidateQueries({ queryKey: ['import-batches'] });
      queryClient.invalidateQueries({ queryKey: ['accounts'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard-summary'] });
    },
  });

  const revertMutation = useMutation({
    mutationFn: (batchId: number) => importsApi.revertBatch(batchId),
    onSuccess: () => {
      setDeletingBatchId(null);
      queryClient.invalidateQueries({ queryKey: ['import-batches'] });
      queryClient.invalidateQueries({ queryKey: ['accounts'] });
    },
  });

  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      if (acceptedFiles.length > 0 && selectedAccount) {
        uploadMutation.mutate(acceptedFiles[0]);
      }
    },
    [selectedAccount, uploadMutation]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'text/csv': ['.csv'],
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
      'application/vnd.ms-excel': ['.xls'],
    },
    maxFiles: 1,
    disabled: !selectedAccount,
  });

  const resetImport = () => {
    setStep('upload');
    setPreview(null);
    setColumnMapping(null);
    setAnalysis(null);
    setResult(null);
    setShowMapping(false);
    setShowTransactions(false);
    setExpectedBalance('');
    setCardPaymentDate('');
  };

  const updateMapping = (field: keyof ColumnMapping, value: string) => {
    if (columnMapping) {
      setColumnMapping({ ...columnMapping, [field]: value || null });
    }
  };

  const columnOptions = preview ? [{ value: '', label: 'Nao mapear' }, ...preview.columns.map((c) => ({ value: c, label: c }))] : [];

  return (
    <MainLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Importar Extrato</h1>
            <p className="text-slate-500">Carregue extratos bancarios em CSV ou Excel</p>
          </div>
          {step !== 'upload' && (
            <Button variant="secondary" size="sm" onClick={resetImport}>
              <RotateCcw className="h-4 w-4 mr-1.5" />
              Nova importacao
            </Button>
          )}
        </div>

        {/* Steps indicator */}
        <div className="flex items-center gap-3">
          {[
            { key: 'upload', label: '1. Upload' },
            { key: 'analysis', label: '2. Analise' },
            { key: 'result', label: '3. Resultado' },
          ].map(({ key, label }, i) => {
            const isActive = step === key;
            const isDone =
              (key === 'upload' && step !== 'upload') ||
              (key === 'analysis' && step === 'result');
            return (
              <div key={key} className="flex items-center gap-2">
                {i > 0 && <div className="w-8 h-px bg-slate-200" />}
                <div
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-primary-50 text-primary-700'
                      : isDone
                        ? 'bg-emerald-50 text-emerald-700'
                        : 'text-slate-400'
                  }`}
                >
                  {isDone && <CheckCircle className="h-3.5 w-3.5" />}
                  {label}
                </div>
              </div>
            );
          })}
        </div>

        {/* Step 1: Upload */}
        {step === 'upload' && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 space-y-4">
              <Card>
                <CardContent className="pt-6">
                  {/* Account selection */}
                  <div className="mb-5">
                    <Select
                      label="Conta destino"
                      value={selectedAccount}
                      onChange={(e) => setSelectedAccount(e.target.value)}
                      options={[
                        { value: '', label: 'Selecione uma conta...' },
                        ...accounts.map((a) => ({
                          value: a.id.toString(),
                          label: `${a.name} (${a.bank_name}) - ${a.currency}`,
                        })),
                      ]}
                    />
                  </div>

                  {/* Credit card date */}
                  {isCreditCard && (
                    <div className="mb-5">
                      <Input
                        label="Data de pagamento da fatura"
                        type="date"
                        value={cardPaymentDate}
                        onChange={(e) => setCardPaymentDate(e.target.value)}
                        hint="Obrigatorio para cartao de credito (ajusta datas das parcelas)"
                      />
                    </div>
                  )}

                  {/* Dropzone */}
                  <div
                    {...getRootProps()}
                    className={`border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-all ${
                      !selectedAccount
                        ? 'border-slate-200 bg-slate-50 opacity-60 cursor-not-allowed'
                        : isDragActive
                          ? 'border-primary-400 bg-primary-50'
                          : 'border-slate-300 hover:border-primary-400 hover:bg-slate-50'
                    }`}
                  >
                    <input {...getInputProps()} />
                    <div className="flex flex-col items-center gap-3">
                      {uploadMutation.isPending ? (
                        <>
                          <div className="w-10 h-10 border-3 border-primary-200 border-t-primary-600 rounded-full animate-spin" />
                          <p className="text-sm text-slate-500">Processando arquivo...</p>
                        </>
                      ) : (
                        <>
                          <div className="w-14 h-14 rounded-2xl bg-primary-50 flex items-center justify-center">
                            <Upload className="h-6 w-6 text-primary-600" />
                          </div>
                          <div>
                            <p className="text-sm font-medium text-slate-700">
                              {isDragActive ? 'Solte o arquivo aqui' : 'Arraste um arquivo ou clique para selecionar'}
                            </p>
                            <p className="text-xs text-slate-400 mt-1">CSV, Excel (.xlsx, .xls)</p>
                          </div>
                        </>
                      )}
                    </div>
                  </div>

                  {uploadMutation.isError && (
                    <div className="mt-4 p-3 bg-rose-50 border border-rose-200 rounded-xl text-sm text-rose-700">
                      <AlertCircle className="inline h-4 w-4 mr-1.5" />
                      {(uploadMutation.error as any)?.response?.data?.detail || 'Erro ao fazer upload'}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>

            {/* Import history */}
            <div>
              <Card>
                <CardHeader>
                  <CardTitle>Historico</CardTitle>
                </CardHeader>
                <CardContent>
                  {batches.length === 0 ? (
                    <p className="text-sm text-slate-400 text-center py-4">Nenhuma importacao</p>
                  ) : (
                    <div className="space-y-2 max-h-96 overflow-y-auto">
                      {batches.slice(0, 15).map((batch) => (
                        <div key={batch.id} className="p-2.5 rounded-lg bg-slate-50 text-sm">
                          <div className="flex items-center justify-between mb-1">
                            <span className="font-medium text-slate-700 truncate max-w-[160px]">
                              {batch.filename}
                            </span>
                            <button
                              onClick={() => setDeletingBatchId(batch.id)}
                              className="text-slate-400 hover:text-rose-500 p-0.5"
                              title="Reverter"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </div>
                          <div className="flex items-center gap-2 text-xs text-slate-400">
                            <span>{batch.imported_records} importadas</span>
                            {batch.duplicate_records > 0 && (
                              <span>| {batch.duplicate_records} dup</span>
                            )}
                            <span className={`ml-auto px-1.5 py-0.5 rounded text-xs ${getImportStatusColor(batch.status)}`}>
                              {getImportStatusLabel(batch.status)}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          </div>
        )}

        {/* Step 2: Analysis (+ optional mapping) */}
        {step === 'analysis' && preview && columnMapping && (
          <div className="space-y-4">
            {/* Mapping panel (collapsible) */}
            <Card>
              <CardHeader>
                <button
                  onClick={() => setShowMapping(!showMapping)}
                  className="flex items-center justify-between w-full"
                >
                  <div className="flex items-center gap-2">
                    <Settings2 className="h-4 w-4 text-slate-400" />
                    <CardTitle>Mapeamento de Colunas</CardTitle>
                    {preview.has_template && !showMapping && (
                      <Badge color="primary" variant="soft" size="sm">Template salvo</Badge>
                    )}
                  </div>
                  {showMapping ? (
                    <ChevronUp className="h-4 w-4 text-slate-400" />
                  ) : (
                    <ChevronDown className="h-4 w-4 text-slate-400" />
                  )}
                </button>
              </CardHeader>
              {showMapping && (
                <CardContent>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    <Select
                      label="Data *"
                      value={columnMapping.date_column}
                      onChange={(e) => updateMapping('date_column', e.target.value)}
                      options={columnOptions}
                    />
                    <Select
                      label="Descricao *"
                      value={columnMapping.description_column}
                      onChange={(e) => updateMapping('description_column', e.target.value)}
                      options={columnOptions}
                    />
                    <Select
                      label="Valor"
                      value={columnMapping.amount_column || ''}
                      onChange={(e) => updateMapping('amount_column', e.target.value)}
                      options={columnOptions}
                    />
                    <Select
                      label="Valor R$"
                      value={columnMapping.valor_brl_column || ''}
                      onChange={(e) => updateMapping('valor_brl_column', e.target.value)}
                      options={columnOptions}
                    />
                    <Select
                      label="Valor US$"
                      value={columnMapping.valor_usd_column || ''}
                      onChange={(e) => updateMapping('valor_usd_column', e.target.value)}
                      options={columnOptions}
                    />
                    <Select
                      label="Valor EUR"
                      value={columnMapping.valor_eur_column || ''}
                      onChange={(e) => updateMapping('valor_eur_column', e.target.value)}
                      options={columnOptions}
                    />
                    <Select
                      label="Saldo"
                      value={columnMapping.balance_column || ''}
                      onChange={(e) => updateMapping('balance_column', e.target.value)}
                      options={columnOptions}
                    />
                    <Select
                      label="Categoria"
                      value={columnMapping.category_column || ''}
                      onChange={(e) => updateMapping('category_column', e.target.value)}
                      options={columnOptions}
                    />
                    {isCreditCard && (
                      <Select
                        label="Data Pagamento"
                        value={columnMapping.card_payment_date_column || ''}
                        onChange={(e) => updateMapping('card_payment_date_column', e.target.value)}
                        options={columnOptions}
                      />
                    )}
                  </div>

                  {/* Preview rows */}
                  {preview.preview_rows.length > 0 && (
                    <div className="mt-4 overflow-x-auto rounded-lg border border-slate-200">
                      <table className="min-w-full text-xs">
                        <thead className="bg-slate-50">
                          <tr>
                            {preview.columns.map((col) => (
                              <th key={col} className="px-3 py-2 text-left font-medium text-slate-500">
                                {col}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {preview.preview_rows.slice(0, 5).map((row, i) => (
                            <tr key={i} className="border-t border-slate-100">
                              {preview.columns.map((col) => (
                                <td key={col} className="px-3 py-1.5 text-slate-600 whitespace-nowrap">
                                  {String(row[col] ?? '')}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}

                  <div className="mt-4 flex justify-end">
                    <Button
                      onClick={() => analyzeMutation.mutate()}
                      disabled={analyzeMutation.isPending || !columnMapping.date_column || !columnMapping.description_column}
                      isLoading={analyzeMutation.isPending}
                    >
                      Analisar
                    </Button>
                  </div>
                </CardContent>
              )}
            </Card>

            {/* Analysis results */}
            {analysis && (
              <>
                {/* Summary cards */}
                <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                  <div className="p-3 bg-emerald-50 rounded-xl text-center">
                    <p className="text-2xl font-bold text-emerald-700">{analysis.new_count}</p>
                    <p className="text-xs text-emerald-600">Novas</p>
                  </div>
                  <div className="p-3 bg-slate-50 rounded-xl text-center">
                    <p className="text-2xl font-bold text-slate-500">{analysis.duplicate_count + analysis.fuzzy_duplicate_count}</p>
                    <p className="text-xs text-slate-400">Duplicadas</p>
                  </div>
                  <div className="p-3 bg-amber-50 rounded-xl text-center">
                    <p className="text-2xl font-bold text-amber-600">{analysis.uncertain_count}</p>
                    <p className="text-xs text-amber-500">Incertas</p>
                  </div>
                  <div className="p-3 bg-rose-50 rounded-xl text-center">
                    <p className="text-2xl font-bold text-rose-600">{analysis.error_count}</p>
                    <p className="text-xs text-rose-500">Erros</p>
                  </div>
                  <div className="p-3 bg-primary-50 rounded-xl text-center">
                    <p className="text-2xl font-bold text-primary-700">{analysis.total_rows}</p>
                    <p className="text-xs text-primary-500">Total</p>
                  </div>
                </div>

                {/* Balance validation */}
                <Card>
                  <CardHeader>
                    <CardTitle>Validacao de Saldo</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                      <div className="p-3 rounded-xl bg-slate-50">
                        <p className="text-xs text-slate-400 mb-0.5">Soma das transacoes</p>
                        <p className="text-lg font-bold text-slate-900 tabular-nums">
                          {formatCurrency(analysis.calculated_total || 0)}
                        </p>
                        <p className="text-xs text-slate-400 mt-1">
                          {analysis.positive_count} creditos ({formatCurrency(analysis.positive_total || 0)})
                          {' / '}
                          {analysis.negative_count} debitos ({formatCurrency(analysis.negative_total || 0)})
                        </p>
                      </div>
                      <div className="p-3 rounded-xl bg-slate-50">
                        <p className="text-xs text-slate-400 mb-0.5">Saldo esperado (informe)</p>
                        <Input
                          type="text"
                          placeholder="Ex: -1709.62"
                          value={expectedBalance}
                          onChange={(e) => setExpectedBalance(e.target.value)}
                        />
                      </div>
                      {expectedBalance && (
                        <div className="p-3 rounded-xl bg-slate-50">
                          <p className="text-xs text-slate-400 mb-0.5">Diferenca</p>
                          {(() => {
                            const diff = (analysis.calculated_total || 0) - parseFloat(expectedBalance);
                            const isOk = Math.abs(diff) < 0.02;
                            return (
                              <>
                                <p className={`text-lg font-bold tabular-nums ${isOk ? 'text-emerald-600' : 'text-rose-600'}`}>
                                  {formatCurrency(diff)}
                                </p>
                                <p className={`text-xs mt-1 ${isOk ? 'text-emerald-500' : 'text-rose-500'}`}>
                                  {isOk ? 'Saldo confere!' : 'Saldo divergente'}
                                </p>
                              </>
                            );
                          })()}
                        </div>
                      )}
                    </div>

                    {/* Running balance divergence alert */}
                    {analysis.first_balance_divergence_row && (
                      <div className="p-3 bg-amber-50 border border-amber-200 rounded-xl text-sm text-amber-700">
                        <AlertTriangle className="inline h-4 w-4 mr-1.5" />
                        Saldo diverge na linha {analysis.first_balance_divergence_row} (comparando saldo do arquivo com saldo calculado)
                      </div>
                    )}
                  </CardContent>
                </Card>

                {/* Uncertain transactions */}
                {analysis.uncertain_rows.length > 0 && (
                  <Card>
                    <CardHeader>
                      <CardTitle>
                        <AlertTriangle className="inline h-4 w-4 text-amber-500 mr-1.5" />
                        Transacoes Incertas ({analysis.uncertain_rows.length})
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-2">
                        {analysis.uncertain_rows.map((row) => (
                          <div key={row.row} className="p-3 rounded-lg bg-amber-50/50 border border-amber-100 text-sm">
                            <div className="flex items-center justify-between mb-1">
                              <span className="font-medium text-slate-700">
                                Linha {row.row}: {row.description}
                              </span>
                              <Badge color="amber" variant="soft" size="sm">
                                {Math.round(row.similarity * 100)}% similar
                              </Badge>
                            </div>
                            <p className="text-xs text-slate-500">
                              Similar a: &quot;{row.similar_to_description}&quot; ({formatCurrency(row.amount)})
                            </p>
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                )}

                {/* Transaction preview (collapsible) */}
                <Card>
                  <CardHeader>
                    <button
                      onClick={() => setShowTransactions(!showTransactions)}
                      className="flex items-center justify-between w-full"
                    >
                      <div className="flex items-center gap-2">
                        <FileSpreadsheet className="h-4 w-4 text-slate-400" />
                        <CardTitle>Transacoes ({analysis.transactions_preview.length})</CardTitle>
                      </div>
                      {showTransactions ? (
                        <ChevronUp className="h-4 w-4 text-slate-400" />
                      ) : (
                        <ChevronDown className="h-4 w-4 text-slate-400" />
                      )}
                    </button>
                  </CardHeader>
                  {showTransactions && (
                    <CardContent>
                      <div className="overflow-x-auto rounded-lg border border-slate-200 max-h-[500px] overflow-y-auto">
                        <table className="min-w-full text-xs">
                          <thead className="bg-slate-50 sticky top-0">
                            <tr>
                              <th className="px-3 py-2 text-left font-medium text-slate-500">#</th>
                              <th className="px-3 py-2 text-left font-medium text-slate-500">Status</th>
                              <th className="px-3 py-2 text-left font-medium text-slate-500">Data</th>
                              <th className="px-3 py-2 text-left font-medium text-slate-500">Descricao</th>
                              <th className="px-3 py-2 text-right font-medium text-slate-500">Valor</th>
                              <th className="px-3 py-2 text-right font-medium text-slate-500">Saldo Calc.</th>
                              {analysis.transactions_preview.some(t => t.file_balance !== null) && (
                                <>
                                  <th className="px-3 py-2 text-right font-medium text-slate-500">Saldo Arq.</th>
                                  <th className="px-3 py-2 text-center font-medium text-slate-500">OK</th>
                                </>
                              )}
                            </tr>
                          </thead>
                          <tbody>
                            {analysis.transactions_preview.map((t) => {
                              const statusColor =
                                t.status === 'new' ? 'text-emerald-600 bg-emerald-50' :
                                t.status === 'duplicate' ? 'text-slate-400 bg-slate-50' :
                                'text-amber-600 bg-amber-50';
                              return (
                                <tr
                                  key={t.row}
                                  className={`border-t border-slate-100 ${t.status === 'duplicate' ? 'opacity-50' : ''}`}
                                >
                                  <td className="px-3 py-1.5 text-slate-400">{t.row}</td>
                                  <td className="px-3 py-1.5">
                                    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${statusColor}`}>
                                      {t.status === 'new' ? 'Nova' : t.status === 'duplicate' ? 'Dup' : 'Incerta'}
                                    </span>
                                  </td>
                                  <td className="px-3 py-1.5 text-slate-600 whitespace-nowrap">
                                    {t.date}
                                    {t.adjusted_date && t.adjusted_date !== t.date && (
                                      <span className="text-primary-500 ml-1" title={`Ajustada: ${t.adjusted_date}`}>*</span>
                                    )}
                                  </td>
                                  <td className="px-3 py-1.5 text-slate-700 max-w-xs truncate">
                                    {t.description}
                                    {t.is_installment && (
                                      <Badge color="violet" variant="soft" size="sm" className="ml-1">parc</Badge>
                                    )}
                                  </td>
                                  <td className={`px-3 py-1.5 text-right tabular-nums font-medium ${t.amount >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                                    {formatCurrency(t.amount)}
                                  </td>
                                  <td className="px-3 py-1.5 text-right tabular-nums text-slate-500">
                                    {t.running_balance !== null ? formatCurrency(t.running_balance) : '-'}
                                  </td>
                                  {analysis.transactions_preview.some(tx => tx.file_balance !== null) && (
                                    <>
                                      <td className="px-3 py-1.5 text-right tabular-nums text-slate-500">
                                        {t.file_balance !== null ? formatCurrency(t.file_balance) : '-'}
                                      </td>
                                      <td className="px-3 py-1.5 text-center">
                                        {t.balance_ok === true && <CheckCircle className="h-3.5 w-3.5 text-emerald-500 inline" />}
                                        {t.balance_ok === false && <X className="h-3.5 w-3.5 text-rose-500 inline" />}
                                      </td>
                                    </>
                                  )}
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </CardContent>
                  )}
                </Card>

                {/* Action buttons */}
                <div className="flex items-center gap-3 justify-between">
                  <Button variant="secondary" onClick={resetImport}>
                    <ArrowLeft className="h-4 w-4 mr-1.5" />
                    Voltar
                  </Button>
                  <div className="flex items-center gap-3">
                    {!showMapping && (
                      <Button variant="secondary" size="sm" onClick={() => setShowMapping(true)}>
                        <Settings2 className="h-4 w-4 mr-1.5" />
                        Ajustar mapeamento
                      </Button>
                    )}
                    <Button
                      onClick={() => processMutation.mutate()}
                      disabled={processMutation.isPending || analysis.new_count === 0}
                      isLoading={processMutation.isPending}
                    >
                      Importar {analysis.new_count} transacao{analysis.new_count !== 1 ? 'es' : ''}
                      <ArrowRight className="h-4 w-4 ml-1.5" />
                    </Button>
                  </div>
                </div>
              </>
            )}

            {/* Loading analysis */}
            {!analysis && !analyzeMutation.isPending && !showMapping && (
              <div className="text-center py-8 text-slate-400">
                <p>Abra o mapeamento de colunas para configurar e analisar</p>
              </div>
            )}
            {analyzeMutation.isPending && (
              <div className="text-center py-12">
                <div className="w-10 h-10 border-3 border-primary-200 border-t-primary-600 rounded-full animate-spin mx-auto" />
                <p className="mt-3 text-sm text-slate-500">Analisando arquivo...</p>
              </div>
            )}

            {analyzeMutation.isError && (
              <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl text-sm text-rose-700">
                <AlertCircle className="inline h-4 w-4 mr-1.5" />
                {(analyzeMutation.error as any)?.response?.data?.detail || 'Erro na analise'}
              </div>
            )}
          </div>
        )}

        {/* Step 3: Result */}
        {step === 'result' && result && (
          <Card>
            <CardContent className="pt-8 text-center">
              <div className={`w-16 h-16 rounded-2xl mx-auto mb-4 flex items-center justify-center ${
                result.success ? 'bg-emerald-50' : 'bg-rose-50'
              }`}>
                {result.success ? (
                  <CheckCircle className="h-8 w-8 text-emerald-600" />
                ) : (
                  <AlertCircle className="h-8 w-8 text-rose-600" />
                )}
              </div>
              <h2 className="text-xl font-bold text-slate-900 mb-2">
                {result.success ? 'Importacao concluida!' : 'Importacao com problemas'}
              </h2>

              <div className="grid grid-cols-3 gap-4 max-w-md mx-auto my-6">
                <div className="p-3 bg-emerald-50 rounded-xl">
                  <p className="text-2xl font-bold text-emerald-700">{result.imported_count}</p>
                  <p className="text-xs text-emerald-600">Importadas</p>
                </div>
                <div className="p-3 bg-slate-50 rounded-xl">
                  <p className="text-2xl font-bold text-slate-500">{result.duplicate_count}</p>
                  <p className="text-xs text-slate-400">Duplicadas</p>
                </div>
                <div className="p-3 bg-rose-50 rounded-xl">
                  <p className="text-2xl font-bold text-rose-600">{result.error_count}</p>
                  <p className="text-xs text-rose-500">Erros</p>
                </div>
              </div>

              {result.categories_assigned > 0 && (
                <p className="text-sm text-slate-500 mb-2">
                  {result.categories_assigned} transacoes categorizadas automaticamente
                </p>
              )}

              {result.balance_validated && (
                <div className={`p-3 rounded-xl text-sm mb-4 ${
                  result.balance_matches ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'
                }`}>
                  {result.balance_matches
                    ? 'Saldo validado e confere!'
                    : `Saldo diverge: diferenca de ${formatCurrency(result.balance_difference || 0)}`
                  }
                </div>
              )}

              {result.errors.length > 0 && (
                <div className="text-left mt-4 p-4 bg-rose-50 rounded-xl max-h-48 overflow-y-auto">
                  <p className="text-sm font-medium text-rose-700 mb-2">Erros:</p>
                  {result.errors.slice(0, 10).map((err, i) => (
                    <p key={i} className="text-xs text-rose-600">
                      Linha {err.row}: {err.message}
                    </p>
                  ))}
                </div>
              )}

              <div className="mt-6">
                <Button onClick={resetImport}>
                  Nova importacao
                </Button>
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      {/* Delete batch modal */}
      {deletingBatchId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-2xl p-6 shadow-elevated max-w-sm w-full mx-4">
            <h3 className="text-lg font-bold text-slate-900 mb-2">Reverter importacao?</h3>
            <p className="text-sm text-slate-500 mb-5">
              Todas as transacoes deste lote serao excluidas e o saldo da conta sera ajustado.
            </p>
            <div className="flex gap-3 justify-end">
              <Button variant="secondary" size="sm" onClick={() => setDeletingBatchId(null)}>
                Cancelar
              </Button>
              <Button
                variant="danger"
                size="sm"
                onClick={() => revertMutation.mutate(deletingBatchId)}
                isLoading={revertMutation.isPending}
              >
                Reverter
              </Button>
            </div>
          </div>
        </div>
      )}
    </MainLayout>
  );
}
