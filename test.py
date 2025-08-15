import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

try:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT version();")
    print("Conectado ao PostgreSQL:", cur.fetchone())
    conn.close()
except Exception as e:
    print("Erro de conexão:", e)
