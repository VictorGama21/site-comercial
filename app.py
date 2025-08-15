import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime, date, timedelta
import hashlib
from dateutil.relativedelta import relativedelta
import unidecode
import os
from dotenv import load_dotenv

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
        CREATE TABLE IF NOT EXISTS visits (
            id SERIAL PRIMARY KEY,
            store_id INTEGER NOT NULL REFERENCES stores(id),
            visit_date DATE NOT NULL,
            weekday TEXT NOT NULL,
            buyer TEXT,
            supplier TEXT,
            segment TEXT,
            warranty TEXT,
            info TEXT,
            status TEXT NOT NULL DEFAULT 'Pendente' CHECK(status IN ('Pendente','Concluída')),
            created_by INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            completed_by INTEGER REFERENCES users(id)
        );
    """)

    # Índices para performance
    cur.execute("CREATE INDEX IF NOT EXISTS idx_visits_date ON visits(visit_date);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_visits_store ON visits(store_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_visits_supplier ON visits(supplier);")

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

def get_stores():
    conn = get_conn()
    df = pd.read_sql_query("SELECT id, name FROM stores ORDER BY name;", conn)
    conn.close()
    return df

def get_user_by_email(email: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, email, name, role, password_hash, store_id FROM users WHERE email=%s;", (email,))
    row = cur.fetchone()
    conn.close()
    if row:
        keys = ["id", "email", "name", "role", "password_hash", "store_id"]
        return dict(zip(keys, row))
    return None

def get_suppliers():
    conn = get_conn()
    df = pd.read_sql_query("SELECT DISTINCT supplier FROM visits WHERE supplier IS NOT NULL AND supplier <> '' ORDER BY supplier;", conn)
    conn.close()
    return df["supplier"].dropna().tolist()

def create_visit(store_id: int, visit_date: date, buyer: str, supplier: str, segment: str, warranty: str, info: str, created_by: int, repeat_weekly=False):
    wd = WEEKDAYS_PT[visit_date.weekday()]
    conn = get_conn()
    cur = conn.cursor()

    def insert_one(vdate):
        cur.execute("""
            INSERT INTO visits (store_id, visit_date, weekday, buyer, supplier, segment, warranty, info, status, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Pendente', %s);
        """, (store_id, vdate, WEEKDAYS_PT[vdate.weekday()], buyer.strip(), supplier.strip(), segment.strip(), warranty.strip(), info.strip(), created_by))

    insert_one(visit_date)

    if repeat_weekly:
        for i in range(1, 4):
            insert_one(visit_date + relativedelta(weeks=i))

    conn.commit()
    conn.close()

def list_visits(store_id=None, status=None, start=None, end=None):
    q = [
        "SELECT v.id, s.name AS loja, v.visit_date AS data, v.weekday AS dia_semana,",
        "v.buyer AS comprador, v.supplier AS fornecedor, v.segment AS segmento,",
        "v.warranty AS garantia, v.info AS info, v.status",
        "FROM visits v JOIN stores s ON s.id = v.store_id WHERE 1=1"
    ]
    params = []

    if store_id:
        q.append("AND v.store_id = %s")
        params.append(store_id)
    if status:
        placeholders = ",".join(["%s"] * len(status))
        q.append(f"AND v.status IN ({placeholders})")
        params.extend(status)
    if start:
        q.append("AND v.visit_date >= %s")
        params.append(start)
    if end:
        q.append("AND v.visit_date <= %s")
        params.append(end)

    q.append("ORDER BY v.visit_date ASC, v.id ASC")

    conn = get_conn()
    df = pd.read_sql_query("\n".join(q), conn, params=params)
    conn.close()

    if not df.empty:
        df["data"] = pd.to_datetime(df["data"]).dt.strftime("%d/%m/%Y")
    return df

def mark_visit_completed(visit_id: int, user_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE visits
        SET status = 'Concluída', completed_at = CURRENT_TIMESTAMP, completed_by = %s
        WHERE id = %s;
    """, (user_id, visit_id))
    conn.commit()
    conn.close()

# -----------------------------
# UI Helpers
# -----------------------------
def require_login():
    if "user" not in st.session_state or st.session_state.user is None:
        st.stop()

def login_form():
    st.subheader("Entrar")
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Senha", type="password")
        submitted = st.form_submit_button("Entrar")

    if submitted:
        user = get_user_by_email(email.strip().lower())
        if not user:
            st.error("Usuário não encontrado.")
            return
        if not verify_password(password, user["password_hash"]):
            st.error("Senha inválida.")
            return
        st.session_state.user = {k: user[k] for k in ["id", "email", "name", "role", "store_id"]}
        st.success(f"Bem-vindo(a), {st.session_state.user['name']}!")
        st.rerun()

