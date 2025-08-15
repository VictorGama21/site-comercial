import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date
import hashlib
from dateutil.relativedelta import relativedelta
import unidecode

DB_PATH = "visitas.db"


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
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS stores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('comercial','loja')),
            password_hash TEXT NOT NULL,
            store_id INTEGER,
            FOREIGN KEY(store_id) REFERENCES stores(id)
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS visits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_id INTEGER NOT NULL,
            visit_date DATE NOT NULL,
            weekday TEXT NOT NULL,
            buyer TEXT,
            supplier TEXT,
            segment TEXT,
            warranty TEXT,
            info TEXT,
            status TEXT NOT NULL DEFAULT 'Pendente' CHECK(status IN ('Pendente','Concluída')),
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            completed_by INTEGER,
            FOREIGN KEY(store_id) REFERENCES stores(id),
            FOREIGN KEY(created_by) REFERENCES users(id),
            FOREIGN KEY(completed_by) REFERENCES users(id)
        );
        """
    )

    conn.commit()
    conn.close()


def seed_data():
    """Cria dados de exemplo apenas se a BD estiver vazia."""
    conn = get_conn()
    cur = conn.cursor()

    lojas = [
        "HIPODROMO",
        "RIO DOCE",
        "CARUARU",
        "HIPODROMO CAFETERIA",
        "JANGA CAFETERIA",
        "ESPINHEIRO",
        "AFLITOS",
        "PONTA VERDE",
        "JATIUCA",
        "FAROL",
        "BEIRA MAR",
        "JARDIM ATLÂNTICO",
        "CASA CAIADA VERDAO",
        "JANGA VERDAO",
        "BAIRRO NOVO VERDAO"
    ]

    # Inserir lojas se ainda não existirem
    cur.execute("SELECT COUNT(*) FROM stores;")
    stores_count = cur.fetchone()[0]
    if stores_count == 0:
        for loja in lojas:
            cur.execute("INSERT OR IGNORE INTO stores(name) VALUES(?);", (loja,))

    # Obter IDs atualizados das lojas
    cur.execute("SELECT id, name FROM stores;")
    stores_map = {name: _id for _id, name in cur.fetchall()}

    # Inserir usuários se ainda não existirem
    cur.execute("SELECT COUNT(*) FROM users;")
    users_count = cur.fetchone()[0]
    if users_count == 0:
        users = [
            ("comercial@quitandaria.com", "Comercial Master", "comercial", hash_password("123456"), None)
        ]

        # Criar um usuário para cada loja
        for loja in lojas:
            email_loja = "loja." + unidecode.unidecode(loja.lower().replace(" ", ".")) + "@quitandaria.com"
            users.append((email_loja, loja, "loja", hash_password("123456"), stores_map.get(loja)))

        cur.executemany(
            "INSERT INTO users(email, name, role, password_hash, store_id) VALUES(?,?,?,?,?);",
            users
        )

    conn.commit()
    conn.close()


# -----------------------------
# Camada de dados (CRUD)
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
    cur.execute("SELECT id, email, name, role, password_hash, store_id FROM users WHERE email=?;", (email,))
    row = cur.fetchone()
    conn.close()
    if row:
        keys = ["id", "email", "name", "role", "password_hash", "store_id"]
        return dict(zip(keys, row))
    return None


def create_visit(store_id: int, visit_date: date, buyer: str, supplier: str, segment: str, warranty: str, info: str, created_by: int):
    wd = WEEKDAYS_PT[visit_date.weekday()]
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO visits (store_id, visit_date, weekday, buyer, supplier, segment, warranty, info, status, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pendente', ?);
        """,
        (store_id, visit_date.isoformat(), wd, buyer.strip(), supplier.strip(), segment.strip(), warranty.strip(), info.strip(), created_by),
    )
    conn.commit()
    conn.close()


def list_visits(store_id: int | None = None, status: list[str] | None = None, start: date | None = None, end: date | None = None):
    q = [
        "SELECT v.id, s.name AS loja, v.visit_date AS data, v.weekday AS dia_semana,",
        "v.buyer AS responsavel_comprador, v.supplier AS fornecedor, v.segment AS segmento,",
        "v.warranty AS garantia_comercial, v.info AS info, v.status, v.created_at, v.completed_at",
        "FROM visits v JOIN stores s ON s.id = v.store_id WHERE 1=1",
    ]
    params = []

    if store_id:
        q.append("AND v.store_id = ?")
        params.append(store_id)

    if status:
        placeholders = ",".join(["?"] * len(status))
        q.append(f"AND v.status IN ({placeholders})")
        params.extend(status)

    if start:
        q.append("AND date(v.visit_date) >= date(?)")
        params.append(start.isoformat())
    if end:
        q.append("AND date(v.visit_date) <= date(?)")
        params.append(end.isoformat())

    q.append("ORDER BY v.visit_date ASC, v.id ASC")

    conn = get_conn()
    df = pd.read_sql_query("\n".join(q), conn, params=params)
    conn.close()

    # Converter coluna data para datetime (p/ apresentação)
    if not df.empty:
        df["data"] = pd.to_datetime(df["data"]).dt.date
    return df


