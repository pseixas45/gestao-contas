"""Serviço de importação de extratos de investimentos.

Suporta:
- XP: PosicaoDetalhadaHistorica_dd_mm_aaaa.xlsx
- Itaú: ITAU EXTRATO-CARTEIRA-aaaa-mm.pdf
- C6: TBD
"""
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import List, Optional, Tuple, Dict, Any
from pathlib import Path

import openpyxl
from sqlalchemy.orm import Session

from app.models import (
    BankAccount, AssetClass, AssetClassCode, Asset,
    InvestmentSnapshot, InvestmentPosition, ImportBatch,
)
from app.models.import_batch import ImportStatus, FileType


# ============================================================
# Helpers
# ============================================================

def _parse_money(value: Any) -> Optional[Decimal]:
    """'R$ 154.250,73' → Decimal('154250.73'). Aceita também float/int."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    s = str(value).strip()
    if not s:
        return None
    # Remover prefixos R$, espaços, etc
    s = s.replace("R$", "").replace("R\\$", "").strip()
    # Detectar formato BR (1.234,56) vs US (1,234.56)
    if "," in s and "." in s:
        # Última separadora vence
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _parse_pct(value: Any) -> Optional[Decimal]:
    """'9,18%' → Decimal('9.18'). '0%' → 0."""
    if value is None or value == "":
        return None
    s = str(value).strip().replace("%", "").strip()
    if not s:
        return None
    s = s.replace(",", ".")
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _parse_date_br(value: Any) -> Optional[date]:
    """'31/12/2025' → date(2025,12,31). Aceita objeto date também."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _normalize_name(name: str) -> str:
    """Normaliza nome de ativo para matching entre snapshots."""
    if not name:
        return ""
    s = str(name).strip().upper()
    # Remover múltiplos espaços
    s = re.sub(r"\s+", " ", s)
    # Tratar mojibake comum (latin-1 → utf-8)
    try:
        s = s.encode("latin-1").decode("utf-8").upper()
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass
    return s


# Map de subcategoria XP → AssetClassCode
SUBCATEGORY_MAP = {
    "alternativos": AssetClassCode.ALTERNATIVOS,
    "inflacao": AssetClassCode.INFLACAO,
    "inflação": AssetClassCode.INFLACAO,
    "pre-fixado": AssetClassCode.PRE_FIXADO,
    "prefixado": AssetClassCode.PRE_FIXADO,
    "pré-fixado": AssetClassCode.PRE_FIXADO,
    "pos-fixado": AssetClassCode.POS_FIXADO,
    "pós-fixado": AssetClassCode.POS_FIXADO,
    "fundos listados": AssetClassCode.FII,
    "fii": AssetClassCode.FII,
    "fundos imobiliarios": AssetClassCode.FII,
    "renda variavel": AssetClassCode.RENDA_VARIAVEL,
    "renda variável": AssetClassCode.RENDA_VARIAVEL,
    "acoes": AssetClassCode.RENDA_VARIAVEL,
    "ações": AssetClassCode.RENDA_VARIAVEL,
    "multimercado": AssetClassCode.MULTIMERCADO,
    "cripto": AssetClassCode.CRIPTO,
    "crypto": AssetClassCode.CRIPTO,
    "cambial": AssetClassCode.CAMBIAL,
    "previdencia": AssetClassCode.PREVIDENCIA,
    "previdência": AssetClassCode.PREVIDENCIA,
    "vgbl": AssetClassCode.PREVIDENCIA,
    "pgbl": AssetClassCode.PREVIDENCIA,
}


def _detect_subcategory_class(label: str) -> Optional[AssetClassCode]:
    """Mapeia 'X% | Subcategoria' para AssetClassCode."""
    if not label:
        return None
    # Tentar fix mojibake
    try:
        label = label.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass
    s = str(label).lower().strip()
    # Padrão "X% | Subcategoria"
    parts = s.split("|")
    if len(parts) > 1:
        s = parts[-1].strip()
    # Remover acentos (proxy simples)
    for k, v in SUBCATEGORY_MAP.items():
        if k in s:
            return v
    return None


# ============================================================
# XP Position Parser
# ============================================================

