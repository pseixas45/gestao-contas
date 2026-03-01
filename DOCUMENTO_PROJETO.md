# Documento Vivo do Projeto - Sistema de Gestão de Contas Bancárias

**Versão:** 1.0
**Data de Criação:** 12/01/2026
**Última Atualização:** 12/01/2026
**Status do Projeto:** Em Desenvolvimento

---

## 1. Resumo Executivo

O **Sistema de Gestão de Contas Bancárias** é uma aplicação web desenvolvida para centralizar e simplificar o controle financeiro pessoal de usuários que possuem múltiplas contas em diferentes instituições bancárias.

### Problema Identificado
Pessoas com contas em múltiplos bancos enfrentam dificuldade em:
- Consolidar informações financeiras dispersas
- Categorizar e entender seus gastos
- Projetar saldos futuros considerando todas as contas
- Importar histórico de transações de forma eficiente

### Solução Proposta
Uma plataforma unificada que permite:
- Importação em massa de extratos bancários (CSV, Excel) com suporte a múltiplas contas em um único arquivo
- Categorização automática e inteligente de transações
- Visualização consolidada de todas as contas
- Projeção de saldos futuros baseada em histórico

### Diferencial Competitivo
- **Importação em bulk**: Permite carregar histórico de várias contas simultaneamente
- **Coluna de categoria no arquivo**: Suporte para importar transações já categorizadas
- **Detecção inteligente de duplicatas**: Evita duplicação mesmo com transações idênticas no mesmo dia
- **Interface 100% em Português BR**

---

## 2. Objetivos Mensuráveis

### 2.1 Objetivos de Curto Prazo (MVP)

| Objetivo | Métrica de Sucesso | Status |
|----------|-------------------|--------|
| Permitir cadastro de múltiplas contas bancárias | Usuário consegue cadastrar ≥5 contas de bancos diferentes | ✅ Concluído |
| Importar extratos via arquivo | Taxa de sucesso de importação ≥95% | ✅ Concluído |
| Categorizar transações automaticamente | ≥70% das transações categorizadas automaticamente após 30 dias de uso | 🔄 Em progresso |
| Visualizar saldo consolidado | Dashboard mostrando saldo total atualizado em <2 segundos | ✅ Concluído |

### 2.2 Objetivos de Médio Prazo

| Objetivo | Métrica de Sucesso | Status |
|----------|-------------------|--------|
| Projeção de saldos futuros | Precisão de ≥85% na projeção de 30 dias | 🔄 Em progresso |
| Regras de categorização personalizadas | Usuário consegue criar ≥10 regras customizadas | ✅ Concluído |
| Detecção de transações recorrentes | Identificar ≥90% das transações recorrentes (salário, aluguel) | 📋 Planejado |

### 2.3 Objetivos de Longo Prazo

| Objetivo | Métrica de Sucesso | Status |
|----------|-------------------|--------|
| Relatórios e análises avançadas | Gerar relatórios de gastos por categoria/período | 📋 Planejado |
| Alertas e notificações | Notificar sobre saldo baixo, gastos acima da média | 📋 Planejado |
| Importação de PDF (OCR) | Extrair transações de extratos em PDF | 📋 Planejado |
| Multi-usuário familiar | Permitir contas compartilhadas com permissões | 📋 Planejado |

---

## 3. Público Alvo

### 3.1 Persona Primária: "Paulo, o Multi-Bancarizado"

- **Idade:** 30-50 anos
- **Perfil:** Profissional com renda média-alta
- **Comportamento financeiro:**
  - Possui 3-6 contas em bancos diferentes (tradicionais + digitais)
  - Usa cartões de crédito de múltiplas instituições
  - Tem investimentos em diferentes plataformas
  - Busca controle financeiro mas não tem tempo para planilhas manuais
- **Dores:**
  - Perde tempo acessando apps de vários bancos
  - Não consegue ter visão consolidada do patrimônio
  - Dificuldade em entender para onde vai o dinheiro
  - Extratos antigos difíceis de analisar
- **Necessidades:**
  - Centralizar informações em um único lugar
  - Importar histórico de anos anteriores facilmente
  - Categorização automática para economizar tempo

### 3.2 Persona Secundária: "Mariana, a Planejadora"

