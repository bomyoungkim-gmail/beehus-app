from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime, date
from selenium.webdriver.common.keys import Keys
from typing import Callable, Optional, Tuple

import time
from datetime import datetime

PT_MONTHS = {
    1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril", 5: "maio", 6: "junho",
    7: "julho", 8: "agosto", 9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro",
}

Locator = Tuple[By, str]

class SeleniumHelpers:
    def __init__(self, driver, timeout=50):
        self.driver = driver
        self.wait = WebDriverWait(driver, timeout)
    

    # clickable element
    def click_element(self, by, value):
        element = self.wait.until(
            EC.element_to_be_clickable((by, value))
        )
        element.click()

    def click_element_maybe_shadow(self, by, value):
        element = self._find_element_maybe_shadow(by, value)
        self.wait.until(lambda d: element.is_displayed() and element.is_enabled())
        element.click()

    # any clickable elements
    def click_any_element(self, by, values: list):
        element = self.wait.until(
            EC.any_of(
                *[EC.element_to_be_clickable((by, v)) for v in values]
            )
        )
        element.click()


    def find_element(self, by, value):
        element = self.wait.until(
            EC.presence_of_element_located((by, value))
        )
        # element.click()
        return element
    

    def find_any_element(self, by, values: list):
        element = self.wait.until(
            EC.any_of(
                *[EC.presence_of_element_located((by, v)) for v in values]
            )
        )
        # element.click()
        return element
    

    def hover_element(self, by, value):
        element = self.wait.until(EC.visibility_of_element_located((by, value)))
        ActionChains(self.driver).move_to_element(element).perform()
        try:
            self.wait.until(lambda d: element.get_attribute("aria-expanded") == "true")
            return element
        except Exception:
            self.driver.execute_script(
                "arguments[0].dispatchEvent(new MouseEvent('mouseover', {bubbles:true}));",
                element
            )
            self.wait.until(lambda d: element.get_attribute("aria-expanded") == "true")
            return element
    

    def wait_for_element(self, by, value):
        return self.wait.until(
            EC.presence_of_element_located((by, value))
        )

    def wait_for_visible(self, by, value):
        return self.wait.until(
            EC.visibility_of_element_located((by, value))
        )

    def wait_for_invisibility(self, by, value):
        return self.wait.until(
            EC.invisibility_of_element_located((by, value))
        )
    

    def send_keys(self, by, value, text):
        """Send keys to an input element."""
        element = self.find_element(by, value)
        element.send_keys(text)
    

    def clear_and_send_keys(self, by, value, text):
        """Clear and send keys to an input element."""
        element = self.find_element(by, value)
        element.click()
        element.send_keys(Keys.CONTROL, "a")
        element.send_keys(Keys.BACKSPACE)
        element.send_keys(text)

    
    def wait_until(self, condition, timeout: Optional[int] = None):
        """Generic wait for custom condition."""
        if timeout is None:
            return self.wait.until(condition)
        return WebDriverWait(self.driver, timeout).until(condition)

    def wait_ready_state(self, timeout_seconds: int = 30):
        """Wait until document.readyState is complete."""
        return WebDriverWait(self.driver, timeout_seconds).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )


    def _query_shadow_dom_css(self, selector: str):
        script = """
            const selector = arguments[0];
            const deepQuery = (root) => {
                const direct = root.querySelector(selector);
                if (direct) return direct;
                const nodes = root.querySelectorAll('*');
                for (const node of nodes) {
                    if (node.shadowRoot) {
                        const found = deepQuery(node.shadowRoot);
                        if (found) return found;
                    }
                }
                return null;
            };
            return deepQuery(document);
        """
        return self.driver.execute_script(script, selector)


    def _find_element_maybe_shadow(self, by, value, timeout: Optional[int] = None):
        wait = self.wait if timeout is None else WebDriverWait(self.driver, timeout)
        if by == By.CSS_SELECTOR:
            try:
                el = wait.until(lambda d: self._query_shadow_dom_css(value))
                if el:
                    return el
            except Exception:
                pass
        return wait.until(EC.presence_of_element_located((by, value)))

    def _resolve_datepicker_trigger(self, trigger_locator):
        by, value = trigger_locator
        fallback_locators = [
            (by, value),
            (
                By.CSS_SELECTOR,
                "input[inputmode='none'], input[idsmask*='date'], input[placeholder*='DD/MM'], "
                "input[placeholder*='dd/mm'], ids-datepicker input, "
                "button[aria-label*='calend' i], button[aria-haspopup='dialog'][aria-label*='data' i], "
                "ids-datepicker button"
            ),
            (
                By.XPATH,
                "//ids-datepicker//*[self::input or self::button]"
            ),
        ]

        for locator in fallback_locators:
            try:
                el = self._find_element_maybe_shadow(*locator, timeout=8)
                if el and el.is_displayed() and el.is_enabled():
                    return el
            except Exception:
                continue

        raise RuntimeError(
            f"Nao foi possivel localizar o trigger do datepicker usando locator principal: {trigger_locator}"
        )


    def _set_input_value_js(self, el, date_str: str) -> bool:
        script = """
            const el = arguments[0];
            const val = arguments[1];

            const setter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype,
                'value'
            ).set;
            setter.call(el, val);

            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            el.dispatchEvent(new Event('blur', { bubbles: true }));
        """
        self.driver.execute_script(script, el, date_str)
        return (el.get_attribute("value") or "").strip() == date_str


    def set_date_ddmmyyyy(self, primary: Locator, fallback: Optional[Locator], date_str: str) -> None:
        """
        Tenta setar data DD/MM/YYYY em inputs de dois tipos:
        - typeable (idsmask/date)
        - datepicker overlay (idsdatepicker, inputmode=none)
        """
        last_err: Optional[Exception] = None

        for loc in [primary, fallback]:
            if not loc:
                continue
            try:
                el = self.wait.until(EC.presence_of_element_located(loc))
                self._set_date_on_element(el, date_str)
                return
            except Exception as e:
                last_err = e

        raise last_err or RuntimeError("Não foi possível localizar nenhum campo de data para edição.")


    def _set_date_on_element(self, el, date_str: str) -> None:
        # Detecta “datepicker” vs “typeable”
        inputmode = (el.get_attribute("inputmode") or "").strip().lower()
        role = (el.get_attribute("role") or "").strip().lower()

        if inputmode == "none" or role == "combobox":
            self._set_date_via_datepicker_overlay(el, date_str)
        else:
            self._set_date_via_typing(el, date_str)


    def _set_date_via_typing(self, el, date_str: str) -> None:
        # Seu caso: após clicar, ESC libera edição
        el.click()
        el.send_keys(Keys.ESCAPE)
        el.send_keys(Keys.CONTROL, "a")
        el.send_keys(Keys.BACKSPACE)
        el.send_keys(date_str)
        el.send_keys(Keys.ENTER)

        self.wait.until(lambda d: (el.get_attribute("value") or "").strip() == date_str)


    def _set_date_via_datepicker_overlay(self, el, date_str: str) -> None:
        # date_str = DD/MM/YYYY
        dt = datetime.strptime(date_str, "%d/%m/%Y")
        day = dt.day
        month_pt = PT_MONTHS[dt.month]
        year = dt.year

        el.click()

        # Aguarda o modal do datepicker aparecer (overlay)
        modal = self.wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "section.ids-datepicker.ids-modal"))
        )

        # Clica no dia pelo aria-label (ex.: "quinta-feira 1 janeiro 2026") :contentReference[oaicite:6]{index=6}
        day_btn_xpath = (
            f".//button[contains(@class,'ids-calendar-day') and "
            f"contains(@aria-label, '{day} {month_pt} {year}')]"
        )
        day_btn = self.wait.until(lambda m: modal.find_element(By.XPATH, day_btn_xpath))
        day_btn.click()

        # Confirma: tenta botão "confirmar" do datepicker/modal ou o contextual #btn-confirmar :contentReference[oaicite:7]{index=7}
        # (sem depender de uma classe única)
        confirm_candidates = [
            (By.XPATH, ".//button[normalize-space()='confirmar' or .//span[normalize-space()='Confirmar']]"),
            (By.CSS_SELECTOR, "button#btn-confirmar"),
        ]
        clicked = False
        for by, sel in confirm_candidates:
            try:
                btn = modal.find_element(by, sel) if by == By.XPATH else self.driver.find_element(by, sel)
                if btn.is_displayed() and btn.is_enabled():
                    btn.click()
                    clicked = True
                    break
            except Exception:
                continue

        if not clicked:
            # Se não houver botão explícito, fecha com ESC (alguns datepickers aplicam seleção no click)
            el.send_keys(Keys.ESCAPE)

        # Espera o value refletir
        self.wait.until(lambda d: (el.get_attribute("value") or "").strip() == date_str)


    def set_angular_datepicker(self, trigger_locator, overlay_locator,
                            day_selector_template, day_alt_template, 
                            confirm_locator, date_str):
        """
        Interage com datepicker Angular usando abordagem híbrida.
        Tenta 3 estratégias: input direto, JavaScript, UI interaction.
        
        Args:
            trigger_locator: Seletor do elemento que abre o datepicker
            overlay_locator: Seletor do overlay/modal do datepicker
            day_selector_template: Template XPath para botão do dia
            day_alt_template: Template XPath alternativo
            confirm_locator: Seletor do botão confirmar
            date_str: Data no formato DD/MM/YYYY
        """

        
        # ESTRATÉGIA 1: Input direto (mais rápido)
        try:
            date_input = self._resolve_datepicker_trigger(trigger_locator)
            if date_input and date_input.is_displayed() and date_input.is_enabled():
                if self._set_input_value_js(date_input, date_str):
                    return  # Sucesso!
                date_input.click()
                date_input.send_keys(Keys.ESCAPE)
                date_input.send_keys(Keys.CONTROL, "a")
                date_input.send_keys(Keys.BACKSPACE)
                date_input.send_keys(date_str)
                date_input.send_keys(Keys.TAB)
                time.sleep(1)
                if (date_input.get_attribute("value") or "").strip() == date_str:
                    return  # Sucesso!
        except Exception:
            pass

        # ESTRATÉGIA 2: JavaScript Executor
        try:
            date_input = self.driver.find_element(By.XPATH, "//input[contains(@class, 'ids-')]")
            self._set_input_value_js(date_input, date_str)
            time.sleep(1)
            if date_input.get_attribute("value") == date_str:
                return  # Sucesso!
        except Exception:
            pass

        # ESTRATÉGIA 3: UI Interaction (calendário)
        dt = datetime.strptime(date_str, "%d/%m/%Y")
        dia = dt.day
        mes = PT_MONTHS[dt.month]
        ano = dt.year
        
        try:
            trigger = self._resolve_datepicker_trigger(trigger_locator)
        except Exception as e:
            raise RuntimeError("Nao foi possivel localizar o trigger do datepicker.") from e
        self.wait.until(lambda d: trigger.is_displayed() and trigger.is_enabled())
        trigger.click()
        
        try:
            self._find_element_maybe_shadow(*overlay_locator)
        except Exception:
            pass
        
        time.sleep(1)
        
        day_xpath = day_selector_template.format(dia=dia, mes=mes, ano=ano)
        try:
            day_button = self.find_element(By.XPATH, day_xpath)
            day_button.click()
        except Exception:
            day_xpath_alt = day_alt_template.format(dia=dia, mes=mes, ano=ano)
            day_button = self.find_element(By.XPATH, day_xpath_alt)
            day_button.click()
        
        time.sleep(1)
        
        try:
            confirm_btn = self.find_element(*confirm_locator)
            confirm_btn.click()
        except Exception:
            pass
        
        try:
            self.wait.until(EC.invisibility_of_element_located(overlay_locator))
        except:
            time.sleep(2)