def mark_visit_completed(visit_id: int, user_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE visits
        SET status = 'Concluída', completed_at = CURRENT_TIMESTAMP, completed_by = ?
        WHERE id = ?;
        """,
        (user_id, visit_id),
    )
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
    with st.form("login_form", clear_on_submit=False):
        email = st.text_input("Email", placeholder="ex: loja@empresa.com")
        password = st.text_input("Senha", type="password")
        submitted = st.form_submit_button("Entrar")

    if submitted:
        user = get_user_by_email(email.strip().lower())
        if not user:
            st.error("Utilizador não encontrado.")
            return
        if not verify_password(password, user["password_hash"]):
            st.error("Senha inválida.")
            return
        st.session_state.user = {
            k: user[k] for k in ["id", "email", "name", "role", "store_id"]
        }
        st.success(f"Bem-vindo(a), {st.session_state.user['name']}!")
        st.rerun()

def logout_button():
    if st.sidebar.button("Terminar sessão", use_container_width=True):
        st.session_state.user = None
        st.rerun()

# -----------------------------
# Páginas
# -----------------------------

def page_agendar_visita():
    st.header("Agendar Visita (Comercial)")
    stores = get_stores()
    store_names = stores["name"].tolist()
    store_map = dict(zip(stores["name"], stores["id"]))

    with st.form("form_agendar"):
        loja_nome = st.selectbox("Loja", store_names)
        dt = st.date_input("Data da visita", value=date.today() + relativedelta(days=1))
        comprador = st.text_input("Responsável Comprador da Categoria")
        fornecedor = st.text_input("Fornecedor")
        segmento = st.text_input("Segmento da visita")
        garantia = st.selectbox("Garantia comercial", ["", "Sim", "Não", "A confirmar"])
        info = st.text_area("Informação (Troca / Validade / Observações)")
        submitted = st.form_submit_button("Agendar")

    if submitted:
        if not loja_nome:
            st.warning("Selecione a loja.")
            return
        if not fornecedor:
            st.warning("Informe o fornecedor.")
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
        )
        st.success("Visita agendada com sucesso!")


def page_minhas_visitas_loja():
    st.header("Minhas Visitas (Loja)")

    user = st.session_state.user
    store_id = user["store_id"]

    colf1, colf2 = st.columns(2)
    with colf1:
        status = st.multiselect("Status", ["Pendente", "Concluída"], default=["Pendente"])
    with colf2:
        start = st.date_input("Início", value=date.today() - relativedelta(days=7))
        end = st.date_input("Fim", value=date.today() + relativedelta(days=30))

    df = list_visits(store_id=store_id, status=status, start=start, end=end)

    if df.empty:
        st.info("Nenhuma visita encontrada para o período/estado selecionado.")
        return

    st.dataframe(df, use_container_width=True, hide_index=True)

    st.subheader("Marcar visita como concluída")
    ids = df["id"].tolist()
    if ids:
        visit_id = st.selectbox("Selecionar visita", ids, format_func=lambda i: f"#{i} - {df.loc[df['id']==i, 'loja'].iloc[0]} - {df.loc[df['id']==i, 'data'].iloc[0]}")
        if st.button("Marcar Concluída"):
            mark_visit_completed(visit_id, user_id=user["id"])
            st.success("Visita marcada como concluída.")
            st.rerun()

def page_dashboard_comercial():
    st.header("Agenda Geral (Comercial)")

    stores = get_stores()
    stores_filter = ["Todas"] + stores["name"].tolist()

    col1, col2, col3 = st.columns(3)
    with col1:
        loja_nome = st.selectbox("Loja", stores_filter)
        loja_id = None if loja_nome == "Todas" else int(stores.loc[stores["name"] == loja_nome, "id"].iloc[0])
    with col2:
        status = st.multiselect("Status", ["Pendente", "Concluída"], default=["Pendente", "Concluída"])
    with col3:
        start = st.date_input("Início", value=date.today() - relativedelta(days=7))
        end = st.date_input("Fim", value=date.today() + relativedelta(days=60))

    df = list_visits(store_id=loja_id, status=status, start=start, end=end)

    if df.empty:
        st.info("Sem visitas no período/critério selecionado.")
        return

    st.dataframe(df, use_container_width=True, hide_index=True)

    # KPIs simples
    st.subheader("Resumo")
    k1, k2 = st.columns(2)
    with k1:
        st.metric("Total de visitas", len(df))
    with k2:
        concl = (df["status"] == "Concluída").sum()
        st.metric("Concluídas", int(concl))


# -----------------------------
# App principal
# -----------------------------

def main():
    st.set_page_config(page_title="Sistema de Visitas", page_icon="📅", layout="wide")

    # Inicialização de BD e seed
    init_db()
    seed_data()

    st.sidebar.title("📅 Sistema de Visitas")

    if "user" not in st.session_state:
        st.session_state.user = None

    if st.session_state.user is None:
        login_form()
        st.caption("Dica: Em caso de duvidas acionar o time comercial (81) 992042186 Victor Analista de Compras")
        return

    # Sidebar info do utilizador
    user = st.session_state.user
    st.sidebar.write(f"*Utilizador:* {user['name']}")
    st.sidebar.write(f"*Perfil:* {user['role'].capitalize()}")

    # Navegação por perfil
    if user["role"] == "comercial":
        page = st.sidebar.radio("Navegação", ["Agenda Geral", "Agendar Visita"])  # ordem
        logout_button()

        if page == "Agenda Geral":
            page_dashboard_comercial()
        else:
            page_agendar_visita()

    elif user["role"] == "loja":
        page = st.sidebar.radio("Navegação", ["Minhas Visitas"])  # simples para loja
        logout_button()

        page_minhas_visitas_loja()

    else:
        st.error("Perfil desconhecido. Contacte o administrador.")


if __name__ == "__main__":
    main()
