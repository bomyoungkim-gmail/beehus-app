"""
Canonical processing config handling.
Generates deterministic python script from visual config.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_VISUAL_CONFIG: Dict[str, Any] = {
    "ativo_mode": "direct",
    "ativo_direct_cols": "Ativo, Nome Ativo",
    "ativo_comp_base_cols": "Ativo Base, Ativo",
    "ativo_comp_part2_cols": "Operacao, Operação",
    "ativo_comp_part3_cols": "Emissor",
    "ativo_comp_part4_primary_cols": "Vencimento",
    "ativo_comp_part4_fallback_cols": "Codigo, Código",
    "ativo_separator": " - ",
    "quant_cols": "q, Quant, Quantidade",
    "pu_cols": "pu, PU, Preco Unitario",
    "saldo_bruto_cols": "sb, SaldoBruto, Saldo Bruto",
    "caixa_cols": "Caixa, Eh Caixa, e_caixa",
    "moeda_fixa": "BRL",
    "filter_zero_enabled": False,
    "filter_zero_cols": "sb, SaldoBruto, Saldo Bruto",
    "filter_empty_enabled": False,
    "filter_empty_cols": "Ativo, Nome Ativo",
    "only_enabled": False,
    "only_cols": "Caixa, Eh Caixa, e_caixa",
    "only_mode": "sim",
    "only_true_values": "1, true, sim, s, yes, y",
}


def normalize_processing_config(raw: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        return None

    mode = str(raw.get("mode") or "").strip().lower()
    if mode == "visual":
        return {
            "mode": "visual",
            "visual_config": normalize_visual_config(raw.get("visual_config")),
        }

    if mode == "advanced":
        return {
            "mode": "advanced",
            "advanced_script": str(raw.get("advanced_script") or ""),
        }

    return None


def build_script_from_processing_config(raw: Optional[Dict[str, Any]]) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    normalized = normalize_processing_config(raw)
    if not normalized:
        return None, None

    if normalized["mode"] == "visual":
        return build_script_from_visual_config(normalized.get("visual_config")), normalized

    script = str(normalized.get("advanced_script") or "").strip()
    return (script or None), normalized


def normalize_visual_config(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    cfg = dict(DEFAULT_VISUAL_CONFIG)
    if not isinstance(raw, dict):
        return cfg
    for k, v in raw.items():
        if k not in cfg:
            continue
        if isinstance(cfg[k], bool):
            cfg[k] = bool(v)
        else:
            cfg[k] = str(v) if v is not None else ""
    if cfg["ativo_mode"] not in {"direct", "compose"}:
        cfg["ativo_mode"] = "direct"
    if cfg["only_mode"] not in {"sim", "nao"}:
        cfg["only_mode"] = "sim"
    return cfg


def _split_csv_aliases(value: str) -> List[str]:
    return [x.strip() for x in str(value or "").split(",") if x.strip()]


def build_script_from_visual_config(raw: Optional[Dict[str, Any]]) -> str:
    cfg = normalize_visual_config(raw)
    cfg_json = json.dumps(cfg, ensure_ascii=False, sort_keys=True)
    cfg_py = repr(cfg)
    return f"""# VISUAL_BUILDER_JOB_V3
# VISUAL_CONFIG_JSON: {cfg_json}
cfg = {cfg_py}

df = df_input.copy() if df_input is not None else pd.DataFrame()
df.columns = [str(c).strip() for c in df.columns]

def aliases(value):
    return [x.strip() for x in str(value or "").split(",") if x.strip()]

def pick_col(candidates):
    lower_map = {{str(c).strip().lower(): c for c in df.columns}}
    for name in candidates:
        key = str(name).strip().lower()
        if key in lower_map:
            return lower_map[key]
    return None

def txt(candidates, default=""):
    col = pick_col(candidates)
    if col:
        return df[col].astype(str).fillna("").str.strip()
    return pd.Series([default] * len(df), index=df.index)

