# Sistema de Gestão de Contas Bancárias

Sistema completo para gestão de contas bancárias pessoais com:
- Importação de extratos (CSV, Excel, PDF)
- Categorização automática de transações
- Projeção de saldos futuros
- Interface em Português BR

## Requisitos

- Docker e Docker Compose
- Ou: Python 3.11+, Node.js 18+, MySQL 8.0

## Início Rápido (Docker)

```bash
# Clonar e entrar no diretório
cd gestao-contas

# Iniciar todos os serviços
docker-compose up -d

# Aguardar inicialização (cerca de 30 segundos)
# O sistema estará disponível em:
# - Frontend: http://localhost:3000
# - API: http://localhost:8000
# - Docs API: http://localhost:8000/docs
```

## Primeiro Acesso

1. Acesse http://localhost:3000
2. Clique em "Criar conta" para registrar um usuário
3. Faça login com as credenciais criadas

## Execução Local (sem Docker)

### Backend

```bash
cd backend

# Criar ambiente virtual
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Instalar dependências
pip install -r requirements.txt

# Configurar variáveis de ambiente
copy .env.example .env
# Edite o .env com suas configurações de banco

# Executar
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend

# Instalar dependências
npm install

# Executar
npm run dev
```

## Estrutura do Projeto

```
gestao-contas/
├── backend/           # API FastAPI
│   ├── app/
│   │   ├── api/       # Endpoints
│   │   ├── models/    # Modelos SQLAlchemy
│   │   ├── schemas/   # Schemas Pydantic
│   │   └── services/  # Lógica de negócio
│   └── requirements.txt
│
├── frontend/          # Interface Next.js
│   ├── src/
│   │   ├── app/       # Páginas
│   │   ├── components/# Componentes React
│   │   └── lib/       # Utilitários
│   └── package.json
│
└── docker-compose.yml
```

## Funcionalidades

### Contas Bancárias
- Cadastro de múltiplas contas (Itaú, Bradesco, Nubank, etc.)
- Tipos: Conta Corrente, Poupança, Cartão de Crédito, Investimentos
- Saldo inicial e acompanhamento

### Importação de Extratos
1. Selecione a conta destino
2. Faça upload do arquivo (CSV, Excel ou PDF)
3. Confirme o mapeamento de colunas
4. Visualize preview antes de importar
5. Sistema detecta duplicatas automaticamente

### Categorização Automática
- **Regras manuais**: "Se descrição contém 'UBER' → Transporte"
- **Aprendizado**: Sistema aprende com suas categorizações
- **Sugestões**: Transações pendentes mostram sugestões

### Projeção de Saldos
- Métodos: Média histórica, Tendência, Recorrentes
- Detecta transações recorrentes (salário, aluguel, etc.)
- Gráfico de projeção por conta

## API Endpoints Principais

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| POST | /api/v1/auth/login | Login |
| GET | /api/v1/accounts | Listar contas |
| GET | /api/v1/transactions | Listar transações |
| GET | /api/v1/transactions/pending | Transações pendentes |
| POST | /api/v1/imports/upload | Upload de arquivo |
| POST | /api/v1/imports/process | Processar importação |
| GET | /api/v1/projections/{id} | Projeção de saldo |

Documentação completa: http://localhost:8000/docs

## Variáveis de Ambiente

### Backend (.env)
```
DATABASE_URL=mysql+pymysql://user:pass@localhost:3306/gestao_contas
SECRET_KEY=sua-chave-secreta
DEBUG=true
```

### Frontend (.env.local)
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Tecnologias

- **Backend**: FastAPI, SQLAlchemy, PyJWT, Pandas
- **Frontend**: Next.js 14, React 18, Tailwind CSS, React Query
- **Banco**: MySQL 8.0
- **Containers**: Docker, Docker Compose
