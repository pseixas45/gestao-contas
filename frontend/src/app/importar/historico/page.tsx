'use client';

import { useState, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import MainLayout from '@/components/layout/MainLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import Button from '@/components/ui/Button';
import Select from '@/components/ui/Select';
import { formatCurrency } from '@/lib/utils';
import { Upload, CheckCircle, AlertCircle, FileText } from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface BulkUploadResult {
  total_rows: number;
  columns: string[];
  detected_mapping: {
    date_column: string;
    description_column: string;
    amount_column: string | null;
    balance_column: string | null;
    bank_column: string | null;
    account_column: string | null;
    category_column: string | null;
    valor_brl_column: string | null;
    valor_usd_column: string | null;
    valor_eur_column: string | null;
    card_payment_date_column: string | null;
  };
  banks_accounts_found: Array<{ bank: string; account: string }>;
  preview_rows: Record<string, any>[];
  temp_file_path: string;
  file_type: string;
}

interface BulkProcessResult {
  total_rows: number;
  accounts_processed: number;
  accounts_created: number;
  categories_created: number;
  transactions_imported: number;
  duplicates_skipped: number;
  errors: string[];
  accounts_summary: Array<{
    bank: string;
    account: string;
    imported: number;
    duplicates: number;
  }>;
}

type Step = 'upload' | 'mapping' | 'result';

export default function ImportarHistoricoPage() {
  const [step, setStep] = useState<Step>('upload');
  const [isUploading, setIsUploading] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadResult, setUploadResult] = useState<BulkUploadResult | null>(null);
  const [processResult, setProcessResult] = useState<BulkProcessResult | null>(null);

  // Mapeamento de colunas
  const [mapping, setMapping] = useState({
    date_column: '',
    description_column: '',
    amount_column: '',
    bank_column: '',
    account_column: '',
    balance_column: '',
    category_column: '',
    valor_brl_column: '',
    valor_usd_column: '',
    valor_eur_column: '',
    card_payment_date_column: '',
  });

  const [options, setOptions] = useState({
    create_missing_accounts: true,
    create_missing_categories: true,
    skip_duplicates: true,
  });

  // Upload do arquivo
  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    if (acceptedFiles.length === 0) return;

    setIsUploading(true);
    setError(null);

    const formData = new FormData();
    formData.append('file', acceptedFiles[0]);

    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_URL}/api/v1/imports/bulk-upload`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body: formData,
      });

      if (!response.ok) {
        const errText = await response.text();
        let errMessage = 'Erro ao processar arquivo';
        try {
          const errJson = JSON.parse(errText);
          // detail pode ser string ou objeto
          if (typeof errJson.detail === 'string') {
            errMessage = errJson.detail;
          } else if (errJson.detail) {
            errMessage = JSON.stringify(errJson.detail);
          } else {
            errMessage = JSON.stringify(errJson);
          }
        } catch {
          errMessage = errText || `Erro HTTP ${response.status}`;
        }
        throw new Error(errMessage);
      }

      const result: BulkUploadResult = await response.json();
      console.log('Upload result:', result);
      setUploadResult(result);

      // Preencher mapeamento detectado
      setMapping({
        date_column: result.detected_mapping.date_column || '',
        description_column: result.detected_mapping.description_column || '',
        amount_column: result.detected_mapping.amount_column || '',
        bank_column: result.detected_mapping.bank_column || '',
        account_column: result.detected_mapping.account_column || '',
        balance_column: result.detected_mapping.balance_column || '',
        category_column: result.detected_mapping.category_column || '',
        valor_brl_column: result.detected_mapping.valor_brl_column || '',
        valor_usd_column: result.detected_mapping.valor_usd_column || '',
        valor_eur_column: result.detected_mapping.valor_eur_column || '',
        card_payment_date_column: result.detected_mapping.card_payment_date_column || '',
      });

      setStep('mapping');
    } catch (err: any) {
      let errorMessage = 'Erro desconhecido';
      if (typeof err === 'string') {
        errorMessage = err;
      } else if (err instanceof Error) {
        errorMessage = err.message;
      } else if (err && typeof err === 'object') {
        errorMessage = err.message || err.detail || JSON.stringify(err);
      }
      setError(errorMessage);
    } finally {
      setIsUploading(false);
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'text/csv': ['.csv'],
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
    },
    maxFiles: 1,
  });

  // Processar importação
  const handleProcess = async () => {
    if (!uploadResult) return;

    // Validar campos obrigatórios
    if (!mapping.date_column || !mapping.description_column) {
      setError('Preencha as colunas de Data e Descrição');
      return;
    }

    // Pelo menos um campo de valor deve estar preenchido
    const hasValueColumn = mapping.amount_column || mapping.valor_brl_column ||
                           mapping.valor_usd_column || mapping.valor_eur_column;
    if (!hasValueColumn) {
      setError('Preencha pelo menos uma coluna de valor (R$, US$, EUR ou Valor genérico)');
      return;
    }

    if (!mapping.bank_column || !mapping.account_column) {
      setError('Preencha as colunas de Banco e Conta');
      return;
    }

    setIsProcessing(true);
    setError(null);

    const formData = new FormData();
    formData.append('temp_file_path', uploadResult.temp_file_path);
    formData.append('file_type', uploadResult.file_type);
    formData.append('date_column', mapping.date_column);
    formData.append('description_column', mapping.description_column);
    formData.append('bank_column', mapping.bank_column);
    formData.append('account_column', mapping.account_column);
    if (mapping.amount_column) {
      formData.append('amount_column', mapping.amount_column);
    }
    if (mapping.balance_column) {
      formData.append('balance_column', mapping.balance_column);
    }
    if (mapping.category_column) {
      formData.append('category_column', mapping.category_column);
    }
    if (mapping.valor_brl_column) {
      formData.append('valor_brl_column', mapping.valor_brl_column);
    }
    if (mapping.valor_usd_column) {
      formData.append('valor_usd_column', mapping.valor_usd_column);
    }
    if (mapping.valor_eur_column) {
      formData.append('valor_eur_column', mapping.valor_eur_column);
    }
    if (mapping.card_payment_date_column) {
      formData.append('card_payment_date_column', mapping.card_payment_date_column);
    }
    formData.append('create_missing_accounts', options.create_missing_accounts.toString());
    formData.append('create_missing_categories', options.create_missing_categories.toString());
    formData.append('skip_duplicates', options.skip_duplicates.toString());

    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_URL}/api/v1/imports/bulk-process`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body: formData,
      });

      if (!response.ok) {
        const errText = await response.text();
        let errMessage = 'Erro ao processar importação';
        try {
          const errJson = JSON.parse(errText);
          // detail pode ser string ou objeto
          if (typeof errJson.detail === 'string') {
            errMessage = errJson.detail;
          } else if (errJson.detail) {
            errMessage = JSON.stringify(errJson.detail);
          } else {
            errMessage = JSON.stringify(errJson);
          }
        } catch {
          errMessage = errText || `Erro HTTP ${response.status}`;
        }
        throw new Error(errMessage);
      }

      const result: BulkProcessResult = await response.json();
      setProcessResult(result);
      setStep('result');
    } catch (err: any) {
      console.error('Erro na importação:', err);
      let errorMessage = 'Erro desconhecido';
      if (typeof err === 'string') {
        errorMessage = err;
      } else if (err instanceof Error) {
        errorMessage = err.message;
      } else if (err && typeof err === 'object') {
        errorMessage = err.message || err.detail || JSON.stringify(err);
      }
      setError(errorMessage);
    } finally {
      setIsProcessing(false);
    }
  };

  const resetImport = () => {
    setStep('upload');
    setUploadResult(null);
    setProcessResult(null);
    setError(null);
    setMapping({
      date_column: '',
      description_column: '',
      amount_column: '',
      bank_column: '',
      account_column: '',
      balance_column: '',
      category_column: '',
      valor_brl_column: '',
      valor_usd_column: '',
      valor_eur_column: '',
      card_payment_date_column: '',
    });
  };

  const columnOptions = uploadResult
    ? [{ value: '', label: 'Selecione...' }, ...uploadResult.columns.map((c) => ({ value: c, label: c }))]
    : [];

  return (
    <MainLayout>
      <div className="space-y-6">
        {/* Cabeçalho */}
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Importar Histórico Completo</h1>
          <p className="text-gray-600">
            Importe um arquivo com todas as contas de uma vez (Banco, Conta, Data, Descrição, Valor)
          </p>
        </div>

        {/* Steps */}
        <div className="flex items-center gap-4 mb-8">
          {['upload', 'mapping', 'result'].map((s, i) => (
            <div key={s} className="flex items-center">
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
                  step === s
                    ? 'bg-primary-600 text-white'
                    : i < ['upload', 'mapping', 'result'].indexOf(step)
                    ? 'bg-green-500 text-white'
                    : 'bg-gray-200 text-gray-500'
                }`}
              >
                {i + 1}
              </div>
              {i < 2 && <div className="w-12 h-0.5 bg-gray-200 mx-2" />}
            </div>
          ))}
        </div>

        {/* Erro */}
        {error && (
          <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
            {error}
          </div>
        )}

        {/* Step 1: Upload */}
        {step === 'upload' && (
          <Card>
            <CardHeader>
              <CardTitle>1. Selecione o arquivo</CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="p-4 bg-blue-50 rounded-lg text-blue-800 text-sm">
                <p className="font-medium mb-2">Formato esperado do arquivo:</p>
                <p>O arquivo deve conter as colunas: <strong>Banco</strong>, <strong>Conta</strong>, <strong>Data</strong>, <strong>Descrição</strong></p>
                <p className="mt-1">Valores: <strong>Valor R$</strong>, <strong>Valor US$</strong>, <strong>Valor EUR</strong> (ou <strong>Valor</strong> genérico)</p>
                <p className="mt-1 text-blue-600">Opcionais: <strong>Categoria</strong>, <strong>Data Pagto Cartao</strong>, <strong>Saldo</strong></p>
                <p className="mt-2">Exemplo com multi-moeda:</p>
                <code className="block mt-1 p-2 bg-white rounded text-xs">
                  Banco;Conta;Data;Descrição;Data Pagto Cartao;Valor R$;Valor US$;Valor EUR;Categoria<br />
                  Itaú;CC Principal;01/01/2024;SALÁRIO;;5000,00;;;Salário<br />
                  Nubank;Cartão;05/01/2024;AMAZON 2/10;10/02/2024;;-50,00;;Compras<br />
                  BTG;USD Account;02/01/2024;DIVIDEND;;;100,00;;Investimentos
                </code>
              </div>

              <div
                {...getRootProps()}
                className={`border-2 border-dashed rounded-lg p-12 text-center cursor-pointer transition-colors ${
                  isDragActive
                    ? 'border-primary-500 bg-primary-50'
                    : 'border-gray-300 hover:border-primary-400'
                }`}
              >
                <input {...getInputProps()} />
                {isUploading ? (
                  <div className="text-primary-600">Processando arquivo...</div>
                ) : (
                  <>
                    <Upload className="mx-auto text-gray-400 mb-4" size={48} />
                    <p className="text-gray-600 mb-2">
                      Arraste um arquivo ou clique para selecionar
                    </p>
                    <p className="text-sm text-gray-400">CSV ou Excel (.xlsx)</p>
                  </>
                )}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Step 2: Mapping */}
        {step === 'mapping' && uploadResult && (
          <Card>
            <CardHeader>
              <CardTitle>2. Mapeamento de colunas</CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <p className="text-gray-600">
                {uploadResult.total_rows} linhas encontradas. Configure o mapeamento das colunas:
              </p>

              {/* Contas encontradas */}
              {uploadResult.banks_accounts_found.length > 0 && (
                <div className="p-4 bg-green-50 rounded-lg">
                  <p className="font-medium text-green-800 mb-2">
                    Contas detectadas no arquivo:
                  </p>
                  <ul className="text-sm text-green-700 space-y-1">
                    {uploadResult.banks_accounts_found.map((ba, i) => (
                      <li key={i}>• {ba.bank} - {ba.account}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Mapeamento - Campos obrigatórios */}
              <div>
                <h3 className="text-sm font-medium text-gray-700 mb-3">Campos Obrigatórios</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                  <Select
                    label="Coluna de Banco *"
                    value={mapping.bank_column}
                    onChange={(e) => setMapping({ ...mapping, bank_column: e.target.value })}
                    options={columnOptions}
                  />

                  <Select
                    label="Coluna de Conta *"
                    value={mapping.account_column}
                    onChange={(e) => setMapping({ ...mapping, account_column: e.target.value })}
                    options={columnOptions}
                  />

                  <Select
                    label="Coluna de Data *"
                    value={mapping.date_column}
                    onChange={(e) => setMapping({ ...mapping, date_column: e.target.value })}
                    options={columnOptions}
                  />

                  <Select
                    label="Coluna de Descrição *"
                    value={mapping.description_column}
                    onChange={(e) => setMapping({ ...mapping, description_column: e.target.value })}
                    options={columnOptions}
                  />
                </div>
              </div>

              {/* Mapeamento - Valores Multi-moeda */}
              <div className="p-4 bg-blue-50 rounded-lg">
                <h3 className="text-sm font-medium text-blue-800 mb-2">Colunas de Valor (Multi-moeda)</h3>
                <p className="text-xs text-blue-600 mb-3">
                  Selecione as colunas de valor para cada moeda. Pelo menos uma deve ser preenchida.
                </p>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <Select
                    label="Valor em R$ (BRL)"
                    value={mapping.valor_brl_column}
                    onChange={(e) => setMapping({ ...mapping, valor_brl_column: e.target.value })}
                    options={columnOptions}
                  />

                  <Select
                    label="Valor em US$ (USD)"
                    value={mapping.valor_usd_column}
                    onChange={(e) => setMapping({ ...mapping, valor_usd_column: e.target.value })}
                    options={columnOptions}
                  />

                  <Select
                    label="Valor em EUR"
                    value={mapping.valor_eur_column}
                    onChange={(e) => setMapping({ ...mapping, valor_eur_column: e.target.value })}
                    options={columnOptions}
                  />
                </div>

                <div className="mt-4 pt-4 border-t border-blue-200">
                  <Select
                    label="Ou Coluna de Valor Genérico (se não houver colunas por moeda)"
                    value={mapping.amount_column}
                    onChange={(e) => setMapping({ ...mapping, amount_column: e.target.value })}
                    options={columnOptions}
                  />
                </div>
              </div>

              {/* Mapeamento - Campos opcionais */}
              <div>
                <h3 className="text-sm font-medium text-gray-700 mb-3">Campos Opcionais</h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <Select
                    label="Coluna de Categoria"
                    value={mapping.category_column}
                    onChange={(e) => setMapping({ ...mapping, category_column: e.target.value })}
                    options={columnOptions}
                  />

                  <Select
                    label="Coluna de Saldo"
                    value={mapping.balance_column}
                    onChange={(e) => setMapping({ ...mapping, balance_column: e.target.value })}
                    options={columnOptions}
                  />

                  <Select
                    label="Data Pagamento Cartão"
                    value={mapping.card_payment_date_column}
                    onChange={(e) => setMapping({ ...mapping, card_payment_date_column: e.target.value })}
                    options={columnOptions}
                  />
                </div>
              </div>

              {/* Opções */}
              <div className="p-4 bg-gray-50 rounded-lg space-y-3">
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={options.create_missing_accounts}
                    onChange={(e) => setOptions({ ...options, create_missing_accounts: e.target.checked })}
                    className="rounded"
                  />
                  <span>Criar bancos e contas automaticamente se não existirem</span>
                </label>

                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={options.create_missing_categories}
                    onChange={(e) => setOptions({ ...options, create_missing_categories: e.target.checked })}
                    className="rounded"
                  />
                  <span>Criar categorias automaticamente se não existirem</span>
                </label>

                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={options.skip_duplicates}
                    onChange={(e) => setOptions({ ...options, skip_duplicates: e.target.checked })}
                    className="rounded"
                  />
                  <span>Ignorar transações duplicadas</span>
                </label>
              </div>

              {/* Preview */}
              <div>
                <h4 className="font-medium mb-2">Preview (primeiras 10 linhas):</h4>
                <div className="overflow-x-auto border rounded-lg">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50">
                      <tr>
                        {uploadResult.columns.map((col) => (
                          <th key={col} className="px-4 py-2 text-left whitespace-nowrap">
                            {col}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {uploadResult.preview_rows.slice(0, 10).map((row, i) => (
                        <tr key={i} className="border-t">
                          {uploadResult.columns.map((col) => (
                            <td key={col} className="px-4 py-2 whitespace-nowrap">
                              {row[col]}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="flex gap-4">
                <Button variant="secondary" onClick={resetImport}>
                  Voltar
                </Button>
                <Button onClick={handleProcess} isLoading={isProcessing}>
                  Importar Histórico
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Step 3: Result */}
        {step === 'result' && processResult && (
          <Card>
            <CardHeader>
              <CardTitle>3. Resultado da importação</CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="p-6 rounded-lg bg-green-50 text-center">
                <CheckCircle className="mx-auto text-green-500 mb-4" size={48} />
                <h3 className="text-lg font-medium text-green-800">Importação concluída!</h3>
              </div>

              {/* Resumo */}
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
                <div className="p-4 bg-gray-50 rounded-lg text-center">
                  <p className="text-2xl font-bold text-green-600">{processResult.transactions_imported}</p>
                  <p className="text-sm text-gray-500">Transações Importadas</p>
                </div>
                <div className="p-4 bg-gray-50 rounded-lg text-center">
                  <p className="text-2xl font-bold text-blue-600">{processResult.accounts_processed}</p>
                  <p className="text-sm text-gray-500">Contas Processadas</p>
                </div>
                <div className="p-4 bg-gray-50 rounded-lg text-center">
                  <p className="text-2xl font-bold text-purple-600">{processResult.accounts_created}</p>
                  <p className="text-sm text-gray-500">Contas Criadas</p>
                </div>
                <div className="p-4 bg-gray-50 rounded-lg text-center">
                  <p className="text-2xl font-bold text-indigo-600">{processResult.categories_created || 0}</p>
                  <p className="text-sm text-gray-500">Categorias Criadas</p>
                </div>
                <div className="p-4 bg-gray-50 rounded-lg text-center">
                  <p className="text-2xl font-bold text-orange-600">{processResult.duplicates_skipped}</p>
                  <p className="text-sm text-gray-500">Duplicatas Ignoradas</p>
                </div>
              </div>

              {/* Detalhes por conta */}
              {processResult.accounts_summary.length > 0 && (
                <div>
                  <h4 className="font-medium mb-2">Detalhes por conta:</h4>
                  <div className="overflow-x-auto border rounded-lg">
                    <table className="w-full text-sm">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="px-4 py-2 text-left">Banco</th>
                          <th className="px-4 py-2 text-left">Conta</th>
                          <th className="px-4 py-2 text-right">Importadas</th>
                          <th className="px-4 py-2 text-right">Duplicatas</th>
                        </tr>
                      </thead>
                      <tbody>
                        {processResult.accounts_summary.map((acc, i) => (
                          <tr key={i} className="border-t">
                            <td className="px-4 py-2">{acc.bank}</td>
                            <td className="px-4 py-2">{acc.account}</td>
                            <td className="px-4 py-2 text-right text-green-600">{acc.imported}</td>
                            <td className="px-4 py-2 text-right text-orange-600">{acc.duplicates}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Erros */}
              {processResult.errors.length > 0 && (
                <div className="p-4 bg-red-50 rounded-lg">
                  <h4 className="font-medium text-red-800 mb-2">Erros ({processResult.errors.length}):</h4>
                  <ul className="text-sm text-red-600 space-y-1 max-h-40 overflow-y-auto">
                    {processResult.errors.slice(0, 20).map((err, i) => (
                      <li key={i}>{err}</li>
                    ))}
                    {processResult.errors.length > 20 && (
                      <li>... e mais {processResult.errors.length - 20} erros</li>
                    )}
                  </ul>
                </div>
              )}

              <Button onClick={resetImport}>Nova Importação</Button>
            </CardContent>
          </Card>
        )}
      </div>
    </MainLayout>
  );
}
