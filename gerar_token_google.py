"""Executar UMA vez no seu computador para autorizar o robô a ler o Gmail e criar eventos no Google Agenda.

1. No Google Cloud Console (projeto gestao-advdebora), crie uma credencial OAuth do tipo
   "App para computador" e baixe o arquivo como credentials.json nesta pasta.
2. Rode:  pip install google-auth-oauthlib  e depois  python gerar_token_google.py
3. Entre com deboraewenne@gmail.com e autorize. Copie os três valores exibidos para os
   Secrets do GitHub (GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN).
"""
from google_auth_oauthlib.flow import InstalledAppFlow

ESCOPOS = ["https://www.googleapis.com/auth/gmail.readonly",
           "https://www.googleapis.com/auth/calendar.events"]
flow = InstalledAppFlow.from_client_secrets_file("credentials.json", ESCOPOS)
cred = flow.run_local_server(port=0, access_type="offline", prompt="consent")
print("\nGMAIL_CLIENT_ID     =", cred.client_id)
print("GMAIL_CLIENT_SECRET =", cred.client_secret)
print("GMAIL_REFRESH_TOKEN =", cred.refresh_token)
