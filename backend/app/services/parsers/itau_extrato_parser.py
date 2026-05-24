"""Parser para PDF Extrato Mensal do Itaú Personnalité.

Arquivo: Itaú_Extrato Mensal_MesAAAA.pdf

Estrutura:
- Página 1: Resumo com total investimentos
- Páginas 2-4: Conta corrente (ignorar)
- Páginas 5-7: Fundos de Investimento (saldo bruto/líquido, rendimento, cotas)
- Página 7: CDB e Renda Fixa (data aplic, vencto, aplicado, remuneração, bruto, líquido)
- Páginas 8-9: Previdência (plano, tipo, saldo anterior/atual, rendimento, cotas)
"""
import re
import calendar
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Any

from app.models.investment import AssetClassCode, RateIndex, RateType
from app.services.parsers.base import (
    ParsedPosition, ParsedSnapshot,
    parse_money, parse_pct, parse_date_br, normalize_name,
)
from app.services.parsers.rate_extractor import extract_rate

# Mapeamento de meses em português
MONTH_MAP = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "março": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9,
    "outubro": 10, "novembro": 11, "dezembro": 12,
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
}


class ItauExtratoMensalParser:
    """Parser para PDF Extrato Mensal do Itaú."""

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)

    def parse(self) -> ParsedSnapshot:
        try:
            import pdfplumber
        except ImportError:
            raise RuntimeError("pdfplumber não instalado. pip install pdfplumber")

        snapshot_date = self._extract_date_from_filename()
        if not snapshot_date:
            raise ValueError(f"Não foi possível extrair data do nome: {self.file_path.name}")

        positions: List[ParsedPosition] = []
        total_value = None
        total_gross = None
        total_net = None
        total_yield = Decimal("0")

        with pdfplumber.open(self.file_path) as pdf:
            pages_text = [p.extract_text() or "" for p in pdf.pages]

        # Página 1: total investimentos
        # Formato: "02. Investimentos" na linha N, "R$ 770.059,03" na linha N+1
        if pages_text:
            lines_p1 = pages_text[0].split("\n")
            for i, line in enumerate(lines_p1):
                if re.match(r"0[2-3]\.\s*Investimentos", line):
                    # Valor está na próxima linha
                    if i + 1 < len(lines_p1):
                        m = re.search(r"R\$\s*([\d.,]+)", lines_p1[i + 1])
                        if m:
                            total_value = parse_money(m.group(1))
                    break

        # Processar todas as páginas
        all_text = "\n".join(pages_text)

        # Fundos de Investimento
        fund_positions = self._parse_fundos(pages_text)
        positions.extend(fund_positions)

        # CDB e Renda Fixa
        cdb_positions = self._parse_cdb(pages_text)
        positions.extend(cdb_positions)

        # Previdência
        prev_positions = self._parse_previdencia(pages_text)
        positions.extend(prev_positions)

        # Calcular totais
        total_gross = sum(
            (p.get("value_gross") or p.get("value") or Decimal("0")) for p in positions
        ) or None
        total_net = sum(
            (p.get("value_net") or Decimal("0")) for p in positions
            if p.get("value_net")
        ) or None
        total_yield = sum(
            (p.get("yield_month_value") or Decimal("0")) for p in positions
        ) or None

        if not total_value:
            total_value = total_gross

        return ParsedSnapshot(
            snapshot_date=snapshot_date,
            total_value=total_value,
            total_invested=None,
            available_balance=Decimal("0"),
            total_gross=total_gross,
            total_net=total_net,
            yield_month_value=total_yield,
            positions=positions,
        )

    def _extract_date_from_filename(self) -> Optional[date]:
        """Extrato Mensal_Abril2026 -> date(2026, 4, 30)."""
        name = self.file_path.stem  # sem extensão
        # Padrão: Mes + Ano (ex: Abril2026, Marco2026)
        for month_name, month_num in MONTH_MAP.items():
            # Case insensitive, com ou sem acento
            pattern = re.compile(rf"{month_name}\s*(\d{{4}})", re.IGNORECASE)
            m = pattern.search(name)
            if m:
                year = int(m.group(1))
                last_day = calendar.monthrange(year, month_num)[1]
                return date(year, month_num, last_day)

        # Fallback: yyyy-mm
        m = re.search(r"(\d{4})-(\d{2})", name)
        if m:
            y, mo = int(m.group(1)), int(m.group(2))
            last_day = calendar.monthrange(y, mo)[1]
            return date(y, mo, last_day)

        return None

    def _parse_fundos(self, pages_text: List[str]) -> List[ParsedPosition]:
        """Extrai fundos de investimento."""
        positions = []
        in_fundos = False

        for text in pages_text:
            lines = text.split("\n")

            for idx, line in enumerate(lines):
                # Detectar início da seção de fundos
                if "Fundos de Investimento" in line and ("saldo bruto" in line or "saldo" in line.lower()):
                    in_fundos = True
                    continue

                # Detectar fim (CDB ou Previdência)
                if in_fundos and ("CDB" in line and "Renda Fixa" in line and "Estruturados" in line):
                    in_fundos = False
                    continue

                if not in_fundos:
                    continue

                # Detectar linha de fundo: "NOME_FUNDO saldo bruto 31/03/26 saldo bruto 30/04/26 saldo líquido"
                if "saldo bruto" in line.lower() and "CNPJ" not in line:
                    fund_name = line.split("saldo")[0].strip()
                    if not fund_name or len(fund_name) < 5:
                        continue

                    # Próxima linha tem CNPJ e valores
                    cnpj_line = lines[idx + 1] if idx + 1 < len(lines) else ""
                    if "CNPJ" not in cnpj_line:
                        continue

                    # Extrair valores R$ da linha CNPJ
                    money_strs = re.findall(r"R?\$?\s*([\d.,]+)", cnpj_line)
                    # Filtrar: pegar apenas valores que são dinheiro (> 1.00 com vírgula)
                    values = []
                    for ms in money_strs:
                        v = parse_money(ms)
                        if v is not None:
                            values.append(v)

                    if len(values) < 2:
                        continue

                    # values: [saldo_anterior, saldo_atual, saldo_liquido]
                    value_gross = values[-2] if len(values) >= 3 else values[-1]
                    value_net = values[-1] if len(values) >= 3 else None
                    value = value_gross

                    # Buscar rendimento bruto no mês
                    yield_month = None
                    yield_month_pct = None
                    for check_idx in range(idx + 2, min(idx + 20, len(lines))):
                        check_line = lines[check_idx]
                        if "RENDIMENTO BRUTO NO MES" in check_line:
                            nums = re.findall(r"(-?[\d.,]+)", check_line)
                            for n in nums:
                                v = parse_money(n)
                                if v is not None:
                                    yield_month = v
                                    break
                            break

                    # Buscar rentabilidade do mês (primeira % após "abr 2026")
                    for check_idx in range(idx + 2, min(idx + 12, len(lines))):
                        check_line = lines[check_idx]
                        if re.search(r"abr\s+2026|jan\s+2026|fev\s+2026|mar\s+2026", check_line, re.IGNORECASE):
                            pcts = re.findall(r"(-?\d+[,.]?\d+)%", check_line)
                            if pcts:
                                yield_month_pct = parse_pct(pcts[0] + "%")
                            break

                    # Buscar cotas
                    quantity = None
                    for check_idx in range(idx + 2, min(idx + 20, len(lines))):
                        check_line = lines[check_idx]
                        if "SALDO FINAL" in check_line:
                            # "30/04 SALDO FINAL 333.198,23 22,6653910 14.700,75053"
                            nums = re.findall(r"[\d.,]+", check_line)
                            if len(nums) >= 4:
                                try:
                                    quantity = Decimal(nums[-1].replace(",", ".").replace(".", "", nums[-1].count(".") - 1) if "." in nums[-1] and "," in nums[-1] else nums[-1].replace(",", "."))
                                except Exception:
                                    pass
                            break

                    # Classificar fundo
                    asset_class = self._classify_fund(fund_name)

                    positions.append(ParsedPosition(
                        name=fund_name,
                        name_normalized=normalize_name(fund_name),
                        asset_class=asset_class,
                        value=value,
                        value_invested=None,
                        value_gross=value_gross,
                        value_net=value_net,
                        quantity=quantity,
                        allocation_pct=None,
                        yield_net_pct=None,
                        yield_gross_pct=yield_month_pct,
                        yield_value=None,
                        yield_month_value=yield_month,
                        maturity_date=None,
                        contracted_rate=None,
                        rate_index=None,
                        rate_spread=None,
                        rate_type=None,
                        application_date=None,
                    ))

        return positions

    def _parse_cdb(self, pages_text: List[str]) -> List[ParsedPosition]:
        """Extrai CDB e Renda Fixa."""
        positions = []

        for text in pages_text:
            lines = text.split("\n")

            in_cdb = False
            for idx, line in enumerate(lines):
                # Detectar seção CDB
                if "CDB" in line and "Renda Fixa" in line and ("saldo bruto" in line.lower() or "Estruturados" in line):
                    in_cdb = True
                    continue

                if not in_cdb:
                    continue

                # Fim da seção
                if "Previd" in line or "Indicadores" in line or "total aplica" in line.lower():
                    break

                # Pular headers e totais
                if "produto" in line.lower() and "aplica" in line.lower():
                    continue
                if "CDB e Renda Fixa" in line and "produto" not in line.lower():
                    continue
                if line.strip().startswith("TOTAL") or line.strip().startswith("total"):
                    continue
                if "saldos" in line.lower() and "calculados" in line.lower():
                    break

                # Parse CDB: "CDB-DI 06/01/25 11/12/29 1.025,00 100,00% DI 1.223,23 1.188,54"
                dates = re.findall(r"(\d{2}/\d{2}/\d{2,4})", line)
                if len(dates) < 2:
                    continue

                # Nome = antes da primeira data
                name_part = line[:line.find(dates[0])].strip()
                if not name_part:
                    continue

                application_date = parse_date_br(dates[0])
                maturity_date = parse_date_br(dates[1])

                # Extrair valores numéricos após as datas
                after_dates = line[line.rfind(dates[1]) + len(dates[1]):].strip()
                nums = re.findall(r"[\d.,]+", after_dates)

                if len(nums) < 3:
                    continue

                value_invested = parse_money(nums[0])

                # Remuneração: "100,00% DI" ou "IPCA + 5%"
                # Está entre valor aplicado e saldo bruto
                rate_section = after_dates[after_dates.find(nums[0]) + len(nums[0]):].strip()
                # Pegar texto até o próximo número grande (saldo bruto)
                rate_text = ""
                contracted_rate = None
                rate_m = re.search(r"([\d,]+%\s*DI|[\d,]+%\s*CDI|IPCA\s*\+?\s*[\d,]+%|CDI\s*\+\s*[\d,]+%)", rate_section, re.IGNORECASE)
                if rate_m:
                    contracted_rate = rate_m.group(0).strip()

                rate_index, rate_spread, rate_type = extract_rate(contracted_rate or "")

                # Saldo bruto e líquido: últimos 2 números
                value_gross = parse_money(nums[-2])
                value_net = parse_money(nums[-1])
                value = value_gross or value_net

                if not value or value == 0:
                    continue

                # Calcular rendimento do mês (aproximado)
                yield_month = None
                if value_gross and value_invested:
                    # Não temos saldo anterior, skip

                    pass

                # Criar nome único incluindo data de aplicação
                name = name_part
                if application_date:
                    name = f"{name_part} {application_date.strftime('%d/%m/%y')}"

                positions.append(ParsedPosition(
                    name=name,
                    name_normalized=normalize_name(name),
                    asset_class=AssetClassCode.POS_FIXADO if rate_index == RateIndex.CDI else AssetClassCode.PRE_FIXADO if rate_index == RateIndex.PRE else AssetClassCode.RENDA_FIXA,
                    value=value,
                    value_invested=value_invested,
                    value_gross=value_gross,
                    value_net=value_net,
                    quantity=None,
                    allocation_pct=None,
                    yield_net_pct=None,
                    yield_gross_pct=None,
                    yield_value=None,
                    yield_month_value=yield_month,
                    maturity_date=maturity_date,
                    contracted_rate=contracted_rate,
                    rate_index=rate_index,
                    rate_spread=rate_spread,
                    rate_type=rate_type,
                    application_date=application_date,
                ))

        return positions

    def _parse_previdencia(self, pages_text: List[str]) -> List[ParsedPosition]:
        """Extrai planos de previdência."""
        positions = []
        in_prev = False

        for text in pages_text:
            lines = text.split("\n")

            for idx, line in enumerate(lines):
                # Detectar seção
                if "Previd" in line and "saldo bruto" in line.lower():
                    in_prev = True
                    continue

                if not in_prev:
                    continue

                # Fim da seção
                if "Indicadores de mercado" in line or "Cr" in line and "dito" in line:
                    in_prev = False
                    continue

                # Detectar plano: "Nome Do Plano saldo bruto 31/03/26 saldo bruto 30/04/26"
                if "saldo bruto" in line.lower() and ("Vgbl" in line or "Pgbl" in line or "Prev" in line):
                    plan_name = line.split("saldo")[0].strip()
                    if not plan_name or len(plan_name) < 5:
                        continue

                    # Próxima linha: CNPJ e valores
                    cnpj_line = lines[idx + 1] if idx + 1 < len(lines) else ""
                    money_strs = re.findall(r"R?\$?\s*([\d.,]+)", cnpj_line)
                    values = []
                    for ms in money_strs:
                        v = parse_money(ms)
                        if v is not None:
                            values.append(v)

                    if len(values) < 2:
                        continue

                    value = values[-1]  # saldo atual
                    value_gross = value

                    # Tipo VGBL/PGBL
                    plan_type = "VGBL" if "Vgbl" in plan_name or "VGBL" in plan_name else "PGBL"

                    # Buscar rendimento
                    yield_month = None
                    yield_month_pct = None
                    quantity = None

                    for check_idx in range(idx + 2, min(idx + 20, len(lines))):
                        check_line = lines[check_idx]

                        if "Rendimento R$" in check_line:
                            nums = re.findall(r"(-?[\d.,]+)", check_line)
                            for n in nums:
                                v = parse_money(n)
                                if v is not None:
                                    yield_month = v
                                    break

                        # Rentabilidade do mês
                        if re.search(r"abr\s+2026|jan\s+2026|fev\s+2026|mar\s+2026", check_line, re.IGNORECASE):
                            pcts = re.findall(r"(-?\d+[,.]?\d+)%", check_line)
                            if pcts:
                                yield_month_pct = parse_pct(pcts[0] + "%")

                        # Cotas
                        if "SaldoAtual" in check_line:
                            nums = re.findall(r"[\d.,]+", check_line)
                            if len(nums) >= 3:
                                try:
                                    quantity = Decimal(nums[-1].replace(",", "."))
                                except Exception:
                                    pass

                        # Próximo plano
                        if check_line.strip().startswith("Itau ") and "saldo bruto" in check_line:
                            break
                        if "Indicadores" in check_line:
                            break

                    # Se não encontrou rendimento explícito, calcular
                    if yield_month is None and len(values) >= 2:
                        yield_month = values[-1] - values[-2]  # atual - anterior

                    positions.append(ParsedPosition(
                        name=plan_name,
                        name_normalized=normalize_name(plan_name),
                        asset_class=AssetClassCode.PREVIDENCIA,
                        value=value,
                        value_invested=None,
                        value_gross=value_gross,
                        value_net=None,  # Previdência: tributação só no resgate
                        quantity=quantity,
                        allocation_pct=None,
                        yield_net_pct=None,
                        yield_gross_pct=yield_month_pct,
                        yield_value=None,
                        yield_month_value=yield_month,
                        maturity_date=None,
                        contracted_rate=None,
                        rate_index=None,
                        rate_spread=None,
                        rate_type=None,
                        application_date=None,
                    ))

        return positions

    def _classify_fund(self, name: str) -> AssetClassCode:
        """Classifica fundo pelo nome."""
        n = name.upper()
        if "BITCOIN" in n or "CRYPTO" in n or "CRIPTO" in n:
            return AssetClassCode.CRIPTO
        if "MORGAN STANLEY" in n or "ACOES" in n or "AÇÕES" in n or "EQUITY" in n:
            return AssetClassCode.RENDA_VARIAVEL
        if "INFRA" in n or "INFLAC" in n or "INFLAÇÃO" in n:
            return AssetClassCode.INFLACAO
        if "MULTIMERCADO" in n or "MM" in n.split() or "MULT" in n.split():
            return AssetClassCode.MULTIMERCADO
        if "DINAMICO" in n and "RF" in n:
            return AssetClassCode.POS_FIXADO
        if "RF" in n.split() or "RENDA FIXA" in n or "PRIVILEGE" in n or "CRED BANC" in n:
            return AssetClassCode.POS_FIXADO
        return AssetClassCode.MULTIMERCADO
