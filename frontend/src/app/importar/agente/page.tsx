'use client';

import { useReducer, useCallback, useRef, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import MainLayout from '@/components/layout/MainLayout';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card';
import Button from '@/components/ui/Button';
import Badge from '@/components/ui/Badge';
import Link from 'next/link';
import {
  Upload, Play, RotateCcw, CheckCircle, XCircle, AlertTriangle,
  Loader2, FileText, Trash2, ChevronRight,
} from 'lucide-react';
import { formatCurrency } from '@/lib/utils';
import {
  importAgentApi, importsApi, investmentsApi, accountsApi,
  type AgentClassification, type ImportResult,
} from '@/lib/api';

// ============ Types ============

interface AgentFile {
  id: string;
  file: File;
  filename: string;
  // Classification
  classStatus: 'pending' | 'classifying' | 'done' | 'error';
  classification: AgentClassification | null;
  // User overrides
  overrideAccountId: number | null;
  cardPaymentDate: string;
  skipped: boolean;
  // Processing
  procStatus: 'waiting' | 'uploading' | 'analyzing' | 'processing' | 'done' | 'skipped' | 'error';
  importResult: ImportResult | null;
  investmentResult: { snapshot_date: string; total_value: number; positions_count: number } | null;
  procError: string | null;
}

interface AgentState {
  phase: 'upload' | 'review' | 'processing' | 'results';
  files: AgentFile[];
}

type Action =
  | { type: 'ADD_FILES'; files: AgentFile[] }
  | { type: 'UPDATE_CLASSIFICATION'; id: string; classification: AgentClassification }
  | { type: 'CLASSIFICATION_ERROR'; id: string; error: string }
  | { type: 'SET_OVERRIDE_ACCOUNT'; id: string; accountId: number | null }
  | { type: 'SET_CARD_PAYMENT_DATE'; id: string; date: string }
  | { type: 'TOGGLE_SKIP'; id: string }
  | { type: 'REMOVE_FILE'; id: string }
  | { type: 'START_REVIEW' }
  | { type: 'START_PROCESSING' }
  | { type: 'UPDATE_PROC_STATUS'; id: string; status: AgentFile['procStatus'] }
  | { type: 'SET_IMPORT_RESULT'; id: string; result: ImportResult }
  | { type: 'SET_INVESTMENT_RESULT'; id: string; result: AgentFile['investmentResult'] }
  | { type: 'SET_PROC_ERROR'; id: string; error: string }
  | { type: 'FINISH_PROCESSING' }
  | { type: 'RESET' };

function reducer(state: AgentState, action: Action): AgentState {
  switch (action.type) {
    case 'ADD_FILES':
      return { ...state, files: [...state.files, ...action.files] };
    case 'UPDATE_CLASSIFICATION':
      return {
        ...state,
        files: state.files.map(f =>
          f.id === action.id ? { ...f, classStatus: 'done', classification: action.classification } : f
        ),
      };
    case 'CLASSIFICATION_ERROR':
      return {
        ...state,
        files: state.files.map(f =>
          f.id === action.id ? { ...f, classStatus: 'error', procError: action.error } : f
        ),
      };
    case 'SET_OVERRIDE_ACCOUNT':
      return {
        ...state,
        files: state.files.map(f =>
          f.id === action.id ? { ...f, overrideAccountId: action.accountId } : f
        ),
      };
    case 'SET_CARD_PAYMENT_DATE':
      return {
        ...state,
        files: state.files.map(f =>
          f.id === action.id ? { ...f, cardPaymentDate: action.date } : f
        ),
      };
    case 'TOGGLE_SKIP':
      return {
        ...state,
        files: state.files.map(f =>
          f.id === action.id ? { ...f, skipped: !f.skipped } : f
        ),
      };
    case 'REMOVE_FILE':
      return { ...state, files: state.files.filter(f => f.id !== action.id) };
    case 'START_REVIEW':
      return { ...state, phase: 'review' };
    case 'START_PROCESSING':
      return { ...state, phase: 'processing' };
    case 'UPDATE_PROC_STATUS':
      return {
        ...state,
        files: state.files.map(f =>
          f.id === action.id ? { ...f, procStatus: action.status } : f
        ),
      };
    case 'SET_IMPORT_RESULT':
      return {
        ...state,
        files: state.files.map(f =>
          f.id === action.id ? { ...f, procStatus: 'done', importResult: action.result } : f
        ),
      };
    case 'SET_INVESTMENT_RESULT':
      return {
        ...state,
        files: state.files.map(f =>
          f.id === action.id ? { ...f, procStatus: 'done', investmentResult: action.result } : f
        ),
      };
    case 'SET_PROC_ERROR':
      return {
        ...state,
        files: state.files.map(f =>
          f.id === action.id ? { ...f, procStatus: 'error', procError: action.error } : f
        ),
      };
    case 'FINISH_PROCESSING':
      return { ...state, phase: 'results' };
    case 'RESET':
      return { phase: 'upload', files: [] };
    default:
      return state;
  }
}

// ============ Helpers ============

function getAccountId(f: AgentFile): number | null {
  return f.overrideAccountId ?? f.classification?.detected_account_id ?? null;
}

function getFileType(f: AgentFile): string {
  return f.classification?.file_type ?? 'transaction';
}

let idCounter = 0;
function genId() { return `agent-file-${++idCounter}-${Date.now()}`; }

const STATUS_ICONS: Record<string, React.ReactNode> = {
  waiting: <div className="w-5 h-5 rounded-full border-2 border-slate-300" />,
  uploading: <Loader2 size={18} className="animate-spin text-blue-500" />,
  analyzing: <Loader2 size={18} className="animate-spin text-amber-500" />,
  processing: <Loader2 size={18} className="animate-spin text-indigo-500" />,
  done: <CheckCircle size={18} className="text-emerald-500" />,
  skipped: <div className="w-5 h-5 rounded-full bg-slate-200" />,
  error: <XCircle size={18} className="text-rose-500" />,
};

const STATUS_LABELS: Record<string, string> = {
  waiting: 'Aguardando',
  uploading: 'Enviando...',
  analyzing: 'Analisando...',
  processing: 'Importando...',
  done: 'Concluido',
  skipped: 'Pulado',
  error: 'Erro',
};

// ============ Component ============

export default function ImportAgentPage() {
  const [state, dispatch] = useReducer(reducer, { phase: 'upload', files: [] });
  const fileInputRef = useRef<HTMLInputElement>(null);
  const processingRef = useRef(false);

  const { data: accounts = [] } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
  });

  // ---- File handling ----

  const handleFiles = useCallback(async (fileList: FileList | File[]) => {
    const newFiles: AgentFile[] = Array.from(fileList).map(file => ({
      id: genId(),
      file,
      filename: file.name,
      classStatus: 'pending' as const,
      classification: null,
      overrideAccountId: null,
      cardPaymentDate: '',
      skipped: false,
      procStatus: 'waiting' as const,
      importResult: null,
      investmentResult: null,
      procError: null,
    }));

    dispatch({ type: 'ADD_FILES', files: newFiles });

    // Classify each file (max 3 concurrent)
    const queue = [...newFiles];
    const run = async () => {
      while (queue.length > 0) {
        const batch = queue.splice(0, 3);
        await Promise.all(batch.map(async (af) => {
          dispatch({ type: 'UPDATE_CLASSIFICATION', id: af.id, classification: { ...af.classification } as AgentClassification }); // trigger classifying
          try {
            const result = await importAgentApi.classify(af.file);
            dispatch({ type: 'UPDATE_CLASSIFICATION', id: af.id, classification: result });
          } catch (e: unknown) {
            dispatch({ type: 'CLASSIFICATION_ERROR', id: af.id, error: (e as Error).message || 'Erro ao classificar' });
          }
        }));
      }
    };
    run();

    if (state.phase === 'upload') {
      dispatch({ type: 'START_REVIEW' });
    }
  }, [state.phase]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files.length > 0) handleFiles(e.dataTransfer.files);
  }, [handleFiles]);

  // ---- Processing ----

  const processAll = useCallback(async () => {
    if (processingRef.current) return;
    processingRef.current = true;
    dispatch({ type: 'START_PROCESSING' });

    const toProcess = state.files.filter(f => !f.skipped && getAccountId(f));
    // Sort: transactions first, then investments
    const sorted = [...toProcess].sort((a, b) => {
      const ta = getFileType(a) === 'transaction' ? 0 : 1;
      const tb = getFileType(b) === 'transaction' ? 0 : 1;
      return ta - tb;
    });

    for (const af of sorted) {
      const accountId = getAccountId(af)!;
      const fileType = getFileType(af);

      try {
        if (fileType === 'investment') {
          dispatch({ type: 'UPDATE_PROC_STATUS', id: af.id, status: 'processing' });
          const formData = new FormData();
          formData.append('file', af.file);
          formData.append('account_id', String(accountId));
          formData.append('provider', 'auto');
          const result = await investmentsApi.upload(af.file, accountId, 'auto');
          dispatch({ type: 'SET_INVESTMENT_RESULT', id: af.id, result });
        } else {
          // Step 1: Upload
          dispatch({ type: 'UPDATE_PROC_STATUS', id: af.id, status: 'uploading' });
          const preview = await importsApi.upload(af.file, accountId);

          if (!preview.detected_mapping) {
            dispatch({ type: 'SET_PROC_ERROR', id: af.id, error: 'Mapeamento de colunas nao detectado' });
            continue;
          }

          // Fix XPVisa: force card_payment_date_column to null
          if (accountId === 10 && preview.detected_mapping.card_payment_date_column) {
            preview.detected_mapping.card_payment_date_column = null;
          }

          // Step 2: Analyze
          dispatch({ type: 'UPDATE_PROC_STATUS', id: af.id, status: 'analyzing' });
          const analysis = await importsApi.analyze(
            preview.batch_id,
            preview.detected_mapping,
            accountId,
            af.cardPaymentDate || undefined,
          );

          // Skip if all duplicates
          if (analysis.new_count === 0) {
            dispatch({ type: 'UPDATE_PROC_STATUS', id: af.id, status: 'skipped' });
            continue;
          }

          // Step 3: Process
          dispatch({ type: 'UPDATE_PROC_STATUS', id: af.id, status: 'processing' });
          const result = await importsApi.process(
            preview.batch_id,
            preview.detected_mapping,
            accountId,
            false, // validate_balance
            undefined, // expected_final_balance
            true, // skip_duplicates
            af.cardPaymentDate || undefined,
          );
          dispatch({ type: 'SET_IMPORT_RESULT', id: af.id, result });
        }
      } catch (e: unknown) {
        dispatch({ type: 'SET_PROC_ERROR', id: af.id, error: (e as Error).message || 'Erro no processamento' });
      }
    }

    // Mark skipped files
    for (const af of state.files.filter(f => f.skipped)) {
      dispatch({ type: 'UPDATE_PROC_STATUS', id: af.id, status: 'skipped' });
    }

    dispatch({ type: 'FINISH_PROCESSING' });
    processingRef.current = false;
  }, [state.files]);

  // ---- Computed ----

  const allClassified = state.files.length > 0 && state.files.every(f => f.classStatus === 'done' || f.classStatus === 'error');
  const activeFiles = state.files.filter(f => !f.skipped);
  const allHaveAccount = activeFiles.every(f => getAccountId(f) !== null);
  const canProcess = allClassified && allHaveAccount && activeFiles.length > 0;

  const stats = useMemo(() => {
    const done = state.files.filter(f => f.procStatus === 'done');
    return {
      total: state.files.length,
      processed: done.length,
      skipped: state.files.filter(f => f.procStatus === 'skipped').length,
      errors: state.files.filter(f => f.procStatus === 'error').length,
      imported: done.reduce((s, f) => s + (f.importResult?.imported_count ?? f.investmentResult?.positions_count ?? 0), 0),
      duplicates: done.reduce((s, f) => s + (f.importResult?.duplicate_count ?? 0), 0),
    };
  }, [state.files]);

  // ============ RENDER ============

  return (
    <MainLayout>
      <div className="space-y-6">
        {/* Header with tabs */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Importar Extratos</h1>
            <div className="flex gap-1 mt-2">
              <Link
                href="/importar"
                className="px-3 py-1.5 text-sm font-medium text-slate-500 hover:text-slate-700 rounded-lg hover:bg-slate-100"
              >
                Manual
              </Link>
              <span className="px-3 py-1.5 text-sm font-medium text-primary-700 bg-primary-50 rounded-lg">
                Agente
              </span>
            </div>
          </div>
          {state.phase !== 'upload' && (
            <Button variant="ghost" size="sm" onClick={() => dispatch({ type: 'RESET' })}>
              <RotateCcw size={14} /> Recomecar
            </Button>
          )}
        </div>

        {/* ===== UPLOAD / REVIEW PHASE ===== */}
        {(state.phase === 'upload' || state.phase === 'review') && (
          <Card>
            <CardHeader>
              <CardTitle>
                {state.phase === 'upload' ? 'Solte seus arquivos' : `${state.files.length} arquivo(s) detectado(s)`}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {/* Dropzone */}
              <div
                onDrop={handleDrop}
                onDragOver={e => e.preventDefault()}
                onClick={() => fileInputRef.current?.click()}
                className="border-2 border-dashed border-slate-300 rounded-xl p-8 text-center cursor-pointer hover:border-primary-400 hover:bg-primary-50/30 transition-colors mb-6"
              >
                <Upload size={32} className="mx-auto mb-3 text-slate-400" />
                <p className="text-sm text-slate-600 font-medium">
                  Arraste arquivos de extrato aqui ou clique para selecionar
                </p>
                <p className="text-xs text-slate-400 mt-1">
                  CSV, XLSX, XLS, PDF — multiplos arquivos aceitos
                </p>
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept=".csv,.xlsx,.xls,.pdf"
                  className="hidden"
                  onChange={e => e.target.files && handleFiles(e.target.files)}
                />
              </div>

              {/* File list */}
              {state.files.length > 0 && (
                <div className="border border-slate-200 rounded-xl overflow-hidden">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-200">
                        <th className="w-10 px-3 py-2"></th>
                        <th className="px-3 py-2 text-left font-medium text-slate-600">Arquivo</th>
                        <th className="px-3 py-2 text-left font-medium text-slate-600">Banco / Conta</th>
                        <th className="px-3 py-2 text-center font-medium text-slate-600">Tipo</th>
                        <th className="px-3 py-2 text-left font-medium text-slate-600">Data Fatura</th>
                        <th className="px-3 py-2 text-left font-medium text-slate-600">Avisos</th>
                        <th className="w-10 px-3 py-2"></th>
                      </tr>
                    </thead>
                    <tbody>
                      {state.files.map(f => {
                        const c = f.classification;
                        const accountId = getAccountId(f);
                        const needsDate = c?.needs_card_payment_date;
                        const isClassifying = f.classStatus === 'pending' || (f.classStatus === 'done' && !c);

                        return (
                          <tr
                            key={f.id}
                            className={`border-b border-slate-100 ${f.skipped ? 'opacity-40' : ''}`}
                          >
                            <td className="px-3 py-2 text-center">
                              <input
                                type="checkbox"
                                checked={!f.skipped}
                                onChange={() => dispatch({ type: 'TOGGLE_SKIP', id: f.id })}
                                className="rounded"
                              />
                            </td>
                            <td className="px-3 py-2">
                              <div className="flex items-center gap-2">
                                <FileText size={16} className="text-slate-400 flex-shrink-0" />
                                <span className="text-slate-800 truncate max-w-[200px]">{f.filename}</span>
                              </div>
                            </td>
                            <td className="px-3 py-2">
                              {isClassifying ? (
                                <Loader2 size={14} className="animate-spin text-slate-400" />
                              ) : c?.confidence === 'high' ? (
                                <span className="text-slate-800">{c.detected_account_name || c.detected_bank}</span>
                              ) : (
                                <select
                                  value={accountId ?? ''}
                                  onChange={e => dispatch({
                                    type: 'SET_OVERRIDE_ACCOUNT',
                                    id: f.id,
                                    accountId: e.target.value ? Number(e.target.value) : null,
                                  })}
                                  className="px-2 py-1 border border-amber-300 rounded text-xs bg-amber-50 focus:outline-none focus:ring-1 focus:ring-primary-500"
                                >
                                  <option value="">Selecione conta...</option>
                                  {accounts.map(a => (
                                    <option key={a.id} value={a.id}>{a.name}</option>
                                  ))}
                                </select>
                              )}
                            </td>
                            <td className="px-3 py-2 text-center">
                              {c?.file_type === 'investment' ? (
                                <Badge color="#8b5cf6" variant="soft">Investimento</Badge>
                              ) : (
                                <Badge color="#3b82f6" variant="soft">Transacao</Badge>
                              )}
                            </td>
                            <td className="px-3 py-2">
                              {needsDate && !f.skipped ? (
                                <input
                                  type="date"
                                  value={f.cardPaymentDate}
                                  onChange={e => dispatch({ type: 'SET_CARD_PAYMENT_DATE', id: f.id, date: e.target.value })}
                                  className="px-2 py-1 border border-slate-300 rounded text-xs focus:outline-none focus:ring-1 focus:ring-primary-500"
                                />
                              ) : (
                                <span className="text-slate-400">-</span>
                              )}
                            </td>
                            <td className="px-3 py-2">
                              {(c?.warnings ?? []).map((w, i) => (
                                <div key={i} className="flex items-center gap-1 text-xs text-amber-600">
                                  <AlertTriangle size={12} /> {w}
                                </div>
                              ))}
                            </td>
                            <td className="px-3 py-2">
                              <button
                                onClick={() => dispatch({ type: 'REMOVE_FILE', id: f.id })}
                                className="p-1 hover:bg-rose-50 rounded"
                              >
                                <Trash2 size={14} className="text-slate-400 hover:text-rose-500" />
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Process button */}
              {state.files.length > 0 && (
                <div className="mt-4 flex items-center justify-between">
                  <p className="text-xs text-slate-500">
                    {activeFiles.length} arquivo(s) para processar
                    {!allClassified && ' — classificando...'}
                    {allClassified && !allHaveAccount && ' — selecione conta para arquivos pendentes'}
                  </p>
                  <Button onClick={processAll} disabled={!canProcess}>
                    <Play size={16} /> Processar Todos
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* ===== PROCESSING PHASE ===== */}
        {state.phase === 'processing' && (
          <Card>
            <CardHeader>
              <CardTitle>Processando...</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {state.files.map(f => (
                  <div key={f.id} className="flex items-center gap-3 p-3 rounded-lg bg-slate-50">
                    <div className="flex-shrink-0">{STATUS_ICONS[f.procStatus]}</div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-slate-800 truncate">{f.filename}</p>
                      <p className="text-xs text-slate-500">
                        {STATUS_LABELS[f.procStatus]}
                        {f.importResult && ` — ${f.importResult.imported_count} importadas, ${f.importResult.duplicate_count} duplicatas`}
                        {f.investmentResult && ` — ${f.investmentResult.positions_count} posicoes, R$ ${Number(f.investmentResult.total_value).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`}
                        {f.procError && ` — ${f.procError}`}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* ===== RESULTS PHASE ===== */}
        {state.phase === 'results' && (
          <>
            {/* Summary cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <Card>
                <CardContent className="pt-4 pb-4 text-center">
                  <p className="text-2xl font-bold text-slate-900">{stats.processed}</p>
                  <p className="text-xs text-slate-500">Processados</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-4 pb-4 text-center">
                  <p className="text-2xl font-bold text-emerald-600">{stats.imported}</p>
                  <p className="text-xs text-slate-500">Importados</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-4 pb-4 text-center">
                  <p className="text-2xl font-bold text-slate-400">{stats.duplicates}</p>
                  <p className="text-xs text-slate-500">Duplicatas</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-4 pb-4 text-center">
                  <p className="text-2xl font-bold text-rose-600">{stats.errors}</p>
                  <p className="text-xs text-slate-500">Erros</p>
                </CardContent>
              </Card>
            </div>

            {/* Detail per file */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle>Detalhe por Arquivo</CardTitle>
                  <Button variant="ghost" size="sm" onClick={() => dispatch({ type: 'RESET' })}>
                    <RotateCcw size={14} /> Nova Importacao
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {state.files.map(f => {
                    const accountName = f.classification?.detected_account_name
                      || accounts.find(a => a.id === getAccountId(f))?.name
                      || '-';

                    return (
                      <div
                        key={f.id}
                        className={`flex items-center gap-3 p-3 rounded-lg border ${
                          f.procStatus === 'error' ? 'border-rose-200 bg-rose-50' :
                          f.procStatus === 'done' ? 'border-emerald-200 bg-emerald-50' :
                          'border-slate-200 bg-slate-50'
                        }`}
                      >
                        <div className="flex-shrink-0">{STATUS_ICONS[f.procStatus]}</div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <p className="text-sm font-medium text-slate-800 truncate">{f.filename}</p>
                            <span className="text-xs text-slate-400">{accountName}</span>
                          </div>
                          <p className="text-xs text-slate-600 mt-0.5">
                            {f.importResult && (
                              <>
                                {f.importResult.imported_count} importadas
                                {f.importResult.duplicate_count > 0 && `, ${f.importResult.duplicate_count} duplicatas`}
                                {f.importResult.error_count > 0 && `, ${f.importResult.error_count} erros`}
                              </>
                            )}
                            {f.investmentResult && (
                              <>
                                Snapshot {f.investmentResult.snapshot_date} — {f.investmentResult.positions_count} posicoes,{' '}
                                {formatCurrency(Number(f.investmentResult.total_value))}
                              </>
                            )}
                            {f.procStatus === 'skipped' && 'Pulado (todas duplicatas ou excluido)'}
                            {f.procError && <span className="text-rose-600">{f.procError}</span>}
                          </p>
                        </div>
                        {f.procStatus === 'error' && (
                          <Link
                            href="/importar"
                            className="text-xs text-primary-600 hover:text-primary-800 flex items-center gap-1"
                          >
                            Manual <ChevronRight size={12} />
                          </Link>
                        )}
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>
          </>
        )}
      </div>
    </MainLayout>
  );
}
