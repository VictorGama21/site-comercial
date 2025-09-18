import streamlit as st
import psycopg2
import pandas as pd
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
import hashlib
import unidecode
import os
from dotenv import load_dotenv
import io
from openpyxl import load_workbook
from openpyxl.styles import PatternFill

# -----------------------------
# Configuração do ambiente
# -----------------------------
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://usuario:senha@host:porta/database")

# -----------------------------
# Utilidades
# -----------------------------
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed

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

# -----------------------------
# Banco de dados
# -----------------------------
def get_conn():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # Tabelas
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

# -----------------------------
# Seed inicial
# -----------------------------
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
# Funções de CRUD de visitas
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

def reabrir_visit(visit_id: int):
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

def get_stores():
    conn = get_conn()
    df = pd.read_sql_query("SELECT id, name FROM stores ORDER BY name;", conn)
    conn.close()
    return df

def get_visits(user):
    conn = get_conn()
    if user["role"] == "comercial":
        df = pd.read_sql_query("""
            SELECT v.id, s.name AS store, v.visit_date, v.weekday, u.name AS buyer, sup.name AS supplier,
                   v.segment, v.warranty, v.info, v.status, v.manager_comment
            FROM visits v
            LEFT JOIN stores s ON v.store_id = s.id
            LEFT JOIN users u ON v.created_by = u.id
            LEFT JOIN suppliers sup ON v.supplier_id = sup.id
            ORDER BY v.visit_date DESC;
        """, conn)
    else:
        df = pd.read_sql_query("""
            SELECT v.id, s.name AS store, v.visit_date, v.weekday, u.name AS buyer, sup.name AS supplier,
                   v.segment, v.warranty, v.info, v.status, v.manager_comment
            FROM visits v
            LEFT JOIN stores s ON v.store_id = s.id
            LEFT JOIN users u ON v.created_by = u.id
            LEFT JOIN suppliers sup ON v.supplier_id = sup.id
            WHERE v.store_id = %s
            ORDER BY v.visit_date DESC;
        """, conn, params=(user["store_id"],))
    conn.close()
    return df

# -----------------------------
# Exportação Excel
# -----------------------------
def export_visitas_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Visitas")
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
                if cell.value == "Concluída":
                    cell.fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
                elif cell.value == "Pendente":
                    cell.fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
                elif cell.value == "Não Compareceu":
                    cell.fill = PatternFill(start_color="FFD966", end_color="FFD966", fill_type="solid")
    final_output = io.BytesIO()
    wb.save(final_output)
    return final_output.getvalue()

# -----------------------------
# Inicialização
# -----------------------------
init_db()
seed_data()

# -----------------------------
# Streamlit App
# -----------------------------
st.set_page_config(page_title="Gestão de Visitas", layout="wide")
st.title("🗂️ Gestão de Visitas - Quitandaria")

# Sessão de login
if "user" not in st.session_state:
    st.session_state.user = None

def login(email, password):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, name, role, password_hash, store_id FROM users WHERE email=%s;", (email,))
    row = cur.fetchone()
    conn.close()
    if row and verify_password(password, row[3]):
        st.session_state.user = {"id": row[0], "name": row[1], "role": row[2], "store_id": row[4]}
        return True
    return False

if st.session_state.user is None:
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Senha", type="password")
        submitted = st.form_submit_button("Login")
        if submitted:
            if login(email, password):
                st.success(f"Bem-vindo {st.session_state.user['name']}!")
            else:
                st.error("Email ou senha incorretos.")
else:
    user = st.session_state.user
    st.sidebar.write(f"👤 {user['name']} ({user['role']})")
    if st.sidebar.button("Logout"):
        st.session_state.user = None
        st.experimental_rerun()

    # Dashboard
    df_visits = get_visits(user)
    st.subheader("📋 Visitas Agendadas")
    st.dataframe(df_visits, use_container_width=True)

    # Exportar Excel
    if st.button("Exportar Excel"):
        excel_bytes = export_visitas_excel(df_visits)
        st.download_button(
            label="Download Excel",
            data=excel_bytes,
            file_name=f"visitas_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    # Ações de visitas (concluir, não compareceu, reabrir)
    st.subheader("🔧 Ações de Visita")
    visit_ids = df_visits["id"].tolist()
    selected_visit = st.selectbox("Selecione a visita", visit_ids)
    manager_comment = st.text_area("Comentário do gerente (opcional)")

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("✅ Concluir"):
            concluir_visit(selected_visit, user["id"], manager_comment)
            st.success("Visita concluída!")
            st.experimental_rerun()
    with col2:
        if st.button("❌ Não Compareceu"):
            nao_compareceu_visit(selected_visit, user["id"], manager_comment)
            st.success("Status atualizado para 'Não Compareceu'.")
            st.experimental_rerun()
    with col3:
        if st.button("🔄 Reabrir"):
            reabrir_visit(selected_visit)
            st.success("Visita reaberta para Pendente.")
            st.experimental_rerun()

    # Cadastro de visita (apenas comercial)
    if user["role"] == "comercial":
        st.subheader("➕ Cadastrar Nova Visita")
        stores_df = get_stores()
        selected_stores = st.multiselect("Selecione as lojas", options=stores_df["id"], format_func=lambda x: stores_df[stores_df["id"]==x]["name"].values[0])
        visit_date = st.date_input("Data da visita", date.today())
        buyer = st.text_input("Comprador")
        supplier = st.text_input("Fornecedor")
        segment = st.selectbox("Segmento", SEGMENTOS_FIXOS)
        warranty = st.text_input("Garantia")
        info = st.text_area("Informações adicionais")
        repeat_weekly = st.checkbox("Repetir semanalmente (4 semanas)")

        if st.button("Salvar Visita"):
            create_visit(selected_stores, visit_date, buyer, supplier, segment, warranty, info, user["id"], repeat_weekly)
            st.success("Visita(s) cadastrada(s) com sucesso!")
            st.experimental_rerun()
