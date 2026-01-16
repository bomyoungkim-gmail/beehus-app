import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

PAIR_RE = re.compile(r"(\d)\s*ou\s*(\d)")


def build_digit_to_button_map(driver, timeout=50):
    """
    Mapeia dígitos (0-9) para botões do teclado digital do Itaú.
    
    Args:
        driver: WebDriver instance
        timeout: Tempo máximo de espera em segundos
        
    Returns:
        dict: Mapeamento de dígito (str) para elemento WebElement
        
    Raises:
        RuntimeError: Se não conseguir mapear todos os dígitos 0-9
    """
    wait = WebDriverWait(driver, timeout)
    
    container = wait.until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "div.it-auth-keyboard__digits"))
    )
    # pega apenas botões "normais" (exclui o de apagar)
    buttons = container.find_elements(
        By.CSS_SELECTOR, "button.it-auth-keyboard__digit:not(.it-auth-keyboard__digit--remove)"
    )

    digit_to_btn = {}

    for btn in buttons:
        label = btn.text.strip()
    
        m = PAIR_RE.search(label)
    
        if not m:
            continue
    
        d1, d2 = m.group(1), m.group(2)
    
        digit_to_btn[d1] = btn
        digit_to_btn[d2] = btn

    # valida se mapeou tudo (0-9)
    missing = [str(d) for d in range(10) if str(d) not in digit_to_btn]

    if missing:
        raise RuntimeError(f"Não consegui mapear estes dígitos no teclado: {missing}")

    return digit_to_btn