class XPPositionParser:
    """Parser para PosicaoDetalhadaHistorica_dd_mm_aaaa.xlsx (XP)."""

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)

    def parse(self) -> Dict[str, Any]:
        """Retorna dict com:
        - snapshot_date: date
        - total_value: Decimal
        - total_invested: Decimal
        - available_balance: Decimal
        - positions: List[dict] com {name, asset_class_code, value, value_invested, ...}
        """
        wb = openpyxl.load_workbook(self.file_path, read_only=True, data_only=True)
        sh = wb.active

        rows = list(sh.iter_rows(values_only=True))

        # 1. Detectar data — primeiro do nome do arquivo, fallback do header
        snapshot_date = self._extract_date_from_filename()
        if not snapshot_date and rows:
            # Linha 0 tem "Data da Posição Histórica: 31/12/2025"
            for row in rows[:5]:
                for cell in row:
                    if cell and "Posi" in str(cell) and "Hist" in str(cell):
                        m = re.search(r"(\d{2}/\d{2}/\d{4})", str(cell))
                        if m:
                            snapshot_date = _parse_date_br(m.group(1))
                            break

        if not snapshot_date:
            raise ValueError(f"Não foi possível detectar a data do snapshot em {self.file_path.name}")

        # 2. Extrair totais — linha 3 geralmente
        total_value = None
        total_invested = None
        available_balance = None

        for i in range(min(10, len(rows))):
            row = rows[i]
            if not row:
                continue
            # Linha de totais: 4 valores R$ consecutivos no início
            if row[0] and "R$" in str(row[0]):
                values = []
                for c in row[:5]:
                    v = _parse_money(c)
                    if v is not None:
                        values.append(v)
                if len(values) >= 3:
                    total_value = values[0]
                    total_invested = values[1]
                    available_balance = values[2]
                    break

        # 3. Extrair posições — iterar linhas
        positions = []
        current_class = None
        # Diferentes layouts de colunas (depende da subcategoria)
        # Layout fundos:    [name, value, alloc%, yield_net%, yield_gross%, value_invested, value_net]
        # Layout renda fixa:[name, value, alloc%, value_invested, value_orig, rate, date_app, maturity, qty, unit_price, ir, iof, value_net]
        current_layout = None  # 'fund' ou 'rf'

        for i, row in enumerate(rows):
            if not row or all(c is None or str(c).strip() == "" for c in row):
                continue

            first_cell = row[0]
            if not first_cell:
                continue
            first_str = str(first_cell).strip()

            # Detectar subcategoria "X% | Nome"
            if "|" in first_str and "%" in first_str:
                detected_class = _detect_subcategory_class(first_str)
                if detected_class:
                    current_class = detected_class
                    # Detectar layout pelo cabeçalho da subcategoria
                    headers = [str(c).lower() if c else "" for c in row[1:8]]
                    # 'posição a mercado' (renda fixa) vs 'posição' (fundos)
                    if any("mercado" in h for h in headers):
                        current_layout = "rf"
                    else:
                        current_layout = "fund"
                continue

            # Pular linha de seção pai (ex: "Fundos de Investimentos" + valor)
            # Detectar: nome curto sem '|' e com valor R$ na col 6
            if (
                first_str
                and "|" not in first_str
                and len(first_str) < 60
                and (row[6] if len(row) > 6 else None)
                and (not row[1] or not str(row[1]).startswith("R$"))
            ):
                # Provavelmente cabeçalho de seção pai
                continue

            # Tentar extrair posição
            if current_class and current_layout:
                pos = self._parse_position_row(row, current_class, current_layout)
                if pos:
                    positions.append(pos)

        return {
            "snapshot_date": snapshot_date,
            "total_value": total_value,
            "total_invested": total_invested,
            "available_balance": available_balance or Decimal("0"),
            "positions": positions,
        }

    def _extract_date_from_filename(self) -> Optional[date]:
        """PosicaoDetalhadaHistorica_31_12_2025 → date(2025,12,31)."""
        m = re.search(r"_(\d{2})_(\d{2})_(\d{4})", self.file_path.name)
        if m:
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            try:
                return date(y, mo, d)
            except ValueError:
                return None
        return None

    def _parse_position_row(
        self,
        row: tuple,
        asset_class: AssetClassCode,
        layout: str,
    ) -> Optional[Dict[str, Any]]:
        """Extrai uma posição de uma linha. Retorna None se não for válida."""
        if not row or not row[0]:
            return None

        name = str(row[0]).strip()
        if not name or name.startswith("R$") or "|" in name:
            return None

        # Extrair valores comuns (col B = valor, col C = % alocação)
        value = _parse_money(row[1] if len(row) > 1 else None)
        if value is None or value == 0:
            return None

        allocation_pct = _parse_pct(row[2] if len(row) > 2 else None)

        if layout == "fund":
            yield_net = _parse_pct(row[3] if len(row) > 3 else None)
            yield_gross = _parse_pct(row[4] if len(row) > 4 else None)
            value_invested = _parse_money(row[5] if len(row) > 5 else None)
            return {
                "name": name,
                "name_normalized": _normalize_name(name),
                "asset_class": asset_class,
                "value": value,
                "value_invested": value_invested,
                "allocation_pct": allocation_pct,
                "yield_net_pct": yield_net,
                "yield_gross_pct": yield_gross,
                "yield_value": None,
                "quantity": None,
                "maturity_date": None,
                "contracted_rate": None,
            }
        else:  # rf (renda fixa)
            value_invested = _parse_money(row[3] if len(row) > 3 else None)
            contracted_rate = str(row[5]).strip() if len(row) > 5 and row[5] else None
            maturity_date = _parse_date_br(row[7] if len(row) > 7 else None)
            quantity = None
            try:
                if len(row) > 8 and row[8] is not None:
                    quantity = Decimal(str(row[8]).replace(",", "."))
            except (InvalidOperation, ValueError):
                pass
            return {
                "name": name,
                "name_normalized": _normalize_name(name),
                "asset_class": asset_class,
                "value": value,
                "value_invested": value_invested,
                "allocation_pct": allocation_pct,
                "yield_net_pct": None,
                "yield_gross_pct": None,
                "yield_value": None,
                "quantity": quantity,
                "maturity_date": maturity_date,
                "contracted_rate": contracted_rate,
            }


