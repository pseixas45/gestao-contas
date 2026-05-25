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
        """Parse retornando apenas o último mês (compatibilidade)."""
        snapshots = self.parse_all_months()
        if not snapshots:
            raise ValueError(f"Nenhum snapshot extraído de {self.file_path.name}")
        return snapshots[-1]

    def parse_all_months(self) -> List[ParsedSnapshot]:
        """Parse retornando snapshots de todos os meses presentes no PDF."""
        try:
            import pdfplumber
        except ImportError:
            raise RuntimeError("pdfplumber não instalado. pip install pdfplumber")

        import calendar

        # positions_by_month: {date -> [positions]}
        positions_by_month: Dict[date, List[ParsedPosition]] = {}
        # totals_by_month: {date -> Decimal} (da linha Renda Fixa / Total)
        totals_by_month: Dict[date, Decimal] = {}
        # rent_by_month: {date -> {name_norm -> {month_pct}}}
        rent_by_month: Dict[date, Dict[str, Dict[str, Any]]] = {}

        with pdfplumber.open(self.file_path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables() or []
                for tbl in tables:
                    if not tbl or len(tbl) < 2:
                        continue
                    header = tbl[0]

                    if self._is_position_table(header, tbl):
                        self._parse_position_table_all_months(tbl, positions_by_month, totals_by_month)
                    elif self._is_rent_table(header):
                        self._parse_rent_table_all_months(tbl, rent_by_month)

        # Montar snapshots por mês
        snapshots: List[ParsedSnapshot] = []
        for snap_date in sorted(positions_by_month.keys()):
            positions = positions_by_month[snap_date]
            if not positions:
                continue

            # Usar total da linha "Renda Fixa" se disponível, senão somar posições
            total_value = totals_by_month.get(snap_date) or sum(p["value"] for p in positions)

            # Enriquecer com rentabilidade
            rent_table = rent_by_month.get(snap_date, {})
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

            snapshots.append(ParsedSnapshot(
                snapshot_date=snap_date,
                total_value=total_value,
                total_invested=None,
                available_balance=Decimal("0"),
                positions=positions,
            ))

        return snapshots

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
        """Extrai posições da tabela de posição por produto (último mês apenas)."""
        positions_by_month: Dict[date, List[ParsedPosition]] = {}
        self._parse_position_table_all_months(tbl, positions_by_month)
        if positions_by_month:
            last_date = max(positions_by_month.keys())
            positions.extend(positions_by_month[last_date])

    def _parse_position_table_all_months(self, tbl: List[List], positions_by_month: Dict[date, List[ParsedPosition]], totals_by_month: Optional[Dict[date, Decimal]] = None):
        """Extrai posições de TODOS os meses da tabela."""
        import calendar
        header = tbl[0]

        # Mapear índices de coluna -> data do snapshot
        month_columns: List[tuple] = []  # (idx, date)
        for idx, cell in enumerate(header):
            cell_str = str(cell or "").strip().upper()
            m = re.match(r"([A-Z]{3})/(\d{2})", cell_str)
            if m:
                month_num = MONTH_ABBR.get(m.group(1))
                year = 2000 + int(m.group(2))
                if month_num:
                    last_day = calendar.monthrange(year, month_num)[1]
                    snap_date = date(year, month_num, last_day)
                    month_columns.append((idx, snap_date))

        if not month_columns:
            return

        for row in tbl[1:]:
            if not row:
                continue

            name = self._clean_name(row[0])
            if not name:
                continue

            name_lower = name.lower()
            # Capturar totais da linha de subtotal (Renda Fixa, Total, etc.)
            if name_lower in ("total", "renda fixa", "renda variavel", "renda variável", "total geral"):
                if totals_by_month is not None:
                    for col_idx, snap_date in month_columns:
                        if col_idx >= len(row):
                            continue
                        cell = str(row[col_idx] or "").strip()
                        m_val = re.search(r"R?\$?\s*([\d.][\d.,]*)", cell)
                        if m_val:
                            val = parse_money(m_val.group(1))
                            if val and val > 0:
                                # Usar o maior total encontrado (ex: "Renda Fixa" inclui tudo)
                                if snap_date not in totals_by_month or val > totals_by_month[snap_date]:
                                    totals_by_month[snap_date] = val
                continue

            asset_class = self._classify_product(name)
            rate_index, rate_spread, rate_type = self._detect_rate_from_name(name)

            for col_idx, snap_date in month_columns:
                if col_idx >= len(row):
                    continue
                cell = str(row[col_idx] or "").strip()
                if not cell or cell == "-":
                    continue

                m_val = re.search(r"R?\$?\s*([\d.][\d.,]*)", cell)
                if not m_val:
                    continue
                value = parse_money(m_val.group(1))
                if not value or value <= 0:
                    continue

                m_pct = re.search(r"\(([\d,]+)%\)", cell)
                alloc = parse_pct(m_pct.group(1) + "%") if m_pct else None

                if snap_date not in positions_by_month:
                    positions_by_month[snap_date] = []

                positions_by_month[snap_date].append(ParsedPosition(
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
        """Extrai rentabilidade por produto (último mês apenas, compatibilidade)."""
        rent_by_month: Dict[date, Dict[str, Dict[str, Any]]] = {}
        self._parse_rent_table_all_months(tbl, rent_by_month)
        if rent_by_month:
            last_date = max(rent_by_month.keys())
            rent_table.update(rent_by_month[last_date])

    def _parse_rent_table_all_months(self, tbl: List[List], rent_by_month: Dict[date, Dict[str, Dict[str, Any]]]):
        """Extrai rentabilidade de TODOS os meses."""
        import calendar
        header = tbl[0]

        # Mapear colunas de meses
        month_columns: List[tuple] = []  # (idx, date)
        for idx, cell in enumerate(header):
            cell_str = str(cell or "").strip().upper()
            m = re.match(r"([A-Z]{3})/(\d{2})", cell_str)
            if m:
                month_num = MONTH_ABBR.get(m.group(1))
                year = 2000 + int(m.group(2))
                if month_num:
                    last_day = calendar.monthrange(year, month_num)[1]
                    snap_date = date(year, month_num, last_day)
                    month_columns.append((idx, snap_date))

        if not month_columns:
            return

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

            for col_idx, snap_date in month_columns:
                if col_idx >= len(row):
                    continue
                month_pct = parse_pct(row[col_idx])
                if month_pct is not None:
                    if snap_date not in rent_by_month:
                        rent_by_month[snap_date] = {}
                    rent_by_month[snap_date][name_norm] = {"month_pct": month_pct}

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
