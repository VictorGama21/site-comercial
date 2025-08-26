import streamlit as st
from datetime import date, timedelta
import pandas as pd
from utils import (
    get_stores, get_suppliers, ensure_supplier, get_promoters,
    create_visit, create_promoter_visit,
    list_visits, list_promoter_visits,
    concluir_visit, concluir_promoter_visit,
    WEEKDAYS_PT, SEGMENTOS_FIXOS,
    export_visitas_excel
)

# -----------------------------
# Página de agendamento de visitas de lojas
# -----------------------------
def page_agendar_visita_loja():
    st.header("Agendar Visita - Lojas")

    stores = get_stores()
    store_map = {s['name']: s['id'] for _, s in stores.iterrows()}
    compradores = ["Aldo", "Eduardo", "Henrique", "Jose Duda", "Thiago", "Victor", "Robson", "Outro"]
    
    with st.form("form_agendar_loja"):
        lojas_escolhidas = st.multiselect("Lojas", stores["name"].tolist())
        dt = st.date_input("Data", value=date.today() + timedelta(days=1))
        comprador = st.selectbox("Comprador responsável", compradores)
        fornecedor = st.text_input("Fornecedor")
        segmento = st.selectbox("Segmento", SEGMENTOS_FIXOS)
        garantia = st.selectbox("Garantia", ["", "Sim", "Não", "A confirmar"])
        info = st.text_area("Informações")
        repetir = st.checkbox("Repetir toda semana (4 semanas)")

        if st.form_submit_button("Agendar"):
            if not lojas_escolhidas or not fornecedor:
                st.warning("Preencha todos os campos obrigatórios.")
            else:
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
                st.success("✅ Visita agendada com sucesso!")
                st.experimental_rerun()

# -----------------------------
# Página de agendamento de visitas de promotores
# -----------------------------
def page_agendar_visita_promotor():
    st.header("Agendar Visita - Promotores")

    stores = get_stores()
    store_map = {s['name']: s['id'] for _, s in stores.iterrows()}
    promoters = get_promoters()
    promoter_map = {p['name']: p['id'] for _, p in promoters.iterrows()}

    with st.form("form_agendar_promotor"):
        lojas_escolhidas = st.multiselect("Lojas", stores["name"].tolist())
        dt = st.date_input("Data", value=date.today() + timedelta(days=1))
        promotor = st.selectbox("Promotor responsável", promoters["name"].tolist())
        campaign = st.text_input("Campanha / Ação")
        info = st.text_area("Observações")
        repetir = st.checkbox("Repetir toda semana (4 semanas)")

        if st.form_submit_button("Agendar"):
            if not lojas_escolhidas or not campaign:
                st.warning("Preencha todos os campos obrigatórios.")
            else:
                store_ids = [store_map[l] for l in lojas_escolhidas]
                create_promoter_visit(
                    store_ids=store_ids,
                    visit_date=dt,
                    promoter_id=promoter_map[promotor],
                    campaign=campaign,
                    observations=info,
                    created_by=st.session_state.user["id"],
                    repeat_weekly=repetir
                )
                st.success("✅ Visita de promotor agendada com sucesso!")
                st.experimental_rerun()

# -----------------------------
# Lista / Dashboard de visitas de lojas
# -----------------------------
def page_minhas_visitas_loja():
    st.header("Minhas Visitas - Lojas")

    user = st.session_state.user
    if not user or user["store_id"] is None:
        st.warning("Usuário não associado a nenhuma loja.")
        return

    status = st.multiselect("Status", ["Pendente", "Concluída"], default=["Pendente", "Concluída"])
    df = list_visits(store_id=user["store_id"], status=status)

    if df.empty:
        st.info("Nenhuma visita encontrada.")
        return

    excel_bytes = export_visitas_excel(df)
    st.download_button(
        "📥 Baixar visitas (Excel)",
        data=excel_bytes,
        file_name="minhas_visitas.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    for _, row in df.iterrows():
        st.write(f"📅 {row['data']} - Loja: {row['loja']} - Comprador: {row['comprador']} - Fornecedor: {row['fornecedor']}")
        if row.get("manager_comment"):
            st.info(f"💬 Comentário do Gerente: {row['manager_comment']}")
        comentario = st.text_area("💬 Comentário do gerente (opcional)", key=f"comentario_loja_{row['id']}")
        if row["status"] == "Pendente":
            if st.button("✅ Concluir visita", key=f"concluir_loja_{row['id']}"):
                concluir_visit(row["id"], user["id"], comentario if comentario.strip() else None)
                st.success("Visita concluída!")
                st.experimental_rerun()
        else:
            st.write("✔️ Já concluída")

# -----------------------------
# Lista / Dashboard de visitas de promotores
# -----------------------------
def page_minhas_visitas_promotor():
    st.header("Minhas Visitas - Promotores")

    user = st.session_state.user
    status = st.multiselect("Status", ["Pendente", "Concluída"], default=["Pendente", "Concluída"])
    df = list_promoter_visits(status=status)

    if df.empty:
        st.info("Nenhuma visita encontrada.")
        return

    excel_bytes = export_visitas_excel(df)
    st.download_button(
        "📥 Baixar visitas (Excel)",
        data=excel_bytes,
        file_name="visitas_promotores.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    for _, row in df.iterrows():
        st.write(f"📅 {row['data']} - Loja: {row['loja']} - Promotor: {row['promoter']} - Campanha: {row['campaign']}")
        comentario = st.text_area("💬 Comentário do gerente (opcional)", key=f"comentario_promotor_{row['id']}")
        if row["status"] == "Pendente":
            if st.button("✅ Concluir visita", key=f"concluir_promotor_{row['id']}"):
                concluir_promoter_visit(row["id"], user["id"], comentario if comentario.strip() else None)
                st.success("Visita concluída!")
                st.experimental_rerun()
        else:
            st.write("✔️ Já concluída")
