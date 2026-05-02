# Deploy & Infraestrutura

> Documentação de deploy do sistema **Gestão de Contas**.
> Este arquivo contém **referências** aos serviços usados.
> **NÃO** contém credenciais — essas ficam só no `.env` (que está no `.gitignore`).

## Visão geral

```
Browser → Vercel (frontend Next.js) → Render (backend FastAPI) → Supabase (Postgres)
```

| Camada | Serviço | URL produção | Plano | Custo |
|---|---|---|---|---|
| **Banco de dados** | Supabase | `db.hxnrsporzoneveawxtrc.supabase.co` | Free | R$ 0 |
| **Backend (API)** | Render | `https://gestao-contas-api.onrender.com` | Free | R$ 0 |
| **Frontend (UI)** | Vercel | `https://gestao-contas-seven.vercel.app` | Hobby Free | R$ 0 |

---

## 🗄️ Supabase (Banco de dados)

**Para que serve**: PostgreSQL gerenciado. Guarda todos os dados (transações, categorias, regras, histórico de categorização, projeções).

**Conta**: pseixas (já existente, projeto compartilhado)

| Item | Valor |
|---|---|
| Projeto Supabase | `hxnrsporzoneveawxtrc` |
| Região | `sa-east-1` (São Paulo) |
| Postgres versão | 17.6 |
| Schema isolado | `gestao_contas` (tabelas separadas de outros projetos) |
| Painel | https://supabase.com/dashboard/project/hxnrsporzoneveawxtrc |

**Conexões**:

| Uso | URL |
|---|---|
| **Direto** (migrations, scripts) | `postgresql://postgres:[SENHA]@db.hxnrsporzoneveawxtrc.supabase.co:5432/postgres` |
| **Pooler** (produção, recomendado para apps com muitas conexões) | `postgresql://postgres.hxnrsporzoneveawxtrc:[SENHA]@aws-1-sa-east-1.pooler.supabase.com:6543/postgres?pgbouncer=true` |

**Senha**: armazenada localmente em `backend/.env` (NÃO commitar). Para resetar: painel Supabase → Settings → Database → Reset password.

**Tabelas migradas** (14):
- users, banks, categories, bank_accounts, exchange_rates
- categorization_rules, categorization_history, import_batches
- transactions (~13k linhas), budgets, cash_projection_items
- saved_report_views, import_templates, account_balance_logs

---

## ⚙️ Render (Backend FastAPI)

**Para que serve**: Servidor Python que roda o backend (FastAPI). Lógica de negócio: autenticação, parsing de extratos, categorização automática, projeção de caixa, etc.

**Painel**: https://dashboard.render.com

| Item | Valor |
|---|---|
| Service name | `gestao-contas-api` |
| URL pública | `https://gestao-contas-api.onrender.com` |
| Tipo | Web Service (Docker) |
| Region | Ohio |
| Plan | Free (512 MB RAM, cold start após 15 min) |
| Branch | `master` (auto-deploy a cada push) |
| Root Directory | `backend` |
| Dockerfile | `backend/Dockerfile` (já configurado) |

**Endpoints úteis**:
- `GET /docs` — Swagger UI (documentação interativa)
- `GET /health` — health check
- `POST /api/v1/auth/login` — login (form-data: username, password)

**Variáveis de ambiente** (configuradas no painel Render → Environment):

| Variável | Descrição |
|---|---|
| `DATABASE_URL` | URL do Supabase Postgres (com senha) |
| `DB_SCHEMA` | `gestao_contas` |
| `SECRET_KEY` | JWT secret (token_urlsafe(48)) |
| `ALGORITHM` | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` (24h) |
| `APP_NAME` | `Gestão de Contas` |
| `DEBUG` | `False` |
| `CORS_ORIGINS` | URL do Vercel + localhost (separadas por vírgula) |
| `MAX_UPLOAD_SIZE` | `10485760` |
| `UPLOAD_DIR` | `/tmp/uploads` |

**Login padrão (JWT)**: `pseixas` / `pseixas123` (definido no banco — pode ser trocado via API).

---

## 🌐 Vercel (Frontend Next.js)

**Para que serve**: Hospeda o frontend Next.js. Build automático e CDN global.

**Painel**: https://vercel.com/dashboard

| Item | Valor |
|---|---|
| Projeto | `gestao-contas` |
| URL pública | `https://gestao-contas-seven.vercel.app` |
| Plano | Hobby (Free) |
| Framework | Next.js 14 |
| Root Directory | `frontend` |
| Branch | `master` (auto-deploy a cada push) |