- **Idade:** 25-35 anos
- **Perfil:** Profissional em início de carreira focada em planejamento
- **Comportamento financeiro:**
  - Possui 2-3 contas bancárias
  - Quer planejar compras grandes e viagens
  - Precisa projetar saldos futuros
- **Dores:**
  - Não sabe se terá saldo suficiente no futuro
  - Dificuldade em identificar gastos supérfluos
- **Necessidades:**
  - Projeção confiável de saldos
  - Identificação de padrões de gastos

### 3.3 Critérios de Exclusão

O sistema **não é destinado** a:
- Empresas (foco exclusivo em pessoa física)
- Contadores ou escritórios de contabilidade
- Usuários que necessitam integração bancária em tempo real (Open Banking)

---

## 4. Funcionalidades / Escopo

### 4.1 Funcionalidades Implementadas (MVP)

#### Autenticação e Usuários
- [x] Registro de novos usuários
- [x] Login com JWT (JSON Web Token)
- [x] Sessão persistente com refresh automático

#### Gestão de Bancos e Contas
- [x] Cadastro de bancos (Itaú, Bradesco, Nubank, Inter, Santander, etc.)
- [x] Cadastro de contas bancárias por banco
- [x] Tipos de conta: Corrente, Poupança, Cartão de Crédito, Investimentos
- [x] Saldo inicial e acompanhamento de saldo atual
- [x] Cores personalizadas por banco para identificação visual

#### Importação de Transações
- [x] Upload de arquivos CSV e Excel
- [x] Importação em bulk (múltiplas contas em um arquivo)
- [x] Mapeamento flexível de colunas
- [x] Coluna de conta bancária para identificar destino
- [x] Coluna de categoria opcional no arquivo
- [x] Preview antes de confirmar importação
- [x] Detecção de duplicatas (mesmo hash = mesma transação)
- [x] Tratamento de transações idênticas no mesmo dia (sufixo no hash)
- [x] Histórico de importações com estatísticas

#### Transações
- [x] Listagem de transações com filtros (data, conta, categoria)
- [x] Busca por descrição
- [x] Edição manual de transações
- [x] Categorização individual
- [x] Lista de transações pendentes de categorização

#### Categorias
- [x] Categorias pré-definidas (Alimentação, Transporte, Moradia, etc.)
- [x] Tipos: Receita e Despesa
- [x] Cores e ícones personalizados
- [x] Categorias hierárquicas (subcategorias)

#### Regras de Categorização
- [x] Criar regras baseadas em texto (contém, começa com, igual)
- [x] Aplicar regras automaticamente em novas transações
- [x] Prioridade de regras configurável

#### Projeção de Saldos
- [x] Projeção baseada em média histórica
- [x] Projeção por tendência
- [x] Gráfico de projeção por conta

### 4.2 Funcionalidades Planejadas (Backlog)

#### Alta Prioridade
- [ ] Dashboard consolidado com gráficos
- [ ] Relatório de gastos por categoria
- [ ] Detecção automática de transações recorrentes
- [ ] Exportação de dados (CSV, Excel)

#### Média Prioridade
- [ ] Importação de PDF via OCR
- [ ] Orçamento mensal por categoria
- [ ] Alertas de saldo baixo
- [ ] Metas de economia

#### Baixa Prioridade
- [ ] App mobile (React Native)
- [ ] Integração Open Banking
- [ ] Multi-usuário familiar
- [ ] Backup automático na nuvem

### 4.3 Fora do Escopo (Não será implementado)

- Integração em tempo real com bancos
- Funcionalidades para empresas/CNPJ
- Emissão de boletos ou pagamentos
- Consultoria financeira automatizada
- Investimentos automatizados

---

## 5. Histórias de Uso

### HU-01: Registro e Primeiro Acesso
**Como** novo usuário
**Quero** criar minha conta e configurar meus bancos
**Para que** eu possa começar a usar o sistema

**Critérios de Aceite:**
1. Usuário acessa a tela de registro
2. Preenche nome, email e senha
3. Sistema valida dados e cria conta
4. Após login, usuário é direcionado ao dashboard
5. Usuário pode cadastrar seus bancos e contas

**Status:** ✅ Implementado

