"""Parser para PDF de Posição Consolidada da XP Investimentos.

Arquivo: XP_Investimentos historico_DD_MM_YYYY.pdf

Estrutura:
- Páginas 2-5: Renda Fixa (seções Prefixada, Pós-Fixada, Inflação)
- Páginas 6-9: Fundos de investimento (seções por classe)
- Página 10: Saldo projetado + PATRIMÔNIO TOTAL
- Páginas 11-12: Próximos Vencimentos (com taxas contratadas)
"""
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Any

from app.models.investment import AssetClassCode, RateIndex, RateType
from app.services.parsers.base import (
    ParsedPosition, ParsedSnapshot,
    parse_money, parse_pct, parse_date_br, normalize_name, detect_asset_class,
)
from app.services.parsers.rate_extractor import extract_rate


class XPPdfParser:
    """Parser para PDF de posição consolidada XP."""

    FILENAME_DATE_RE = re.compile(r"(\d{2})_(\d{2})_(\d{4})")

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)

    def parse(self) -> ParsedSnapshot:
        try:
            import pdfplumber
        except ImportError:
            raise RuntimeError("pdfplumber não instalado. pip install pdfplumber")

        snapshot_date = self._extract_date_from_filename()
        if not snapshot_date:
            raise ValueError(f"Não foi possível extrair data do nome do arquivo: {self.file_path.name}")

        positions: List[ParsedPosition] = []
        total_value = None
        available_balance = Decimal("0")
        # Tabela de taxas contratadas (nome -> rate info) extraída de Próximos Vencimentos
        rate_table: Dict[str, Dict[str, Any]] = {}

        with pdfplumber.open(self.file_path) as pdf:
            pages_text = []
            for page in pdf.pages:
                text = page.extract_text() or ""
                pages_text.append(text)

            for i, text in enumerate(pages_text):
                lines = text.split("\n")

                # Detectar PATRIMÔNIO TOTAL
                for line in lines:
                    if "PATRIM" in line and "TOTAL" in line:
                        m = re.search(r"R\$\s*([\d.,]+)", line)
                        if m:
                            total_value = parse_money(m.group(1))

                # Detectar saldo disponível
                for line in lines:
                    if "SALDO DISPON" in line:
                        m = re.search(r"R\$\s*([\d.,]+)", line)
                        if m:
                            available_balance = parse_money(m.group(1)) or Decimal("0")

                # Detectar seção de Renda Fixa
                if any("Renda Fixa" in l for l in lines[:7]):
                    self._parse_renda_fixa_pages(pages_text, positions)
                    break  # RF parsing handles all RF pages

            # Parse fundos pages
            for i, text in enumerate(pages_text):
                lines = text.split("\n")
                if any("Fundos de investimento" in l for l in lines[:7]):
                    self._parse_fundos_pages(pages_text[i:], positions)
                    break

            # Parse Próximos Vencimentos
            for i, text in enumerate(pages_text):
                if "XIMOS VENCIMENTOS" in text:
                    self._parse_proximos_vencimentos(pages_text[i:], rate_table)
                    break

        # Enriquecer posições com dados de taxas
        self._enrich_with_rates(positions, rate_table)

        # Calcular totais
        total_invested = sum(
            (p.get("value_invested") or Decimal("0")) for p in positions
        ) or None
        total_net = sum(
            (p.get("value_net") or p.get("value") or Decimal("0")) for p in positions
        ) or None

        if total_value is None:
            total_value = sum(p["value"] for p in positions)

        return ParsedSnapshot(
            snapshot_date=snapshot_date,
            total_value=total_value,
            total_invested=total_invested,
            available_balance=available_balance,
            total_net=total_net,
            positions=positions,
        )

    def _extract_date_from_filename(self) -> Optional[date]:
        """Extrai data do nome: historico_30_04_2026 ou _DD_MM_YYYY."""
        m = self.FILENAME_DATE_RE.search(self.file_path.name)
        if m:
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            try:
                return date(y, mo, d)
            except ValueError:
                return None
        return None

    def _parse_renda_fixa_pages(self, pages_text: List[str], positions: List[ParsedPosition]):
        """Extrai posições de Renda Fixa de todas as páginas relevantes."""
        current_class = None
        in_rf = False

        for text in pages_text:
            lines = text.split("\n")

            for idx, line in enumerate(lines):
                # Detectar início da seção RF
                if "Renda Fixa" in line and "%" in line and not in_rf:
                    in_rf = True
                    continue

                if not in_rf:
                    continue

                # Detectar fim da seção RF (início de Fundos)
                if "Fundos de investimento" in line:
                    return

                # Detectar subseção: "5.3% | Prefixada" ou "60.1% | Inflação"
                if "|" in line and "%" in line:
                    current_class = detect_asset_class(line)
                    if not current_class:
                        # Tentar pela label direta
                        label = line.split("|")[-1].strip().lower()
                        if "prefixa" in label:
                            current_class = AssetClassCode.PRE_FIXADO
                        elif "fixada" in label or "fixado" in label:
                            current_class = AssetClassCode.POS_FIXADO
                        elif "infla" in label:
                            current_class = AssetClassCode.INFLACAO
                    continue

                # Pular headers e linhas auxiliares
                if not current_class:
                    continue
                if "Ativo" in line and "Aplica" in line:
                    continue
                if "Compra" in line and "Judicial" in line:
                    continue
                if "Posi" in line and "Consolidada" in line:
                    continue
                if line.strip().isdigit():
                    continue

                # Extrair posição de RF
                # Padrão: nome com datas e valores R$
                # Linhas podem ser multi-line: nome + taxa em linhas separadas
                money_matches = re.findall(r"R\$\s*[\d.,]+", line)
                date_matches = re.findall(r"\d{2}/\d{2}/\d{4}", line)

                if money_matches and date_matches and len(date_matches) >= 2:
                    pos = self._parse_rf_line(line, lines, idx, current_class)
                    if pos:
                        positions.append(pos)

    def _parse_rf_line(self, line: str, all_lines: List[str], line_idx: int,
                       asset_class: AssetClassCode) -> Optional[ParsedPosition]:
        """Extrai uma posição de Renda Fixa de uma linha com dados."""
        # Encontrar o nome do ativo (pode estar na linha anterior ou no início desta)
        # Padrão: "DEB SABESP - JAN/2040 15/07/2025 15/01/2040 ..."
        # Ou split: linha anterior tem "DEB ENAUTA -" e esta tem os dados

        # Extrair datas
        dates = re.findall(r"(\d{2}/\d{2}/\d{4})", line)
        if len(dates) < 2:
            return None

        application_date = parse_date_br(dates[0])
        # Carência e vencimento podem ser iguais ou diferentes
        maturity_date = parse_date_br(dates[1])
        if len(dates) >= 3:
            maturity_date = parse_date_br(dates[2])

        # Extrair valores R$
        money_strs = re.findall(r"R\$\s*([\d.,]+)", line)
        if len(money_strs) < 2:
            return None

        value_invested = parse_money(money_strs[0])
        # Último valor = Valor Líquido
        value_net = parse_money(money_strs[-1])
        # Penúltimo = Posição (valor de mercado / na curva)
        value = parse_money(money_strs[-2]) if len(money_strs) >= 3 else value_net

        if not value or value == 0:
            return None

        # Extrair nome do ativo
        # O nome está antes da primeira data
        name_part = line[:line.find(dates[0])].strip()
        if not name_part or len(name_part) < 3:
            # Nome pode estar na linha anterior
            if line_idx > 0:
                prev = all_lines[line_idx - 1].strip()
                # Limpar mojibake do header
                if "Ativo" in prev or "Compra" in prev or "%" in prev:
                    prev = ""
                if prev and not prev.startswith("R$"):
                    name_part = prev
                    # Verificar se há continuação do nome 2 linhas acima
                    if line_idx > 1:
                        prev2 = all_lines[line_idx - 2].strip()
                        if prev2 and "|" not in prev2 and "Ativo" not in prev2 and not prev2.startswith("R$"):
                            # Pode ser taxa que ficou acima, não nome
                            pass

        if not name_part or len(name_part) < 3:
            return None

        # Limpar nome: remover sufixo "- MES/ANO" se muito curto
        name = name_part.strip().rstrip("-").strip()

        # Detectar taxa contratada na linha ou linhas adjacentes
        contracted_rate = None
        rate_index, rate_spread, rate_type = None, None, None

        # Taxa pode estar: na própria linha, na linha anterior, ou na linha seguinte
        for check_line in [line] + ([all_lines[line_idx - 1]] if line_idx > 0 else []) + ([all_lines[line_idx + 1]] if line_idx + 1 < len(all_lines) else []):
            # Padrão "IPC-A + 6,25%" ou "97,00% CDI" ou "CDI + 4,60%"
            rate_m = re.search(r"(IPC-?A\s*\+?\s*[\d,]+%|[\d,]+%\s*CDI|CDI\s*\+\s*[\d,]+%|\+\s*[\d,]+%|TR\b)", check_line)
            if rate_m:
                contracted_rate = rate_m.group(0).strip()
                # Normalizar IPC-A para IPCA
                cr = contracted_rate.replace("IPC-A", "IPCA").replace("IPC A", "IPCA")
                rate_index, rate_spread, rate_type = extract_rate(cr)
                break

        # Se a taxa está na linha seguinte (ex: "6,25%")
        if not contracted_rate and line_idx + 1 < len(all_lines):
            next_line = all_lines[line_idx + 1].strip()
            pct_m = re.match(r"^(\d{1,2},\d+%)$", next_line)
            if pct_m:
                # Verificar contexto da linha anterior para o índice
                prev_context = line
                if "IPC" in prev_context or "IPCA" in prev_context:
                    contracted_rate = f"IPCA + {pct_m.group(1)}"
                    rate_index, rate_spread, rate_type = extract_rate(contracted_rate)

        return ParsedPosition(
            name=name,
            name_normalized=normalize_name(name),
            asset_class=asset_class,
            value=value,
            value_invested=value_invested,
            value_net=value_net,
            value_gross=value,
            quantity=None,
            allocation_pct=None,
            yield_net_pct=None,
            yield_gross_pct=None,
            yield_value=None,
            yield_month_value=None,
            maturity_date=maturity_date,
            contracted_rate=contracted_rate,
            rate_index=rate_index,
            rate_spread=rate_spread,
            rate_type=rate_type,
            application_date=application_date,
        )

    def _parse_fundos_pages(self, pages_text: List[str], positions: List[ParsedPosition]):
        """Extrai posições de Fundos de todas as páginas relevantes."""
        current_class = None

        for text in pages_text:
            lines = text.split("\n")

            # Detectar se essa página tem fundos
            has_fundo_header = any("Ativo" in l and "Cota" in l for l in lines)
            if not has_fundo_header and not any("Fundos" in l for l in lines[:5]):
                # Verificar se é página de Saldo Projetado (fim dos fundos)
                if any("Saldo projetado" in l for l in lines):
                    return
                continue

            for idx, line in enumerate(lines):
                # Detectar seção: "14.4% | Fundos de Inflação" ou "Fundos de Renda Fixa Pós-Fixado"
                if "Fundos" in line:
                    if "|" in line:
                        current_class = detect_asset_class(line)
                    else:
                        line_lower = line.lower()
                        if "infla" in line_lower:
                            current_class = AssetClassCode.FII
                        elif "alternativ" in line_lower:
                            current_class = AssetClassCode.ALTERNATIVOS
                        elif "listado" in line_lower:
                            current_class = AssetClassCode.FII
                        elif "fixa" in line_lower and "fixado" in line_lower.split("fixa")[-1]:
                            current_class = AssetClassCode.POS_FIXADO
                        elif "fixa" in line_lower:
                            current_class = AssetClassCode.POS_FIXADO
                    continue

                # Pular headers
                if "Ativo" in line and "Cota" in line:
                    continue
                if "Posi" in line and "Consolidada" in line:
                    continue
                if "Saldo projetado" in line:
                    return
                if line.strip().isdigit():
                    continue

                if not current_class:
                    continue

                # Parse linha de fundo: "Nome 30/04/2026 1.234,56 100,00 R$ 0,00 R$ 50.000,00 R$ 50.000,00"
                pos = self._parse_fund_line(line, current_class)
                if pos:
                    positions.append(pos)

    def _parse_fund_line(self, line: str, asset_class: AssetClassCode) -> Optional[ParsedPosition]:
        """Extrai posição de fundo de uma linha."""
        # Padrão: nome data_cota valor_cota qtd_cotas R$ em_cotiz R$ posicao R$ liquido
        date_m = re.search(r"(\d{2}/\d{2}/\d{4})", line)
        if not date_m:
            return None

        name = line[:date_m.start()].strip()
        if not name or len(name) < 3:
            return None

        rest = line[date_m.end():].strip()

        # Extrair valores R$
        money_strs = re.findall(r"R\$\s*([\d.,]+)", rest)
        if len(money_strs) < 2:
            return None

        # Posição = penúltimo R$, Valor Líquido = último R$
        value = parse_money(money_strs[-2])
        value_net = parse_money(money_strs[-1])

        if not value or value == 0:
            # Tentar o último
            value = value_net
            if not value or value == 0:
                return None

        # Extrair qtd cotas (número entre a data e o primeiro R$)
        qty_part = rest[:rest.find("R$")].strip() if "R$" in rest else ""
        qty = None
        # Pode ter "valor_cota qtd_cotas"
        nums = re.findall(r"[\d.,]+", qty_part)
        if len(nums) >= 2:
            # Segundo número é qtd cotas
            try:
                qty = Decimal(nums[1].replace(",", ".").replace(".", "", nums[1].count(".") - 1) if "." in nums[1] and "," in nums[1] else nums[1].replace(",", "."))
            except Exception:
                pass

        return ParsedPosition(
            name=name,
            name_normalized=normalize_name(name),
            asset_class=asset_class,
            value=value,
            value_net=value_net,
            value_gross=value,
            value_invested=None,
            quantity=qty,
            allocation_pct=None,
            yield_net_pct=None,
            yield_gross_pct=None,
            yield_value=None,
            yield_month_value=None,
            maturity_date=None,
            contracted_rate=None,
            rate_index=None,
            rate_spread=None,
            rate_type=None,
            application_date=None,
        )

    def _parse_proximos_vencimentos(self, pages_text: List[str], rate_table: Dict[str, Dict]):
        """Extrai taxas contratadas da tabela Próximos Vencimentos."""
        for text in pages_text:
            if "XIMOS VENCIMENTOS" not in text:
                continue

            lines = text.split("\n")
            for line in lines:
                # Pular headers e footers
                if "tulo" in line and "Aplica" in line:
                    continue
                if "Posi" in line and "Consolidada" in line:
                    continue
                if line.strip().isdigit():
                    continue
                if "XIMOS VENCIMENTOS" in line:
                    continue
                if "POSI" in line and "CONSOLIDADA" in line:
                    continue

                # Padrão: "DEB FLU U LIGT11 13/12/2024 31/08/2027 R$ 5.641,86 0,00% TR 17.5 R$ 6.820,04"
                dates = re.findall(r"(\d{2}/\d{2}/\d{4})", line)
                if len(dates) < 2:
                    continue

                money_strs = re.findall(r"R\$\s*([\d.,]+)", line)
                if len(money_strs) < 1:
                    continue

                # Nome = tudo antes da primeira data
                name = line[:line.find(dates[0])].strip()
                if not name:
                    continue

                application_date = parse_date_br(dates[0])
                maturity_date = parse_date_br(dates[1])
                value_invested = parse_money(money_strs[0])
                value_net = parse_money(money_strs[-1]) if len(money_strs) >= 2 else None

                # Taxa contratada: entre o primeiro R$ e a taxa IR
                # Extrair do trecho entre invested e o próximo número/R$
                invest_end = line.find(money_strs[0]) + len(money_strs[0])
                rate_section = line[invest_end:].strip()

                # Buscar padrão de taxa
                contracted_rate = None
                rate_index, rate_spread, rate_type = None, None, None

                # Padrões: "IPC-A +7,70%", "97,00% CDI", "CDI +4,60%", "+13,97%", "0,00% TR"
                rate_m = re.search(
                    r"(IPC-?A\s*\+?\s*[\d,]+%|[\d,]+%\s*(?:CDI|TR)|CDI\s*\+\s*[\d,]+%|\+\s*[\d,]+%)",
                    rate_section
                )
                if rate_m:
                    contracted_rate = rate_m.group(0).strip()
                    cr = contracted_rate.replace("IPC-A", "IPCA")
                    rate_index, rate_spread, rate_type = extract_rate(cr)

                    # "+13,97%" sem índice → pré-fixado
                    if not rate_index and contracted_rate.startswith("+"):
                        pct = parse_pct(contracted_rate.replace("+", ""))
                        if pct:
                            rate_index = RateIndex.PRE
                            rate_spread = pct
                            rate_type = RateType.SPREAD

                name_norm = normalize_name(name)
                rate_table[name_norm] = {
                    "contracted_rate": contracted_rate,
                    "rate_index": rate_index,
                    "rate_spread": rate_spread,
                    "rate_type": rate_type,
                    "application_date": application_date,
                    "maturity_date": maturity_date,
                    "value_invested": value_invested,
                    "value_net": value_net,
                }

    def _enrich_with_rates(self, positions: List[ParsedPosition], rate_table: Dict[str, Dict]):
        """Enriquece posições com dados de taxas da tabela Próximos Vencimentos."""
        if not rate_table:
            return

        for pos in positions:
            name_norm = pos.get("name_normalized", "")
            # Tentar match direto
            match = rate_table.get(name_norm)

            # Se não achou, tentar match parcial (nome do ativo contém o título)
            if not match:
                for key, val in rate_table.items():
                    # Comparar primeiras palavras significativas
                    if key in name_norm or name_norm in key:
                        match = val
                        break
                    # Match por código: ex "LIGT11" em "DEB LIGHT - AGO/2027" vs "DEB FLU U LIGT11"
                    key_words = set(key.split())
                    name_words = set(name_norm.split())
                    overlap = key_words & name_words
                    if len(overlap) >= 2:
                        match = val
                        break

            if match:
                # Só atualizar se a posição não tem os dados
                if not pos.get("rate_index") and match.get("rate_index"):
                    pos["rate_index"] = match["rate_index"]
                    pos["rate_spread"] = match["rate_spread"]
                    pos["rate_type"] = match["rate_type"]
                if not pos.get("contracted_rate") and match.get("contracted_rate"):
                    pos["contracted_rate"] = match["contracted_rate"]
                if not pos.get("application_date") and match.get("application_date"):
                    pos["application_date"] = match["application_date"]
                if not pos.get("maturity_date") and match.get("maturity_date"):
                    pos["maturity_date"] = match["maturity_date"]
                if not pos.get("value_invested") and match.get("value_invested"):
                    pos["value_invested"] = match["value_invested"]
                # value_net da tabela de vencimentos pode ser mais preciso (com IR)
                if match.get("value_net") and not pos.get("value_net"):
                    pos["value_net"] = match["value_net"]
