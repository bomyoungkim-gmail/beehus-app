"""
Transformador de Base de Ativos CDB/LCA/LCI
=============================================
Converte o formato bruto (coluna única "Ativo Original") para o formato
padronizado com 9 colunas separadas por ponto-e-vírgula (;).

Colunas de saída:
    BeehusName | beehusName | Emissor | Type | Vencimento | Ticker |
    Yield | Indexer | Indexer Percentual

Uso:
    python transformar_cdb_lca_lci.py <arquivo_entrada.csv> [arquivo_saida.csv]

    Se o arquivo de saída não for informado, gera automaticamente com sufixo
    "_transformado" no mesmo diretório do arquivo de entrada.

Exemplos de entrada aceitos:
    "CDB PRE DU CDB1257NSWK - CDB BANCO C6 CONSIGNADO S.A. - JAN/2027 - +15,75% - 22/01/2027"
    "CDB FLU CDBA259IGIA - CDB BANCO PLENO - OUT/2028 - 108,50% CDI - 16/10/2028"
    "CDB FLU CDB8255W1Y3 - CDB BANCO XP S.A. - AGO/2030 - IPC-A +7,10% - 12/08/2030"
    "LCA 25F07417671 - LCA BNDES - JUN/2028 - 91,00% CDI - 30/06/2028"
    "LCA PRE 24F01076130 - LCA BANCO BOCOM BBM SA - JUN/2028 - +10,85% - 05/06/2028"
    "LCI 25C03754733 - LCI CEF - MAR/2027 - 95,50% CDI - 18/03/2027"
"""

import re
import sys
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

MONTH_PT = {
    "01": "Jan", "02": "Fev", "03": "Mar", "04": "Abr",
    "05": "Mai", "06": "Jun", "07": "Jul", "08": "Ago",
    "09": "Set", "10": "Out", "11": "Nov", "12": "Dez",
}

OUTPUT_FIELDS = [
    "BeehusName",
    "beehusName",
    "Emissor",
    "Type",
    "Vencimento",
    "Ticker",
    "Yield",
    "Indexer",
    "Indexer Percentual",
]

