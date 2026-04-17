"""
Transforma arquivo Cri_Cra_Deb_-_comtaxa.csv no formato base_nova_xp_selecionados_filled.csv

Lógica:
  - Quando Taxa e Data Vencimento estão preenchidos (≠ NaN), utiliza esses campos.
  - Caso contrário, extrai taxa, indexador e vencimento do campo 'Ativo Original'.

Uso:
  python transforma_cri_cra_deb.py <arquivo_entrada.csv> [arquivo_saida.csv]

  Se arquivo_saida não for informado, grava em 'saida_formato_xp.csv'.
"""

import pandas as pd
import re
import sys
from datetime import datetime

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
MONTH_PT = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez",
}


# ---------------------------------------------------------------------------
# Funções de parsing
# ---------------------------------------------------------------------------
def parse_taxa(taxa_str: str) -> tuple:
    """
    Interpreta a coluna Taxa.
    Retorna (indexer, indexer_pct, yield_val).

    Formatos reconhecidos:
      - 'Pré-Fixado 12,2874%'   -> FixedRate, 0.0, 12.2874
      - '101,0000% DI'          -> CDI, 101.0, None
      - 'DI + 1,2500%'          -> CDI, 100.0, 1.25
      - 'IPCA + 6,4899%'        -> IPC-A, 100.0, 6.4899
    """
    s = taxa_str.strip()

    # Pré-Fixado
    m = re.match(r"Pré-Fixado\s+([\d,]+)%", s)
    if m:
        return "FixedRate", 0.0, float(m.group(1).replace(",", "."))

    # X% DI  (percentual do CDI)
    m = re.match(r"([\d,]+)%\s*DI", s)
    if m:
        return "CDI", float(m.group(1).replace(",", ".")), None

    # DI + spread
    m = re.match(r"DI\s*\+\s*([\d,]+)%", s)
    if m:
        return "CDI", 100.0, float(m.group(1).replace(",", "."))

    # IPCA + spread
    m = re.match(r"IPCA?\s*\+\s*([\d,]+)%", s)
    if m:
        return "IPC-A", 100.0, float(m.group(1).replace(",", "."))

    return None, None, None


def parse_ativo_longo(ativo: str) -> dict | None:
    """
    Formato longo do Ativo Original (quando Taxa é NaN e há dados de taxa inline).
    Ex.: 'CRI 24G1967273 - LVCP SECURITIZADORA - 2034-06-20 - 100% - CDI - 3.975 - 24G1967273'
    """
    parts = [p.strip() for p in ativo.split(" - ")]

    # Procura a parte com 'N%' (percentual do indexador)
    pct_idx = None
    for i, p in enumerate(parts):
        if re.match(r"^\d+%$", p):
            pct_idx = i
            break

    if pct_idx is None or pct_idx < 2:
        return None

    emissor = " - ".join(parts[1 : pct_idx - 1]) if pct_idx > 2 else parts[1]
    date_str = parts[pct_idx - 1]
    pct = float(parts[pct_idx].replace("%", ""))
    indexer_raw = parts[pct_idx + 1] if pct_idx + 1 < len(parts) else ""
    spread = float(parts[pct_idx + 2]) if pct_idx + 2 < len(parts) else None

    indexer_map = {"CDI": "CDI", "IPC-A": "IPC-A", "IPCA": "IPC-A"}
    indexer = indexer_map.get(indexer_raw.upper(), indexer_raw)

    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        venc = dt.strftime("%d/%m/%Y")
    except ValueError:
        venc = date_str

    return {
        "emissor": emissor,
        "vencimento": venc,
        "indexer": indexer,
        "indexer_pct": pct,
        "yield": spread,
    }


def parse_ativo_curto(ativo: str) -> dict | None:
    """
    Formato curto do Ativo Original.
    Ex.: 'CRI 24D2765715 - CRI CYRELA - ABR/2031 - 15/04/2031'
         'CRI PRE 23J1428588 - CRI MOVIDA - OUT/2030 - 15/10/2030'
    """
    parts = [p.strip() for p in ativo.split(" - ")]
    if len(parts) < 2:
        return None

    name = parts[1]
    date_str = parts[-1]
    m = re.match(r"(\d{2}/\d{2}/\d{4})", date_str)
    venc = m.group(1) if m else None

    first = parts[0]
    is_pre = "PRE" in first.upper().split()

    # Extrai código do primeiro token (remove tipo e PRE)
    tokens = first.split()
    code_tokens = [t for t in tokens[1:] if t.upper() != "PRE"]
    code = " ".join(code_tokens) if code_tokens else ""

    return {"emissor": name, "vencimento": venc, "is_pre": is_pre, "code": code}


def limpar_emissor(emissor: str) -> str:
    """Remove prefixos redundantes CRI/CRA/DEB do nome do emissor."""
    for prefix in ("CRI ", "CRA ", "DEB "):
        if emissor.upper().startswith(prefix):
            emissor = emissor[len(prefix) :]
    return emissor.strip()


