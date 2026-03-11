"""
Conferencia ativo - consulta ANBIMA com Selenium

Instalacao (Python 3):
    pip install selenium pandas openpyxl

Opcional (recomendado para facilitar o ChromeDriver local):
    pip install webdriver-manager
"""

from __future__ import annotations

import logging
import re
import time
import unicodedata
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
from selenium.webdriver import Chrome
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

try:
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager

    HAS_WEBDRIVER_MANAGER = True
except Exception:
    HAS_WEBDRIVER_MANAGER = False


INPUT_FILE = "entrada.csv"
OUTPUT_FILE = "saida_final.csv"
PROGRESS_FILE = "saida_final.progress.csv"

ANBIMA_BUSCA_URL = "https://data.anbima.com.br/busca"
SAVE_EVERY_N_ROWS = 10
DEFAULT_WAIT_SECONDS = 20

COL_ATIVO_ORIGINAL = "Ativo Original"
COL_CODIGO_ATIVO = "Codigo Ativo"
COL_TAXA = "Taxa"
COL_DATA_VENCIMENTO = "Data Vencimento"
COL_STATUS = "_status"


def normalizar_texto(texto: str) -> str:
    """Remove acentos e normaliza para comparacoes flexiveis."""
    if texto is None:
        return ""
    texto_norm = unicodedata.normalize("NFKD", str(texto))
    return "".join(ch for ch in texto_norm if not unicodedata.combining(ch)).lower().strip()


def extrair_codigo_ativo(texto: str) -> str:
    """
    Extrai codigo de ativo para CRA, CRI e Debentures.
    Retorna string vazia quando nao encontra.
    """
    if texto is None or (isinstance(texto, float) and pd.isna(texto)):
        return ""

    texto_limpo = str(texto).strip()
    if not texto_limpo:
        return ""

    texto_upper = texto_limpo.upper()

    # 1) CRA: exemplo CRA021002N3
    if "CRA" in texto_upper:
        match_cra = re.search(r"\b(CRA[A-Z0-9]{6,})\b", texto_upper)
        if match_cra:
            return match_cra.group(1).strip()

    # 2) CRI: exemplo "CRI 23J1255114"
    if "CRI" in texto_upper:
        match_cri = re.search(r"\bCRI\s+([0-9]{2}[A-Z][0-9]{7,})\b", texto_upper)
        if match_cri:
            return match_cri.group(1).strip()

    # 3) Debenture: exemplos "DEB FLU U RUMOA6", "DEB PRE ABCD12"
    if "DEB" in texto_upper:
        match_deb = re.search(r"\bDEB\s+(?:FLU|PRE)(?:\s+DU|\s+U)?\s+([A-Z0-9]{5,})\b", texto_upper)
        if match_deb:
            return match_deb.group(1).strip()

    return ""


def iniciar_driver(headless: bool = False) -> Chrome:
    """Inicia o Chrome com Selenium, usando webdriver-manager quando disponivel."""
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")

    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")

    if HAS_WEBDRIVER_MANAGER:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
    else:
        driver = webdriver.Chrome(options=chrome_options)

    driver.set_page_load_timeout(60)
    return driver


def esperar_pagina_pronta(driver: Chrome, timeout: int = DEFAULT_WAIT_SECONDS) -> None:
    """Espera document.readyState == complete."""
    WebDriverWait(driver, timeout).until(lambda d: d.execute_script("return document.readyState") == "complete")


def localizar_input_busca(driver: Chrome, timeout: int = DEFAULT_WAIT_SECONDS):
    """
    Tenta localizar o campo de busca nos seletores prioritarios.
    """
    wait = WebDriverWait(driver, timeout)
    seletores = [
        (By.CSS_SELECTOR, 'input[data-cy="input-base"]'),
        (By.CSS_SELECTOR, 'input[data-test-cy="searchInput"]'),
        (By.CSS_SELECTOR, "input#search"),
    ]

    ultimo_erro: Optional[Exception] = None
    for by, selector in seletores:
        try:
            return wait.until(EC.element_to_be_clickable((by, selector)))
        except Exception as exc:
            ultimo_erro = exc
            continue

    raise TimeoutException(f"Nao foi possivel localizar input de busca. Ultimo erro: {ultimo_erro}")


def abrir_primeiro_resultado_se_necessario(driver: Chrome, codigo: str, timeout: int = 12) -> None:
    """
    Se a busca exibir lista de resultados, clica no primeiro item.
    Se ja estiver no detalhe, nao faz nada.
    """
    wait = WebDriverWait(driver, timeout)

    # Se os campos de detalhe ja estao visiveis, nao precisa clicar em resultado.
    try:
        wait.until(
            EC.any_of(
                EC.presence_of_element_located((By.CSS_SELECTOR, "dl.list-item__items")),
                EC.presence_of_element_located((By.XPATH, "//*[@id='cri-cra-item-Remuneração-0']//dd")),
                EC.presence_of_element_located((By.XPATH, "//*[@id='cri-cra-item-data-vencimento-0']//dd")),
            )
        )
        return
    except TimeoutException:
        pass

    # Tenta clicar em primeiro resultado da busca.
    candidatos = [
        (By.XPATH, "(//a[contains(@href,'/ativo/')])[1]"),
        (By.XPATH, f"(//a[contains(translate(normalize-space(.), 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), '{codigo.upper()}')])[1]"),
        (By.XPATH, "(//main//a)[1]"),
    ]

    for by, selector in candidatos:
        try:
            link = wait.until(EC.element_to_be_clickable((by, selector)))
            href = (link.get_attribute("href") or "").strip().lower()
            texto = (link.text or "").strip().lower()
            if "/ativo/" in href or codigo.lower() in texto:
                link.click()
                esperar_pagina_pronta(driver, timeout=timeout)
                return
        except TimeoutException:
            continue
        except WebDriverException:
            continue


