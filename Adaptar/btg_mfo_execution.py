from pydantic import BaseModel
from time import sleep

from scraping.btg_mfo.btg_mfo import BTGMFO
from scraping.btg_mfo.files_handler import *

class btg_mfo_auth(BaseModel):
  username: str
  password: str
  token: str

def btg_mfo_execute(auth: btg_mfo_auth, company_name: str, consume_date: str, user_id: str):
  current_step = ""
  try:
    ## Step 1 - Inicializa o BOT
    current_step = "Inicializa o BOT"
    company_file_path = company_name + "/" + consume_date
    
    bot = BTGMFO(headless=True, suffix_dir=company_file_path)

    # Step 2 - Login
    current_step = "Logar"
    print("Iniciando a etapa: " + current_step)

    login_result = bot.login_step(auth["username"], auth["password"], auth["token"])

    if login_result["step_finished"] == False:
      print("Erro ao logar.")
      print(login_result)
      return login_result
    
    print("Fim da etapa: " + current_step + " com sucesso.")

    sleep(2)

    ## Step 3 - Navega até a página de relatórios
    current_step = "Navegar até a página de Relatórios de WM."
    print("Iniciando a etapa: " + current_step)

    navigate_result = bot.navigate_step()

    if navigate_result["step_finished"] == False:
      print("Erro ao navegar até a página de relatórios.")
      return navigate_result

    print("Fim da etapa: " + current_step + " com sucesso.")

    sleep(2)

    ## Step 4 - Seleciona os relatórios os filtros da página de relatórios
    current_step = "Selecionar os relatórios com os filtros da página de Relatórios de WM."
    print("Iniciando a etapa: " + current_step)

    select_report_result = bot.select_report_step()

    if select_report_result["step_finished"] == False:
      print("Erro ao selecionar os relatórios.")
      return select_report_result
    
    print("Finalizando a etapa: " + current_step + " com sucesso.")

    sleep(2)

    ## Step 5 - Espera o Power BI carregar e a página de relatório de POSIÇÕES
    ##        - Seleciona a data "-" que representa "d-0" espera carregar e 
    ##        - baixa o arquivo .xlsx do relatório de POSIÇÕES que contém os dados
    ##        - de todas as POSIÇÕES de todos os clientes do parceiro relacionados
    ##        - a conta de acessor.
    current_step = "Baixa o arquivo .xlsx do relatório de POSIÇÕES"
    print("Iniciando a etapa: " + current_step)

    positions_dzero_download_result = bot.positions_dzero_download_step()

    if positions_dzero_download_result["step_finished"] == False:
      print("Erro ao baixar o relatório de POSIÇÕES.")
      return positions_dzero_download_result

    print("Finalizando a etapa: " + current_step + " com sucesso.")

    ## Step 6 - Espera o Power BI carregar e a página de relatório de MOVIMENTAÇÕES
    ##        - Espera carregar e baixa o arquivo .xlsx do relatório de MOVIMENTAÇÕES
    ##        - que contém os dados de todas as MOVIMENTAÇÕES de todos os clientes
    ##        - do parceiro relacionados a conta de acessor.
    current_step = "Baixa o arquivo .xlsx do relatório de MOVIMENTAÇÕES"
    print("Iniciando a etapa: " + current_step)

    movements_download_result = bot.movements_download_step()

    if movements_download_result["step_finished"] == False:
      print("Erro ao baixar o relatório de MOVIMENTAÇÕES.")
      return movements_download_result
    
    print("Finalizando a etapa: " + current_step + " com sucesso.")

    print("Scraping finalizado com sucesso. Todos os passos do scraping foram concluídos. :)")
    print("Finalizando o BOT.")
    bot._finish_run()

    current_step = "Salvando os arquivos baixados como base64."
    print("Iniciando a etapa: " + current_step)

    files_result = retrieve_files(bot._download_dir)

    if files_result["step_finished"] == False:
      return files_result

    bases = files_to_base64(files_result["files"])

    if bases["step_finished"] == False:
      return bases

    insertion_result = save_raw_files({
      "user_id": user_id,
      "company_id": company_name,
      "consume_date": consume_date,
      "files_base64": bases["files_base64"]
    })

    if insertion_result["step_finished"] == False:
      return insertion_result

    print("Finalizando a etapa: " + current_step + " com sucesso.")

    return {
      "step": "finished",
      "step_finished": True,
      "message": "Todos os passos foram concluídos com sucesso."
    }
  except Exception as e:
    print("!!! Erro inesperado no scraping !!!")
    print(f"Erro no passo: {current_step}")
    print(e)
    return {
      "step": "Erro inesperado no scraping durante o passo: " + current_step + ".",
      "step_finished": False,
      "error": str(e)
    }