# ============================================================
# Itaú PDF Parser
# ============================================================

# Mapa de seção Itaú → AssetClassCode (na carteira detalhada)
ITAU_SECTION_MAP = {
    "juros pos-fixados": AssetClassCode.POS_FIXADO,
    "juros pós-fixados": AssetClassCode.POS_FIXADO,
    "juros prefixados": AssetClassCode.PRE_FIXADO,
    "juros pre-fixados": AssetClassCode.PRE_FIXADO,
    "inflacao": AssetClassCode.INFLACAO,
    "inflação": AssetClassCode.INFLACAO,
    "multimercados": AssetClassCode.MULTIMERCADO,
    "multimercado": AssetClassCode.MULTIMERCADO,
    "acoes": AssetClassCode.RENDA_VARIAVEL,
    "ações": AssetClassCode.RENDA_VARIAVEL,
    "cambial": AssetClassCode.CAMBIAL,
    "fii": AssetClassCode.FII,
    "fundos imobiliarios": AssetClassCode.FII,
    "previdencia": AssetClassCode.PREVIDENCIA,
    "previdência": AssetClassCode.PREVIDENCIA,
}


def _normalize_section_name(label: str) -> str:
    """Normaliza nome de seção para mapping (lowercase, sem mojibake)."""
    if not label:
        return ""
    s = str(label).strip().lower()
    try:
        s = s.encode("latin-1").decode("utf-8").lower()
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass
    return s


