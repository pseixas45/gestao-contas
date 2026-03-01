'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import MainLayout from '@/components/layout/MainLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import Button from '@/components/ui/Button';
import Input from '@/components/ui/Input';
import Select from '@/components/ui/Select';
import { categoriesApi, rulesApi } from '@/lib/api';
import { Plus, Edit2, Trash2, Tag } from 'lucide-react';
import Link from 'next/link';

export default function CategoriasPage() {
  const queryClient = useQueryClient();
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [editingCategory, setEditingCategory] = useState<any>(null);

  const [formData, setFormData] = useState({
    name: '',
    type: 'expense',
    color: '#6B7280',
    icon: '',
    parent_id: '',
  });

  // Buscar categorias
  const { data: categories = [], isLoading } = useQuery({
    queryKey: ['categories'],
    queryFn: () => categoriesApi.list(false),
  });

  // Buscar categorias flat para parent select
  const { data: flatCategories = [] } = useQuery({
    queryKey: ['categories', 'flat'],
    queryFn: () => categoriesApi.list(true, true),
  });

  // Criar categoria
  const createMutation = useMutation({
    mutationFn: (data: any) => categoriesApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['categories'] });
      resetForm();
    },
  });

  // Atualizar categoria
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) => categoriesApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['categories'] });
      resetForm();
    },
  });

  // Excluir categoria
  const deleteMutation = useMutation({
    mutationFn: (id: number) => categoriesApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['categories'] });
    },
  });

  const resetForm = () => {
    setFormData({
      name: '',
      type: 'expense',
      color: '#6B7280',
      icon: '',
      parent_id: '',
    });
    setEditingCategory(null);
    setIsFormOpen(false);
  };

  const handleEdit = (category: any) => {
    setFormData({
      name: category.name,
      type: category.type,
      color: category.color,
      icon: category.icon || '',
      parent_id: category.parent_id?.toString() || '',
    });
    setEditingCategory(category);
    setIsFormOpen(true);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const data = {
      name: formData.name,
      type: formData.type,
      color: formData.color,
      icon: formData.icon || null,
      parent_id: formData.parent_id ? parseInt(formData.parent_id) : null,
    };

    if (editingCategory) {
      updateMutation.mutate({ id: editingCategory.id, data });
    } else {
      createMutation.mutate(data);
    }
  };

  const handleDelete = (id: number) => {
    if (confirm('Tem certeza que deseja desativar esta categoria?')) {
      deleteMutation.mutate(id);
    }
  };

  const typeOptions = [
    { value: 'expense', label: 'Despesa' },
    { value: 'income', label: 'Receita' },
    { value: 'transfer', label: 'Transferência' },
  ];

  // Renderizar categoria com filhos
  const renderCategory = (category: any, level = 0) => (
    <div key={category.id}>
      <div
        className={`flex items-center justify-between py-3 px-4 hover:bg-gray-50 ${
          level > 0 ? 'ml-8 border-l' : ''
        }`}
      >
        <div className="flex items-center gap-3">
          <div
            className="w-4 h-4 rounded-full"
            style={{ backgroundColor: category.color }}
          />
          <span className="font-medium">{category.name}</span>
          <span
            className={`px-2 py-0.5 rounded text-xs ${
              category.type === 'expense'
                ? 'bg-red-100 text-red-700'
                : category.type === 'income'
                ? 'bg-green-100 text-green-700'
                : 'bg-gray-100 text-gray-700'
            }`}
          >
            {category.type === 'expense'
              ? 'Despesa'
              : category.type === 'income'
              ? 'Receita'
              : 'Transferência'}
          </span>
          {!category.is_active && (
            <span className="px-2 py-0.5 rounded text-xs bg-gray-100 text-gray-500">
              Inativa
            </span>
          )}
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => handleEdit(category)}
            className="p-1 text-gray-500 hover:text-primary-600"
          >
            <Edit2 size={16} />
          </button>
          <button
            onClick={() => handleDelete(category.id)}
            className="p-1 text-gray-500 hover:text-red-600"
          >
            <Trash2 size={16} />
          </button>
        </div>
      </div>
      {category.children?.map((child: any) => renderCategory(child, level + 1))}
    </div>
  );

  return (
    <MainLayout>
      <div className="space-y-6">
        {/* Cabeçalho */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-800">Categorias</h1>
            <p className="text-gray-600">Gerencie categorias de despesas e receitas</p>
          </div>
          <div className="flex gap-2">
            <Link href="/categorias/regras">
              <Button variant="secondary">
                <Tag size={18} className="mr-2" />
                Regras
              </Button>
            </Link>
            <Button onClick={() => setIsFormOpen(true)}>
              <Plus size={18} className="mr-2" />
              Nova Categoria
            </Button>
          </div>
        </div>

        {/* Formulário */}
        {isFormOpen && (
          <Card>
            <CardHeader>
              <CardTitle>{editingCategory ? 'Editar Categoria' : 'Nova Categoria'}</CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <Input
                    label="Nome"
                    id="name"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    required
                  />

                  <Select
                    label="Tipo"
                    id="type"
                    value={formData.type}
                    onChange={(e) => setFormData({ ...formData, type: e.target.value })}
                    options={typeOptions}
                  />

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Cor</label>
                    <input
                      type="color"
                      value={formData.color}
                      onChange={(e) => setFormData({ ...formData, color: e.target.value })}
                      className="h-10 w-full rounded border border-gray-300"
                    />
                  </div>

                  <Select
                    label="Categoria Pai (opcional)"
                    id="parent_id"
                    value={formData.parent_id}
                    onChange={(e) => setFormData({ ...formData, parent_id: e.target.value })}
                    options={[
                      { value: '', label: 'Nenhuma (categoria raiz)' },
                      ...flatCategories
                        .filter((c) => c.id !== editingCategory?.id)
                        .map((c) => ({ value: c.id, label: c.name })),
                    ]}
                  />
                </div>

                <div className="flex gap-2 justify-end">
                  <Button type="button" variant="secondary" onClick={resetForm}>
                    Cancelar
                  </Button>
                  <Button
                    type="submit"
                    isLoading={createMutation.isPending || updateMutation.isPending}
                  >
                    {editingCategory ? 'Salvar' : 'Criar'}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        )}

        {/* Lista de Categorias */}
        <Card>
          <CardContent className="p-0">
            {isLoading ? (
              <div className="text-center py-8 text-gray-500">Carregando...</div>
            ) : categories.length === 0 ? (
              <div className="text-center py-8 text-gray-500">Nenhuma categoria cadastrada</div>
            ) : (
              <div className="divide-y">{categories.map((cat) => renderCategory(cat))}</div>
            )}
          </CardContent>
        </Card>
      </div>
    </MainLayout>
  );
}
