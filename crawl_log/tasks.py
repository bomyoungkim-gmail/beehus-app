from celery import shared_task
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from contextlib import contextmanager
import time
from dotenv import load_dotenv
import os
from crawl_log.models import CrawlLog

# ---------------------------------------------------
# task hello
# ---------------------------------------------------
@shared_task
def hello():
  message = f'Olá, Mundo'
  return message


# ---------------------------------------------------
# scrap JPMorgan com Selenium Remoto
# ---------------------------------------------------
@contextmanager
def get_webdriver(retries=3, delay=2):
  """
  Get WebDriver - Selenium local ou remoto via Selenium Grid
  
  Args:
    retries: Número de tentativas de conexão
    delay: Delay entre tentativas (segundos)
  """
  # Tentar SELENIUM_URL primeiro, depois fallback para localhost
  selenium_url = os.environ.get('SELENIUM_URL') or os.getenv('SELENIUM_URL') or 'http://selenium:4444'
  
  print(f"🔍 SELENIUM_URL configurada: {selenium_url}")
  
  driver = None
  
  # Configurar Chrome options
  chrome_options = Options()
  chrome_options.add_argument('--no-sandbox')
  chrome_options.add_argument('--disable-dev-shm-usage')
  
  # Tentar conectar ao Selenium Grid remoto com retry
  for attempt in range(retries):
    try:
      print(f"Conectando ao Selenium remoto ({selenium_url}) - Tentativa {attempt + 1}/{retries}...")
      driver = webdriver.Remote(command_executor=selenium_url, options=chrome_options)
      print("✅ Conectado ao Selenium remoto com sucesso!")
      break
    except Exception as e:
      print(f"❌ Erro na tentativa {attempt + 1}: {e}")
      if attempt < retries - 1:
        print(f"⏳ Aguardando {delay}s antes de reconectar...")
        time.sleep(delay)
      else:
        print(f"⚠️ Falha em todas as {retries} tentativas. Tentando Chrome local como fallback...")
        try:
          driver = webdriver.Chrome(options=chrome_options)
          print("✅ Chrome local conectado como fallback!")
          break
        except Exception as local_e:
          print(f"❌ Chrome local também falhou: {local_e}")
          raise Exception(f"Não foi possível conectar a nenhum WebDriver (remoto ou local)")
  
  try:
    yield driver
  finally:
    if driver:
      try:
        driver.quit()
        print("✅ WebDriver desconectado com sucesso")
      except Exception as e:
        print(f"⚠️ Erro ao desconectar WebDriver: {e}")

@shared_task
def login_to_jpmorgan(user, password):
  _url = "https://secure.chase.com/web/auth/?treatment=jpo#/logon/logon/chaseOnline"

  with get_webdriver(retries=3, delay=2) as driver:
    try:
      # 1. Accessar the JPMorgan login page
      driver.get(_url)
      
      # 2. Preencher usuario e a senha
      user_id_field = WebDriverWait(driver, 10).until(
          EC.element_to_be_clickable((By.ID, "userId-input-field-input"))
      )
      user_id_field.send_keys(user)
      
      password_field = driver.find_element(By.ID, "password-input-field-input")
      password_field.send_keys(password)
      
      """       
      # 3. Sign-in button
      signin_button = driver.find_element(By.ID, "signin-button")
      signin_button.click()

      contact_method = WebDriverWait(driver, 5).until(
          EC.element_to_be_clickable((By.ID, "header-simplerAuth-dropdownoptions-styledselect"))
      )
      contact_method.click()

      select_text_method = WebDriverWait(driver, 5).until(
          EC.element_to_be_clickable((By.ID, "container-primary-1-simplerAuth-dropdownoptions-styledselect"))
      )
      select_text_method.click()

      # 4. Sign-in button
      verify_button = driver.find_element(By.ID, "requestIdentificationCode-sm")
      verify_button.click()
      """
      # id="otpcode_input-input-field" -> one time code
      # id="password_input-input-field" -> password field
      # id="log_on_to_landing_page-sm" -> notao de log-on

      
      # Aguardar o browser aberto
      time.sleep(15)

      CrawlLog.objects.create(
          url=_url,
          status_code=200
      )
      
    except Exception as e:
      print(f"❌ An error occurred: {str(e)}")
      CrawlLog.objects.create(
          url=_url,
          status_code=500
      )

if __name__ == "__main__":
  load_dotenv()
  jp_user = os.getenv("JP_USERID")
  jp_pass = os.getenv("JP_PASSWORD")
  login_to_jpmorgan.delay(jp_user, jp_pass)