def capturar_campos_ativo(driver: Chrome, timeout: int = 12) -> Tuple[str, str]:
    """
    Captura Remuneracao e Data de vencimento:
    1) Pelos IDs conhecidos
    2) Fallback por varredura de dl.list-item__items
    """
    wait = WebDriverWait(driver, timeout)
    taxa = ""
    vencimento = ""

    # 1) Tentativa por ID conhecido
    try:
        taxa_el = wait.until(EC.presence_of_element_located((By.XPATH, "//*[@id='cri-cra-item-Remuneração-0']//dd")))
        taxa = (taxa_el.text or "").strip()
    except TimeoutException:
        taxa = ""

    try:
        venc_el = wait.until(
            EC.presence_of_element_located((By.XPATH, "//*[@id='cri-cra-item-data-vencimento-0']//dd"))
        )
        vencimento = (venc_el.text or "").strip()
    except TimeoutException:
        vencimento = ""

    if taxa and vencimento:
        return taxa, vencimento

    # 2) Fallback por dt/dd em todos os blocos
    try:
        blocos = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "dl.list-item__items")))
    except TimeoutException:
        blocos = []

    for bloco in blocos:
        try:
            dt_text = bloco.find_element(By.TAG_NAME, "dt").text.strip()
            dd_text = bloco.find_element(By.TAG_NAME, "dd").text.strip()
        except NoSuchElementException:
            continue

        dt_norm = normalizar_texto(dt_text)
        if "remuneracao" in dt_norm and not taxa:
            taxa = dd_text
        if "data de vencimento" in dt_norm and not vencimento:
            vencimento = dd_text

        if taxa and vencimento:
            break

    return taxa, vencimento


def buscar_dados_anbima(driver: Chrome, codigo: str, max_tentativas: int = 2) -> Tuple[str, str, str]:
    """
    Busca dados do ativo na ANBIMA.
    Retorna (taxa, vencimento, status).
    """
    if not codigo:
        return "", "", "sem_codigo"

    for tentativa in range(1, max_tentativas + 1):
        try:
            driver.get(ANBIMA_BUSCA_URL)
            esperar_pagina_pronta(driver)

            campo_busca = localizar_input_busca(driver)
            campo_busca.click()
            campo_busca.send_keys(Keys.CONTROL, "a")
            campo_busca.send_keys(Keys.BACKSPACE)
            campo_busca.send_keys(codigo)
            campo_busca.send_keys(Keys.ENTER)

            # Pequena pausa complementar para disparo de renderizacao reativa.
            time.sleep(0.3)

            # Tenta abrir o resultado automaticamente quando necessario.
            abrir_primeiro_resultado_se_necessario(driver, codigo)

            # Aguarda algo de detalhe aparecer antes da captura.
            WebDriverWait(driver, 12).until(
                EC.any_of(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "dl.list-item__items")),
                    EC.presence_of_element_located((By.XPATH, "//*[contains(text(),'Remuneração')]")),
                    EC.presence_of_element_located((By.XPATH, "//*[contains(text(),'Data de vencimento')]")),
                )
            )

            taxa, vencimento = capturar_campos_ativo(driver, timeout=12)
            if not taxa and not vencimento:
                # Verifica mensagem de nenhum resultado
                pagina = driver.page_source.lower()
                if "nenhum resultado" in pagina or "não encontramos" in pagina or "nao encontramos" in pagina:
                    return "", "", "nao_encontrado"
                return "", "", "sem_campos"

            return taxa, vencimento, "ok"

        except TimeoutException as exc:
            logging.warning("Timeout ao buscar codigo %s (tentativa %s/%s): %s", codigo, tentativa, max_tentativas, exc)
            if tentativa == max_tentativas:
                return "", "", "timeout"
            continue
        except Exception as exc:  # noqa: BLE001
            logging.exception("Erro inesperado ao buscar codigo %s (tentativa %s/%s)", codigo, tentativa, max_tentativas)
            if tentativa == max_tentativas:
                return "", "", f"erro:{exc.__class__.__name__}"
            continue

    return "", "", "falha_desconhecida"


