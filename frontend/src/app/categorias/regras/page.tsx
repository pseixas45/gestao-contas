'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import MainLayout from '@/components/layout/MainLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import Button from '@/components/ui/Button';
import Input from '@/components/ui/Input';
import Select from '@/components/ui/Select';
import { rulesApi, categoriesApi } from '@/lib/api';
import { Plus, Edit2, Trash2, Play, ArrowLeft } from 'lucide-react';
import Link from 'next/link';

export default function RegrasPage() {
  const queryClient = useQueryClient();
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [editingRule, setEditingRule] = useState<any>(null);
  const [testText, setTestText] = useState('');
  const [testResult, setTestResult] = useState<any>(null);

  const [formData, setFormData] = useState({
    category_id: '',
    pattern: '',
    match_type: 'contains',
    priority: '0',
  });

  // Buscar regras
  const { data: rules = [], isLoading } = useQuery({
    queryKey: ['rules'],
    queryFn: () => rulesApi.list(false),
  });

  // Buscar categorias
  const { data: categories = [] } = useQuery({
    queryKey: ['categories', 'flat'],
    queryFn: () => categoriesApi.list(true, true),
  });

  // Criar regra
  const createMutation = useMutation({
    mutationFn: (data: any) => rulesApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rules'] });
      resetForm();
    },
  });

  // Atualizar regra
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) => rulesApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rules'] });
      resetForm();
    },
  });

  // Excluir regra
  const deleteMutation = useMutation({
    mutationFn: (id: number) => rulesApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rules'] });
    },
  });

  // Aplicar regras
  const applyMutation = useMutation({
    mutationFn: () => rulesApi.applyAll(),
  });

  const resetForm = () => {
    setFormData({
      category_id: '',
      pattern: '',
      match_type: 'contains',
      priority: '0',
    });
    setEditingRule(null);
    setIsFormOpen(false);
  };

  const handleEdit = (rule: any) => {
    setFormData({
      category_id: rule.category_id.toString(),
      pattern: rule.pattern,
      match_type: rule.match_type,
      priority: rule.priority.toString(),
    });
    setEditingRule(rule);
    setIsFormOpen(true);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const data = {
      category_id: parseInt(formData.category_id),
      pattern: formData.pattern,
      match_type: formData.match_type,
      priority: parseInt(formData.priority),
    };

    if (editingRule) {
      updateMutation.mutate({ id: editingRule.id, data });
    } else {
      createMutation.mutate(data);
    }
  };

  const handleDelete = (id: number) => {
    if (confirm('Tem certeza que deseja excluir esta regra?')) {
      deleteMutation.mutate(id);
    }
  };

  const handleTest = async () => {
    if (!formData.pattern || !testText) return;
    try {
      const result = await rulesApi.test(formData.pattern, formData.match_type, testText);
      setTestResult(result);
    } catch (error) {
      setTestResult({ matches: false, error: true });
    }
  };

  const matchTypeOptions = [
    { value: 'contains', label: 'Contém' },
    { value: 'starts_with', label: 'Começa com' },
    { value: 'ends_with', label: 'Termina com' },
    { value: 'exact', label: 'Exato' },
    { value: 'regex', label: 'Expressão Regular' },
  ];

  const getMatchTypeLabel = (type: string) => {
    return matchTypeOptions.find((o) => o.value === type)?.label || type;
  };

  return (
    <MainLayout>
      <div className="space-y-6">
        {/* Cabeçalho */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href="/categorias">
              <Button variant="ghost" size="sm">
                <ArrowLeft size={18} />
              </Button>
            </Link>
            <div>
              <h1 className="text-2xl font-bold text-gray-800">Regras de Categorização</h1>
              <p className="text-gray-600">Defina regras para categorização automática</p>
            </div>
          </div>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              onClick={() => applyMutation.mutate()}
              isLoading={applyMutation.isPending}
            >
              <Play size={18} className="mr-2" />
              Aplicar Regras
            </Button>
            <Button onClick={() => setIsFormOpen(true)}>
              <Plus size={18} className="mr-2" />
              Nova Regra
            </Button>
          </div>
        </div>

        {/* Resultado da aplicação */}
        {applyMutation.isSuccess && (
          <div className="p-4 bg-green-50 rounded-lg text-green-700">
            {applyMutation.data?.categorized} transações categorizadas automaticamente
          </div>
        )}

        {/* Formulário */}
        {isFormOpen && (
          <Card>
            <CardHeader>
              <CardTitle>{editingRule ? 'Editar Regra' : 'Nova Regra'}</CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <Input
                    label="Padrão"
                    id="pattern"
                    value={formData.pattern}
                    onChange={(e) => setFormData({ ...formData, pattern: e.target.value })}
                    placeholder="Ex: UBER, IFOOD, MERCADO"
                    required
                  />

                  <Select
                    label="Tipo de Correspondência"
                    id="match_type"
                    value={formData.match_type}
                    onChange={(e) => setFormData({ ...formData, match_type: e.target.value })}
                    options={matchTypeOptions}
                  />

                  <Select
                    label="Categoria"
                    id="category_id"
                    value={formData.category_id}
                    onChange={(e) => setFormData({ ...formData, category_id: e.target.value })}
                    options={categories.map((c) => ({ value: c.id, label: c.name }))}
                    placeholder="Selecione"
                    required
                  />

                  <Input
                    label="Prioridade"
                    id="priority"
                    type="number"
                    value={formData.priority}
                    onChange={(e) => setFormData({ ...formData, priority: e.target.value })}
                  />
                </div>

                {/* Teste da regra */}
                <div className="p-4 bg-gray-50 rounded-lg space-y-3">
                  <p className="text-sm font-medium text-gray-700">Testar regra:</p>
                  <div className="flex gap-2">
                    <Input
                      placeholder="Digite um texto para testar..."
                      value={testText}
                      onChange={(e) => setTestText(e.target.value)}
                      className="flex-1"
                    />
                    <Button type="button" variant="secondary" onClick={handleTest}>
                      Testar
                    </Button>
                  </div>
                  {testResult && (
                    <p
                      className={`text-sm ${
                        testResult.matches ? 'text-green-600' : 'text-red-600'
                      }`}
                    >
                      {testResult.matches
                        ? `Correspondência encontrada: "${testResult.matched_text}"`
                        : 'Nenhuma correspondência'}
                    </p>
                  )}
                </div>

                <div className="flex gap-2 justify-end">
                  <Button type="button" variant="secondary" onClick={resetForm}>
                    Cancelar
                  </Button>
                  <Button
                    type="submit"
                    isLoading={createMutation.isPending || updateMutation.isPending}
                  >
                    {editingRule ? 'Salvar' : 'Criar'}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        )}

        {/* Lista de Regras */}
        <Card>
          <CardContent className="p-0">
            {isLoading ? (
              <div className="text-center py-8 text-gray-500">Carregando...</div>
            ) : rules.length === 0 ? (
              <div className="text-center py-8 text-gray-500">Nenhuma regra cadastrada</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        Padrão
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        Tipo
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        Categoria
                      </th>
                      <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase">
                        Prioridade
                      </th>
                      <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase">
                        Usos
                      </th>
                      <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                        Ações
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {rules.map((rule) => (
                      <tr key={rule.id} className="hover:bg-gray-50">
                        <td className="px-6 py-4">
                          <code className="px-2 py-1 bg-gray-100 rounded text-sm">
                            {rule.pattern}
                          </code>
                        </td>
                        <td className="px-6 py-4 text-sm text-gray-600">
                          {getMatchTypeLabel(rule.match_type)}
                        </td>
                        <td className="px-6 py-4 text-sm">{rule.category_name}</td>
                        <td className="px-6 py-4 text-center text-sm">{rule.priority}</td>
                        <td className="px-6 py-4 text-center text-sm text-gray-500">
                          {rule.hit_count}
                        </td>
                        <td className="px-6 py-4 text-right">
                          <div className="flex justify-end gap-2">
                            <button
                              onClick={() => handleEdit(rule)}
                              className="p-1 text-gray-500 hover:text-primary-600"
                            >
                              <Edit2 size={16} />
                            </button>
                            <button
                              onClick={() => handleDelete(rule.id)}
                              className="p-1 text-gray-500 hover:text-red-600"
                            >
                              <Trash2 size={16} />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </MainLayout>
  );
}