class ItauCarteiraParser:
    """Parser para ITAU EXTRATO-CARTEIRA-aaaa-mm.pdf (Itaú Personnalité)."""

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)

    def parse(self) -> Dict[str, Any]:
        try:
            import pdfplumber
        except ImportError:
            raise RuntimeError("pdfplumber não instalado. pip install pdfplumber")

        with pdfplumber.open(self.file_path) as pdf:
            pages_text = [p.extract_text() or "" for p in pdf.pages]

        # 1. Detectar data do snapshot — fim do mês indicado no nome do arquivo
        snapshot_date = self._extract_date_from_filename()

        # 2. Extrair totais da página 2
        # PDFs do Itaú vêm como (espaço opcional, sem acento garantido):
        #   "saldobruto 755.113,90 753.149,51 +entradas 0,00"
        #   "saldolíquido 751.667,18 749.029,75 -saídas 2.020,63"
        # Os 2 primeiros números são mês ANTERIOR e mês ATUAL.
        # Após eles vêm "+entradas/-saídas" que NÃO devem ser confundidos.
        total_value = None
        net_value = None
        if len(pages_text) > 1:
            page2 = pages_text[1]
            for line in page2.split("\n"):
                line_norm = line.lower().replace(" ", "")
                # Pegar todos os números da linha
                nums = re.findall(r"[\d.]+,\d{2}", line)
                # Se a linha tem 4 números (mes_ant, mes_atual, outro_label, outro_num),
                # o saldo do mês atual é o SEGUNDO. Se tem 2, pega o último.
                def pick(nums_list):
                    if not nums_list:
                        return None
                    if len(nums_list) >= 2:
                        return _parse_money(nums_list[1])  # mês atual
                    return _parse_money(nums_list[-1])

                if "saldobruto" in line_norm:
                    total_value = pick(nums)
                if "saldoliquido" in line_norm or "saldolíquido" in line_norm or "saldolquido" in line_norm:
                    net_value = pick(nums)

        # Também pode vir o total na pg 4 como "Total da Carteira X"
        if total_value is None and len(pages_text) > 3:
            for line in pages_text[3].split("\n"):
                if "total da carteira" in line.lower():
                    nums = re.findall(r"[\d.]+,\d{2}", line)
                    if nums:
                        total_value = _parse_money(nums[-1])

        # 3. Extrair posições da página 4 (carteira detalhada)
        positions = []
        if len(pages_text) > 3:
            positions = self._parse_carteira_detalhada(pages_text[3])
        # Algumas posições podem estar na pg 5 também (dependendo do tamanho)

        return {
            "snapshot_date": snapshot_date,
            "total_value": total_value or net_value,  # fallback: usa líquido se bruto não disponível
            "total_invested": None,  # Itaú não traz valor aplicado consolidado
            "available_balance": Decimal("0"),
            "positions": positions,
        }

    def _extract_date_from_filename(self) -> Optional[date]:
        """ITAU EXTRATO-CARTEIRA-2026-02 → date(2026,2,28) (último dia do mês)."""
        m = re.search(r"(\d{4})-(\d{2})", self.file_path.name)
        if m:
            y, mo = int(m.group(1)), int(m.group(2))
            import calendar
            last_day = calendar.monthrange(y, mo)[1]
            try:
                return date(y, mo, last_day)
            except ValueError:
                return None
        return None

    def _parse_carteira_detalhada(self, text: str) -> List[Dict[str, Any]]:
        """Extrai posições da página 4 do PDF Itaú.

        Estrutura:
            X,X% NomeSecao TotalSecao
            NomeProduto Saldo DataApl Vencto Taxa %Cart Risco Rent12m RentMes RentAnt RentYTD RentAno
        """
        positions = []
        current_class = None
        lines = text.split("\n")

        # Pular linhas até começar a tabela (geralmente após "Produto Saldo(R$)..."
        in_table = False
        for line in lines:
            line_clean = line.strip()
            if not line_clean:
                continue

            # Detectar header de seção: "X,X% NomeSecao TotalValor"
            section_match = re.match(r"^\d{1,2},\d+%\s+(.+?)\s+([\d.]+,\d{2})$", line_clean)
            if section_match:
                section_name = section_match.group(1).strip()
                section_norm = _normalize_section_name(section_name)
                # Mapear para AssetClassCode
                detected = None
                for key, code in ITAU_SECTION_MAP.items():
                    if key in section_norm:
                        detected = code
                        break
                if detected:
                    current_class = detected
                in_table = True
                continue

            # Pular linhas que não são produtos
            if not in_table or not current_class:
                continue
            # Pular linhas auxiliares (% do CDI, Retorno sobre o..., Total da Carteira)
            line_lower = line_clean.lower()
            if (
                line_lower.startswith("% do ")
                or line_lower.startswith("retorno sobre")
                or line_lower.startswith("total da carteira")
                or "indicadores" in line_lower
                or "cdi" == line_lower[:3] and "saldo" not in line_lower
            ):
                continue

            # Tentar parsear linha de produto
            pos = self._parse_product_line(line_clean, current_class)
            if pos:
                positions.append(pos)

        return positions

    def _parse_product_line(self, line: str, asset_class: AssetClassCode) -> Optional[Dict[str, Any]]:
        """Tenta extrair produto de uma linha.

        Variações:
        1. "CDB-DI 1.165,69 06/01/25 11/12/29 0% Baixo 14,50 1,00 1,16 2,17 14,31"
        2. "ITAU CRED BANCARIO 41.605,88 - - - 6% Baixo 14,56 1,00 1,17 2,18 14,38"
        3. "PRIVILEGE RF REF DI 311.289,65 - - - 42% Baixo 14,46 0,99 1,17 2,16 14,34"
        4. Multi-linha: nome muito longo pode quebrar (ex: "ITAU FLEXPREV GLOBAL\\nDINAMICO RF LP VGBL 101.385,47 ...")
        """
        # Padrão: nome (texto) + saldo (R$ XX.XXX,XX) + ... outras colunas
        m = re.match(r"^(.+?)\s+([\d.]+,\d{2})\s+(.+)$", line)
        if not m:
            return None

        name = m.group(1).strip()
        if not name or len(name) < 3:
            return None
        # Pular se nome parece ser um número/percentual
        if re.match(r"^[\d.,%-]+$", name):
            return None
        # Pular linhas que são total/agregado
        if name.lower().startswith("total"):
            return None

        value = _parse_money(m.group(2))
        if value is None or value == 0:
            return None

        rest = m.group(3)
        # Detectar contracted_rate (ex: 100,00% CDI ou 100,0000000%CDI)
        contracted_rate = None
        rate_match = re.search(r"(\d{1,3}[,.]?\d*)\s*%\s*CDI", rest, re.IGNORECASE)
        if rate_match:
            contracted_rate = rate_match.group(0).strip()

        # Detectar maturity_date (formato dd/mm/yy ou dd/mm/yyyy no rest)
        maturity = None
        date_matches = re.findall(r"(\d{2}/\d{2}/\d{2,4})", rest)
        if len(date_matches) >= 2:
            # Normalmente: data aplicação, data vencimento
            mat_str = date_matches[1]
            # Lidar com ano de 2 dígitos
            if len(mat_str.split("/")[2]) == 2:
                d, mo, y = mat_str.split("/")
                y = "20" + y if int(y) < 50 else "19" + y
                mat_str = f"{d}/{mo}/{y}"
            maturity = _parse_date_br(mat_str)

        # Detectar primeira % após "Risco"
        # Padrão de % de carteira: "X% Baixo|Médio|Alto"
        cart_match = re.search(r"(\d{1,3})%\s*(Baixo|M[eé]dio|Alto|Indispon[ií]vel)", rest)
        allocation = None
        if cart_match:
            try:
                allocation = Decimal(cart_match.group(1))
            except (InvalidOperation, ValueError):
                pass

        return {
            "name": name,
            "name_normalized": _normalize_name(name),
            "asset_class": asset_class,
            "value": value,
            "value_invested": None,
            "allocation_pct": allocation,
            "yield_net_pct": None,
            "yield_gross_pct": None,
            "yield_value": None,
            "quantity": None,
            "maturity_date": maturity,
            "contracted_rate": contracted_rate,
        }


