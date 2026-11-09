# Plano de Migração — Supabase → Neon

> **Objetivo:** mover o banco Postgres do **Supabase (São Paulo)** para o **Neon
> (US-East, junto do backend no Render/Ohio)**, eliminando (1) a **latência
> cross-region** (hoje ~2s para mudar categoria) e (2) a **pausa por inatividade**
> do free tier do Supabase (que derrubou o ambiente em 08/11).
>
> **Princípio:** migrar **mantendo o Supabase intacto**. O rollback é só reapontar
> a `DATABASE_URL` de volta. Nada é apagado na origem.

---

## Por que Neon

- O app usa o Supabase **apenas como Postgres puro** (SQLAlchemy + JWT próprio —
  sem Auth/Storage/PostgREST do Supabase), então o banco é **portável**.
- Neon é Postgres gerenciado, **co-localizável com o Render (Ohio)** → mata a
  latência. E faz **scale-to-zero com auto-wake** (dorme ocioso, acorda sozinho no
  próximo acesso) → **não existe a pausa manual** do Supabase.
- Free tier do Neon: 0,5 GB... na prática sobra (hoje usamos ~50 MB / 30.650 linhas).
  Autoscaling até 2 CU (8 GB RAM) no Free; sobe para 16 CU sem migrar nada se crescer.

## Arquitetura

```
ANTES:  Vercel(frontend) → Render(API, Ohio) → Supabase(Postgres, São Paulo)   ← ~8.000 km por query
DEPOIS: Vercel(frontend) → Render(API, Ohio) → Neon(Postgres, us-east-2 Ohio)  ← mesma região
```

---

## Estado atual (baseline capturado em 08/11/2026)

- **22 tabelas, 30.650 linhas**, Postgres **17.6**, schema **`gestao_contas`**.
- **100% dos modelos do app cobrem as tabelas** (verificado — nenhuma tabela órfã).
- Contagem por tabela (checklist de validação):

| tabela | linhas | tabela | linhas |
|---|---|---|---|
| transactions | 14925 | import_batches | 239 |
| categorization_history | 6267 | budgets | 282 |
| exchange_rates | 3148 | account_balance_logs | 240 |
| expense_report_items | 2178 | assets | 170 |
| categorization_rules | 1070 | cash_projection_items | 136 |
| investment_positions | 1137 | expense_reports | 69 |
| market_index_rates | 642 | investment_snapshots | 59 |
| bank_accounts | 14 | categories | 33 |
| asset_classes | 12 | import_templates | 8 |
| banks | 11 | saved_report_views | 9 |
| users | 1 | investment_goals | 0 |

## Ferramentas

- `pg_dump`/`psql` **não** estão instalados → migração via **script Python**
  (`backend/scripts/migrate_supabase_to_neon.py`), que usa os próprios modelos do
  app para criar o schema e copia os dados na ordem de FK. Portável, sem binário externo.

---

## Passo a passo

### Fase 0 — Preparação ✅ (feito)
- [x] Baseline de tabelas/linhas capturado.
- [x] Cobertura de modelos verificada (22/22).
- [x] Script de migração escrito (`migrate_supabase_to_neon.py`).
- [x] Este plano.

### Fase 1 — Criar o projeto Neon  👤 (você)
1. Criar conta em https://neon.tech (grátis, pode logar com GitHub).
2. **New Project** → **Region: AWS US East (Ohio) — us-east-2** (mesma do Render).
   - Postgres version: **17** (igual à origem).
3. Copiar a **connection string** (Dashboard → Connect). Pegar a versão
   **"Direct"/sem pooler** para a migração (role `neondb_owner`, database `neondb`).
4. Me enviar a connection string. Eu rodo a migração.

### Fase 2 — Migrar os dados  🤖 (eu)
1. `NEON_DATABASE_URL=<string> python scripts/migrate_supabase_to_neon.py`
   - cria schema `gestao_contas` + 22 tabelas no Neon (a partir dos modelos);
   - copia as 30.650 linhas (FKs desligadas na carga; sequências resetadas);
   - **verifica**: contagem origem x destino tem que bater 22/22.
2. **Teste funcional local apontando para o Neon** (sem tocar em produção):
   login, listar transações, **mudar categoria** (medir a latência nova),
   dashboard, e conferir o registro `Md Budapest`.

### Fase 3 — Cutover de produção  👤 (você, com meu passo a passo)
1. No painel **Render → Environment**, trocar `DATABASE_URL` para a string do Neon
   (versão **pooled**, com `-pooler`, para o runtime). Manter `DB_SCHEMA=gestao_contas`.
2. Save → Render redeploya (~5 min).
3. **Validar**: `GET /health/db` → 200; login; `Md Budapest` aparece; dashboard bate.
4. (Opcional) Atualizar o `backend/.env` local para o Neon também.

### Fase 4 — Período de observação e descomissionamento
- Rodar alguns dias no Neon validando os números.
- **Supabase fica intacto** como rede de segurança durante a janela.
- Quando confiante: pausar/arquivar o projeto Supabase (sem pressa).
- O **keep-alive** (cron `/health/db`) pode ser mantido (inofensivo, ainda acorda o
  Render) ou removido — no Neon a pausa não existe mais.

---

## Rollback

| Quando | Como | Perda de dados? |
|---|---|---|
| Durante Fase 2 (migração/teste) | Nada a fazer — produção nunca saiu do Supabase | Nenhuma |
| Logo após o cutover (Fase 3), sem uso novo | Reverter `DATABASE_URL` no Render para o Supabase + redeploy | Nenhuma |
| Após **dias de uso** no Neon | Reverter a `DATABASE_URL` **perde** o que foi escrito no Neon no período | ⚠️ Sim — os lançamentos/edições feitos enquanto rodava no Neon ficam só no Neon |

**Mitigação:** durante a janela de observação, evitar cargas pesadas; validar os
números cedo. Se decidir voltar depois de muito uso, eu **re-sincronizo Neon →
Supabase** antes de reverter (o mesmo script, com origem/destino trocados).

## Riscos e mitigação

- **Schema divergente:** evitado — o schema é criado pelos **modelos do app** e o
  app ainda roda `create_all`+migrações no startup contra o Neon.
- **Sequências/IDs colidindo:** o script reseta todas as sequências para `max(id)`.
- **FK/ordem de carga:** cópia em ordem topológica + FKs desligadas na carga.
- **Perda silenciosa de tabela:** a verificação compara as 22 contagens; divergência aborta o go-live.
