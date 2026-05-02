FROM python:3.11-slim

WORKDIR /app

# Instalar dependências do sistema para tabula-py (Java)
RUN apt-get update && apt-get install -y \
    default-jre \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements e instalar dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código da aplicação
COPY . .

# Render injeta a porta via $PORT — usa 8000 como default local
ENV PORT=8000
EXPOSE 8000

# Comando de inicialização (sem --reload em produção)
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