# Mapeamento de nomes curtos para o campo beehusName.
# Chaves em UPPER para facilitar busca case-insensitive.
BANK_SHORT: dict[str, str] = {
    "BANCO C6 CONSIGNADO S.A.":          "C6",
    "BANCO C6 S.A.":                     "C6",
    "BMG":                               "BMG",
    "BANCO PLENO":                       "Pleno",
    "LUSO BRASILEIRO":                   "Luso Brasileiro",
    "PINE":                              "Pine",
    "BANCO PINE S.A.":                   "Pine",
    "BANCO PINE":                        "Pine",
    "AGIBANK":                           "Agibank",
    "BANCO AGIBANK":                     "Agibank",
    "NBC BANK":                          "NBC",
    "BANCO DIGIMAIS S.A.":               "Digimais",
    "BANCO DIGIMAIS":                    "Digimais",
    "BANCO XP S.A.":                     "XP",
    "BANCO XP":                          "XP",
    "BANCO INDUSTRIAL DO BRASIL S.A.":   "Industrial",
    "BANCO INDUSTRIAL DO BRASIL S.A":    "Industrial",
    "FACTA FINANCEIRA S.A.":             "Facta",
    "FACTA FINANCEIRA":                  "Facta",
    "BANCO PAN":                         "Pan",
    "BANCO BTG PACTUAL":                 "BTG Pactual",
    "BTG PACTUAL":                       "BTG Pactual",
    "BANCO ORIGINAL":                    "Original",
    "BANCO DAYCOVAL S/A":                "Daycoval",
    "BANCO DAYCOVAL":                    "Daycoval",
    "BANCO SOFISA S.A.":                 "Sofisa",
    "BANCO SOFISA":                      "Sofisa",
    "BANCO FIBRA S.A.":                  "Fibra",
    "BANCO FIBRA":                       "Fibra",
    "BANCO BOCOM BBM SA":                "Bocom BBM",
    "BANCO BOCOM BBM":                   "Bocom BBM",
    "BNDES":                             "BNDES",
    "BANCO JOHN DEERE S.A.":             "John Deere",
    "BANCO JOHN DEERE":                  "John Deere",
    "BANCO COOPERATIVO SICOOB":          "Sicoob",
    "RABOBANK":                          "Rabobank",
    "BANCO BV S/A":                      "BV",
    "BANCO BV":                          "BV",
    "CEF":                               "CEF",
    "CAIXA ECONOMICA FEDERAL":           "CEF",
    "PAULISTA":                          "Paulista",
    "BANCO PAULISTA S.A.":               "Paulista",
    "BRB":                               "BRB",
    "BANCO CNH CAPITAL S/A":             "CNH",
    "BANCO CNH CAPITAL":                 "CNH",
    "BANCO TRIANGULO S/A":               "Triângulo",
    "BANCO TRIANGULO":                   "Triângulo",
    "BANCO SICREDI S.A.":                "Sicredi",
    "BANCO SICREDI":                     "Sicredi",
    "BANCO ITAU":                        "Itaú",
    "ITAU UNIBANCO":                     "Itaú",
    "BANCO MASTER S.A.":                 "Master",
    "BANCO MASTER":                      "Master",
    "BANCO ABC BRASIL S.A.":             "ABC Brasil",
    "BANCO ABC BRASIL":                  "ABC Brasil",
    "BANCO MERCANTIL DO BRASIL S.A.":    "Mercantil",
    "BANCO MERCANTIL DO BRASIL":         "Mercantil",
    "BANCO BANESTES S.A.":               "Banestes",
    "BANCO BANESTES":                    "Banestes",
    "BANCO DO NORDESTE DO BRASIL S.A.":  "BNB",
    "BANCO DO NORDESTE":                 "BNB",
    "BANCO VOTORANTIM S.A.":             "Votorantim",
    "BANCO VOTORANTIM":                  "Votorantim",
    "BANCO INTER S.A.":                  "Inter",
    "BANCO INTER":                       "Inter",
    "BANCO RENDIMENTO S.A.":             "Rendimento",
    "BANCO RENDIMENTO":                  "Rendimento",
    "BANCO SAFRA S.A.":                  "Safra",
    "BANCO SAFRA":                       "Safra",
    "BANCO SANTANDER":                   "Santander",
    "BANCO BRADESCO":                    "Bradesco",
    "BANCO DO BRASIL":                   "BB",
    "HAITONG":                           "Haitong",
    "BANCO HAITONG":                     "Haitong",
}

# Pré-computa versão upper para lookup
_BANK_SHORT_UPPER = {k.upper(): v for k, v in BANK_SHORT.items()}


# ---------------------------------------------------------------------------
# Funções auxiliares
# ---------------------------------------------------------------------------

def _get_short_name(emissor: str) -> str:
    """Retorna nome curto do emissor para o campo beehusName."""
    up = emissor.upper().strip()
    for key, val in _BANK_SHORT_UPPER.items():
        if key in up:
            return val
    # Fallback: remove prefixo BANCO e sufixos S.A. / S/A
    short = emissor.strip()
    short = re.sub(r"^BANCO\s+", "", short, flags=re.IGNORECASE)
    short = re.sub(r"\s+S\.?A\.?\s*$", "", short, flags=re.IGNORECASE)
    short = re.sub(r"\s+S/A\s*$", "", short, flags=re.IGNORECASE)
    return short.strip()


def _date_with_month_pt(date_str: str) -> str:
    """Converte dd/mm/yyyy → dd/Mon/yyyy (mês abreviado em português)."""
    parts = date_str.strip().split("/")
    if len(parts) == 3:
        dd, mm, yyyy = parts
        return f"{dd}/{MONTH_PT.get(mm, mm)}/{yyyy}"
    return date_str