def logout_button():
    if st.sidebar.button("Sair", use_container_width=True):
        st.session_state.user = None
        st.rerun()

# -----------------------------
# Páginas
# -----------------------------
def page_agendar_visita():
    st.header("Agendar Visita")
    stores = get_stores()
    store_map = dict(zip(stores["name"], stores["id"]))
    compradores = ["Aldo", "Eduardo", "Henrique", "Jose Duda", "Thiago", "Victor", "Robson", "Outro"]
    fornecedores_sugestao = get_suppliers()

    with st.form("form_agendar"):
        loja_nome = st.selectbox("Loja", stores["name"].tolist())
        dt = st.date_input("Data", value=date.today() + timedelta(days=1))
        comprador = st.selectbox("Comprador responsável", compradores)
        fornecedor = st.selectbox("Fornecedor (sugestões)", [""] + fornecedores_sugestao)
        segmento = st.text_input("Segmento")
        garantia = st.selectbox("Garantia comercial", ["", "Sim", "Não", "A confirmar"])
        info = st.text_area("Informações")
        repetir = st.checkbox("Repetir toda semana (4 semanas)")
        submitted = st.form_submit_button("Agendar")

    if submitted:
        if not loja_nome or not fornecedor:
            st.warning("Preencha todos os campos obrigatórios.")
            return
        create_visit(
            store_id=store_map[loja_nome],
            visit_date=dt,
            buyer=comprador,
            supplier=fornecedor,
            segment=segmento,
            warranty=garantia,
            info=info,
            created_by=st.session_state.user["id"],
            repeat_weekly=repetir
        )
        st.success("Visita agendada com sucesso!")

def page_minhas_visitas_loja():
    st.header("Minhas Visitas")
    user = st.session_state.user
    store_id = user["store_id"]

    col1, col2 = st.columns(2)
    with col1:
        status = st.multiselect("Status", ["Pendente", "Concluída"], default=["Pendente"])
    with col2:
        start = st.date_input("Início", value=date.today() - timedelta(days=7))
        end = st.date_input("Fim", value=date.today() + timedelta(days=30))

    df = list_visits(store_id=store_id, status=status, start=start, end=end)
    if df.empty:
        st.info("Nenhuma visita encontrada.")
        return

    st.dataframe(df, use_container_width=True, hide_index=True)

    st.subheader("Marcar visita como concluída")
    ids = df["id"].tolist()
    if ids:
        visit_id = st.selectbox("Selecionar visita", ids, format_func=lambda i: f"#{i} - {df.loc[df['id']==i, 'loja'].iloc[0]} - {df.loc[df['id']==i, 'data'].iloc[0]}")
        if st.button("Concluir"):
            mark_visit_completed(visit_id, user_id=user["id"])
            st.success("Visita concluída.")
            st.rerun()

def page_dashboard_comercial():
    st.header("Agenda Geral")
    stores = get_stores()
    stores_filter = ["Todas"] + stores["name"].tolist()

    col1, col2, col3 = st.columns(3)
    with col1:
        loja_nome = st.selectbox("Loja", stores_filter)
        loja_id = None if loja_nome == "Todas" else int(stores.loc[stores["name"] == loja_nome, "id"].iloc[0])
    with col2:
        status = st.multiselect("Status", ["Pendente", "Concluída"], default=["Pendente", "Concluída"])
    with col3:
        start = st.date_input("Início", value=date.today() - timedelta(days=7))
        end = st.date_input("Fim", value=date.today() + timedelta(days=60))

    df = list_visits(store_id=loja_id, status=status, start=start, end=end)
    if df.empty:
        st.info("Sem visitas no período.")
        return

    st.dataframe(df, use_container_width=True, hide_index=True)
    st.metric("Total de visitas", len(df))
    st.metric("Concluídas", (df["status"] == "Concluída").sum())

# -----------------------------
# App principal
# -----------------------------
def main():
    st.set_page_config(page_title="Sistema de Visitas", layout="wide")
    init_db()
    seed_data()

    st.sidebar.title("📅 Sistema de Visitas")
    if "user" not in st.session_state:
        st.session_state.user = None

    if st.session_state.user is None:
        login_form()
        return

    user = st.session_state.user
    st.sidebar.write(f"**Usuário:** {user['name']}")
    st.sidebar.write(f"**Perfil:** {user['role'].capitalize()}")

    if user["role"] == "comercial":
        page = st.sidebar.radio("Navegação", ["Agenda Geral", "Agendar Visita"])
        logout_button()
        if page == "Agenda Geral":
            page_dashboard_comercial()
        else:
            page_agendar_visita()
    elif user["role"] == "loja":
        st.sidebar.radio("Navegação", ["Minhas Visitas"])
        logout_button()
        page_minhas_visitas_loja()

if __name__ == "__main__":
    main()