def num(candidates, default=0.0):
    col = pick_col(candidates)
    if col:
        raw = df[col]
        parsed = pd.to_numeric(raw, errors="coerce")
        if parsed.notna().any():
            return parsed.fillna(default)
        # Fallback para formato pt-BR (1.234,56)
        return raw.apply(ptbr_to_float).fillna(default)
    return pd.Series([default] * len(df), index=df.index)

def _clean_text(v):
    s = str(v).strip()
    if s.lower() in ["", "-", "nan", "none"]:
        return ""
    return s

def _join_non_empty(parts, sep):
    vals = [_clean_text(x) for x in parts]
    vals = [v for v in vals if v]
    return sep.join(vals)

ativo_direct = txt(aliases(cfg.get("ativo_direct_cols")))
ativo_base = txt(aliases(cfg.get("ativo_comp_base_cols")))
ativo_p2 = txt(aliases(cfg.get("ativo_comp_part2_cols")))
ativo_p3 = txt(aliases(cfg.get("ativo_comp_part3_cols")))
ativo_p4_primary = txt(aliases(cfg.get("ativo_comp_part4_primary_cols")))
ativo_p4_fallback = txt(aliases(cfg.get("ativo_comp_part4_fallback_cols")))
qtd = num(aliases(cfg.get("quant_cols")), 0.0)
pu = num(aliases(cfg.get("pu_cols")), 0.0)
sb = num(aliases(cfg.get("saldo_bruto_cols")), 0.0)
caixa_raw = txt(aliases(cfg.get("caixa_cols"))).str.lower()
caixa = caixa_raw.isin(["1", "true", "sim", "s", "yes", "y"])
caixa = caixa | caixa_raw.str.contains("caixa|conta corrente|saldo em conta", na=False)
ativo_hint = ativo_direct.str.lower()
caixa = caixa | ativo_hint.str.contains("conta corrente|saldo em conta", na=False)
data_ref = report_date or data_do_arquivo(arquivo)

if cfg.get("ativo_mode") == "compose":
    p4 = ativo_p4_primary.where(ativo_p4_primary.astype(str).str.strip().ne(""), ativo_p4_fallback)
    ativo = pd.DataFrame({{
        "a": ativo_base,
        "b": ativo_p2,
        "c": ativo_p3,
        "d": p4,
    }}).apply(lambda r: _join_non_empty([r["a"], r["b"], r["c"], r["d"]], cfg.get("ativo_separator") or " - "), axis=1)
else:
    ativo = ativo_direct

out = pd.DataFrame({{
    "Data": data_ref,
    "Carteira": carteira,
    "Ativo": ativo,
    "Quant": qtd.where(~caixa, sb),
    "PU": pu.where(~caixa, 1.0),
    "SaldoBruto": sb,
    "Caixa": caixa.map({{True: "Sim", False: "Não"}}),
    "Moeda": cfg.get("moeda_fixa") or "BRL",
}})

mask = pd.Series([True] * len(out), index=out.index)
if cfg.get("filter_zero_enabled"):
    fz = num(aliases(cfg.get("filter_zero_cols")), 0.0)
    mask &= fz.ne(0)
if cfg.get("filter_empty_enabled"):
    fe = txt(aliases(cfg.get("filter_empty_cols")))
    mask &= fe.astype(str).str.strip().ne("")
if cfg.get("only_enabled"):
    only_raw = txt(aliases(cfg.get("only_cols"))).str.lower()
    only_true = [x.strip().lower() for x in aliases(cfg.get("only_true_values"))]
    only_flag = only_raw.isin(only_true)
    mask &= only_flag if cfg.get("only_mode") == "sim" else ~only_flag

out = out.loc[mask].reset_index(drop=True)
return out
"""


def extract_visual_config_from_script(script: Optional[str]) -> Optional[Dict[str, Any]]:
    if not script:
        return None
    marker = "# VISUAL_CONFIG_JSON:"
    for line in script.splitlines():
        line = line.strip()
        if line.startswith(marker):
            payload = line[len(marker):].strip()
            try:
                parsed = json.loads(payload)
                if isinstance(parsed, dict):
                    return normalize_visual_config(parsed)
            except Exception:
                return None
    return None
