"""
Utilities for lightweight Excel file introspection.
Supports .xlsx/.xlsm by reading workbook metadata from zip/xml.
"""

from __future__ import annotations

from pathlib import Path
from typing import List
import xml.etree.ElementTree as ET
import zipfile


EXCEL_EXTENSIONS = {".xlsx", ".xlsm", ".xls"}


def is_excel_filename(filename: str) -> bool:
    return Path(filename).suffix.lower() in EXCEL_EXTENSIONS


def list_sheet_names(file_path: str) -> List[str]:
    """
    Return worksheet names from an Excel workbook.
    For .xls legacy files this function uses xlrd when available.
    """
    suffix = Path(file_path).suffix.lower()
    if suffix == ".xls":
        try:
            import xlrd  # type: ignore
        except Exception:
            return []
        book = xlrd.open_workbook(file_path, on_demand=True)
        return list(book.sheet_names())
    if suffix not in {".xlsx", ".xlsm"}:
        return []

    with zipfile.ZipFile(file_path, "r") as archive:
        data = archive.read("xl/workbook.xml")

    root = ET.fromstring(data)
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    sheets = root.findall("m:sheets/m:sheet", ns)
    names: List[str] = []
    for sheet in sheets:
        name = sheet.attrib.get("name")
        if name:
            names.append(name)
    return names
