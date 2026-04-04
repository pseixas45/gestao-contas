# Plano: Importacao Automatizada de Extratos

## Objetivo
Transferir a logica de conversao e validacao do script manual (`extratos/import_all.py`) e do processo via Claude Code para dentro do software, tornando o fluxo de importacao autonomo pelo frontend.

---

## O que o software JA faz
- Upload e parsing de CSV/XLSX/XLS/PDF
- Deteccao automatica de colunas (ColumnDetector)
- Deteccao de duplicatas por hash (SHA-256: account_id + date + desc + amount + currency + card_payment_date)
- Fuzzy matching (85% similaridade) para duplicatas parciais
- Categorizacao automatica via regras
- Templates salvos por conta (column mapping + format hints)
- Analise dry-run com classificacao (new/duplicate/uncertain)
- Validacao de saldo linha a linha
- Deteccao de parcelas (7/10, 7 de 10)
- Suporte multi-moeda (BRL, USD, EUR)

## O que FALTA automatizar

### 1. Perfis de Banco (Bank Format Profiles)
Cada banco tem formato especifico que hoje so o script manual ou o Claude Code sabe tratar:

| Banco | Header Row | Data Start | Sinal | Peculiaridades |
|-------|-----------|------------|-------|----------------|
| Itau XLS | Row 9 | Row 11 | Correto | Marker "lancamentos futuros", "SALDO ANTERIOR" |
| C6 CC XLSX | Row 9 | Row 10 | Entrada - Saida | Colunas separadas Entrada/Saida |
| C6 Master XLSX | Row 2 | Row 3 | Negar | Valores positivos = compras |
| Master XLSX | Row 1 | Row 2 | Negar + /100 | Decimal separator removido |
| Master/Visa CSV | Row 1 | Row 2 | Negar | Convencao Itau (positivo = compra) |
| Visa XLSX | Row 1 | Row 2 | Correto | Negativo = compra |
| XP Visa CSV | Row 1 | Row 2 | Negar | Similar ao Master/Visa CSV |

**Implementacao:**
- Novo modelo `BankFormatConfig` com regras por banco/conta
- Campos: skip_rows, header_row, sign_convention (as_is | negate | entrada_saida | negate_div100), future_marker_patterns, encoding_hints
- Associar a `bank_accounts` (cada conta sabe qual perfil usar)
- Seed inicial com os 7 perfis acima

### 2. Deteccao de Lancamentos Futuros
O Itau marca com "lancamentos futuros" / "saidas futuras". Outros bancos podem ter marcadores similares.

**Implementacao:**
- Campo `future_marker_patterns` no BankFormatConfig (lista de regex)
- No parsing, ao encontrar marker: parar de importar
- Mostrar no preview quantas linhas foram excluidas como futuras
- Permitir ao usuario incluir/excluir manualmente

### 3. Validacao de Saldo Inteligente
Hoje o sistema valida saldo linha a linha, mas nao compara com saldo informado no arquivo.

**Implementacao:**
- Detectar linha de "SALDO" no arquivo (Itau tem "SALDO TOTAL DISPONIVEL DIA")
- Extrair saldo esperado
- Apos processar, comparar saldo da conta com o esperado
- Se divergir: alertar o usuario ANTES de confirmar, mostrando a diferenca
- Para cartoes: validar que soma da fatura bate

### 4. Tratamento de Arquivos v2 (Correcoes)
Quando o usuario carrega uma versao corrigida, o sistema deve detectar e comparar.

**Implementacao:**
- Ao fazer upload, verificar se ja existe batch para mesma conta + periodo similar
- Endpoint `POST /imports/compare-v2`: recebe batch_id antigo + arquivo novo
- Retorna diff: transacoes adicionadas, removidas, alteradas
- UI mostra diff antes de confirmar
- Opcao de "substituir fatura" (deleta batch antigo + importa novo)

### 5. Normalizacao de Parcelas Cross-Fatura
Parcelas como "ORINTER TOUR E TRA06/10" vs "ORINTER TOUR E TRA07/10" sao parcelas diferentes. Mas a mesma parcela "06/10" pode aparecer em 2 faturas diferentes (fatura de marco e fatura de abril ambas tendo a parcela 06/10).

**Implementacao:**
- Na deteccao de duplicatas, considerar: desc_base + numero_parcela + valor
- Se desc_base + valor iguais mas parcela diferente: NAO eh duplicata
- Se desc_base + valor + parcela iguais mas card_payment_date diferente: PROVAVELMENTE duplicata
- Mostrar como "uncertain" para o usuario decidir

### 6. Auto-Deteccao de Banco
Ao fazer upload, inferir qual banco/formato automaticamente.

**Implementacao:**
- Heuristicas por estrutura do arquivo:
  - Itau XLS: "Logotipo Itau" na primeira celula
  - C6 XLSX: "Data Lancamento | Data Contabil | Titulo" no header
  - C6 Master: "Data de compra | Nome no cartao" no header
  - CSV com "data,lancamento,valor": Master ou Visa (inferir pela conta selecionada)
- Fallback: usuario seleciona manualmente

---

## Arquitetura Proposta

### Novos Arquivos Backend
```
backend/app/models/bank_format.py          # Modelo BankFormatConfig
backend/app/services/format_converter.py   # Servico de conversao por banco
backend/app/api/v1/bank_formats.py         # CRUD de perfis de banco
```

### Arquivos a Modificar
```
backend/app/services/import_service.py     # Integrar format_converter no upload_and_preview
backend/app/api/v1/imports.py              # Novo endpoint compare-v2, auto-detect format
backend/app/models/__init__.py             # Registrar BankFormatConfig
backend/app/schemas/import_file.py         # Novos schemas para format detection
frontend/src/app/importar/page.tsx         # UI: auto-detect bank, show futures, v2 diff
frontend/src/lib/api.ts                    # Novos endpoints
```

---

## Fluxo Futuro (Frontend)

```
1. Usuario seleciona conta
2. Usuario faz upload do arquivo
3. Sistema auto-detecta formato do banco
4. Sistema aplica conversao (negar valores, skip rows, etc.)
5. Sistema detecta e remove lancamentos futuros (mostra contagem)
6. Sistema detecta colunas (ColumnDetector existente)
7. Sistema verifica se eh arquivo v2 (mesmo periodo de batch anterior)
   - Se sim: mostra diff e pergunta se quer substituir
8. Preview com mapeamento de colunas (template salvo ou novo)
9. Analise dry-run: new/duplicate/uncertain + validacao de saldo
10. Usuario confirma -> importa
11. Resultado: importadas, duplicatas, saldo final validado
```

---

## Fases de Implementacao

### Fase 1: Perfis de Banco + Conversao Automatica (ALTA PRIORIDADE)
- Criar modelo BankFormatConfig com seed dos 7 perfis
- Criar FormatConverterService
- Integrar no fluxo de upload (entre parse e column detection)
- Testar com todos os bancos existentes

### Fase 2: Lancamentos Futuros + Saldo (ALTA PRIORIDADE)
- Implementar deteccao de markers
- Implementar validacao de saldo pre-import
- UI para mostrar alertas

### Fase 3: Comparacao v2 + Parcelas (MEDIA PRIORIDADE)
- Endpoint de comparacao
- UI de diff
- Melhoria na deteccao de duplicatas cross-fatura

### Fase 4: Auto-Deteccao + Polish (MEDIA PRIORIDADE)
- Heuristicas de auto-deteccao
- Melhorias de UX
- Tornar import_all.py obsoleto
