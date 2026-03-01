from fastapi import APIRouter

from app.api.v1 import auth, banks, accounts, categories, transactions, rules, imports, projections, admin, exchange, budgets, reports

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Autenticação"])
api_router.include_router(banks.router, prefix="/banks", tags=["Bancos"])
api_router.include_router(accounts.router, prefix="/accounts", tags=["Contas"])
api_router.include_router(categories.router, prefix="/categories", tags=["Categorias"])
api_router.include_router(transactions.router, prefix="/transactions", tags=["Transações"])
api_router.include_router(rules.router, prefix="/rules", tags=["Regras"])
api_router.include_router(imports.router, prefix="/imports", tags=["Importação"])
api_router.include_router(projections.router, prefix="/projections", tags=["Projeções"])
api_router.include_router(admin.router, prefix="/admin", tags=["Admin"])
api_router.include_router(exchange.router, prefix="/exchange", tags=["Câmbio"])
api_router.include_router(budgets.router, tags=["Orçamentos"])
api_router.include_router(reports.router, tags=["Relatórios"])
