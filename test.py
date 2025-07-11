# Semplice funzione per testare browseAPI
import json
from browseapi import BrowseAPI
import os
from dotenv import load_dotenv

load_dotenv()
app_id = os.getenv("APP_ID")
cert_id = os.getenv("CERT_ID")

api = BrowseAPI(app_id, cert_id)
responses = api.execute('search', [{'q': 'drone', 'limit': 50}])

for item in responses[0].itemSummaries:
    print(item.conditionId) 