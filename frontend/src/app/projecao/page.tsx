'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import MainLayout from '@/components/layout/MainLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import Select from '@/components/ui/Select';
import { projectionsApi, accountsApi } from '@/lib/api';
import { formatCurrency, formatDate } from '@/lib/utils';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';

export default function ProjecaoPage() {
  const [selectedAccount, setSelectedAccount] = useState('');
  const [monthsAhead, setMonthsAhead] = useState('3');
  const [method, setMethod] = useState('average');

  // Buscar contas
  const { data: accounts = [] } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
  });

  // Buscar projeção
  const { data: projection, isLoading } = useQuery({
    queryKey: ['projection', selectedAccount, monthsAhead, method],
    queryFn: () =>
      projectionsApi.get(parseInt(selectedAccount), parseInt(monthsAhead), method),
    enabled: !!selectedAccount,
  });

  // Buscar transações recorrentes
  const { data: recurring = [] } = useQuery({
    queryKey: ['recurring', selectedAccount],
    queryFn: () => projectionsApi.getRecurring(parseInt(selectedAccount)),
    enabled: !!selectedAccount,
  });

  // Preparar dados para o gráfico
  const chartData = projection
    ? [
        {
          month: 'Atual',
          saldo: projection.current_balance,
        },
        ...projection.projections.map((p) => ({
          month: p.month,
          saldo: p.projected_balance,
        })),
      ]
    : [];

  const methodOptions = [
    { value: 'average', label: 'Média histórica' },
    { value: 'trend', label: 'Tendência' },
    { value: 'recurring', label: 'Transações recorrentes' },
  ];

  const monthOptions = [
    { value: '1', label: '1 mês' },
    { value: '3', label: '3 meses' },
    { value: '6', label: '6 meses' },
    { value: '12', label: '12 meses' },
  ];

  return (
    <MainLayout>
      <div className="space-y-6">
        {/* Cabeçalho */}
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Projeção de Saldo</h1>
          <p className="text-gray-600">Visualize a projeção de saldo das suas contas</p>
        </div>

        {/* Filtros */}
        <Card>
          <CardContent className="py-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <Select
                label="Conta"
                value={selectedAccount}
                onChange={(e) => setSelectedAccount(e.target.value)}
                options={accounts.map((a) => ({
                  value: a.id,
                  label: `${a.name} (${a.bank_name})`,
                }))}
                placeholder="Selecione uma conta"
              />

              <Select
                label="Período"
                value={monthsAhead}
                onChange={(e) => setMonthsAhead(e.target.value)}
                options={monthOptions}
              />

              <Select
                label="Método"
                value={method}
                onChange={(e) => setMethod(e.target.value)}
                options={methodOptions}
              />
            </div>
          </CardContent>
        </Card>

        {/* Conteúdo */}
        {!selectedAccount ? (
          <Card>
            <CardContent className="py-12 text-center text-gray-500">
              Selecione uma conta para ver a projeção
            </CardContent>
          </Card>
        ) : isLoading ? (
          <Card>
            <CardContent className="py-12 text-center text-gray-500">
              Carregando projeção...
            </CardContent>
          </Card>
        ) : projection ? (
          <>
            {/* Gráfico */}
            <Card>
              <CardHeader>
                <CardTitle>Projeção de Saldo - {projection.account_name}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-80">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartData}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="month" />
                      <YAxis
                        tickFormatter={(value) =>
                          new Intl.NumberFormat('pt-BR', {
                            notation: 'compact',
                            compactDisplay: 'short',
                          }).format(value)
                        }
                      />
                      <Tooltip
                        formatter={(value: number) => formatCurrency(value)}
                        labelStyle={{ color: '#374151' }}
                      />
                      <Line
                        type="monotone"
                        dataKey="saldo"
                        stroke="#3b82f6"
                        strokeWidth={2}
                        dot={{ fill: '#3b82f6' }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>

            {/* Detalhes da projeção */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Tabela de projeção */}
              <Card>
                <CardHeader>
                  <CardTitle>Detalhes da Projeção</CardTitle>
                </CardHeader>
                <CardContent className="p-0">
                  <table className="w-full">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                          Mês
                        </th>
                        <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                          Saldo Projetado
                        </th>
                        <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                          Variação
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      <tr className="bg-gray-50">
                        <td className="px-6 py-4 font-medium">Atual</td>
                        <td className="px-6 py-4 text-right font-medium">
                          {formatCurrency(projection.current_balance)}
                        </td>
                        <td className="px-6 py-4 text-right">-</td>
                      </tr>
                      {projection.projections.map((p, i) => (
                        <tr key={i}>
                          <td className="px-6 py-4">{p.month}</td>
                          <td className="px-6 py-4 text-right">
                            {formatCurrency(p.projected_balance)}
                          </td>
                          <td
                            className={`px-6 py-4 text-right ${
                              (p.expected_change || 0) >= 0
                                ? 'text-green-600'
                                : 'text-red-600'
                            }`}
                          >
                            {p.expected_change !== undefined
                              ? formatCurrency(p.expected_change)
                              : '-'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </CardContent>
              </Card>

              {/* Transações recorrentes */}
              <Card>
                <CardHeader>
                  <CardTitle>Transações Recorrentes Detectadas</CardTitle>
                </CardHeader>
                <CardContent className="p-0">
                  {recurring.length === 0 ? (
                    <p className="text-center py-8 text-gray-500">
                      Nenhuma transação recorrente detectada
                    </p>
                  ) : (
                    <table className="w-full">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                            Descrição
                          </th>
                          <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase">
                            Dia
                          </th>
                          <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                            Valor
                          </th>
                        </tr>
                      </thead>
                      <tbody className="divide-y">
                        {recurring.map((r, i) => (
                          <tr key={i}>
                            <td className="px-6 py-4">
                              <div className="font-medium text-sm">{r.description}</div>
                              {r.category_name && (
                                <div className="text-xs text-gray-500">{r.category_name}</div>
                              )}
                            </td>
                            <td className="px-6 py-4 text-center text-sm">
                              Dia {r.typical_day}
                            </td>
                            <td
                              className={`px-6 py-4 text-right font-medium ${
                                r.amount >= 0 ? 'text-green-600' : 'text-red-600'
                              }`}
                            >
                              {formatCurrency(r.amount)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </CardContent>
              </Card>
            </div>
          </>
        ) : null}
      </div>
    </MainLayout>
  );
}
