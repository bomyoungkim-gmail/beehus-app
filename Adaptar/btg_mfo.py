from selenium import webdriver
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.common.exceptions import UnexpectedAlertPresentException, NoAlertPresentException, InvalidSessionIdException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from dotenv import load_dotenv
from typing import Dict, Union, Literal
import os
import time
import json

load_dotenv()

class BTGMFO(webdriver.Firefox):
  def __init__(self, headless=False, suffix_dir="btg-mfo"):
    self._current_dir = os.getcwd()
    self._download_dir = os.path.join(self._current_dir, "downloads", suffix_dir)
    self._create_temp_dirs()

    # printar todas as props dir ao iniciar.
    print(f"Current dir: {self._current_dir}")
    print(f"Download dir: {self._download_dir}")

    firefox_options = FirefoxOptions()
    firefox_options.set_preference("browser.download.folderList", 2)
    firefox_options.set_preference("browser.download.manager.showWhenStarting", False)
    firefox_options.set_preference("browser.download.dir", self._download_dir)

    if headless:
      firefox_options.add_argument("--headless")

    super(BTGMFO, self).__init__(options=firefox_options)
    self.implicitly_wait(10)
    if not headless:
      self.maximize_window()  
      
  def __exit__(self):
    if self.teardown:
      self.quit()
  
  def _create_temp_dirs(self):
    os.makedirs(self._download_dir, exist_ok=True)

  def _finish_run(self, timer=3):
    time.sleep(timer)
    self.quit()

  def _navigate_to_login(self):
    self.get(os.getenv("SCRAPING_BTG_MFO_LOGIN_URL"))
    # self._save_raw_html('login')
  
  def _verify_login(self):
    try:
      login_error_container = self.find_element(By.CLASS_NAME, 'authenticate-panel__form--error-message')
  
      if login_error_container:
        return {
          "logged": False,
          "message": login_error_container.text
        }

      return {
        "logged": True
      }
    except Exception as e:
      return {
        "logged": False,
        "message": "Erro ao tentar logar: " + str(e)
      }

  def login_step(self, username: int, password: str, token: str):
    try:
      self._navigate_to_login()

      print("Preenchendo campos de login...")
      login_field = self.find_element(By.CSS_SELECTOR, f'input[name="login"]')
      password_field = self.find_element(By.CSS_SELECTOR, f'input[name="password"]')
      token_field = self.find_element(By.CSS_SELECTOR, f'input[name="softToken"]')
      submit_button = self.find_element(By.CSS_SELECTOR, "button[name='entrar'][type='submit']")

      login_field.clear()
      password_field.clear()
      token_field.clear()

      username = username
      password = str(password)
      token = str(token)

      masked_password = '*' * len(password) if password else ''
      print(f"Usuário: {username}")
      print(f"Senha: {masked_password}")
      print(f"Token: {token}")

      login_field.send_keys(username)
      password_field.send_keys(password)
      token_field.send_keys(token)

      print("Clicando no botão de login...")
      submit_button.click()

      time.sleep(5)

      verified_login = self._verify_login()

      if verified_login["logged"] == False:
        return {
          "step": "login",
          "step_finished": False,
          "message": verified_login["message"]
        }

      return {
        "step": "login",
        "step_finished": True,
        "message": "Login realizado com sucesso."
      }
    except Exception as e:
      print(f"Erro ao logar: {e}")
      self._finish_run()
      return {
        "step": "login",
        "step_finished": False,
        "message": "Erro inesperado ao realizar realizar o passo de login: " + str(e)
      }
    
  def navigate_step(self):
    try:
      print("Navegando até a página de relatórios...")
      client_selection = self.find_elements(By.ID, "selectClientButton")

      print("Selecionando o tipo de acesso...")
      correct_client_selection = None
      for index, element in enumerate(client_selection):
        if 'FAMILY OFFICE WM' in element.text:
            print('Achei o tipo de acesso correto: ', element.text)
            print('Clicando no elemento...', index)
            correct_client_selection = element
    
      if correct_client_selection:
        # Clicar no botao <button _ngcontent-lvi-c98="" type="button">Acessar &gt;</button>
        print('Clicando no botão de acesso...')
        button = correct_client_selection.find_element(By.XPATH, ".//button[text()='Acessar >']")
        button.click()
      else:
        return {
          "step": "navigation",
          "step_finished": False,
          "message":"Não foi encontrado o tipo de acesso correto. O acesso correto é o perfil 'FAMILY OFFICE WM'."
        }
      
      time.sleep(2)

      print("Clicando no botão de operações...")
      # clicar na div de id : "operation_button"
      operation_button = self.find_element(By.ID, "operation_button")
      operation_button.click()

      time.sleep(1)

      print("Procurando a featurde Relatórios WM Externo...")
      # encontrar e clicar nesse elemento : <p _ngcontent-shc-c27="" class="home-card-place-description"> Consulte os relatórios de WM. </p>
      reports_types = self.find_elements(By.ID, "feature[object Object]1_button")

      correct_report_element = None
      for index, element in enumerate(reports_types):
          if 'Consulte os relatórios de WM.' in element.text:
              correct_report_element = element

      if correct_report_element:
        print("Clicando no botão de 'Relatórios WM Externo...'")
        correct_report_element.click()

        return {
          "step": "navigation",
          "step_finished": True,
          "message":"Navegação realizada com sucesso."
        }
      else:
        return {
          "step": "navigation",
          "step_finished": False,
          "message":"Não foi encontrado o tipo de relatório correto. O relatório correto é: 'Relatórios WM Externo' com o sub texto: 'Consulte os relatórios de WM'."
        }
    except Exception as e:
      print(f"Erro ao navegar: {e}")
      self._finish_run()
      return {
        "step": "navigation",
        "step_finished": False,
        "message": "Erro ao realizar o passo de navegação: " + str(e)
      }
    
  def select_report_step(self):
    try:
      print("Selecionando a categoria 'Investimento'")
      # selecionar <i ng-class="{'arrow--up qa-btn-open': selectSearch.activeInput,
      #              'arrow--down': !selectSearch.activeInput, 
      #              'close qa-btn-close': selectSearch.selectValue &amp;&amp; selectSearch.selectValue!==''}" class="arrow arrow--down" ng-click="selectSearch.selectValue &amp;&amp; selectSearch.selectValue!=='' ? selectSearch.ifActive.clear() : selectSearch.ifActive.toggle($event)">
      # </i>
      open_select_category = self.find_element(By.CSS_SELECTOR, '[placeholder="Selecione uma categoria"]')
      time.sleep(1)
      open_select_category.click()

      #<li ng-repeat="option in selectSearch.options | orderBy: label" class="list__item qa-c-select-search__item ng-binding ng-scope selected" ng-click="!option.labelGroupItem &amp;&amp; selectSearch.ifActive.select(option, $index)" ng-class="{'selected' : selectSearch.hoverItem === $index || selectSearch.options.length === 1, 'label-group-item': option.labelGroupItem}" style="">Investimento</li>
      category_investment = self.find_element(By.XPATH, "//li[text()='Investimento']")
      time.sleep(1)
      category_investment.click()

      print("Selecionando o relatório 'Investimentos (WM Externo) (D-1 e D0)'")
      open_select_report = self.find_element(By.CSS_SELECTOR, '[placeholder="Selecione um relatório"]')
      time.sleep(1)
      open_select_report.click()

      #<li ng-repeat="option in selectSearch.options | orderBy: label" class="list__item qa-c-select-search__item ng-binding ng-scope selected" ng-click="!option.labelGroupItem &amp;&amp; selectSearch.ifActive.select(option, $index)" ng-class="{'selected' : selectSearch.hoverItem === $index || selectSearch.options.length === 1, 'label-group-item': option.labelGroupItem}" style="">Investimento</li>
      report_investment = self.find_element(By.XPATH, "//li[text()='Investimentos (WM Externo) (D-1 e D0)']")
      time.sleep(1)
      report_investment.click()

      print("Clicando no botão de filtro...")
      #<button type="button" class="button button--success" id="--button" title="Filtrar" ng-readonly="button.readonly" ng-disabled="button.disabled" ng-class="{ 'button--small': button.size === 'small', 'button--block': button.size === 'block' }" ng-click="button.onClick()" disabled="disabled">
      #  <!-- ngIf: button.icon -->
      #  <!-- ngIf: !button.hideTitle --><span ng-if="!button.hideTitle" class="button__title ng-binding ng-scope">
      #    Filtrar
      #  </span><!-- end ngIf: !button.hideTitle -->
      #</button>
      filter_button = self.find_element(By.ID, "--button")
      filter_button.click()

      print("Aguardando o PowerBI carregar...")
      # !!! IFRAME DO POWERBI CARREGA SEM MUDAR DE PAGINA/URL!!! #
      time.sleep(5)
      return {
        "step": "select_report",
        "step_finished": True,
        "message": "Relatório selecionado com sucesso."
      }
    except Exception as e:
      print(f"Erro ao selecionar relatório: {e}")
      self._finish_run()
      return {
        "step": "select_report",
        "step_finished": False,
        "message": "Erro ao realizar o passo de seleção de relatório: " + str(e)
      }
    
  def positions_dzero_download_step(self):
    try:
      # Garantir que está no contexto de DOC HTML correto
      self.switch_to.default_content()

      # Esperar até que o iframe com o valor específico no src esteja presente e clicável
      btg_power_bi_iframe = WebDriverWait(self, 35).until(
          EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "https://app.powerbi.com/reportEmbed?reportId=87ba81d5-79c7-4dd0-ad91-2ec526a10e99")]'))
      )

      # Mudar o contexto para o iframe do power BI
      self.switch_to.frame(btg_power_bi_iframe)

      ## Elemento avô do clique do botão da POSIÇÃO. (tag = "g")
      path_element = WebDriverWait(self, 30).until(
          EC.element_to_be_clickable((By.XPATH, '/html/body/div[3]/report-embed/div/div/div[1]/div/div/div/exploration-container/div/div/docking-container/div/div/div/div/exploration-host/div/div/exploration/div/explore-canvas/div/div[2]/div/div[2]/div[2]/visual-container-repeat/visual-container[37]/transform/div/div[3]/div/div/visual-modern/div'))
      )

      ## Mover o scroll para o elemento. (tag = "g")
      self.execute_script("arguments[0].scrollIntoView(true);", path_element)

      ## Elemento pai do botão da POSIÇÃO. (tag = "g")
      pe_children = path_element.find_element(By.CLASS_NAME, 'tile')

      ## Botão da POSIÇÃO
      pe_grand_children = pe_children.find_element(By.CLASS_NAME, 'sub-selectable')

      time.sleep(0.5)
      pe_grand_children.click() ## !! vai trocar de "página do power bi"

      time.sleep(5)

      ## Procurando o campo select para selecionar dzero
      select_position_date = WebDriverWait(self, 30).until(
        EC.presence_of_element_located((By.XPATH, '/html/body/div[3]/report-embed/div/div/div[1]/div/div/div/exploration-container/div/div/docking-container/div/div/div/div/exploration-host/div/div/exploration/div/explore-canvas/div/div[2]/div/div[2]/div[2]/visual-container-repeat/visual-container[14]/transform/div/div[3]/div/div/visual-modern/div/div/div[2]/div'))
      )
      select_position_date.click()

      time.sleep(1)

      ## Selecionando Dzero
      select_d_zero = WebDriverWait(self, 6).until(
          EC.presence_of_element_located((By.XPATH, '/html/body/div[16]/div[1]/div/div[2]/div/div[1]/div/div/div[1]/div'))
      )
      select_d_zero.click()

      time.sleep(1)

      # Colocando o mouse em cima do título da posição para aparecer o botão de download
      # aplicar hoover ou deixar em destaque no elemento: /html/body/div[3]/report-embed/div/div/div[1]/div/div/div/exploration-container/div/div/docking-container/div/div/div/div/exploration-host/div/div/exploration/div/explore-canvas/div/div[2]/div/div[2]/div[2]/visual-container-repeat/visual-container[44]/transform/div/div[3]/div/div/div/div/div/div/h3
      hover_position_title = WebDriverWait(self, 6).until(
          EC.presence_of_element_located((By.XPATH, '/html/body/div[3]/report-embed/div/div/div[1]/div/div/div/exploration-container/div/div/docking-container/div/div/div/div/exploration-host/div/div/exploration/div/explore-canvas/div/div[2]/div/div[2]/div[2]/visual-container-repeat/visual-container[44]/transform/div/div[3]/div/div/div/div/div/div/h3'))
      )
      hover_position_title.click()

      # Procurando e clicando no botão de exportar dados
      #//*[@id="0"], botao que abre o menu de exportar dados
      triple_dot_menu = WebDriverWait(self, 12).until(
          EC.presence_of_element_located((By.XPATH, '/html/body/div[3]/report-embed/div/div/div[1]/div/div/div/exploration-container/div/div/docking-container/div/div/div/div/exploration-host/div/div/exploration/div/explore-canvas/div/div[2]/div/div[2]/div[2]/visual-container-repeat/visual-container[44]/transform/div/visual-container-header/div/div/div/visual-container-options-menu/visual-header-item-container/div/button'))
      )
      triple_dot_menu.click()

      # botao que abre o modal de exportar dados
      export_data_button = WebDriverWait(self, 6).until(
          EC.presence_of_element_located((By.XPATH, '//*[@id="0"]'))
      )
      export_data_button.click()

      time.sleep(0.5)

      # /html/body/div[4]/div[2]/div/mat-dialog-container/div/div/export-data-dialog/mat-dialog-actions/button[1]
      download_data_button = WebDriverWait(self, 6).until(
          EC.presence_of_element_located((By.XPATH, '/html/body/div[4]/div[2]/div/mat-dialog-container/div/div/export-data-dialog/mat-dialog-actions/button[1]'))
      )
      download_data_button.click()

      time.sleep(3)

      # Volta pro HTML principal para voltar pro menu de relatórios
      self.switch_to.default_content()

      filter_button = self.find_element(By.ID, "--button")
      filter_button.click() # !! vai trocar de "página do power bi para a página de relatórios"

      time.sleep(5)

      return {
        "step": "positions_dzero_download",
        "step_finished": True,
        "message": "Relatório de POSIÇÕES D0 baixado com sucesso."
      }
    except Exception as e:
      print(f"Erro ao baixar relatório de POSIÇÕES: {e}")
      self._finish_run()
      return {
        "step": "positions_dzero_download",
        "step_finished": False,
        "message": "Erro ao realizar o passo de download do relatório de POSIÇÕES D0: " + str(e)
      }
  
  def transactions_download_step(self):
    try:
      self.switch_to.default_content()

      # Esperar até que o iframe com o valor específico no src esteja presente e clicável
      btg_power_bi_iframe = WebDriverWait(self, 35).until(
          EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "https://app.powerbi.com/reportEmbed?reportId=87ba81d5-79c7-4dd0-ad91-2ec526a10e99")]'))
      )

      # Mudar o contexto para o iframe
      self.switch_to.frame(btg_power_bi_iframe)

      ## Elemento avô do clique do botão da MOVIMENTAÇÃO. (tag = "g")
      path_element = WebDriverWait(self, 30).until(
          EC.element_to_be_clickable((By.XPATH, '/html/body/div[3]/report-embed/div/div/div[1]/div/div/div/exploration-container/div/div/docking-container/div/div/div/div/exploration-host/div/div/exploration/div/explore-canvas/div/div[2]/div/div[2]/div[2]/visual-container-repeat/visual-container[29]/transform/div/div[3]/div/div/visual-modern/div'))
      )

      ## Mover o scroll para o elemento. (tag = "g")
      self.execute_script("arguments[0].scrollIntoView(true);", path_element)

      ## Elemento pai do botão da MOVIMENTAÇÃO. (tag = "g")
      pe_children = path_element.find_element(By.CLASS_NAME, 'tile')

      ## Botão da MOVIMENTAÇÃO
      pe_grand_children = pe_children.find_element(By.CLASS_NAME, 'sub-selectable')

      time.sleep(0.5)
      pe_grand_children.click() ## vai trocar de "página do power bi"

      time.sleep(4)

      hoover_movement_title = WebDriverWait(self, 15).until(
          EC.presence_of_element_located((By.XPATH, '/html/body/div[3]/report-embed/div/div/div[1]/div/div/div/exploration-container/div/div/docking-container/div/div/div/div/exploration-host/div/div/exploration/div/explore-canvas/div/div[2]/div/div[2]/div[2]/visual-container-repeat/visual-container[43]/transform/div/div[3]/div/div/div/div/div/div/h3'))
      )
      hoover_movement_title.click()

      #//*[@id="0"]
      triple_dot_menu = WebDriverWait(self, 30).until(
          EC.presence_of_element_located((By.XPATH, '/html/body/div[3]/report-embed/div/div/div[1]/div/div/div/exploration-container/div/div/docking-container/div/div/div/div/exploration-host/div/div/exploration/div/explore-canvas/div/div[2]/div/div[2]/div[2]/visual-container-repeat/visual-container[43]/transform/div/visual-container-header/div/div/div/visual-container-options-menu/visual-header-item-container/div/button'))
      )
      triple_dot_menu.click()

      export_data_button = WebDriverWait(self, 6).until(
          EC.presence_of_element_located((By.XPATH, '//*[@id="0"]'))
      )
      export_data_button.click()

      time.sleep(0.5)

      # /html/body/div[4]/div[2]/div/mat-dialog-container/div/div/export-data-dialog/mat-dialog-actions/button[1]
      download_data_button = WebDriverWait(self, 6).until(
          EC.presence_of_element_located((By.XPATH, '/html/body/div[4]/div[2]/div/mat-dialog-container/div/div/export-data-dialog/mat-dialog-actions/button[1]'))
      )
      download_data_button.click()

      time.sleep(3)

      # come back to default context
      self.switch_to.default_content()

      filter_button = self.find_element(By.ID, "--button")
      filter_button.click()

      return {
        "step": "transactions_download",
        "step_finished": True,
        "message": "Relatório de MOVIMENTAÇÕES baixado com sucesso."
      }
    except Exception as e:
      print(f"Erro ao baixar relatório de MOVIMENTAÇÕES: {e}")
      self._finish_run()
      return {
        "step": "transactions_download",
        "step_finished": False,
        "message": "Erro ao realizar o passo de download do relatório de MOVIMENTAÇÕES: " + str(e)
      }