# ============================================================
# C6 Position Parser
# ============================================================

class C6PositionParser:
    """Parser para PDF 'Posição por produto' do C6 Bank.

    Layout esperado:
    - Página 4 (ou similar): header 'Patrimônio final: R$ XX,XX'
    - Tabela 'Posição por produto' com cabeçalho ABR/25 ... MAR/26
    - Cada linha tem o nome do produto + 12 colunas mensais
    - A última coluna (MMM/YY) é o mês mais recente = mês do snapshot
    """

    FILENAME_RE = re.compile(r"C6[-_](\d{2})[-_](\d{2})[-_](\d{4})", re.IGNORECASE)
    MONTH_HEADER_RE = re.compile(r"^[A-Z]{3}/\d{2}$")

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)

    def parse(self) -> Dict[str, Any]:
        try:
            import pdfplumber
        except ImportError:
            raise RuntimeError("pdfplumber não instalado. pip install pdfplumber")

        snapshot_date = self._extract_date_from_filename()
        if not snapshot_date:
            raise ValueError(
                f"Nome do arquivo C6 não contém data no formato C6-DD-MM-YYYY.pdf "
                f"(recebido: {self.file_path.name})"
            )

        positions: List[Dict[str, Any]] = []
        total_patrimony: Optional[Decimal] = None

        with pdfplumber.open(self.file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""

                # Patrimônio final (geralmente pg 4)
                if total_patrimony is None:
                    m = re.search(r"Patrim\S*nio final:\s*R\$\s*([\d.,]+)", text)
                    if m:
                        total_patrimony = _parse_money(m.group(1))

                # Tabelas (extract_tables preserva estrutura)
                for tbl in page.extract_tables() or []:
                    if not tbl or len(tbl) < 2:
                        continue
                    header = [self._norm(c) for c in tbl[0]]
                    # Procurar última coluna que casa MMM/YY (a mais recente)
                    month_col_idx = None
                    for idx in range(len(header) - 1, -1, -1):
                        if self.MONTH_HEADER_RE.match(header[idx].upper()):
                            month_col_idx = idx
                            break
                    if month_col_idx is None:
                        continue

                    for row in tbl[1:]:
                        if not row or len(row) <= month_col_idx:
                            continue
                        name = self._norm(row[0])
                        if not name:
                            continue
                        if name.lower() in ("renda fixa", "renda variavel", "renda variável", "total", "total geral"):
                            continue
                        cell = self._norm(row[month_col_idx] or "")
                        m_val = re.search(r"R\$\s*([\d.][\d.,]*)", cell)
                        if not m_val:
                            continue
                        value = _parse_money(m_val.group(1))
                        if not value or value <= 0:
                            continue
                        positions.append(self._build_position(name, value))

        # Total: usa Patrimônio final se disponível, senão soma das posições
        sum_positions = sum((p["value"] for p in positions), Decimal("0"))
        total_value = total_patrimony or sum_positions

        # allocation_pct
        if total_value > 0:
            for p in positions:
                p["allocation_pct"] = (p["value"] / total_value * 100).quantize(Decimal("0.01"))

        return {
            "snapshot_date": snapshot_date,
            "total_value": total_value,
            "total_invested": None,
            "available_balance": Decimal("0"),
            "positions": positions,
        }

    def _extract_date_from_filename(self) -> Optional[date]:
        """C6-31-03-2026.pdf → date(2026,3,31)."""
        m = self.FILENAME_RE.search(self.file_path.name)
        if not m:
            return None
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return date(y, mo, d)
        except ValueError:
            return None

    @staticmethod
    def _norm(s: Any) -> str:
        if not s:
            return ""
        text = str(s).replace("\n", " ")
        return re.sub(r"\s+", " ", text).strip()

    def _build_position(self, name: str, value: Decimal) -> Dict[str, Any]:
        """Mapeia nome do produto C6 → AssetClassCode."""
        name_lower = name.lower()
        if "ipca" in name_lower or "pós" in name_lower or "pos-" in name_lower or "pos " in name_lower:
            asset_class = AssetClassCode.POS_FIXADO
        elif "prefixado" in name_lower or "prefixada" in name_lower or "pré" in name_lower or "pre-" in name_lower or "pre " in name_lower:
            asset_class = AssetClassCode.PRE_FIXADO
        else:
            asset_class = AssetClassCode.RENDA_FIXA

        return {
            "name": name,
            "name_normalized": _normalize_name(name),
            "asset_class": asset_class,
            "value": value,
            "value_invested": None,
            "quantity": None,
            "allocation_pct": None,  # preenchido após calcular total
            "yield_net_pct": None,
            "yield_gross_pct": None,
            "yield_value": None,
            "maturity_date": None,
            "contracted_rate": None,
        }


# ============================================================
# Service: criar/atualizar Snapshot a partir do parse
# ============================================================

class InvestmentImportService:
    def __init__(self, db: Session):
        self.db = db

    def import_xp_file(self, file_path: str, account_id: int) -> Dict[str, Any]:
        """Importa arquivo XP (Posição Detalhada Histórica)."""
        return self._import_with_parser(XPPositionParser(file_path), file_path, account_id)

    def import_itau_file(self, file_path: str, account_id: int) -> Dict[str, Any]:
        """Importa arquivo Itaú (PDF Carteira)."""
        return self._import_with_parser(ItauCarteiraParser(file_path), file_path, account_id)

    def import_c6_file(self, file_path: str, account_id: int) -> Dict[str, Any]:
        """Importa arquivo C6 (PDF Posição por produto)."""
        return self._import_with_parser(C6PositionParser(file_path), file_path, account_id)

    def _import_with_parser(self, parser, file_path: str, account_id: int) -> Dict[str, Any]:
        """Lógica comum para qualquer parser que retorne o dict padrão."""
        account = self.db.query(BankAccount).filter(BankAccount.id == account_id).first()
        if not account:
            raise ValueError(f"Conta {account_id} não encontrada")

        # Parse
        data = parser.parse()

        # Buscar/criar AssetClass por código (cache)
        class_cache: Dict[AssetClassCode, AssetClass] = {}
        for ac in self.db.query(AssetClass).all():
            class_cache[ac.code] = ac

        # Criar ImportBatch para rastrear
        ext = Path(file_path).suffix.lower()
        if ext == ".pdf":
            file_type = FileType.PDF
        elif ext == ".csv":
            file_type = FileType.CSV
        elif ext in (".xls", ".xlsx"):
            file_type = FileType.XLSX
        else:
            file_type = FileType.XLSX
        batch = ImportBatch(
            account_id=account_id,
            filename=Path(file_path).name,
            file_type=file_type,
            total_records=len(data["positions"]),
            imported_records=0,
            duplicate_records=0,
            error_records=0,
            status=ImportStatus.PROCESSING,
        )
        self.db.add(batch)
        self.db.flush()

        # Verificar/atualizar snapshot
        existing = (
            self.db.query(InvestmentSnapshot)
            .filter(
                InvestmentSnapshot.account_id == account_id,
                InvestmentSnapshot.snapshot_date == data["snapshot_date"],
            )
            .first()
        )
        if existing:
            # Substituir: deletar posições antigas
            for p in list(existing.positions):
                self.db.delete(p)
            existing.total_value = data["total_value"] or Decimal("0")
            existing.total_invested = data["total_invested"]
            existing.available_balance = data["available_balance"]
            existing.import_batch_id = batch.id
            snapshot = existing
            replaced = True
        else:
            snapshot = InvestmentSnapshot(
                account_id=account_id,
                snapshot_date=data["snapshot_date"],
                total_value=data["total_value"] or Decimal("0"),
                total_invested=data["total_invested"],
                available_balance=data["available_balance"],
                import_batch_id=batch.id,
            )
            self.db.add(snapshot)
            replaced = False

        self.db.flush()

        # Criar/buscar assets e posições
        imported = 0
        for pos_data in data["positions"]:
            # Buscar Asset existente por nome normalizado
            asset = (
                self.db.query(Asset)
                .filter(Asset.name_normalized == pos_data["name_normalized"])
                .first()
            )
            if not asset:
                cls = class_cache.get(pos_data["asset_class"])
                if not cls:
                    continue  # Não deveria acontecer se seed rodou
                asset = Asset(
                    name=pos_data["name"],
                    name_normalized=pos_data["name_normalized"],
                    asset_class_id=cls.id,
                )
                self.db.add(asset)
                self.db.flush()

            position = InvestmentPosition(
                snapshot_id=snapshot.id,
                asset_id=asset.id,
                value=pos_data["value"],
                value_invested=pos_data["value_invested"],
                quantity=pos_data["quantity"],
                allocation_pct=pos_data["allocation_pct"],
                yield_net_pct=pos_data["yield_net_pct"],
                yield_gross_pct=pos_data["yield_gross_pct"],
                yield_value=pos_data["yield_value"],
                maturity_date=pos_data["maturity_date"],
                contracted_rate=pos_data["contracted_rate"],
            )
            self.db.add(position)
            imported += 1

        # Atualizar batch
        batch.imported_records = imported
        batch.status = ImportStatus.COMPLETED
        batch.date_start = data["snapshot_date"]
        batch.date_end = data["snapshot_date"]

        self.db.commit()
        self.db.refresh(snapshot)

        return {
            "snapshot_id": snapshot.id,
            "snapshot_date": snapshot.snapshot_date.isoformat(),
            "total_value": float(snapshot.total_value),
            "total_invested": float(snapshot.total_invested) if snapshot.total_invested else None,
            "positions_count": imported,
            "replaced": replaced,
            "batch_id": batch.id,
        }
