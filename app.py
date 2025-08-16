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
            status TEXT NOT NULL DEFAULT 'Pendente' CHECK(status IN ('Pendente','Concluída')),
            created_by INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            completed_by INTEGER REFERENCES users(id)
        );
    """)

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

def get_suppliers():
    conn = get_conn()
    df = pd.read_sql_query("SELECT id, name FROM suppliers ORDER BY name;", conn)
    conn.close()
    return df

def ensure_supplier(name: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO suppliers(name) VALUES(%s) ON CONFLICT(name) DO UPDATE SET name=EXCLUDED.name RETURNING id;", (name.strip(),))
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
        insert_one(visit_date, store_id)
        if repeat_weekly:
            for i in range(1, 4):
                insert_one(visit_date + relativedelta(weeks=i), store_id)

    conn.commit()
    conn.close()

def list_visits(store_id=None, status=None, start=None, end=None):
    q = [
        "SELECT v.id, s.name AS loja, v.visit_date AS data, v.weekday AS dia_semana,",
        "v.buyer AS comprador, sp.name AS fornecedor, v.segment AS segmento,",
        "v.warranty AS garantia, v.info AS info, v.status",
        "FROM visits v JOIN stores s ON s.id = v.store_id JOIN suppliers sp ON sp.id = v.supplier_id WHERE 1=1"
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

def update_visit(visit_id: int, buyer: str, supplier: str, segment: str, warranty: str, info: str):
    supplier_id = ensure_supplier(supplier)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE visits
        SET buyer=%s, supplier_id=%s, segment=%s, warranty=%s, info=%s
        WHERE id=%s;
    """, (buyer, supplier_id, segment, warranty, info, visit_id))
    conn.commit()
    conn.close()

def delete_visit(visit_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM visits WHERE id=%s;", (visit_id,))
    conn.commit()
    conn.close()

# -----------------------------
# UI Helpers
# -----------------------------
def style_table(df):
    def highlight_status(val):
        if val == "Concluída":
            return "background-color: #90EE90; color: black;"
        elif val == "Pendente":
            return "background-color: #FF7F7F; color: black;"
        return ""
    return df.style.applymap(highlight_status, subset=["status"])

# -----------------------------
# Páginas
# -----------------------------
def page_agendar_visita():
    st.header("Agendar Visita")
    stores = get_stores()
    store_map = dict(zip(stores["name"], stores["id"]))
    fornecedores_sugestao = get_suppliers()["name"].tolist()
    compradores = ["Aldo", "Eduardo", "Henrique", "Jose Duda", "Thiago", "Victor", "Robson", "Outro"]

    with st.form("form_agendar"):
        lojas_escolhidas = st.multiselect("Lojas", stores["name"].tolist())
        dt = st.date_input("Data", value=date.today() + timedelta(days=1), format="DD/MM/YYYY")
        comprador = st.selectbox("Comprador responsável", compradores)
        fornecedor = st.text_input("Fornecedor", value="")
        segmento = st.selectbox("Segmento", SEGMENTOS_FIXOS)
        garantia = st.selectbox("Garantia comercial", ["", "Sim", "Não", "A confirmar"])
        info = st.text_area("Informações")
        repetir = st.checkbox("Repetir toda semana (4 semanas)")
        submitted = st.form_submit_button("Agendar")

    if submitted:
        if not lojas_escolhidas or not fornecedor:
            st.warning("Preencha todos os campos obrigatórios.")
            return
        store_ids = [store_map[l] for l in lojas_escolhidas]
        create_visit(
            store_ids=store_ids,
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
        start = st.date_input("Início", value=date.today() - timedelta(days=7), format="DD/MM/YYYY")
        end = st.date_input("Fim", value=date.today() + timedelta(days=60), format="DD/MM/YYYY")

    df = list_visits(store_id=loja_id, status=status, start=start, end=end)
    if df.empty:
        st.info("Sem visitas no período.")
        return

    st.dataframe(style_table(df), use_container_width=True, hide_index=True)
    st.metric("Total de visitas", len(df))
    st.metric("Concluídas", (df["status"] == "Concluída").sum())

    # Dashboard analítico
    st.subheader("📊 Dashboard Analítico")
    col1, col2 = st.columns(2)
    with col1:
        fig1 = px.histogram(df, x="segmento", color="status", title="Visitas por Segmento")
        st.plotly_chart(fig1, use_container_width=True)
    with col2:
        fig2 = px.histogram(df, x="loja", color="status", title="Visitas por Loja")
        st.plotly_chart(fig2, use_container_width=True)

    fig3 = px.line(df, x="data", color="status", title="Evolução das Visitas")
    st.plotly_chart(fig3, use_container_width=True)

    # --- Editar e Excluir ---
    st.subheader("Editar/Excluir Visitas")
    visit_id = st.selectbox("Selecione uma visita", df["id"].tolist())
    if visit_id:
        vrow = df[df["id"] == visit_id].iloc[0]
        comprador = st.text_input("Comprador", vrow["comprador"])
        fornecedor = st.text_input("Fornecedor", vrow["fornecedor"])
        segmento = st.selectbox("Segmento", SEGMENTOS_FIXOS, index=SEGMENTOS_FIXOS.index(vrow["segmento"]) if vrow["segmento"] in SEGMENTOS_FIXOS else 0)
        garantia = st.selectbox("Garantia", ["", "Sim", "Não", "A confirmar"], index=["", "Sim", "Não", "A confirmar"].index(vrow["garantia"]) if vrow["garantia"] in ["", "Sim", "Não", "A confirmar"] else 0)
        info = st.text_area("Informações", vrow["info"])

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Salvar alterações"):
                update_visit(visit_id, comprador, fornecedor, segmento, garantia, info)
                st.success("Visita atualizada!")
                st.rerun()
        with col2:
            if st.button("Excluir visita"):
                delete_visit(visit_id)
                st.warning("Visita excluída!")
                st.rerun()

# -----------------------------
# App principal
# -----------------------------
def main():
    st.set_page_config(page_title="Sistema de Visitas", layout="wide")
    st.markdown("""
        <style>
            body {background: linear-gradient(135deg, #FF8C42, #FFB347);} 
            .stButton>button {background-color: #FF8C42; color: white; font-weight: bold; border-radius: 10px;}
        </style>
    """, unsafe_allow_html=True)

    init_db()
    seed_data()

    st.sidebar.title("📅 Sistema de Visitas - Quitandaria")
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
