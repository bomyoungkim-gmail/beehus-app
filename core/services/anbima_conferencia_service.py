"""
Service layer for "Conferencia Ativo" CSV enrichment against ANBIMA data.
"""

from __future__ import annotations

import logging
import os
import re
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, Protocol
from urllib.parse import quote_plus


ANBIMA_BUSCA_URL = "https://data.anbima.com.br/busca"
logger = logging.getLogger(__name__)
LogFn = Optional[Callable[[str], None]]

COL_ATIVO_ORIGINAL = "Ativo Original"
COL_CODIGO_ATIVO = "Codigo Ativo"
COL_TAXA = "Taxa"
COL_DATA_VENCIMENTO = "Data Vencimento"
COL_STATUS = "_status"


class AtivoDataFetcher(Protocol):
    def fetch(self, codigo: str) -> tuple[str, str, str]:
        """Returns (taxa, data_vencimento, status)."""


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower().strip()


def extrair_codigo_ativo(texto: str) -> str:
    """Extract code from CRA/CRI/DEB text according to business rules."""
    if texto is None:
        return ""

    src = str(texto).strip().upper()
    if not src:
        return ""

    if "CRA" in src:
        match_cra = re.search(r"\b(CRA[A-Z0-9]{6,})\b", src)
        if match_cra:
            return match_cra.group(1).strip()

    if "CRI" in src:
        match_cri = re.search(r"\bCRI\s+([0-9]{2}[A-Z][0-9]{7,})\b", src)
        if match_cri:
            return match_cri.group(1).strip()

    if "DEB" in src:
        match_deb = re.search(r"\bDEB\s+(?:FLU|PRE)(?:\s+DU|\s+U)?\s+([A-Z0-9]{5,})\b", src)
        if match_deb:
            return match_deb.group(1).strip()

    return ""


@dataclass
class SeleniumConfig:
    headless: bool = True
    timeout_seconds: int = 40


class SeleniumAnbimaFetcher:
    def __init__(self, config: Optional[SeleniumConfig] = None, log_func: LogFn = None):
        self.config = config or SeleniumConfig()
        self.driver: Optional[Any] = None
        self.log_func = log_func

    def _log(self, msg: str) -> None:
        if self.log_func:
            self.log_func(msg)
        logger.info("[ConferenciaAtivo] %s", msg)

    def __enter__(self) -> "SeleniumAnbimaFetcher":
        self._log(f"Iniciando Selenium (headless={self.config.headless})...")
        self.driver = self._iniciar_driver(self.config.headless)
        self._log("Selenium inicializado")
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.driver:
            self._log("Encerrando Selenium...")
            self.driver.quit()
            self.driver = None
            self._log("Selenium encerrado")

    def fetch(self, codigo: str) -> tuple[str, str, str]:
        if not self.driver:
            raise RuntimeError("Selenium driver not initialized")
        return _buscar_dados_anbima(
            self.driver,
            codigo,
            max_tentativas=2,
            timeout=self.config.timeout_seconds,
            log_func=self.log_func,
        )

    @staticmethod
    def _iniciar_driver(headless: bool):
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options

        options = Options()
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--window-size=1920,1080")

        remote_url = os.getenv("SELENIUM_REMOTE_URL", "").strip()
        if remote_url:
            return webdriver.Remote(command_executor=remote_url, options=options)

        return webdriver.Chrome(options=options)


class NoopFetcher:
    """Used for fast extraction-only flows (without Selenium calls)."""

    def fetch(self, codigo: str) -> tuple[str, str, str]:
        if not codigo:
            return "", "", "sem_codigo"
        return "", "", "sem_consulta"


def _wait_ready(driver, timeout: int = 40) -> None:
    from selenium.webdriver.support.ui import WebDriverWait

    WebDriverWait(driver, timeout).until(lambda d: d.execute_script("return document.readyState") == "complete")


