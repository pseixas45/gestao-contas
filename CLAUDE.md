# CLAUDE.md - Instruções para o Claude Code

## Projeto: Gestão de Contas

Sistema full-stack de gestão financeira pessoal.
Documento completo do projeto em `DOCUMENTO_PROJETO.md` (consultar para contexto de funcionalidades, backlog e decisões).

### Stack

- **Backend**: FastAPI (Python 3.11), SQLAlchemy, SQLite — porta 8000
- **Frontend**: Next.js 14, React Query, Tailwind CSS — porta 3000
- **Autenticação**: JWT (usuário: `pseixas`, senha: `pseixas123`)

### Estrutura

```
backend/
  app/
    api/v1/        # Rotas da API (transactions, accounts, imports, etc.)
    models/        # Modelos SQLAlchemy
    schemas/       # Schemas Pydantic
    services/      # Serviços de negócio
    database.py    # Configuração do banco
    main.py        # Aplicação FastAPI
frontend/
  src/
    app/           # Pages (Next.js App Router)
    components/    # Componentes React
    lib/           # API client, utilitários
    types/         # TypeScript types
```

### Multi-moeda

- Contas podem ser BRL, USD ou EUR
- Transações têm: `amount` (moeda nativa), `original_amount`, `amount_brl`, `amount_usd`, `amount_eur`
- Todos os campos de valor são NOT NULL no banco
- `original_currency` deve ser definido a partir da moeda da conta, não do default do schema

### Como rodar

```bash
# Backend
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Frontend
cd frontend
npm run dev
```

## Regra obrigatória: Testar antes de entregar

**SEMPRE** testar toda feature nova ou correção de bug antes de reportar como pronta. O teste deve:

1. **Verificar que o backend está rodando** e com o código mais recente (WatchFiles no Windows pode não recarregar — reiniciar o uvicorn se necessário)
2. **Testar a API diretamente** via `curl` com autenticação JWT para confirmar que o endpoint funciona
3. **Testar cenários relevantes** (ex: multi-moeda → testar BRL, USD e EUR)
4. **Limpar dados de teste** criados durante a verificação
5. **Se não souber quais testes são necessários, perguntar ao usuário antes de começar**

Nunca reportar uma feature/fix como concluída sem evidência de teste bem-sucedido.