---

### HU-02: Importar Histórico de Transações
**Como** usuário com histórico em planilhas
**Quero** importar meus extratos de múltiplos bancos
**Para que** eu tenha todo meu histórico financeiro no sistema

**Critérios de Aceite:**
1. Usuário acessa a tela de importação
2. Seleciona arquivo CSV ou Excel
3. Sistema detecta colunas automaticamente
4. Usuário mapeia colunas (data, descrição, valor, conta, categoria)
5. Preview mostra primeiras linhas para validação
6. Usuário confirma e sistema processa
7. Transações são criadas e vinculadas às contas corretas
8. Duplicatas são detectadas e tratadas conforme preferência

**Status:** ✅ Implementado

---

### HU-03: Categorizar Transações
**Como** usuário que deseja entender seus gastos
**Quero** categorizar minhas transações
**Para que** eu saiba para onde meu dinheiro está indo

**Critérios de Aceite:**
1. Usuário visualiza transações pendentes de categorização
2. Pode categorizar individualmente clicando na transação
3. Pode criar regras para categorização automática
4. Regras são aplicadas em novas importações
5. Sistema sugere categorias baseado em padrões

**Status:** ✅ Implementado

---

### HU-04: Visualizar Saldo Consolidado
**Como** usuário com múltiplas contas
**Quero** ver meu saldo total e por conta
**Para que** eu tenha visão clara do meu patrimônio

**Critérios de Aceite:**
1. Dashboard mostra saldo total de todas as contas
2. Lista cada conta com seu saldo individual
3. Cores dos bancos facilitam identificação
4. Saldo é atualizado em tempo real após importações

**Status:** ✅ Implementado

---

### HU-05: Projetar Saldo Futuro
**Como** usuário planejando compras
**Quero** ver projeção do meu saldo nos próximos meses
**Para que** eu saiba se terei dinheiro disponível

**Critérios de Aceite:**
1. Usuário seleciona conta e período de projeção
2. Sistema calcula projeção baseada em histórico
3. Gráfico mostra evolução projetada
4. Usuário pode escolher método de cálculo (média, tendência)

**Status:** ✅ Implementado

---

### HU-06: Criar Regras de Categorização
**Como** usuário que quer economizar tempo
**Quero** criar regras automáticas de categorização
**Para que** minhas transações sejam categorizadas sem esforço

**Critérios de Aceite:**
1. Usuário acessa tela de regras
2. Cria nova regra com padrão de texto
3. Seleciona categoria destino
4. Define prioridade da regra
5. Regra é aplicada em transações futuras

**Status:** ✅ Implementado

---

### HU-07: Visualizar Histórico de Importações
**Como** usuário que faz múltiplas importações
**Quero** ver o histórico de arquivos importados
**Para que** eu saiba o que já foi carregado no sistema

**Critérios de Aceite:**
1. Lista todas as importações realizadas
2. Mostra data, arquivo, quantidade de transações
3. Mostra quantas duplicatas foram encontradas
4. Permite identificar problemas em importações anteriores

**Status:** ✅ Implementado

---

### HU-08: Gerenciar Transações Duplicadas
**Como** usuário importando extratos que podem ter sobreposição
**Quero** que o sistema detecte e trate duplicatas
**Para que** eu não tenha transações repetidas

**Critérios de Aceite:**
1. Sistema gera hash único para cada transação
2. Detecta se transação já existe no banco
3. Opção de pular duplicatas ou importar mesmo assim
4. Transações idênticas no mesmo dia recebem identificador único
5. Feedback mostra quantas duplicatas foram encontradas

**Status:** ✅ Implementado

---

## 6. Cronograma

### Fase 1: MVP (Concluído)
- Autenticação de usuários
- CRUD de bancos e contas
- Importação básica de transações
- Categorização manual
- Listagem de transações

### Fase 2: Importação Avançada (Concluído)
- Importação bulk multi-conta
- Coluna de categoria no arquivo
- Detecção de duplicatas avançada
- Histórico de importações

### Fase 3: Categorização Inteligente (Em Progresso)
- Regras de categorização
- Aplicação automática de regras
- Sugestões de categoria

