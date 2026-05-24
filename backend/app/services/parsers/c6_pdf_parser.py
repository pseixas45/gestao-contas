"""Parser para PDF de Relatório Mensal do C6 Bank.

Arquivo: c6 investimentos DDMM.pdf

Estrutura:
- Página 3: Rentabilidade mensal + CDI (texto)
- Página 4: Evolução da carteira + Posição por produto (tabela com 12 meses)
- Página 5: Produtos restantes + Rentabilidade por produto (tabela com 12 meses + acumulados)
"""
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Any

from app.models.investment import AssetClassCode, RateIndex, RateType
from app.services.parsers.base import (
    ParsedPosition, ParsedSnapshot,
    parse_money, parse_pct, normalize_name,
)

# Mapeamento mês abreviado -> número
MONTH_ABBR = {
    "JAN": 1, "FEV": 2, "MAR": 3, "ABR": 4, "MAI": 5, "JUN": 6,
    "JUL": 7, "AGO": 8, "SET": 9, "OUT": 10, "NOV": 11, "DEZ": 12,
}


class C6PdfParser:
    """Parser para PDF de relatório mensal C6."""

    FILENAME_DATE_RE = re.compile(r"(\d{2})(\d{2})", re.IGNORECASE)

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)

    def parse(self) -> ParsedSnapshot:
        try:
            import pdfplumber
        except ImportError:
            raise RuntimeError("pdfplumber não instalado. pip install pdfplumber")

        snapshot_date = self._extract_date_from_filename()
        positions: List[ParsedPosition] = []
        total_value = None
        yield_month_pct_total = None

        # Tabela de rentabilidade por produto: nome -> {month_pct, acum_periodo, acum_ano}
        rent_table: Dict[str, Dict[str, Any]] = {}

        with pdfplumber.open(self.file_path) as pdf:
            pages_text = [p.extract_text() or "" for p in pdf.pages]

            # Extrair patrimônio final
            for text in pages_text:
                m = re.search(r"Patrim[^:]*:\s*R\$\s*([\d.,]+)", text)
                if m:
                    total_value = parse_money(m.group(1))
                    break

            # Extrair data do snapshot dos headers de mês (último mês na tabela)
            # Se não extraiu do filename, usar a data do relatório
            if not snapshot_date:
                for text in pages_text:
                    m = re.search(r"(\d{2}/\d{2}/\d{4})", text[:200])
                    if m:
                        from app.services.parsers.base import parse_date_br
                        snapshot_date = parse_date_br(m.group(1))
                        break

            if not snapshot_date:
                raise ValueError(f"Não foi possível extrair data do arquivo: {self.file_path.name}")

            # Parse tabelas de posição e rentabilidade
            for page in pdf.pages:
                tables = page.extract_tables() or []
                for tbl in tables:
                    if not tbl or len(tbl) < 2:
                        continue
                    header = tbl[0]

                    # Detectar tabela de posição (headers são meses: MAI/25, JUN/25, ...)
                    if self._is_position_table(header, tbl):
                        self._parse_position_table(tbl, positions)

                    # Detectar tabela de rentabilidade (tem coluna ACUMULADO)
                    elif self._is_rent_table(header):
                        self._parse_rent_table(tbl, rent_table)

        # Enriquecer posições com rentabilidade
        for pos in positions:
            name_norm = pos.get("name_normalized", "")
            if name_norm in rent_table:
                data = rent_table[name_norm]
                if data.get("month_pct") is not None:
                    pos["yield_gross_pct"] = data["month_pct"]

        # Calcular allocation_pct
        if total_value and total_value > 0:
            for pos in positions:
                pos["allocation_pct"] = (pos["value"] / total_value * 100).quantize(Decimal("0.01"))

        return ParsedSnapshot(
            snapshot_date=snapshot_date,
            total_value=total_value or sum(p["value"] for p in positions),
            total_invested=None,
            available_balance=Decimal("0"),
            positions=positions,
        )

    def _extract_date_from_filename(self) -> Optional[date]:
        """c6 investimentos 2604.pdf -> date(2026, 4, 30)."""
        name = self.file_path.stem.lower()

        # Padrão: C6-DD-MM-YYYY → usar último dia do mês (snapshot mensal)
        m = re.search(r"(\d{2})[-_](\d{2})[-_](\d{4})", name)
        if m:
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            import calendar
            last_day = calendar.monthrange(y, mo)[1]
            try:
                return date(y, mo, last_day)
            except ValueError:
                return None

        # Padrão: DDMM (ex: "2604" = dia 26, mês 04 de 2026)
        # Mas na verdade "2604" = ref. abril 2026 → último dia de abril
        m = re.search(r"(\d{2})(\d{2})", name)
        if m:
            century = int(m.group(1))
            month = int(m.group(2))
            if 1 <= month <= 12:
                year = 2000 + century
                import calendar
                last_day = calendar.monthrange(year, month)[1]
                try:
                    return date(year, month, last_day)
                except ValueError:
                    return None

        return None

    def _is_position_table(self, header: List, tbl: List[List]) -> bool:
        """Verifica se é tabela de posição (colunas são meses, dados tem R$)."""
        if not header or len(header) < 5:
            return False
        # Não pode ter coluna ACUMULADO (é tabela de rentabilidade)
        header_text = " ".join(str(c or "") for c in header).upper()
        if "ACUMULADO" in header_text:
            return False
        month_count = 0
        for cell in header:
            if cell and re.match(r"[A-Z]{3}/\d{2}", str(cell).strip().upper()):
                month_count += 1
        if month_count < 6:
            return False
        # Verificar que dados contêm R$ (não %)
        if len(tbl) > 1:
            sample = str(tbl[1][-1] or "")
            if "R$" in sample or re.search(r"\d+\.\d{3}", sample):
                return True
            # Se contém apenas % → é tabela de rentabilidade
            if "%" in sample and "R$" not in sample:
                return False
        return True

    def _is_rent_table(self, header: List) -> bool:
        """Verifica se é tabela de rentabilidade (tem ACUMULADO)."""
        if not header:
            return False
        header_text = " ".join(str(c or "") for c in header).upper()
        return "ACUMULADO" in header_text and "PER" in header_text

    def _parse_position_table(self, tbl: List[List], positions: List[ParsedPosition]):
        """Extrai posições da tabela de posição por produto."""
        header = tbl[0]

        # Encontrar índice da última coluna de mês
        last_month_idx = None
        for idx in range(len(header) - 1, -1, -1):
            cell = str(header[idx] or "").strip().upper()
            if re.match(r"[A-Z]{3}/\d{2}", cell):
                last_month_idx = idx
                break

        if last_month_idx is None:
            return

        for row in tbl[1:]:
            if not row or len(row) <= last_month_idx:
                continue

            name = self._clean_name(row[0])
            if not name:
                continue

            # Pular linhas de total e subtotal
            name_lower = name.lower()
            if name_lower in ("total", "renda fixa", "renda variavel", "renda variável", "total geral"):
                continue

            # Extrair valor da última coluna de mês
            cell = str(row[last_month_idx] or "").strip()
            if not cell or cell == "-":
                continue

            # Extrair R$ e % do cell (formato "R$ 54.154,06\n(34,37%)")
            m_val = re.search(r"R?\$?\s*([\d.][\d.,]*)", cell)
            if not m_val:
                continue
            value = parse_money(m_val.group(1))
            if not value or value <= 0:
                continue

            # Extrair allocation_pct do cell
            m_pct = re.search(r"\(([\d,]+)%\)", cell)
            alloc = parse_pct(m_pct.group(1) + "%") if m_pct else None

            # Classificar ativo
            asset_class = self._classify_product(name)

            # Detectar taxa do nome
            rate_index, rate_spread, rate_type = self._detect_rate_from_name(name)

            positions.append(ParsedPosition(
                name=name,
                name_normalized=normalize_name(name),
                asset_class=asset_class,
                value=value,
                value_invested=None,
                value_gross=None,
                value_net=None,
                quantity=None,
                allocation_pct=alloc,
                yield_net_pct=None,
                yield_gross_pct=None,
                yield_value=None,
                yield_month_value=None,
                maturity_date=None,
                contracted_rate=None,
                rate_index=rate_index,
                rate_spread=rate_spread,
                rate_type=rate_type,
                application_date=None,
            ))

    def _parse_rent_table(self, tbl: List[List], rent_table: Dict[str, Dict]):
        """Extrai rentabilidade por produto."""
        header = tbl[0]

        # Encontrar última coluna de mês (antes de ACUMULADO)
        last_month_idx = None
        for idx in range(len(header) - 1, -1, -1):
            cell = str(header[idx] or "").strip().upper()
            if re.match(r"[A-Z]{3}/\d{2}", cell):
                last_month_idx = idx
                break

        # Encontrar colunas de acumulado
        acum_periodo_idx = None
        acum_ano_idx = None
        for idx, cell in enumerate(header):
            cell_str = str(cell or "").upper()
            if "ACUMULADO" in cell_str:
                if "PER" in cell_str:
                    acum_periodo_idx = idx
                elif "ANO" in cell_str:
                    acum_ano_idx = idx

        for row in tbl[1:]:
            if not row:
                continue

            name = self._clean_name(row[0])
            if not name:
                continue

            name_lower = name.lower()
            if name_lower in ("total", "cdi", "ibovespa"):
                continue

            name_norm = normalize_name(name)

            # Rentabilidade do mês
            month_pct = None
            if last_month_idx and last_month_idx < len(row):
                month_pct = parse_pct(row[last_month_idx])

            rent_table[name_norm] = {
                "month_pct": month_pct,
            }

    def _clean_name(self, cell: Any) -> str:
        """Limpa nome de produto (remove \n e espaços extras)."""
        if not cell:
            return ""
        name = str(cell).replace("\n", " ")
        name = re.sub(r"\s+", " ", name).strip()
        # Tratar mojibake
        try:
            name = name.encode("latin-1").decode("utf-8")
        except (UnicodeDecodeError, UnicodeEncodeError):
            pass
        return name

    def _classify_product(self, name: str) -> AssetClassCode:
        """Classifica produto C6 pelo nome."""
        n = name.upper()
        # Tratar mojibake
        try:
            n = n.encode("latin-1").decode("utf-8").upper()
        except (UnicodeDecodeError, UnicodeEncodeError):
            pass
        if "IPCA" in n:
            return AssetClassCode.INFLACAO
        if "PREFIXAD" in n:
            return AssetClassCode.PRE_FIXADO
        if "LCA" in n or "LCI" in n:
            return AssetClassCode.RENDA_FIXA
        if "FIXAD" in n and ("POS" in n or "PÓS" in n or "P\xd3S" in n):
            return AssetClassCode.POS_FIXADO
        if "COMODIDADE" in n:
            return AssetClassCode.POS_FIXADO
        return AssetClassCode.RENDA_FIXA

    def _detect_rate_from_name(self, name: str) -> tuple:
        """Detecta taxa do nome do produto C6."""
        n = name.upper()
        if "IPCA" in n and "POS" in n.replace("Ó", "O").replace("ó", "o"):
            return RateIndex.IPCA, None, RateType.SPREAD
        if "PREFIXAD" in n:
            return RateIndex.PRE, None, RateType.SPREAD
        if "POS" in n.replace("Ó", "O").replace("ó", "o") and "FIXAD" in n:
            return RateIndex.CDI, Decimal("100"), RateType.PERCENTAGE
        if "COMODIDADE" in n:
            return RateIndex.CDI, Decimal("100"), RateType.PERCENTAGE
        return None, None, None
