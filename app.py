import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime, date, timedelta
import hashlib
from dateutil.relativedelta import relativedelta
import unidecode
import os
from dotenv import load_dotenv
import plotly.express as px
import io
from openpyxl import load_workbook
from openpyxl.styles import PatternFill

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://usuario:senha@host:porta/database")

# -----------------------------
# Utilidades de segurança
# -----------------------------
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed

# -----------------------------
# Base de dados
# -----------------------------
def get_conn():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS stores (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('comercial','loja')),
            password_hash TEXT NOT NULL,
            store_id INTEGER REFERENCES stores(id)
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS suppliers (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS visits (
            id SERIAL PRIMARY KEY,
            store_id INTEGER NOT NULL REFERENCES stores(id),
            visit_date DATE NOT NULL,
            weekday TEXT NOT NULL,
            buyer TEXT,
            supplier_id INTEGER REFERENCES suppliers(id),
            segment TEXT,
            warranty TEXT,
            info TEXT,
            status TEXT NOT NULL DEFAULT 'Pendente' CHECK(status IN ('Pendente','Concluída','Não Compareceu')),
            created_by INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            completed_by INTEGER REFERENCES users(id),
            manager_comment TEXT
        );
    """)

    conn.commit()
    conn.close()

def update_manager_comment(visit_id: int, comment: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE visits
        SET manager_comment = %s
        WHERE id = %s;
    """, (comment, visit_id))
    conn.commit()
    conn.close()

def nao_compareceu_visit(visit_id: int, user_id: int, manager_comment: str = None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE visits
        SET status = 'Não Compareceu',
            completed_at = CURRENT_TIMESTAMP,
            completed_by = %s,
            manager_comment = %s
        WHERE id = %s;
    """, (user_id, manager_comment, visit_id))
    conn.commit()
    conn.close()

def concluir_visit(visit_id: int, user_id: int, manager_comment: str = None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE visits
        SET status = 'Concluída',
            completed_at = CURRENT_TIMESTAMP,
            completed_by = %s,
            manager_comment = %s
        WHERE id = %s;
    """, (user_id, manager_comment, visit_id))
    conn.commit()
    conn.close()

def reabrir_visit(visit_id: int, user_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE visits
        SET status = 'Pendente',
            completed_at = NULL,
            completed_by = NULL
        WHERE id = %s;
    """, (visit_id,))
    conn.commit()
    conn.close()

def seed_data():
    conn = get_conn()
    cur = conn.cursor()

    lojas = [
        "HIPODROMO","RIO DOCE","CARUARU","HIPODROMO CAFETERIA","JANGA CAFETERIA",
        "ESPINHEIRO","AFLITOS","PONTA VERDE","JATIUCA","FAROL","BEIRA MAR",
        "JARDIM ATLÂNTICO","CASA CAIADA VERDAO","JANGA VERDAO","BAIRRO NOVO VERDAO"
    ]

    cur.execute("SELECT COUNT(*) FROM stores;")
    if cur.fetchone()[0] == 0:
        for loja in lojas:
            cur.execute("INSERT INTO stores(name) VALUES(%s) ON CONFLICT DO NOTHING;", (loja,))

    cur.execute("SELECT id, name FROM stores;")
    stores_map = {name: _id for _id, name in cur.fetchall()}

    cur.execute("SELECT COUNT(*) FROM users;")
    if cur.fetchone()[0] == 0:
        users = [
            ("comercial@quitandaria.com", "Comercial Master", "comercial", hash_password("123456"), None)
        ]
        for loja in lojas:
            email_loja = "loja." + unidecode.unidecode(loja.lower().replace(" ", ".")) + "@quitandaria.com"
            users.append((email_loja, loja, "loja", hash_password("123456"), stores_map.get(loja)))

        cur.executemany(
            "INSERT INTO users(email, name, role, password_hash, store_id) VALUES(%s,%s,%s,%s,%s);",
            users
        )

    conn.commit()
    conn.close()

# -----------------------------
# Funções de dados
# -----------------------------
WEEKDAYS_PT = {
    0: "Segunda-feira",
    1: "Terça-feira",
    2: "Quarta-feira",
    3: "Quinta-feira",
    4: "Sexta-feira",
    5: "Sábado",
    6: "Domingo",
}

SEGMENTOS_FIXOS = [
    "HORTIFRUTIGRANJEIRO", "EMBALAGEM", "CONGELADOS", "LATICINIOS", "SUPLEMENTOS",
    "PADARIA", "BEBIDAS", "MERCEARIA", "GRANJEIROS", "ACOUGUE", "OLEOS",
    "HIGIENE E BELEZA", "PET", "LIMPEZA DA CASA", "ECOMMERCE", "ROTISSERIA",
    "FRIOS E EMBUTIDOS", "QUEIJOS", "FLORICULTURA", "EMPORIO", "BAZAR"
]

def get_stores():
    conn = get_conn()
    df = pd.read_sql_query("SELECT id, name FROM stores ORDER BY name;", conn)
    conn.close()
    return df

def export_visitas_excel(df):
    output = io.BytesIO()
    safe_df = df.copy()
    if "data_datetime" in safe_df.columns:
        safe_df = safe_df.drop(columns=["data_datetime"])
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        safe_df.to_excel(writer, index=False, sheet_name="Visitas")

    output.seek(0)
    wb = load_workbook(output)
    ws = wb.active

    col_status = None
    for idx, cell in enumerate(ws[1], start=1):
        if cell.value == "status":
            col_status = idx
            break

    if col_status:
        for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=col_status, max_col=col_status):
            for cell in row:
                if cell.value and str(cell.value).lower() == "concluída":
                    cell.fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
                elif cell.value and str(cell.value).lower() == "pendente":
                    cell.fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
                elif cell.value and str(cell.value).lower() == "não compareceu":
                    cell.fill = PatternFill(start_color="FFD966", end_color="FFD966", fill_type="solid")

    final_output = io.BytesIO()
    wb.save(final_output)
    return final_output.getvalue()

# -----------------------------
# Criação de visitas (corrigido para repetir semanalmente)
# -----------------------------
def ensure_supplier(name: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO suppliers(name)
        VALUES(%s)
        ON CONFLICT(name) DO UPDATE SET name=EXCLUDED.name
        RETURNING id;
    """, (name.strip(),))
    supplier_id = cur.fetchone()[0]
    conn.commit()
    conn.close()
    return supplier_id

def create_visit(store_ids, visit_date: date, buyer: str, supplier: str, segment: str, warranty: str, info: str, created_by: int, repeat_weekly=False):
    supplier_id = ensure_supplier(supplier)
    conn = get_conn()
    cur = conn.cursor()

    def insert_one(vdate, store_id):
        cur.execute("""
            INSERT INTO visits (store_id, visit_date, weekday, buyer, supplier_id, segment, warranty, info, status, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Pendente', %s);
        """, (store_id, vdate, WEEKDAYS_PT[vdate.weekday()], buyer, supplier_id, segment, warranty, info, created_by))

    for store_id in store_ids:
        weeks_to_create = 4 if repeat_weekly else 1
        for i in range(weeks_to_create):
            next_date = visit_date + relativedelta(weeks=i)
            insert_one(next_date, store_id)

    conn.commit()
    conn.close()
