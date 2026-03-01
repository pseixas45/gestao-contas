import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(value: number, currency: 'BRL' | 'USD' | 'EUR' = 'BRL'): string {
  const localeMap: Record<string, string> = {
    BRL: 'pt-BR',
    USD: 'en-US',
    EUR: 'de-DE',
  };
  return new Intl.NumberFormat(localeMap[currency] || 'pt-BR', {
    style: 'currency',
    currency,
  }).format(value);
}

export function formatDate(date: string | Date): string {
  if (typeof date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(date)) {
    // Date-only strings ("2026-01-19") are parsed as UTC by Date constructor,
    // causing a -1 day shift in negative UTC offsets (e.g. BRT = UTC-3).
    // Parse as local date to avoid this.
    const [year, month, day] = date.split('-').map(Number);
    return new Intl.DateTimeFormat('pt-BR').format(new Date(year, month - 1, day));
  }
  const d = typeof date === 'string' ? new Date(date) : date;
  return new Intl.DateTimeFormat('pt-BR').format(d);
}

export function formatDateTime(date: string | Date): string {
  const d = typeof date === 'string' ? new Date(date) : date;
  return new Intl.DateTimeFormat('pt-BR', {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(d);
}

export function getTransactionTypeLabel(amount: number): string {
  return amount >= 0 ? 'Crédito' : 'Débito';
}

export function getAccountTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    checking: 'Conta Corrente',
    savings: 'Poupança',
    credit_card: 'Cartão de Crédito',
    investment: 'Investimentos',
  };
  return labels[type] || type;
}

export function getCategoryTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    income: 'Receita',
    expense: 'Despesa',
    transfer: 'Transferência',
  };
  return labels[type] || type;
}

export function getImportStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    pending: 'Pendente',
    processing: 'Processando',
    completed: 'Concluído',
    completed_with_duplicates: 'Concluído (com duplicatas)',
    failed: 'Falhou',
  };
  return labels[status] || status;
}

export function getImportStatusColor(status: string): string {
  const colors: Record<string, string> = {
    pending: 'bg-yellow-100 text-yellow-800',
    processing: 'bg-blue-100 text-blue-800',
    completed: 'bg-green-100 text-green-800',
    completed_with_duplicates: 'bg-orange-100 text-orange-800',
    failed: 'bg-red-100 text-red-800',
  };
  return colors[status] || 'bg-gray-100 text-gray-800';
}
