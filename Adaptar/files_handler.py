import os
import base64

from data_access.btg_raw_files.btg_mfo_raw_files import BTGMFORawFiles 

def retrieve_files(path_to_files: str):
    try:
        files = []
        for file in os.listdir(path_to_files):
            if file.endswith('.xlsx'):
                print(file)
                files.append(os.path.join(path_to_files, file))
        print("files")
        print(files)
        if len(files) == 0:
            return {
                "step_finished": False,
                "message": "Nenhum arquivo .xlsx encontrado no diretório: " + path_to_files
            }

        return {
            "step_finished": True,
            "message": "Arquivos .xlsx encontrados.",
            "files": files
        }
    except Exception as e:
        print(f"Erro ao recuperar arquivos: {e}")
        return {
            "step_finished": False,
            "message": "Erro ao recuperar arquivos. " + str(e)
        }

## funcao que transforma cada file em um base64
def files_to_base64(files):
    try:
        files_base64 = []
        for file in files:
            file_type = categorize_file_type(file)
            if(os.path.exists(file) and file.endswith('.xlsx') and file_type != "unknown"):
                with open(file, "rb") as f:
                    file_base64 = base64.b64encode(f.read()).decode("utf-8")
                    files_base64.append({
                        "file_type": file_type,
                        "base64": file_base64
                    })
        print("files_base64")
        print(len(files_base64))
        if(len(files_base64) < len(files)):
            return {
                "step_finished": False,
                "message": "Erro ao transformar todos os arquivos em base64."
            }

        # Retornar um dicionário com uma estrutura padronizada
        return {
            "step_finished": True,
            "message": "Arquivos convertidos para base64 com sucesso",
            "files_base64": files_base64  # Mudança importante aqui
        }
    except Exception as e:
        print(f"Erro ao transformar arquivos em base64: {e}")
        return {
            "step_finished": False,
            "message": "Erro ao transformar arquivos em base64. " + str(e)
        }


def save_raw_files(files_data):
    try:
        btg_mfo_raw_files = BTGMFORawFiles()

        # Acessar a lista de arquivos pela nova chave
        files_base64 = files_data["files_base64"]  # Acessando pela nova chave
        user_id = files_data["user_id"]
        company_id = files_data["company_id"]
        consume_date = files_data["consume_date"]

        for file in files_base64:  # Iterando sobre a lista correta
            # Criando uma instância de BTGMFORawFilesData que é esperada pelo insert_one
            btg_mfo_raw_files.upsert({
                "userId": user_id,
                "companyId": company_id,
                "consumeDate": consume_date,
                "fileString": file["base64"],
                "type": file["file_type"]
            })
            
        return {
            "step_finished": True,
            "message": "Arquivos salvos com sucesso."
        }
    except Exception as e:
        print(f"Erro ao salvar arquivos: {e}")
        return {
            "step_finished": False,
            "message": "Erro ao salvar os arquivos. " + str(e)
        }

def categorize_file_type(filename):
    if "Movimenta" in filename:
        return "transaction"
    elif "Posi" in filename:
        return "position"
    else:
        return "unknown"