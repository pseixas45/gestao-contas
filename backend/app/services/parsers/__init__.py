"""Parsers de extratos de investimentos."""
from app.services.parsers.base import ParsedPosition, ParsedSnapshot
from app.services.parsers.xp_pdf_parser import XPPdfParser
from app.services.parsers.itau_extrato_parser import ItauExtratoMensalParser
from app.services.parsers.c6_pdf_parser import C6PdfParser

__all__ = [
    "ParsedPosition",
    "ParsedSnapshot",
    "XPPdfParser",
    "ItauExtratoMensalParser",
    "C6PdfParser",
]