def salvar_progresso(df: pd.DataFrame, progress_file: str, output_file: str) -> None:
    """
    Salva arquivo de progresso com status e arquivo final com as 4 colunas.
    """
    df.to_csv(progress_file, index=False, encoding="utf-8-sig")
    df[[COL_ATIVO_ORIGINAL, COL_CODIGO_ATIVO, COL_TAXA, COL_DATA_VENCIMENTO]].to_csv(
        output_file, index=False, encoding="utf-8-sig"
    )


def carregar_base_com_retomada(input_file: str, output_file: str, progress_file: str) -> pd.DataFrame:
    """
    Carrega CSV de entrada e aplica retomada automatica, priorizando progress_file.
    """
    input_path = Path(input_file)
    if not input_path.exists():
        raise FileNotFoundError(f"Arquivo de entrada nao encontrado: {input_file}")

    df = pd.read_csv(input_path, dtype=str).fillna("")
    if COL_ATIVO_ORIGINAL not in df.columns:
        raise ValueError(f"Coluna obrigatoria ausente no CSV de entrada: '{COL_ATIVO_ORIGINAL}'")

    for col in [COL_CODIGO_ATIVO, COL_TAXA, COL_DATA_VENCIMENTO, COL_STATUS]:
        if col not in df.columns:
            df[col] = ""

    # Prioridade de retomada: progress file (tem status interno)
    progress_path = Path(progress_file)
    if progress_path.exists():
        saved = pd.read_csv(progress_path, dtype=str).fillna("")
        for col in [COL_CODIGO_ATIVO, COL_TAXA, COL_DATA_VENCIMENTO, COL_STATUS]:
            if col in saved.columns and len(saved) == len(df):
                df[col] = saved[col]
        logging.info("Retomada carregada de %s", progress_file)
        return df

    # Fallback: output final (sem status), se existir e tiver mesmo tamanho
    output_path = Path(output_file)
    if output_path.exists():
        saved = pd.read_csv(output_path, dtype=str).fillna("")
        for col in [COL_CODIGO_ATIVO, COL_TAXA, COL_DATA_VENCIMENTO]:
            if col in saved.columns and len(saved) == len(df):
                df[col] = saved[col]

        # Marca como processado se ja tem codigo ou taxa/vencimento.
        processado = (df[COL_CODIGO_ATIVO].str.strip() != "") | (df[COL_TAXA].str.strip() != "") | (
            df[COL_DATA_VENCIMENTO].str.strip() != ""
        )
        df.loc[processado, COL_STATUS] = "retomado"
        logging.info("Retomada parcial carregada de %s", output_file)

    return df


def processar_arquivo(input_file: str, output_file: str, progress_file: str = PROGRESS_FILE) -> None:
    """Processa o CSV de entrada e exporta CSV final com 4 colunas."""
    df = carregar_base_com_retomada(input_file, output_file, progress_file)
    driver: Optional[Chrome] = None

    try:
        driver = iniciar_driver(headless=False)

        total = len(df)
        logging.info("Total de linhas para analisar: %s", total)

        processadas_no_ciclo = 0
        for idx, row in df.iterrows():
            linha_humana = idx + 1
            status_atual = str(row.get(COL_STATUS, "")).strip().lower()

            if status_atual and status_atual not in {"erro", "timeout"}:
                continue

            ativo_original = str(row.get(COL_ATIVO_ORIGINAL, "")).strip()
            codigo = str(row.get(COL_CODIGO_ATIVO, "")).strip() or extrair_codigo_ativo(ativo_original)
            df.at[idx, COL_CODIGO_ATIVO] = codigo

            if not codigo:
                df.at[idx, COL_TAXA] = ""
                df.at[idx, COL_DATA_VENCIMENTO] = ""
                df.at[idx, COL_STATUS] = "sem_codigo"
                logging.info(
                    "[%s/%s] linha=%s codigo=%s taxa=%s vencimento=%s status=%s",
                    linha_humana,
                    total,
                    linha_humana,
                    "",
                    "",
                    "",
                    "sem_codigo",
                )
            else:
                taxa, vencimento, status = buscar_dados_anbima(driver, codigo, max_tentativas=2)
                df.at[idx, COL_TAXA] = taxa if taxa else "N/A"
                df.at[idx, COL_DATA_VENCIMENTO] = vencimento if vencimento else "N/A"
                df.at[idx, COL_STATUS] = status

                logging.info(
                    "[%s/%s] linha=%s codigo=%s taxa=%s vencimento=%s status=%s",
                    linha_humana,
                    total,
                    linha_humana,
                    codigo,
                    df.at[idx, COL_TAXA],
                    df.at[idx, COL_DATA_VENCIMENTO],
                    status,
                )

            processadas_no_ciclo += 1
            if processadas_no_ciclo % SAVE_EVERY_N_ROWS == 0:
                salvar_progresso(df, progress_file, output_file)
                logging.info("Progresso salvo (%s linhas processadas no ciclo).", processadas_no_ciclo)

        # Salva no final
        salvar_progresso(df, progress_file, output_file)
        logging.info("Processamento concluido. Arquivo final: %s", output_file)

    finally:
        if driver is not None:
            driver.quit()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    processar_arquivo(INPUT_FILE, OUTPUT_FILE, PROGRESS_FILE)
