'use client';

import { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useDropzone } from 'react-dropzone';
import MainLayout from '@/components/layout/MainLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import Button from '@/components/ui/Button';
import Input from '@/components/ui/Input';
import Select from '@/components/ui/Select';
import { importsApi, accountsApi } from '@/lib/api';
import { formatCurrency, getImportStatusLabel, getImportStatusColor } from '@/lib/utils';
import { Upload, CheckCircle, AlertCircle, Trash2, Search, ArrowRight } from 'lucide-react';
import type { ImportPreview, ImportResult, ImportAnalysis, ColumnMapping } from '@/types';

type Step = 'upload' | 'mapping' | 'analysis' | 'result';

export default function ImportarPage() {
  const [step, setStep] = useState<Step>('upload');
  const [selectedAccount, setSelectedAccount] = useState('');
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [columnMapping, setColumnMapping] = useState<ColumnMapping | null>(null);
  const [analysis, setAnalysis] = useState<ImportAnalysis | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [validateBalance, setValidateBalance] = useState(false);
  const [expectedBalance, setExpectedBalance] = useState('');
  const [deletingBatchId, setDeletingBatchId] = useState<number | null>(null);
  const [skippedUncertain, setSkippedUncertain] = useState<Set<number>>(new Set());

  const queryClient = useQueryClient();

  // Buscar contas
  const { data: accounts = [] } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
  });

  // Buscar histórico de importações
  const { data: batches = [] } = useQuery({
    queryKey: ['import-batches'],
    queryFn: () => importsApi.listBatches(),
  });

  // Upload mutation
  const uploadMutation = useMutation({
    mutationFn: (file: File) => importsApi.upload(file, parseInt(selectedAccount)),
    onSuccess: (data) => {
      setPreview(data);
      setColumnMapping(data.detected_mapping);
      setStep('mapping');
    },
  });

  // Analyze mutation (dry-run)
  const analyzeMutation = useMutation({
    mutationFn: () =>
      importsApi.analyze({
        batch_id: preview!.batch_id,
        column_mapping: columnMapping!,
        account_id: parseInt(selectedAccount),
      }),
    onSuccess: (data) => {
      setAnalysis(data);
      setSkippedUncertain(new Set());
      setStep('analysis');
    },
  });

  // Process mutation
  const processMutation = useMutation({
    mutationFn: () =>
      importsApi.process({
        batch_id: preview!.batch_id,
        column_mapping: columnMapping!,
        account_id: parseInt(selectedAccount),
        validate_balance: validateBalance,
        expected_final_balance: validateBalance ? parseFloat(expectedBalance) : undefined,
        skip_duplicates: true,
      }),
    onSuccess: (data) => {
      setResult(data);
      setStep('result');
      queryClient.invalidateQueries({ queryKey: ['import-batches'] });
      queryClient.invalidateQueries({ queryKey: ['accounts'] });
    },
  });

  // Revert batch mutation
  const revertMutation = useMutation({
    mutationFn: (batchId: number) => importsApi.revertBatch(batchId),
    onSuccess: () => {
      setDeletingBatchId(null);
      queryClient.invalidateQueries({ queryKey: ['import-batches'] });
      queryClient.invalidateQueries({ queryKey: ['accounts'] });
    },
  });

  // Dropzone
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
      'application/pdf': ['.pdf'],
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
    setSkippedUncertain(new Set());
  };

  const toggleUncertain = (row: number) => {
    setSkippedUncertain((prev) => {
      const next = new Set(prev);
      if (next.has(row)) {
        next.delete(row);
      } else {
        next.add(row);
      }
      return next;
    });
  };

  const stepLabels = ['Upload', 'Mapeamento', 'Análise', 'Resultado'];
  const stepKeys: Step[] = ['upload', 'mapping', 'analysis', 'result'];

  return (
    <MainLayout>
      <div className="space-y-6">
        {/* Cabeçalho */}
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Importar Extrato</h1>
          <p className="text-gray-600">Importe extratos em CSV, Excel ou PDF</p>
        </div>

        {/* Steps */}
        <div className="flex items-center gap-4 mb-8">
          {stepKeys.map((s, i) => (
            <div key={s} className="flex items-center">
              <div className="flex flex-col items-center">
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
                    step === s
                      ? 'bg-primary-600 text-white'
                      : stepKeys.indexOf(step) > i
                      ? 'bg-green-500 text-white'
                      : 'bg-gray-200 text-gray-500'
                  }`}
                >
                  {i + 1}
                </div>
                <span className="text-xs text-gray-500 mt-1">{stepLabels[i]}</span>
              </div>
              {i < 3 && <div className="w-12 h-0.5 bg-gray-200 mx-2 mb-5" />}
            </div>
          ))}
        </div>

        {/* Step 1: Upload */}
        {step === 'upload' && (
          <Card>
            <CardHeader>
              <CardTitle>1. Selecione a conta e o arquivo</CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <Select
                label="Conta de destino"
                value={selectedAccount}
                onChange={(e) => setSelectedAccount(e.target.value)}
                options={accounts.map((a) => ({ value: a.id, label: `${a.name} (${a.bank_name})` }))}
                placeholder="Selecione a conta"
              />

              <div
                {...getRootProps()}
                className={`border-2 border-dashed rounded-lg p-12 text-center cursor-pointer transition-colors ${
                  isDragActive
                    ? 'border-primary-500 bg-primary-50'
                    : selectedAccount
                    ? 'border-gray-300 hover:border-primary-400'
                    : 'border-gray-200 bg-gray-50 cursor-not-allowed'
                }`}
              >
                <input {...getInputProps()} />
                <Upload className="mx-auto text-gray-400 mb-4" size={48} />
                {isDragActive ? (
                  <p className="text-primary-600">Solte o arquivo aqui...</p>
                ) : (
                  <>
                    <p className="text-gray-600 mb-2">
                      {selectedAccount
                        ? 'Arraste um arquivo ou clique para selecionar'
                        : 'Selecione uma conta primeiro'}
                    </p>
                    <p className="text-sm text-gray-400">CSV, Excel (.xlsx) ou PDF</p>
                  </>
                )}
              </div>

              {uploadMutation.isPending && (
                <div className="text-center text-primary-600">Processando arquivo...</div>
              )}

              {uploadMutation.isError && (
                <div className="text-center text-red-500">
                  Erro ao processar arquivo. Verifique o formato.
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Step 2: Mapping */}
        {step === 'mapping' && preview && columnMapping && (
          <Card>
            <CardHeader>
              <CardTitle>2. Mapeamento de colunas</CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <p className="text-gray-600">
                {preview.total_rows} linhas encontradas. Verifique se as colunas foram detectadas corretamente.
              </p>

              {/* Preview dos dados */}
              <div className="overflow-x-auto border rounded-lg">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-2 text-left">Data</th>
                      <th className="px-4 py-2 text-left">Descrição</th>
                      {columnMapping.valor_brl_column && (
                        <th className="px-4 py-2 text-right">R$</th>
                      )}
                      {columnMapping.valor_usd_column && (
                        <th className="px-4 py-2 text-right">US$</th>
                      )}
                      {columnMapping.valor_eur_column && (
                        <th className="px-4 py-2 text-right">EUR</th>
                      )}
                      {!columnMapping.valor_brl_column && !columnMapping.valor_usd_column && !columnMapping.valor_eur_column && columnMapping.amount_column && (
                        <th className="px-4 py-2 text-right">Valor</th>
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {preview.preview_rows.slice(0, 5).map((row, i) => (
                      <tr key={i} className="border-t">
                        <td className="px-4 py-2">{row[columnMapping.date_column]}</td>
                        <td className="px-4 py-2">{row[columnMapping.description_column]}</td>
                        {columnMapping.valor_brl_column && (
                          <td className="px-4 py-2 text-right">{row[columnMapping.valor_brl_column]}</td>
                        )}
                        {columnMapping.valor_usd_column && (
                          <td className="px-4 py-2 text-right">{row[columnMapping.valor_usd_column]}</td>
                        )}
                        {columnMapping.valor_eur_column && (
                          <td className="px-4 py-2 text-right">{row[columnMapping.valor_eur_column]}</td>
                        )}
                        {!columnMapping.valor_brl_column && !columnMapping.valor_usd_column && !columnMapping.valor_eur_column && columnMapping.amount_column && (
                          <td className="px-4 py-2 text-right">{row[columnMapping.amount_column]}</td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Colunas obrigatórias */}
              <div>
                <h3 className="text-sm font-medium text-gray-700 mb-3">Colunas Obrigatórias</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <Select
                    label="Coluna de Data"
                    value={columnMapping.date_column}
                    onChange={(e) =>
                      setColumnMapping({ ...columnMapping, date_column: e.target.value })
                    }
                    options={preview.columns.map((c) => ({ value: c, label: c }))}
                  />

                  <Select
                    label="Coluna de Descrição"
                    value={columnMapping.description_column}
                    onChange={(e) =>
                      setColumnMapping({ ...columnMapping, description_column: e.target.value })
                    }
                    options={preview.columns.map((c) => ({ value: c, label: c }))}
                  />
                </div>
              </div>

              {/* Colunas de Valor Multi-moeda */}
              <div className="p-4 bg-blue-50 rounded-lg">
                <h3 className="text-sm font-medium text-blue-800 mb-3">Colunas de Valor (Multi-moeda)</h3>
                <p className="text-xs text-blue-600 mb-3">
                  Selecione as colunas de valor para cada moeda. Pelo menos uma deve ser preenchida.
                </p>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <Select
                    label="Valor em R$ (BRL)"
                    value={columnMapping.valor_brl_column || ''}
                    onChange={(e) =>
                      setColumnMapping({
                        ...columnMapping,
                        valor_brl_column: e.target.value || null,
                      })
                    }
                    options={[
                      { value: '', label: 'Não disponível' },
                      ...preview.columns.map((c) => ({ value: c, label: c })),
                    ]}
                  />

                  <Select
                    label="Valor em US$ (USD)"
                    value={columnMapping.valor_usd_column || ''}
                    onChange={(e) =>
                      setColumnMapping({
                        ...columnMapping,
                        valor_usd_column: e.target.value || null,
                      })
                    }
                    options={[
                      { value: '', label: 'Não disponível' },
                      ...preview.columns.map((c) => ({ value: c, label: c })),
                    ]}
                  />

                  <Select
                    label="Valor em EUR"
                    value={columnMapping.valor_eur_column || ''}
                    onChange={(e) =>
                      setColumnMapping({
                        ...columnMapping,
                        valor_eur_column: e.target.value || null,
                      })
                    }
                    options={[
                      { value: '', label: 'Não disponível' },
                      ...preview.columns.map((c) => ({ value: c, label: c })),
                    ]}
                  />
                </div>

                {/* Campo de valor genérico como fallback */}
                <div className="mt-4 pt-4 border-t border-blue-200">
                  <Select
                    label="Ou Coluna de Valor Genérico (se não houver colunas separadas por moeda)"
                    value={columnMapping.amount_column || ''}
                    onChange={(e) =>
                      setColumnMapping({ ...columnMapping, amount_column: e.target.value || null })
                    }
                    options={[
                      { value: '', label: 'Não disponível' },
                      ...preview.columns.map((c) => ({ value: c, label: c })),
                    ]}
                  />
                </div>
              </div>

              {/* Colunas opcionais */}
              <div>
                <h3 className="text-sm font-medium text-gray-700 mb-3">Colunas Opcionais</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <Select
                    label="Coluna de Categoria"
                    value={columnMapping.category_column || ''}
                    onChange={(e) =>
                      setColumnMapping({
                        ...columnMapping,
                        category_column: e.target.value || null,
                      })
                    }
                    options={[
                      { value: '', label: 'Não disponível' },
                      ...preview.columns.map((c) => ({ value: c, label: c })),
                    ]}
                  />

                  <Select
                    label="Coluna de Saldo"
                    value={columnMapping.balance_column || ''}
                    onChange={(e) =>
                      setColumnMapping({
                        ...columnMapping,
                        balance_column: e.target.value || null,
                      })
                    }
                    options={[
                      { value: '', label: 'Não disponível' },
                      ...preview.columns.map((c) => ({ value: c, label: c })),
                    ]}
                  />

                  <Select
                    label="Data Pagamento Cartão (para ajuste de fatura)"
                    value={columnMapping.card_payment_date_column || ''}
                    onChange={(e) =>
                      setColumnMapping({
                        ...columnMapping,
                        card_payment_date_column: e.target.value || null,
                      })
                    }
                    options={[
                      { value: '', label: 'Não disponível' },
                      ...preview.columns.map((c) => ({ value: c, label: c })),
                    ]}
                  />
                </div>
              </div>

              <div className="flex gap-4">
                <Button variant="secondary" onClick={resetImport}>
                  Voltar
                </Button>
                <Button
                  onClick={() => analyzeMutation.mutate()}
                  isLoading={analyzeMutation.isPending}
                >
                  <Search size={16} className="mr-2" />
                  Analisar
                </Button>
              </div>

              {analyzeMutation.isError && (
                <div className="p-4 bg-red-50 text-red-700 rounded-lg">
                  Erro ao analisar arquivo. Verifique o mapeamento de colunas.
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Step 3: Analysis */}
        {step === 'analysis' && analysis && (
          <Card>
            <CardHeader>
              <CardTitle>3. Análise de duplicados</CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Overlap warning */}
              {analysis.overlap_info && (
                <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg flex items-start gap-3">
                  <AlertCircle className="text-amber-500 flex-shrink-0 mt-0.5" size={20} />
                  <div>
                    <p className="font-medium text-amber-800">Sobreposição detectada</p>
                    <p className="text-sm text-amber-700">{analysis.overlap_info}</p>
                  </div>
                </div>
              )}

              {/* Date range */}
              {analysis.date_range_start && analysis.date_range_end && (
                <p className="text-sm text-gray-500">
                  Período do arquivo: {new Date(analysis.date_range_start + 'T12:00:00').toLocaleDateString('pt-BR')} a {new Date(analysis.date_range_end + 'T12:00:00').toLocaleDateString('pt-BR')}
                </p>
              )}

              {/* Summary cards */}
              <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                <div className="p-4 bg-green-50 rounded-lg text-center">
                  <p className="text-2xl font-bold text-green-600">{analysis.new_count}</p>
                  <p className="text-sm text-gray-500">Novas</p>
                </div>
                <div className="p-4 bg-gray-50 rounded-lg text-center">
                  <p className="text-2xl font-bold text-gray-400">{analysis.duplicate_count}</p>
                  <p className="text-sm text-gray-500">Duplicatas exatas</p>
                </div>
                <div className="p-4 bg-blue-50 rounded-lg text-center">
                  <p className="text-2xl font-bold text-blue-500">{analysis.fuzzy_duplicate_count}</p>
                  <p className="text-sm text-gray-500">Duplicatas similares</p>
                </div>
                <div className="p-4 bg-amber-50 rounded-lg text-center">
                  <p className="text-2xl font-bold text-amber-500">{analysis.uncertain_count}</p>
                  <p className="text-sm text-gray-500">Incertas</p>
                </div>
                <div className="p-4 bg-red-50 rounded-lg text-center">
                  <p className="text-2xl font-bold text-red-500">{analysis.error_count}</p>
                  <p className="text-sm text-gray-500">Erros</p>
                </div>
              </div>

              {/* Total summary */}
              <div className="p-4 bg-gray-50 rounded-lg">
                <p className="text-sm text-gray-600">
                  <strong>{analysis.total_rows}</strong> linhas no arquivo.{' '}
                  <strong className="text-green-600">{analysis.new_count}</strong> transações novas serão importadas.{' '}
                  <strong className="text-gray-400">{analysis.duplicate_count + analysis.fuzzy_duplicate_count}</strong> duplicatas serão ignoradas.
                </p>
              </div>

              {/* Uncertain rows review */}
              {analysis.uncertain_rows.length > 0 && (
                <div className="border border-amber-200 rounded-lg">
                  <div className="p-4 bg-amber-50 border-b border-amber-200">
                    <h4 className="font-medium text-amber-800">
                      Transações incertas ({analysis.uncertain_rows.length})
                    </h4>
                    <p className="text-sm text-amber-600 mt-1">
                      Estas transações são parecidas com existentes mas não temos certeza se são duplicatas.
                      Marque as que deseja pular.
                    </p>
                  </div>
                  <div className="divide-y">
                    {analysis.uncertain_rows.map((row) => (
                      <div
                        key={row.row}
                        className={`p-4 flex items-center gap-4 ${
                          skippedUncertain.has(row.row) ? 'bg-gray-50 opacity-60' : ''
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={skippedUncertain.has(row.row)}
                          onChange={() => toggleUncertain(row.row)}
                          className="rounded flex-shrink-0"
                        />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="text-sm font-medium">{row.date}</span>
                            <span className="text-sm text-gray-700 truncate">{row.description}</span>
                            <span className={`text-sm font-medium ${row.amount < 0 ? 'text-red-600' : 'text-green-600'}`}>
                              {formatCurrency(row.amount)}
                            </span>
                          </div>
                          <div className="flex items-center gap-2 text-xs text-gray-500">
                            <span>Similar a:</span>
                            <span className="text-gray-600">&quot;{row.similar_to_description}&quot;</span>
                            <span className="px-1.5 py-0.5 bg-amber-100 text-amber-700 rounded">
                              {Math.round(row.similarity * 100)}% similar
                            </span>
                          </div>
                        </div>
                        <span className="text-xs text-gray-400 flex-shrink-0">
                          {skippedUncertain.has(row.row) ? 'Pular' : 'Importar'}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Balance validation */}
              <div className="p-4 bg-gray-50 rounded-lg">
                <label className="flex items-center gap-2 mb-4">
                  <input
                    type="checkbox"
                    checked={validateBalance}
                    onChange={(e) => setValidateBalance(e.target.checked)}
                    className="rounded"
                  />
                  <span>Validar saldo final</span>
                </label>

                {validateBalance && (
                  <Input
                    label="Saldo esperado após importação"
                    type="number"
                    step="0.01"
                    value={expectedBalance}
                    onChange={(e) => setExpectedBalance(e.target.value)}
                    placeholder="0.00"
                  />
                )}
              </div>

              <div className="flex gap-4">
                <Button variant="secondary" onClick={() => setStep('mapping')}>
                  Voltar
                </Button>
                <Button
                  onClick={() => processMutation.mutate()}
                  isLoading={processMutation.isPending}
                  disabled={analysis.new_count === 0 && analysis.uncertain_count === 0}
                >
                  <ArrowRight size={16} className="mr-2" />
                  Importar {analysis.new_count + analysis.uncertain_count - skippedUncertain.size} transações
                </Button>
              </div>

              {processMutation.isError && (
                <div className="p-4 bg-red-50 text-red-700 rounded-lg">
                  Erro ao importar. Tente novamente.
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Step 4: Result */}
        {step === 'result' && result && (
          <Card>
            <CardHeader>
              <CardTitle>4. Resultado da importação</CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <div
                className={`p-6 rounded-lg text-center ${
                  result.success ? 'bg-green-50' : 'bg-red-50'
                }`}
              >
                {result.success ? (
                  <CheckCircle className="mx-auto text-green-500 mb-4" size={48} />
                ) : (
                  <AlertCircle className="mx-auto text-red-500 mb-4" size={48} />
                )}
                <h3 className="text-lg font-medium mb-2">
                  {result.success ? 'Importação concluída!' : 'Importação com problemas'}
                </h3>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="p-4 bg-gray-50 rounded-lg text-center">
                  <p className="text-2xl font-bold text-green-600">{result.imported_count}</p>
                  <p className="text-sm text-gray-500">Importadas</p>
                </div>
                <div className="p-4 bg-gray-50 rounded-lg text-center">
                  <p className="text-2xl font-bold text-orange-600">{result.duplicate_count}</p>
                  <p className="text-sm text-gray-500">Duplicatas</p>
                </div>
                <div className="p-4 bg-gray-50 rounded-lg text-center">
                  <p className="text-2xl font-bold text-red-600">{result.error_count}</p>
                  <p className="text-sm text-gray-500">Erros</p>
                </div>
                {result.balance_validated && (
                  <div className="p-4 bg-gray-50 rounded-lg text-center">
                    <p
                      className={`text-2xl font-bold ${
                        result.balance_matches ? 'text-green-600' : 'text-red-600'
                      }`}
                    >
                      {result.balance_matches ? 'OK' : formatCurrency(result.balance_difference || 0)}
                    </p>
                    <p className="text-sm text-gray-500">Saldo</p>
                  </div>
                )}
              </div>

              {result.errors.length > 0 && (
                <div className="p-4 bg-red-50 rounded-lg">
                  <h4 className="font-medium text-red-800 mb-2">Erros encontrados:</h4>
                  <ul className="text-sm text-red-600 space-y-1">
                    {result.errors.map((err, i) => (
                      <li key={i}>
                        Linha {err.row}: {err.message}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {result.duplicates.length > 0 && (
                <div className="p-4 bg-orange-50 rounded-lg">
                  <h4 className="font-medium text-orange-800 mb-2">
                    Duplicatas ignoradas ({result.duplicate_count}):
                  </h4>
                  <ul className="text-sm text-orange-600 space-y-1">
                    {result.duplicates.slice(0, 5).map((dup, i) => (
                      <li key={i}>
                        {dup.date} - {dup.description} ({formatCurrency(dup.amount)})
                      </li>
                    ))}
                    {result.duplicates.length > 5 && (
                      <li>... e mais {result.duplicates.length - 5}</li>
                    )}
                  </ul>
                </div>
              )}

              <Button onClick={resetImport}>Nova importação</Button>
            </CardContent>
          </Card>
        )}

        {/* Histórico de Importações */}
        <Card>
          <CardHeader>
            <CardTitle>Histórico de Importações</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {batches.length === 0 ? (
              <p className="text-center py-8 text-gray-500">Nenhuma importação realizada</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-6 py-3 text-left">Arquivo</th>
                      <th className="px-6 py-3 text-left">Tipo</th>
                      <th className="px-6 py-3 text-center">Registros</th>
                      <th className="px-6 py-3 text-center">Status</th>
                      <th className="px-6 py-3 text-left">Data</th>
                      <th className="px-6 py-3 text-center">Ações</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {batches.slice(0, 10).map((batch) => (
                      <tr key={batch.id} className="hover:bg-gray-50">
                        <td className="px-6 py-4">{batch.filename}</td>
                        <td className="px-6 py-4 uppercase">{batch.file_type}</td>
                        <td className="px-6 py-4 text-center">
                          {batch.imported_records}/{batch.total_records}
                        </td>
                        <td className="px-6 py-4 text-center">
                          <span
                            className={`px-2 py-1 rounded-full text-xs ${getImportStatusColor(
                              batch.status
                            )}`}
                          >
                            {getImportStatusLabel(batch.status)}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-gray-500">
                          {new Date(batch.imported_at).toLocaleString('pt-BR')}
                        </td>
                        <td className="px-6 py-4 text-center">
                          <button
                            onClick={() => setDeletingBatchId(batch.id)}
                            className="text-gray-400 hover:text-red-600 transition-colors p-1 rounded hover:bg-red-50"
                            title="Excluir importação"
                          >
                            <Trash2 size={18} />
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

        {/* Modal de confirmação de exclusão */}
        {deletingBatchId && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-lg p-6 max-w-md w-full mx-4 shadow-xl">
              <h3 className="text-lg font-semibold text-gray-900 mb-2">Confirmar exclusão</h3>
              <p className="text-gray-600 mb-1">
                Tem certeza que deseja excluir esta importação?
              </p>
              <p className="text-sm text-red-600 mb-6">
                Todas as transações deste lote serão removidas e o saldo da conta será ajustado.
              </p>
              {revertMutation.isError && (
                <div className="mb-4 p-3 bg-red-50 text-red-700 rounded text-sm">
                  Erro ao excluir importação. Tente novamente.
                </div>
              )}
              <div className="flex justify-end gap-3">
                <button
                  onClick={() => { setDeletingBatchId(null); revertMutation.reset(); }}
                  className="px-4 py-2 text-gray-600 hover:text-gray-800 font-medium"
                  disabled={revertMutation.isPending}
                >
                  Cancelar
                </button>
                <button
                  onClick={() => revertMutation.mutate(deletingBatchId)}
                  disabled={revertMutation.isPending}
                  className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50 font-medium"
                >
                  {revertMutation.isPending ? 'Excluindo...' : 'Excluir'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </MainLayout>
  );
}
