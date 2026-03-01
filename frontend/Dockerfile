FROM node:20-alpine

WORKDIR /app

# Copiar package.json
COPY package.json package-lock.json* ./

# Instalar dependências
RUN npm install

# Copiar código
COPY . .

# Expor porta
EXPOSE 3000

# Comando de inicialização
CMD ["npm", "run", "dev"]
