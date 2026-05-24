# Conceitos dos Cards de Investimentos

## Cards do Dashboard

### 1. Patrimônio Total
- **Fonte**: `overview.total_value`
- **Cálculo**: Soma dos `snapshot.total_value` do **último snapshot de cada conta** de investimento
- **O que é**: O valor que cada banco/corretora reporta como patrimônio total no extrato
- **Exemplo**: XP R$ 1.703k + Itaú R$ 770k + C6 R$ 157k = R$ 2.630k

### 2. Variação no Mês
- **Fonte**: `overview.monthly_change` e `overview.monthly_change_pct`
- **Cálculo**:
  1. Pega a data do último snapshot (`max_date`, ex: 30/04/2026)
  2. Busca o patrimônio total consolidado ~35 dias antes (`max_date - 35 dias`)
     - Para cada conta, pega o snapshot mais recente que seja <= essa data
  3. `variação = patrimônio_atual - patrimônio_anterior`
  4. `variação_pct = variação / patrimônio_anterior × 100`
- **Inclui**: Tanto rendimento quanto aportes/resgates (é variação bruta, não rendimento puro)

### 3. Rentabilidade Total
- **Fonte**: `overview.yield_pct` e `overview.yield_value`
- **Cálculo**:
  - `yield_value = total_value - total_invested` (patrimônio atual - capital aplicado)
  - `yield_pct = yield_value / total_invested × 100`
- **Data de início**: Não tem data fixa — é o acumulado desde o primeiro aporte
- **Limitação atual**: Apenas a XP traz `total_invested` do extrato. Itaú e C6 retornam `invested = 0`, o que faz o cálculo considerar só o capital da XP como denominador, inflando o percentual. **O percentual está incorreto enquanto Itaú e C6 não tiverem `total_invested` populado.**

### 4. Aporte do Mês
- **Fonte**: `overview.monthly_contribution`
- **Cálculo**:
  - `aporte = total_invested_atual - total_invested_anterior` (diferença de capital aplicado entre snapshots)
  - Usa o mesmo snapshot anterior da Variação no Mês (~35 dias antes)
- **O que é**: Quanto de capital novo foi aportado (sem contar rendimento)
- **Limitação**: Depende de `total_invested` estar preenchido. Contas sem esse dado (Itaú, C6) contribuem 0.

### 5. Rendimento do Mês
- **Fonte**: `monthly_yield` (último ponto da série)
- **Cálculo**:
  - `yield_value = patrimônio_atual - patrimônio_anterior - max(aporte, 0)`
  - `yield_pct = yield_value / patrimônio_anterior × 100`
  - Usa a série temporal consolidada (todos os snapshots em ordem cronológica)
- **Diferença da Variação no Mês**: Rendimento desconta os aportes. Variação inclui tudo.
- **Limitação**: Se `total_invested` não está preenchido para alguma conta, o aporte calculado é 0 e o rendimento pode incluir aportes reais que não foram descontados.

### 6. Valor Líquido (pós-IR)
- **Fonte**: `net_summary.total_net` e `net_summary.total_ir`
- **Cálculo**: Para cada posição do último snapshot:
  1. Se o extrato já trouxe `value_net` (ex: Itaú CDB), usa direto
  2. Senão, calcula: `rendimento = value_gross - value_invested`, aplica tabela de IR regressivo + IOF com base nos dias desde `application_date`
  3. Isenções: LCA, LCI, CRA, CRI, debêntures incentivadas (IR = 0)
  4. Previdência: tabela regressiva própria (35% → 10%)
- **Limitação**: Posições sem `application_date` ou `value_invested` usam fallback (sem desconto de IR)

---

## Campos-chave por provedor

| Campo | XP | Itaú | C6 |
|-------|-----|------|-----|
| `total_value` (patrimônio) | sim | sim | sim |
| `total_invested` (capital) | sim (soma RF) | **não** | **não** |
| `value_invested` (por posição) | sim (RF) | sim (CDB) | **não** |
| `value_net` (líquido) | sim | sim (fundos/CDB) | **não** |
| `value_gross` (bruto) | sim | sim | **não** |
| `yield_month_value` (rend. mês) | **não** | sim (fundos/prev) | **não** |
| `contracted_rate` (taxa) | sim | sim (CDB) | detectada do nome |
| `application_date` | sim (RF) | sim (CDB) | **não** |

## Bruto vs Líquido no cálculo de rendimento

O rendimento mensal e a variação patrimonial usam `total_value` (valor reportado pelo banco),
**não** o valor líquido (pós-IR). Isso é correto porque:

1. **IR só incide no resgate** — enquanto o investimento está aplicado, o patrimônio cresce sem dedução de IR
2. **Alíquota é regressiva** — o "líquido" de hoje será diferente amanhã mesmo sem variação de mercado (o tempo reduz a alíquota)
3. **O banco reporta o valor bruto** — é o dado oficial do extrato e a referência para acompanhamento

O **Valor Líquido (pós-IR)** no card é uma estimativa pontual ("se eu resgatasse tudo hoje, receberia X"). Não deve ser usado para calcular variação ou rendimento.

## Capital base (total_invested)

Para contas que não trazem `total_invested` do extrato (Itaú, C6):
- O **primeiro snapshot** da conta define o capital base: `total_invested = total_value`
- Snapshots seguintes herdam o `total_invested` anterior se não têm valor próprio
- Isso significa que o rendimento acumulado começa em 0% na data do primeiro snapshot

## Filtro de mês

O dashboard aceita filtro `?month=YYYY-MM`. Quando informado:
- Os cards (Patrimônio, Variação, Aporte) mostram dados daquele mês
- O overview usa o snapshot mais recente <= último dia do mês
- Histórico e gráficos continuam mostrando a série completa

## Pendências para melhorar a precisão

1. **C6 sem dados de posição detalhados**: O extrato C6 não traz valor investido, líquido, taxa, nem data de aplicação por produto. Apenas valor atual e rentabilidade %.
2. **Aportes para Itaú/C6**: Sem `total_invested` incremental, aportes novos após a data base não são rastreados. O rendimento pode ficar subestimado quando há aportes.
