import streamlit as st
from datetime import date, timedelta
from main_functions import get_stores, create_visit, SEGMENTOS_FIXOS  # Importa suas funções já existentes

def page_agendar_visita_loja():
    st.subheader("Agendamento de Visitas - Lojas")
    stores = get_stores()
    compradores = ["Aldo", "Eduardo", "Henrique", "Jose Duda", "Thiago", "Victor", "Robson", "Outro"]

    with st.form("form_loja"):
        lojas_escolhidas = st.multiselect("Lojas", stores["name"].tolist())
        dt = st.date_input("Data", value=date.today() + timedelta(days=1))
        comprador = st.selectbox("Comprador responsável", compradores)
        fornecedor = st.text_input("Fornecedor")
        segmento = st.selectbox("Segmento", SEGMENTOS_FIXOS)
        garantia = st.selectbox("Garantia comercial", ["", "Sim", "Não", "A confirmar"])
        info = st.text_area("Informações")
        repetir = st.checkbox("Repetir toda semana (4 semanas)")

        submitted = st.form_submit_button("Agendar")

    if submitted:
        if not lojas_escolhidas or not fornecedor:
            st.warning("Preencha todos os campos obrigatórios.")
        else:
            store_ids = [store["id"] for store in stores if store["name"] in lojas_escolhidas]
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
            st.success("✅ Visita agendada com sucesso!")

def page_agendar_visita_degustacao():
    st.subheader("Agendamento de Degustação / Promotor")
    promotores = ["Promotor A", "Promotor B", "Promotor C"]  # Pode vir do DB depois
    campanhas = ["Campanha 1", "Campanha 2", "Campanha 3"]

    with st.form("form_degustacao"):
        promotor = st.selectbox("Promotor responsável", promotores)
        dt = st.date_input("Data", value=date.today() + timedelta(days=1))
        local = st.text_input("Local da Degustação")
        campanha = st.selectbox("Campanha", campanhas)
        info = st.text_area("Observações")
        repetir = st.checkbox("Repetir toda semana (4 semanas)")

        submitted = st.form_submit_button("Agendar Degustação")

    if submitted:
        if not local:
            st.warning("Preencha o local da degustação.")
        else:
            # Aqui você pode criar uma função específica ou reaproveitar create_visit com algum tipo="degustacao"
            create_visit(
                store_ids=[],  # Pode ser vazio ou armazenar em outro campo tipo 'location'
                visit_date=dt,
                buyer=promotor,
                supplier=campanha,
                segment="Degustação",
                warranty="",
                info=info,
                created_by=st.session_state.user["id"],
                repeat_weekly=repetir
            )
            st.success("✅ Degustação agendada com sucesso!")

# -------------------------
# Página única de agendamento
# -------------------------
def page_agendar():
    tipo_visita = st.radio("Tipo de visita", ["Promotor", "Degustação"])

    if tipo_visita == "Promotor":
        page_agendar_visita_loja()
    else:
        page_agendar_visita_degustacao()