### Fase 4: Dashboard e Relatórios (Próxima)
- Dashboard consolidado
- Gráficos de gastos por categoria
- Gráfico de evolução de saldo
- Relatórios exportáveis

### Fase 5: Projeções Avançadas (Planejado)
- Detecção de recorrências
- Projeção com recorrências
- Alertas de saldo

### Fase 6: Recursos Adicionais (Backlog)
- Orçamento por categoria
- Metas de economia
- Importação de PDF
- Multi-usuário

---

## 7. Stack Tecnológica

### Backend
- **Framework:** FastAPI (Python 3.11+)
- **ORM:** SQLAlchemy 2.0
- **Banco de Dados:** SQLite (desenvolvimento) / MySQL (produção)
- **Autenticação:** JWT com bcrypt
- **Processamento de arquivos:** Pandas

### Frontend
- **Framework:** Next.js 14
- **Biblioteca UI:** React 18
- **Estilização:** Tailwind CSS
- **Estado:** React Query + Context API
- **Gráficos:** Recharts

### Infraestrutura
- **Containerização:** Docker + Docker Compose
- **Proxy Reverso:** Nginx (produção)

---

## 8. Contatos e Responsáveis

| Papel | Nome | Responsabilidade |
|-------|------|------------------|
| Product Owner | Paulo | Definição de requisitos e prioridades |
| Desenvolvedor | Claude (AI) | Implementação técnica |

---

## 9. Backlog de Melhorias Futuras

Esta seção documenta melhorias identificadas durante o desenvolvimento que devem ser priorizadas futuramente.

### 9.1 Melhorias Técnicas (Infraestrutura)

| ID | Melhoria | Descrição | Impacto | Esforço |
|----|----------|-----------|---------|---------|
| MT-01 | **Estabilidade do servidor** | Backend cai frequentemente, necessita reinicialização manual. Implementar supervisor de processos (PM2, Supervisor) ou health checks automáticos | Alto | Médio |
| MT-02 | **Gerenciamento de portas** | Processos zombie ocupam portas. Criar script de inicialização que limpa portas antes de subir serviços | Médio | Baixo |
| MT-03 | **Logs estruturados** | Implementar logging centralizado com rotação de arquivos para facilitar debug | Médio | Baixo |
| MT-04 | **Testes automatizados** | Criar suite de testes unitários e de integração (pytest + Jest) | Alto | Alto |
| MT-05 | **CI/CD Pipeline** | Configurar GitHub Actions para build, testes e deploy automático | Médio | Médio |
| MT-06 | **Migração para PostgreSQL** | SQLite tem limitações de concorrência. Migrar para PostgreSQL em produção | Médio | Médio |
| MT-07 | **Cache com Redis** | Adicionar cache para queries frequentes (saldos, dashboard) | Médio | Médio |
| MT-08 | **Rate limiting** | Proteger API contra abuso com limite de requisições | Baixo | Baixo |

### 9.2 Melhorias de UX/UI

| ID | Melhoria | Descrição | Impacto | Esforço |
|----|----------|-----------|---------|---------|
| UX-01 | **Feedback visual de carregamento** | Tela "Carregando..." sem indicação de progresso. Adicionar spinners e mensagens contextuais | Alto | Baixo |
| UX-02 | **Tratamento de erros amigável** | Mensagens como "Erro ao processar" são genéricas. Mostrar erros específicos e ações sugeridas | Alto | Médio |
| UX-03 | **Modo offline** | Permitir visualização de dados em cache quando sem conexão | Baixo | Alto |
| UX-04 | **Tema escuro** | Adicionar opção de dark mode | Baixo | Baixo |
| UX-05 | **Responsividade mobile** | Otimizar interface para uso em smartphones | Médio | Médio |
| UX-06 | **Atalhos de teclado** | Navegação rápida via teclado para usuários avançados | Baixo | Baixo |
| UX-07 | **Tour guiado** | Onboarding interativo para novos usuários | Médio | Médio |
| UX-08 | **Notificações toast** | Feedback visual para ações (salvo, importado, erro) | Médio | Baixo |

### 9.3 Melhorias Funcionais

