from typing import Literal
from dataclasses import dataclass
from data_access import beehus_connection as bc
from datetime import datetime, timezone

import uuid
import pytz

@dataclass
class BTGMFORawFilesData:
  _id: str
  userId: str
  companyId: str
  consumeDate: str
  fileString: str
  type: Literal['position', 'transaction']

class BTGMFORawFiles:
  def __init__(self, conn=None):
    self._conn = bc.get_connection(conn=conn)
    self.collection = self._conn["rawBTGMFOFile"]

  ## CRUD ## 
  def insert_one(self, data):
    current_time = datetime.now(pytz.utc)

    # O método espera um objeto BTGMFORawFilesData, mas estamos recebendo um dicionário
    # Vamos adaptar para funcionar com dicionário ou BTGMFORawFilesData
    data_dict = {
      "_id": str(uuid.uuid4()),
      "userId": data.get("userId") if isinstance(data, dict) else data.userId,
      "companyId": data.get("companyId") if isinstance(data, dict) else data.companyId,
      "consumeDate": data.get("consumeDate") if isinstance(data, dict) else data.consumeDate,
      "fileString": data.get("fileString") if isinstance(data, dict) else data.fileString,
      "type": data.get("type") if isinstance(data, dict) else data.type,
      "createdAt": current_time,
      "updatedAt": current_time
    }

    return self.collection.insert_one(data_dict)
  
  def get_one(self, query):
    return self._conn.btg_mfo_raw_files.find(query)
  
  def update_one(self, query, data):
    return self._conn.btg_mfo_raw_files.update_one(query, {"$set": data})
  
  def delete_one(self, query):
    return self._conn.btg_mfo_raw_files.delete_one(query)

  def upsert(self, data):
    current_time = datetime.now(pytz.utc)
    
    # Criar dicionário independente do tipo de entrada
    if isinstance(data, dict):
        companyId = data.get("companyId")
        consumeDate = data.get("consumeDate")
        type = data.get("type")
        fileString = data.get("fileString")
        userId = data.get("userId")
    else:
        companyId = data.companyId
        consumeDate = data.consumeDate
        type = data.type
        fileString = data.fileString
        userId = data.userId
    
    # filtro para o upsert
    filter_query = {
        "companyId": companyId,
        "consumeDate": consumeDate,
        "type": type
    }
    
    # dados a serem atualizados ou inseridos
    update_data = {
        "$set": {
            "userId": userId,
            "fileString": fileString,
            "updatedAt": current_time
        },
        "$setOnInsert": {
            "_id": str(uuid.uuid4()),
            "createdAt": current_time
        }
    }
    
    # Executar o upsert
    return self.collection.update_one(
        filter_query, 
        update_data, 
        upsert=True
    )