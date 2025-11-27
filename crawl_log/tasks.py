from celery import shared_task
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from contextlib import contextmanager
import time
from dotenv import load_dotenv
import os
from crawl_log.models import CrawlLog

# ---------------------------------------------------
# task hello
# ---------------------------------------------------
@shared_task
def hello(name):
  message = f'Olá, {name}'
  return message


# ---------------------------------------------------
# scrap JPMorgan
# ---------------------------------------------------
@contextmanager
def get_webdriver():
  driver = webdriver.Chrome()
  try:
    yield driver
  finally:
    driver.quit()

@shared_task
def login_to_jpmorgan(user, password):
  _url = "https://secure.chase.com/web/auth/?treatment=jpo#/logon/logon/chaseOnline"

  with get_webdriver() as driver:
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
      print(f"An error occurred: {str(e)}")

if __name__ == "__main__":
  load_dotenv()
  jp_user = os.getenv("JP_USERID")
  jp_pass = os.getenv("JP_PASSWORD")
  login_to_jpmorgan.delay(jp_user, jp_pass)