def vencimento_por_extenso(venc_str: str) -> str:
    """Converte dd/mm/yyyy para dd/Mmm/yyyy (mês em português)."""
    try:
        dt = datetime.strptime(venc_str, "%d/%m/%Y")
        return f"{dt.day:02d}/{MONTH_PT[dt.month]}/{dt.year}"
    except (ValueError, TypeError):
        return venc_str


def montar_beehus(tipo, emissor, indexer, pct, yld, venc) -> str:
    """Monta o campo BeehusName / beehusName."""
    venc_fmt = vencimento_por_extenso(venc) if venc else ""

    if indexer == "FixedRate":
        if yld is not None and yld > 0:
            return f"{tipo} {emissor} {yld:.4f}% {venc_fmt}"
        return f"{tipo} {emissor} PRE {venc_fmt}"

    if indexer == "CDI":
        base = f"{tipo} {emissor} {pct:.2f}%CDI"
        if yld is not None and yld > 0:
            base += f" + {yld:.4f}%"
        return f"{base} {venc_fmt}"

    if indexer == "IPC-A":
        base = f"{tipo} {emissor} {pct:.2f}%IPC-A"
        if yld is not None and yld > 0:
            base += f" + {yld:.4f}%"
        return f"{base} {venc_fmt}"

    return f"{tipo} {emissor} {venc_fmt}"


# ---------------------------------------------------------------------------
# Transformação principal
# ---------------------------------------------------------------------------
def transformar(df_src: pd.DataFrame) -> pd.DataFrame:
    """Recebe o DataFrame de entrada e retorna no formato XP."""
    rows = []

    for _, r in df_src.iterrows():
        ativo = r["Ativo Original"]
        codigo = r["Codigo Ativo"] if pd.notna(r["Codigo Ativo"]) else ""
        taxa = r["Taxa"]
        data_venc = r["Data Vencimento"]

        tipo = ativo.split()[0]  # CRI, CRA ou DEB

        has_taxa = pd.notna(taxa) and str(taxa).strip() not in ("", "N/A", "nan")
        has_venc = pd.notna(data_venc) and str(data_venc).strip() not in ("", "N/A", "nan")

        # --- Caminho 1: Taxa e Data Vencimento preenchidos ----------------
        if has_taxa and has_venc:
            indexer, pct, yld = parse_taxa(str(taxa))
            venc = str(data_venc).strip()
            parsed = parse_ativo_curto(ativo)
            emissor = limpar_emissor(parsed["emissor"]) if parsed else ativo
            if not codigo and parsed:
                codigo = parsed.get("code", "")

        # --- Caminho 2: extrair do Ativo Original -------------------------
        else:
            parsed_long = parse_ativo_longo(ativo)
            if parsed_long:
                emissor = parsed_long["emissor"]
                venc = parsed_long["vencimento"]
                indexer = parsed_long["indexer"]
                pct = parsed_long["indexer_pct"]
                yld = parsed_long["yield"]
            else:
                parsed = parse_ativo_curto(ativo)
                if parsed:
                    emissor = limpar_emissor(parsed["emissor"])
                    venc = parsed["vencimento"]
                    if not codigo:
                        codigo = parsed.get("code", "")
                    if parsed.get("is_pre"):
                        indexer, pct, yld = "FixedRate", 0.0, None
                    else:
                        indexer, pct, yld = None, None, None
                else:
                    emissor, venc = ativo, None
                    indexer, pct, yld = None, None, None

        yield_str = f"{yld:.4f}%" if yld is not None else ""
        beehus = montar_beehus(tipo, emissor, indexer or "", pct or 0, yld, venc)

        rows.append(
            {
                "BeehusName": beehus,
                "beehusName": beehus,
                "Emissor": emissor,
                "Type": tipo,
                "Vencimento": venc if venc else "",
                "Ticker": str(codigo),
                "Yield": yield_str,
                "Indexer": indexer if indexer else "",
                "Indexer Percentual": pct if pct is not None else "",
            }
        )

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------
def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    arquivo_entrada = sys.argv[1]
    arquivo_saida = sys.argv[2] if len(sys.argv) > 2 else "saida_formato_xp.csv"

    # Detecta encoding
    try:
        df = pd.read_csv(arquivo_entrada, encoding="utf-8-sig", sep=None, engine="python")
    except UnicodeDecodeError:
        df = pd.read_csv(arquivo_entrada, encoding="latin-1", sep=None, engine="python")

    print(f"Lido: {len(df)} linhas de '{arquivo_entrada}'")

    resultado = transformar(df)

    resultado.to_csv(arquivo_saida, index=False, encoding="utf-8-sig")
    print(f"Salvo: {len(resultado)} linhas em '{arquivo_saida}'")

    # Resumo
    print(f"\nDistribuição por Indexer:")
    dist = resultado["Indexer"].value_counts(dropna=False)
    for k, v in dist.items():
        label = k if k else "(sem info)"
        print(f"  {label}: {v}")


if __name__ == "__main__":
    main()