| ID | Melhoria | Descrição | Impacto | Esforço |
|----|----------|-----------|---------|---------|
| MF-01 | **Dashboard analítico** | Gráficos de pizza (gastos por categoria), linha (evolução), barras (comparativo mensal) | Alto | Médio |
| MF-02 | **Relatórios exportáveis** | Exportar transações e relatórios em PDF, Excel, CSV | Alto | Médio |
| MF-03 | **Busca avançada** | Filtros combinados: período + categoria + valor + conta + texto | Médio | Baixo |
| MF-04 | **Transações recorrentes** | Detectar e marcar automaticamente (salário, aluguel, Netflix) | Alto | Alto |
| MF-05 | **Orçamento por categoria** | Definir limite mensal e alertar quando próximo/excedido | Alto | Médio |
| MF-06 | **Metas financeiras** | Criar metas de economia com acompanhamento visual | Médio | Médio |
| MF-07 | **Importação de OFX** | Suporte ao formato OFX usado por muitos bancos | Médio | Médio |
| MF-08 | **Importação de PDF** | OCR para extrair transações de extratos em PDF | Médio | Alto |
| MF-09 | **Conciliação bancária** | Comparar transações importadas vs extrato oficial | Médio | Alto |
| MF-10 | **Anexar comprovantes** | Upload de imagens/PDFs vinculados a transações | Baixo | Médio |
| MF-11 | **Notas em transações** | Campo de observações livre para cada transação | Baixo | Baixo |
| MF-12 | **Tags customizadas** | Além de categoria, permitir múltiplas tags por transação | Médio | Médio |
| MF-13 | **Split de transações** | Dividir uma transação em múltiplas categorias | Médio | Médio |
| MF-14 | **Transferências entre contas** | Identificar e vincular automaticamente transferências | Médio | Médio |

### 9.4 Melhorias de Segurança

| ID | Melhoria | Descrição | Impacto | Esforço |
|----|----------|-----------|---------|---------|
| MS-01 | **Autenticação 2FA** | Segundo fator via app authenticator ou SMS | Alto | Médio |
| MS-02 | **Sessões ativas** | Visualizar e encerrar sessões em outros dispositivos | Médio | Baixo |
| MS-03 | **Audit log** | Registrar todas as ações do usuário para auditoria | Médio | Médio |
| MS-04 | **Criptografia de dados** | Criptografar dados sensíveis em repouso | Alto | Alto |
| MS-05 | **Backup automático** | Rotina de backup com retenção configurável | Alto | Médio |
| MS-06 | **Recuperação de senha** | Fluxo de reset via email | Alto | Baixo |

### 9.5 Melhorias de Performance

| ID | Melhoria | Descrição | Impacto | Esforço |
|----|----------|-----------|---------|---------|
| MP-01 | **Paginação otimizada** | Lazy loading de transações com scroll infinito | Médio | Baixo |
| MP-02 | **Índices de banco** | Otimizar queries com índices apropriados | Alto | Baixo |
| MP-03 | **Compressão de respostas** | Habilitar gzip/brotli na API | Baixo | Baixo |
| MP-04 | **Importação assíncrona** | Processar arquivos grandes em background com notificação | Alto | Médio |
| MP-05 | **Agregações pré-calculadas** | Materializar totais por categoria/mês para dashboard rápido | Médio | Médio |

### 9.6 Priorização Sugerida

**Sprint 1 - Estabilidade:**
- MT-01 (Supervisor de processos)
- MT-02 (Script de portas)
- UX-01 (Feedback de carregamento)
- UX-02 (Erros amigáveis)

**Sprint 2 - Dashboard:**
- MF-01 (Dashboard analítico)
- MF-03 (Busca avançada)
- MP-01 (Paginação)

**Sprint 3 - Relatórios:**
- MF-02 (Exportação)
- MF-04 (Recorrentes)
- MT-03 (Logs)

**Sprint 4 - Segurança:**
- MS-06 (Reset senha)
- MS-05 (Backup)
- MT-04 (Testes)

---

## 10. Histórico de Alterações

| Data | Versão | Descrição |
|------|--------|-----------|
| 12/01/2026 | 1.0 | Criação do documento inicial |
| 12/01/2026 | 1.1 | Adicionada seção de Backlog de Melhorias Futuras |

---

*Este é um documento vivo e será atualizado conforme o projeto evolui.*