def _parse_rate(rate_info: str) -> tuple[str, str, str]:
    """
    Interpreta a string de taxa e retorna (indexer, yield_val, indexer_pct).

    Padrões reconhecidos:
        "+15,75%"           → FixedRate  / 15.75% / 0.0
        "108,50% CDI"       → CDI        / ""     / 108.5
        "100% CDI + 1,05%"  → CDI        / 1.05%  / 100.0
        "CDI +1,80%"        → CDI        / 1.80%  / 100.0
        "IPC-A +7,10%"      → IPC-A      / 7.10%  / 100.0
    """
    clean = rate_info.strip().replace(",", ".")

    # --- IPCA ---
    if "IPC-A" in clean or "IPCA" in clean:
        m = re.search(r"[+]?\s*([\d.]+)%", clean)
        yield_val = f"{float(m.group(1)):.2f}%" if m else ""
        return "IPC-A", yield_val, "100.0"

    # --- CDI ---
    if "CDI" in clean:
        # Padrão "CDI +1.80%" → 100% CDI + spread
        m_cdi_spread = re.match(r"CDI\s*\+\s*([\d.]+)%", clean)
        if m_cdi_spread:
            return "CDI", f"{float(m_cdi_spread.group(1)):.2f}%", "100.0"

        # Padrão "108.50% CDI" ou "100% CDI + 1.05%"
        m_pct = re.match(r"([\d.]+)%\s*CDI", clean)
        if m_pct:
            pct = float(m_pct.group(1))
            m_spread = re.search(r"CDI\s*\+\s*([\d.]+)%", clean)
            if m_spread:
                return "CDI", f"{float(m_spread.group(1)):.2f}%", str(pct)
            return "CDI", "", str(pct)

    # --- Prefixado ---
    if clean.startswith("+") or re.match(r"[\d.]+%$", clean):
        m = re.search(r"[+]?\s*([\d.]+)%", clean)
        yield_val = f"{float(m.group(1)):.2f}%" if m else ""
        return "FixedRate", yield_val, "0.0"

    # --- Fallback ---
    m = re.search(r"([\d.]+)%", clean)
    yield_val = f"{float(m.group(1)):.2f}%" if m else ""
    return "FixedRate", yield_val, "0.0"


# ---------------------------------------------------------------------------
# Parser principal
# ---------------------------------------------------------------------------

def parse_line(line: str) -> dict | None:
    """
    Recebe uma linha no formato bruto e retorna dicionário com os 9 campos
    do formato de saída.  Retorna None se a linha for cabeçalho ou inválida.
    """
    line = line.strip().strip('"')
    if not line or line.upper() == "ATIVO ORIGINAL":
        return None

    parts = [p.strip() for p in line.split(" - ")]
    if len(parts) < 5:
        return None

    header     = parts[0]       # "CDB PRE DU CDB1257NSWK"
    type_emiss = parts[1]       # "CDB BANCO C6 CONSIGNADO S.A."
    rate_info  = parts[-2]      # "+15,75%" | "108,50% CDI" | "IPC-A +7,10%"
    maturity   = parts[-1]      # "22/01/2027"

    # --- Tipo e Ticker ---
    tokens = header.split()
    asset_type = tokens[0]                         # CDB | LCA | LCI
    ticker     = tokens[-1]                        # código do ativo

    # --- Emissor ---
    emissor = re.sub(
        r"^(CDB|LCA|LCI|LIG|LFSC|CDCA)\s+", "", type_emiss, flags=re.IGNORECASE
    ).strip()

    # --- Taxas ---
    indexer, yield_val, indexer_pct = _parse_rate(rate_info)

    # --- BeehusName (longo) ---
    if indexer == "FixedRate":
        rate_str = yield_val.replace("%", "") + "%"
        beehus_long = f"{asset_type} {emissor} {rate_str} {maturity}"
    elif indexer == "CDI":
        pct_display = f"{float(indexer_pct):.0f}%" if float(indexer_pct) == int(float(indexer_pct)) else f"{float(indexer_pct)}%"
        if yield_val:
            beehus_long = f"{asset_type} {emissor} {pct_display} CDI + {yield_val} {maturity}"
        else:
            beehus_long = f"{asset_type} {emissor} {pct_display} CDI {maturity}"
    elif indexer == "IPC-A":
        beehus_long = f"{asset_type} {emissor} 100% IPC-A + {yield_val} {maturity}"
    else:
        beehus_long = f"{asset_type} {emissor} {rate_info} {maturity}"

    # --- beehusName (curto, com mês em português) ---
    short = _get_short_name(emissor)
    date_pt = _date_with_month_pt(maturity)

    if indexer == "FixedRate":
        beehus_short = f"{asset_type} {short} {yield_val.replace('%', '')}% {date_pt}"
    elif indexer == "CDI":
        pct_fmt = f"{float(indexer_pct):.2f}%"
        if yield_val:
            beehus_short = f"{asset_type} {short} {pct_fmt}CDI + {yield_val} {date_pt}"
        else:
            beehus_short = f"{asset_type} {short} {pct_fmt}CDI {date_pt}"
    elif indexer == "IPC-A":
        beehus_short = f"{asset_type} {short} 100.00%IPCA + {yield_val} {date_pt}"
    else:
        beehus_short = f"{asset_type} {short} {rate_info} {date_pt}"

    return {
        "BeehusName":        beehus_long,
        "beehusName":        beehus_short,
        "Emissor":           emissor,
        "Type":              asset_type,
        "Vencimento":        maturity.strip(),
        "Ticker":            ticker,
        "Yield":             yield_val,
        "Indexer":           indexer,
        "Indexer Percentual": indexer_pct,
    }