def _wait_asset_detail_ready(driver, timeout: int = 20) -> None:
    """
    Wait until the detail page is effectively ready for scraping fields.
    Accepts either:
    - detail blocks rendered
    - explicit no-result messages rendered
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait

    _wait_ready(driver, timeout=timeout)

    def _detail_or_no_result(drv) -> bool:
        url = (drv.current_url or "").lower()
        if "/caracteristicas" in url or "/ativo/" in url:
            return True
        if drv.find_elements(By.CSS_SELECTOR, "dl.list-item__items"):
            return True
        if drv.find_elements(By.CSS_SELECTOR, "dl#cri-cra-item-Remunera\\00e7\\00e3o-0 dd"):
            return True
        if drv.find_elements(By.CSS_SELECTOR, "dl#cri-cra-item-data-vencimento-0 dd"):
            return True
        if drv.find_elements(By.CSS_SELECTOR, "dl#debentures-item-remuneracao-0 dd"):
            return True
        if drv.find_elements(By.CSS_SELECTOR, "dl#debentures-item-data-vencimento-0 dd"):
            return True
        try:
            body_text = (
                drv.execute_script("return ((document.body && document.body.innerText) || '').toLowerCase()") or ""
            )
            if (
                "nenhum resultado" in body_text
                or "não encontramos" in body_text
                or "nao encontramos" in body_text
            ):
                return True
        except Exception:
            pass
        return False

    WebDriverWait(driver, timeout).until(_detail_or_no_result)


def _dismiss_cookie_banner_if_present(driver) -> bool:
    from selenium.webdriver.common.by import By

    candidates = [
        (By.XPATH, "//button[contains(., 'Prosseguir')]"),
        (By.XPATH, "//*[self::button or @role='button'][contains(., 'Prosseguir')]"),
        (By.XPATH, "//*[contains(@class, 'cookie')]//*[self::button or @role='button']"),
    ]
    for by, sel in candidates:
        try:
            elements = driver.find_elements(by, sel)
            if not elements:
                continue
            btn = elements[0]
            try:
                btn.click()
            except Exception:
                driver.execute_script("arguments[0].click();", btn)
            return True
        except Exception:
            continue
    return False


def _is_on_expected_asset(driver, codigo: str) -> bool:
    code = (codigo or "").strip().upper()
    if not code:
        return False

    cur_url = (driver.current_url or "").upper()
    if code in cur_url:
        return True

    try:
        title = (driver.title or "").upper()
        if code in title:
            return True
    except Exception:
        pass

    try:
        body_text = (driver.execute_script("return (document.body && document.body.innerText) || ''") or "").upper()
        return code in body_text
    except Exception:
        return False


def _locate_search_input(driver, timeout: int = 40):
    from selenium.common.exceptions import TimeoutException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    wait = WebDriverWait(driver, timeout)
    selectors = [
        (By.CSS_SELECTOR, 'input[data-cy="input-base"]'),
        (By.CSS_SELECTOR, 'input[data-test-cy="searchInput"]'),
        (By.CSS_SELECTOR, "input#search"),
    ]
    for by, selector in selectors:
        try:
            return wait.until(EC.element_to_be_clickable((by, selector)))
        except TimeoutException:
            continue
    raise TimeoutException("Search input not found")


def _open_first_result_if_needed(driver, codigo: str, timeout: int = 20) -> None:
    from selenium.common.exceptions import TimeoutException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    # Already in detail page.
    if "/ativo/" in (driver.current_url or "").lower():
        return

    # Fast-path: do not block for the full timeout if detail page is already visible.
    if driver.find_elements(By.CSS_SELECTOR, "dl.list-item__items"):
        return

    links = [
        (
            By.XPATH,
            f"(//a[contains(@href,'/ativo/') and contains(translate(normalize-space(.), 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), '{codigo.upper()}')])[1]",
        ),
        (
            By.XPATH,
            f"(//a[contains(translate(normalize-space(.), 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), '{codigo.upper()}')])[1]",
        ),
        (
            By.XPATH,
            f"(//*[contains(translate(normalize-space(.), 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), '{codigo.upper()}')]/ancestor::a[1])[1]",
        ),
        (
            By.XPATH,
            f"(//*[contains(translate(normalize-space(.), 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), '{codigo.upper()}')]/ancestor::*[@role='link'][1])[1]",
        ),
        (
            By.XPATH,
            f"(//*[contains(translate(normalize-space(.), 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), '{codigo.upper()}')]/ancestor::*[@role='button'][1])[1]",
        ),
        (By.XPATH, "(//a[contains(@href,'/ativo/')])[1]"),
        (By.XPATH, "(//main//a)[1]"),
    ]
    wait = WebDriverWait(driver, min(timeout, 12))
    for by, locator in links:
        try:
            link = wait.until(EC.element_to_be_clickable((by, locator)))
            href = (link.get_attribute("href") or "").lower()
            text = (link.text or "").lower()
            if "/ativo/" in href or codigo.lower() in text or link.get_attribute("role") in {"link", "button"}:
                try:
                    link.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", link)
                _wait_asset_detail_ready(driver, timeout=timeout)
                if _is_on_expected_asset(driver, codigo):
                    return
        except TimeoutException:
            continue
        except Exception:
            continue

    # Last-resort JS fallback: find a node containing the code and click closest clickable ancestor.
    try:
        clicked = driver.execute_script(
            """
            const code = (arguments[0] || '').toUpperCase();
            const root = document.querySelector('main') || document.body;
            const all = root.querySelectorAll('*');
            for (const el of all) {
              const txt = (el.textContent || '').toUpperCase();
              if (!txt.includes(code)) continue;
              const target = el.closest('a,button,[role="link"],[role="button"]');
              if (!target) continue;
              target.click();
              return true;
            }
            return false;
            """,
            codigo,
        )
        if clicked:
            _wait_asset_detail_ready(driver, timeout=timeout)
            if _is_on_expected_asset(driver, codigo):
                return
    except Exception:
        pass


def _capture_fields(driver, timeout: int = 20) -> tuple[str, str]:
    from selenium.common.exceptions import NoSuchElementException, TimeoutException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    wait = WebDriverWait(driver, max(3, min(timeout, 12)))
    taxa = ""
    venc = ""

    # Fast non-blocking lookup for known IDs (CRI/CRA + Debenture).
    taxa_selectors = [
        # CRI/CRA
        (By.CSS_SELECTOR, "dl#cri-cra-item-Remunera\\00e7\\00e3o-0 dd"),
        (By.CSS_SELECTOR, "dl#cri-cra-item-remuneracao-0 dd"),
        (By.XPATH, "//*[@id='cri-cra-item-Remuneração-0']//dd"),
        (By.XPATH, "//*[@id='cri-cra-item-remuneracao-0']//dd"),
        # Debenture
        (By.CSS_SELECTOR, "dl#debentures-item-remuneracao-0 dd"),
        (By.XPATH, "//*[@id='debentures-item-remuneracao-0']//dd"),
    ]
    for by, selector in taxa_selectors:
        try:
            found = driver.find_elements(by, selector)
            if found:
                taxa = (found[0].text or "").strip()
                if taxa:
                    break
        except Exception:
            continue

    venc_selectors = [
        (By.CSS_SELECTOR, "dl#cri-cra-item-data-vencimento-0 dd"),
        (By.XPATH, "//*[@id='cri-cra-item-data-vencimento-0']//dd"),
        (By.CSS_SELECTOR, "dl#debentures-item-data-vencimento-0 dd"),
        (By.XPATH, "//*[@id='debentures-item-data-vencimento-0']//dd"),
    ]
    for by, selector in venc_selectors:
        try:
            found = driver.find_elements(by, selector)
            if found:
                venc = (found[0].text or "").strip()
                if venc:
                    break
        except Exception:
            continue

    if taxa and venc:
        return taxa, venc

    try:
        blocks = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "dl.list-item__items")))
    except TimeoutException:
        blocks = []

    for block in blocks:
        try:
            dt_text = block.find_element(By.TAG_NAME, "dt").text.strip()
            dd_text = block.find_element(By.TAG_NAME, "dd").text.strip()
        except NoSuchElementException:
            continue
        normalized = _normalize_text(dt_text)
        if (
            "remuneracao" in normalized
            or "taxa indicativa" in normalized
            or "taxa" == normalized
            or "juros" in normalized
        ) and not taxa:
            taxa = dd_text
        if ("data de vencimento" in normalized or "vencimento" in normalized) and not venc:
            venc = dd_text
        if taxa and venc:
            break

    # Last fallback by label text -> first sibling <dd>.
    if not taxa:
        try:
            taxa_dd = driver.find_elements(
                By.XPATH,
                "//dt[contains(translate(normalize-space(.),"
                " 'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇabcdefghijklmnopqrstuvwxyz',"
                " 'AAAAAEEEEIIIIOOOOOUUUUCABCDEFGHIJKLMNOPQRSTUVWXYZ'),"
                " 'REMUNERACAO')]/following-sibling::dd[1]",
            )
            if taxa_dd:
                taxa = (taxa_dd[0].text or "").strip()
        except Exception:
            pass
    if not venc:
        try:
            venc_dd = driver.find_elements(
                By.XPATH,
                "//dt[contains(translate(normalize-space(.),"
                " 'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇabcdefghijklmnopqrstuvwxyz',"
                " 'AAAAAEEEEIIIIOOOOOUUUUCABCDEFGHIJKLMNOPQRSTUVWXYZ'),"
                " 'DATA DE VENCIMENTO')]/following-sibling::dd[1]",
            )
            if venc_dd:
                venc = (venc_dd[0].text or "").strip()
        except Exception:
            pass

    if taxa and venc:
        return taxa, venc

    # Fallback: extract values from raw HTML when SPA rendered DOM is incomplete.
    try:
        html = driver.page_source or ""
        taxa_match = re.search(
            r"Remunera(?:ç|c)(?:a|ã)o.*?<dd[^>]*>(.*?)</dd>",
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        venc_match = re.search(
            r"Data\\s*de\\s*vencimento.*?<dd[^>]*>(.*?)</dd>",
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if taxa_match and not taxa:
            taxa = re.sub(r"<[^>]+>", "", taxa_match.group(1)).strip()
        if venc_match and not venc:
            venc = re.sub(r"<[^>]+>", "", venc_match.group(1)).strip()
    except Exception:
        pass

    return taxa, venc


def _get_body_text(driver) -> str:
    try:
        return (driver.execute_script("return (document.body && document.body.innerText) || ''") or "").replace(
            "\xa0", " "
        )
    except Exception:
        return ""


def _detect_card_type(compact_text: str, code_index: int, window: str) -> str:
    txt = (compact_text or "").lower()
    if txt and code_index > 0:
        prefix = txt[:code_index]
        last_deb = max(prefix.rfind("debêntures ("), prefix.rfind("debentures ("))
        last_cri = prefix.rfind("cris e cras (")
        if last_deb >= 0 or last_cri >= 0:
            return "debenture" if last_deb > last_cri else "cri_cra"

    near = (window or "")[:900].lower()
    if "debêntures (" in near or "debentures (" in near or "lei 12.431" in near or "pu par" in near:
        return "debenture"
    if "cris e cras (" in near or "securitizadora" in near or "série e emissão" in near or "devedor" in near:
        return "cri_cra"
    return "desconhecido"


def _capture_fields_from_busca_text(body_text: str, codigo: str) -> tuple[str, str, str]:
    if not body_text:
        return "", "", "desconhecido"

    compact = re.sub(r"\s+", " ", body_text).strip()
    code = (codigo or "").strip().upper()
    if not compact or not code:
        return "", "", "desconhecido"

    # Focus parsing around the searched code to avoid unrelated footer/header text.
    upper = compact.upper()
    idx = upper.find(code)
    window = compact[idx : idx + 2600] if idx >= 0 else compact[:2600]

    card_type = _detect_card_type(compact, idx, window)
    taxa = ""
    venc = ""

    if card_type == "debenture":
        taxa_match = re.search(
            r"Remunera(?:ç|c)(?:a|ã)o\s*(.*?)\s*(?:Data de vencimento|Duration|Setor|Data da emiss[aã]o|PU PAR|PU Indicativo|Ver resultados de)",
            window,
            flags=re.IGNORECASE,
        )
    else:
        taxa_match = re.search(
            r"Remunera(?:ç|c)(?:a|ã)o\s*(.*?)\s*(?:Duration|Securitizadora|Data da emiss[aã]o|Data de vencimento|PU Indicativo|Devedor|S[ée]rie e Emiss[aã]o|Ver resultados de)",
            window,
            flags=re.IGNORECASE,
        )
    if taxa_match:
        taxa = (taxa_match.group(1) or "").strip(" -|")

    venc_match = re.search(r"Data de vencimento\s*(\d{2}/\d{2}/\d{4})", window, flags=re.IGNORECASE)
    if venc_match:
        venc = (venc_match.group(1) or "").strip()

    return taxa, venc, card_type


def _wait_busca_content_ready(driver, codigo: str, timeout: int = 40) -> str:
    from selenium.webdriver.support.ui import WebDriverWait

    code = (codigo or "").strip().upper()

    def _condition(drv):
        text = _get_body_text(drv)
        if not text:
            return False
        lower = text.lower()
        if "não encontramos" in lower or "nao encontramos" in lower or "nenhum resultado" in lower:
            return text
        if code and code in text.upper():
            return text
        return False

    return WebDriverWait(driver, timeout).until(_condition)


def _click_ver_detalhes_if_available(driver) -> bool:
    from selenium.webdriver.common.by import By

    selectors = [
        (By.XPATH, "(//a[contains(., 'Ver detalhes')])[1]"),
        (By.XPATH, "(//button[contains(., 'Ver detalhes')])[1]"),
        (By.XPATH, "(//*[(@role='button' or @role='link') and contains(., 'Ver detalhes')])[1]"),
    ]
    for by, sel in selectors:
        try:
            elems = driver.find_elements(by, sel)
            if not elems:
                continue
            el = elems[0]
            try:
                el.click()
            except Exception:
                driver.execute_script("arguments[0].click();", el)
            return True
        except Exception:
            continue
    return False


def _buscar_dados_anbima(
    driver,
    codigo: str,
    max_tentativas: int = 2,
    timeout: int = 40,
    log_func: LogFn = None,
) -> tuple[str, str, str]:
    from selenium.common.exceptions import TimeoutException, WebDriverException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    if not codigo:
        if log_func:
            log_func("Sem codigo para consulta")
        return "", "", "sem_codigo"

    def _timeout_context() -> str:
        try:
            from selenium.webdriver.common.by import By

            current_url = (driver.current_url or "")[:140]
            title = (driver.title or "")[:100]
            links = len(driver.find_elements(By.CSS_SELECTOR, 'a[href*="/ativo/"]'))
            dls = len(driver.find_elements(By.CSS_SELECTOR, "dl.list-item__items"))
            body = (
                driver.execute_script("return ((document.body && document.body.innerText) || '').toLowerCase()") or ""
            )
            has_no_result = (
                "não encontramos" in body or "nao encontramos" in body or "nenhum resultado" in body
            )
            return (
                f"url='{current_url}' title='{title}' links_ativo={links} dl_items={dls} "
                f"has_no_result={str(has_no_result).lower()}"
            )
        except Exception:
            return "contexto_timeout_indisponivel"

    for tentativa in range(1, max_tentativas + 1):
        try:
            t0 = time.perf_counter()
            if log_func:
                log_func(f"Consultando ANBIMA para codigo={codigo} (tentativa {tentativa}/{max_tentativas})")
            driver.get(f"{ANBIMA_BUSCA_URL}?q={quote_plus(codigo)}")
            _wait_ready(driver, timeout=timeout)
            if _dismiss_cookie_banner_if_present(driver) and log_func:
                log_func("Banner de cookie aceito automaticamente")
            body_text = _wait_busca_content_ready(driver, codigo, timeout=timeout)
            taxa, venc, card_type = _capture_fields_from_busca_text(body_text, codigo)
            if not taxa and not venc:
                page = body_text.lower()
                if "nenhum resultado" in page or "nao encontramos" in page or "não encontramos" in page:
                    if log_func:
                        log_func(f"Codigo {codigo}: nao encontrado")
                    return "", "", "nao_encontrado"
                if log_func:
                    log_func(f"Codigo {codigo}: sem campos de retorno")
                return "", "", "sem_campos"
            if log_func:
                elapsed = time.perf_counter() - t0
                log_func(
                    f"Codigo {codigo}: consulta OK em {elapsed:.2f}s (tipo={card_type}) "
                    f"(taxa='{taxa or 'N/A'}', vencimento='{venc or 'N/A'}')"
                )
            return taxa, venc, "ok"
        except TimeoutException:
            if log_func:
                log_func(f"Codigo {codigo}: timeout na tentativa {tentativa}")
                log_func(f"Codigo {codigo}: contexto timeout -> {_timeout_context()}")
            if tentativa == max_tentativas:
                return "", "", "timeout"
            continue
        except WebDriverException:
            if log_func:
                log_func(f"Codigo {codigo}: erro webdriver na tentativa {tentativa}")
            if tentativa == max_tentativas:
                return "", "", "webdriver_error"
            continue
        except Exception:
            if log_func:
                log_func(f"Codigo {codigo}: erro inesperado na tentativa {tentativa}")
            if tentativa == max_tentativas:
                return "", "", "erro"
            continue

    return "", "", "erro"


def processar_dataframe(
    df,
    fetcher: AtivoDataFetcher,
    save_every: int = 10,
    progress_path: Optional[Path] = None,
    log_func: LogFn = None,
) :
    if COL_ATIVO_ORIGINAL not in df.columns:
        raise ValueError(f"Coluna obrigatoria ausente: '{COL_ATIVO_ORIGINAL}'")

    output = df.copy().fillna("")
    for col in [COL_CODIGO_ATIVO, COL_TAXA, COL_DATA_VENCIMENTO, COL_STATUS]:
        if col not in output.columns:
            output[col] = ""

    processed_count = 0
    total_rows = len(output.index)
    if log_func:
        log_func(f"Total de linhas para processar: {total_rows}")
    for idx, row in output.iterrows():
        status = str(row.get(COL_STATUS, "")).strip().lower()
        if status and status not in {"erro", "timeout", "webdriver_error"}:
            if log_func:
                log_func(f"Linha {idx + 1}/{total_rows}: ja processada anteriormente (status={status}), pulando")
            continue

        original = str(row.get(COL_ATIVO_ORIGINAL, "")).strip()
        codigo = str(row.get(COL_CODIGO_ATIVO, "")).strip() or extrair_codigo_ativo(original)
        output.at[idx, COL_CODIGO_ATIVO] = codigo
        if log_func:
            log_func(f"Linha {idx + 1}/{total_rows}: ativo='{original[:80]}' codigo='{codigo or '-'}'")

        if not codigo:
            output.at[idx, COL_TAXA] = ""
            output.at[idx, COL_DATA_VENCIMENTO] = ""
            output.at[idx, COL_STATUS] = "sem_codigo"
            if log_func:
                log_func(f"Linha {idx + 1}/{total_rows}: sem codigo extraido")
        else:
            taxa, venc, fetch_status = fetcher.fetch(codigo)
            output.at[idx, COL_TAXA] = taxa or "N/A"
            output.at[idx, COL_DATA_VENCIMENTO] = venc or "N/A"
            output.at[idx, COL_STATUS] = fetch_status
            if log_func:
                log_func(
                    f"Linha {idx + 1}/{total_rows}: status={fetch_status} taxa='{output.at[idx, COL_TAXA]}' "
                    f"vencimento='{output.at[idx, COL_DATA_VENCIMENTO]}'"
                )

        processed_count += 1
        if progress_path and processed_count % max(1, save_every) == 0:
            output.to_csv(progress_path, index=False, encoding="utf-8-sig")
            if log_func:
                log_func(f"Checkpoint salvo ({processed_count} linhas processadas)")

    return output


def processar_csv_arquivo(
    input_path: Path,
    output_path: Path,
    *,
    use_selenium: bool = True,
    headless: bool = True,
    save_every: int = 10,
    log_func: LogFn = None,
) -> Path:
    import pandas as pd

    if log_func:
        log_func(f"Lendo CSV de entrada: {input_path}")
    df = pd.read_csv(input_path, dtype=str).fillna("")
    progress_path = output_path.with_suffix(".progress.csv")
    if log_func:
        log_func(f"CSV carregado com {len(df.index)} linhas")

    if use_selenium:
        with SeleniumAnbimaFetcher(SeleniumConfig(headless=headless), log_func=log_func) as fetcher:
            result = processar_dataframe(
                df,
                fetcher,
                save_every=save_every,
                progress_path=progress_path,
                log_func=log_func,
            )
    else:
        if log_func:
            log_func("Processamento sem Selenium (somente extracao de codigo)")
        result = processar_dataframe(
            df,
            NoopFetcher(),
            save_every=save_every,
            progress_path=progress_path,
            log_func=log_func,
        )

    final_cols = [COL_ATIVO_ORIGINAL, COL_CODIGO_ATIVO, COL_TAXA, COL_DATA_VENCIMENTO]
    if log_func:
        log_func("Gerando CSV final...")
    result[final_cols].to_csv(output_path, index=False, encoding="utf-8-sig")
    result.to_csv(progress_path, index=False, encoding="utf-8-sig")
    if log_func:
        log_func(f"CSV final gerado: {output_path}")
    return output_path