**Variáveis de ambiente** (Project Settings → Environment Variables):

| Variável | Valor |
|---|---|
| `NEXT_PUBLIC_API_URL` | `https://gestao-contas-api.onrender.com` |

**Limites Hobby Free**:
- 100 GB bandwidth/mês
- 6.000 build minutes/mês
- Custom domains ilimitados

---

## 🚀 Deploy (passo a passo)

### Mudança no código → push automático

Toda vez que você fizer `git push origin master`:
1. **Render** detecta e faz redeploy do backend (~5 min)
2. **Vercel** detecta e faz redeploy do frontend (~2 min)

### Migrar dados do SQLite local para o Supabase

```bash
# 1. Configurar backend/.env com DATABASE_URL do Supabase + DB_SCHEMA=gestao_contas
# 2. Instalar driver
pip install psycopg2-binary==2.9.9

# 3. Dry-run (simula)
cd backend
python ../scripts/migrate_sqlite_to_postgres.py --dry-run

# 4. Aplicar
python ../scripts/migrate_sqlite_to_postgres.py
```

### Atualizar CORS após deploy do Vercel

1. Acesse Render → Service → Environment
2. Edite `CORS_ORIGINS` para incluir o domínio Vercel:
   ```
   https://gestao-contas-XXX.vercel.app,http://localhost:3000
   ```
3. Save → Render faz redeploy automático

---

## 🔧 Desenvolvimento local

### Backend
```bash
cd backend
# Criar .env (copiar de .env.example) com URL do Supabase ou SQLite local
python -m uvicorn app.main:app --host 0.0.0.0 --port 8002
```

### Frontend
```bash
cd frontend
# Criar .env.local com NEXT_PUBLIC_API_URL=http://localhost:8002
npm install
npm run dev
```

Acesse: http://localhost:3000

---

## 🐛 Troubleshooting

### Backend Render não responde
- Plan Free dorme após 15 min — primeira request demora ~30s (cold start, normal)
- Verificar logs no painel Render → aba Logs
- Verificar Build status na aba Events

### "Password authentication failed" no Supabase
- Senha do banco pode ter sido alterada
- Resetar em: Supabase Dashboard → Settings → Database → Reset password
- Atualizar `.env` local + variável `DATABASE_URL` no Render

### Frontend Vercel não conecta ao backend
- Verificar `NEXT_PUBLIC_API_URL` aponta para a URL correta do Render
- Verificar `CORS_ORIGINS` no Render inclui o domínio Vercel
- Re-deploy do Vercel após mudar variáveis

### Cold start está atrapalhando
- Upgrade plano Render Starter ($7/mês) — sempre on
- Ou usar Fly.io (always-on no free tier, mas precisa CLI)

---

## 📊 Limites e custos atuais (free tiers)

| Serviço | Limite | Quando virar problema |
|---|---|---|
| Supabase DB | 500 MB | ~50 anos de uso pessoal (estamos com ~50 MB) |
| Supabase bandwidth | 5 GB/mês | só se hospedar mídia |
| Render compute | 750h/mês | sempre OK pro free (sleep agressivo) |
| Render bandwidth | 100 GB/mês | sempre OK pro pessoal |
| Vercel bandwidth | 100 GB/mês | sempre OK pro pessoal |
| Vercel build | 6000 min/mês | ~1500 deploys, longe |

**Custo total atual: R$ 0/mês**

Se quiser tirar cold start: ~R$ 35-40/mês (Render Starter).