# ---------------------------------------------------------------------------
# Leitura / Escrita
# ---------------------------------------------------------------------------

def transform(input_path: str, output_path: str) -> None:
    """Lê o CSV de entrada, transforma e grava o CSV de saída."""

    # Tenta detectar encoding
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            with open(input_path, "r", encoding=enc) as f:
                lines = f.readlines()
            break
        except UnicodeDecodeError:
            continue
    else:
        raise RuntimeError(f"Não foi possível decodificar {input_path}")

    rows: list[dict] = []
    errors: list[tuple[int, str]] = []

    for i, line in enumerate(lines, start=1):
        line = line.strip()
        if not line:
            continue
        result = parse_line(line)
        if result is None and i > 1 and line.strip('"').upper() != "ATIVO ORIGINAL":
            errors.append((i, line))
        elif result is not None:
            rows.append(result)

    # Grava saída
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        f.write(";".join(OUTPUT_FIELDS) + "\n")
        for row in rows:
            vals = [row[field] for field in OUTPUT_FIELDS]
            f.write(";".join(vals) + "\n")

    # Resumo
    print(f"{'='*60}")
    print(f"  Arquivo de entrada : {input_path}")
    print(f"  Arquivo de saída   : {output_path}")
    print(f"  Linhas processadas : {len(rows)}")
    if errors:
        print(f"  Linhas ignoradas   : {len(errors)}")
        for num, txt in errors[:5]:
            print(f"    Linha {num}: {txt[:80]}...")
    print(f"{'='*60}")

    # Distribuição por tipo
    from collections import Counter
    types = Counter(r["Type"] for r in rows)
    indexers = Counter(r["Indexer"] for r in rows)
    print(f"\n  Por tipo    : {dict(types)}")
    print(f"  Por indexador: {dict(indexers)}")
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("Erro: informe o arquivo de entrada.\n")
        print("  python transformar_cdb_lca_lci.py <entrada.csv> [saida.csv]")
        sys.exit(1)

    input_path = sys.argv[1]
    if not os.path.isfile(input_path):
        print(f"Erro: arquivo não encontrado: {input_path}")
        sys.exit(1)

    if len(sys.argv) >= 3:
        output_path = sys.argv[2]
    else:
        p = Path(input_path)
        output_path = str(p.parent / f"{p.stem}_transformado{p.suffix}")

    transform(input_path, output_path)


if __name__ == "__main__":
    main()
