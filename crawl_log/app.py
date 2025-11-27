import time
from dotenv import load_dotenv
import os
from crawl_log.tasks import hello, login_to_jpmorgan

if __name__ == "__main__":
  # carregar variaveis de ambiente
  load_dotenv()

  jp_user = os.getenv("JP_USERID")
  jp_pass = os.getenv("JP_PASSWORD")
  
  # executar as tasks
  hello.delay('Mundo')
  
  login_to_jpmorgan.delay(jp_user, jp_pass)