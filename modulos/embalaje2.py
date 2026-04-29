import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
from config import RUTAS
from utils.db_helpers import obtener_operarios_habilitados, validar_pin_operario

# --- MOTORES DE GUARDADO ---

def guardar_control_calidad_embalaje(datos):
    try:
        conn = sqlite3.connect(RUTAS["lab"])
        cursor = conn.cursor()
        # Asumiendo una nueva tabla para controles periódicos
        cursor.execute('''
            INSERT INTO controles_embalaje (fecha, hora, maquina, lote_lumen, embalador, tension, visual, obs)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', datos)
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Error al guardar control: {e}")
        return False

def guardar_cierre_produccion_embalaje(datos):
    try:
        conn = sqlite3.connect(RUTAS["lab"])
        cursor = conn.cursor()
        # Asumiendo tu tabla original pero solo para el cierre
        cursor.execute('''
            INSERT INTO registro_embalaje (fecha, turno, maquina, lote_lumen, producto, embalador, cajas, unidades_caja, total, descarte, motivo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', datos)
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Error al guardar cierre: {e}")
        return False

def cargar_historial_controles(maquina, fecha):
    try:
        conn = sqlite3.connect(RUTAS["lab"])
        df = pd.read_sql_query('''
            SELECT hora as HORA, embalador as OPERARIO, tension as TENSION, visual as VISUAL, obs as OBS 
            FROM controles_embalaje 
            WHERE maquina=? AND fecha=? ORDER BY hora DESC
        ''', conn, params=(maquina, fecha))
        conn.close()
        return df
    except:
        return pd.DataFrame()

# --- INTERFAZ PRINCIPAL ---

def interfaz_embalaje(maquina, lote_lumen, nombre_producto):
    st.markdown(f"### 📦 Sector Embalaje - {maquina}")
    st.caption(f"**Lote:** {lote_lumen} | **Producto:** {nombre_producto}")
    
    ahora = datetime.now()
    fecha_hoy = ahora.strftime("%Y-%m-%d")
    hora_actual = ahora.strftime("%H:%M:%S")

    # Cargamos la lista de operarios habilitados (DRY aplicado)
    lista_operarios = obtener_operarios_habilitados()

    # Dividimos la pantalla en dos pestañas claras
    tab_qc, tab_prod = st.tabs(["🔍 1. Controles de Calidad", "📦 2. Cierre de Producción"])

    # ==========================================
    # PESTAÑA 1: CONTROLES PERIÓDICOS (Llevan Hora)
    # ==========================================
    with tab_qc:
        with st.form(f"form_qc_{maquina}"):
            st.markdown(f"**Control de las {hora_actual}**")
            col1, col2 = st.columns(2)
            tension = col1.selectbox("Control de Tensión", ["OK", "Baja", "Alta", "Descarte"])
            visual = col2.selectbox("Control Visual", ["OK", "Manchas", "Rayas", "Roturas"])
            obs = st.text_input("Observaciones (Opcional)")
            
            st.divider()
            col_op, col_pin, col_btn = st.columns([2, 1, 1])
            operario_qc = col_op.selectbox("Operador", lista_operarios, key=f"op_qc_{maquina}")
            pin_qc = col_pin.text_input("PIN", type="password", key=f"pin_qc_{maquina}")
            btn_qc = col_btn.form_submit_button("Guardar Control", use_container_width=True)

            if btn_qc:
                if operario_qc == "-":
                    st.warning("⚠️ Selecciona un operario.")
                else:
                    legajo_qc = operario_qc.split(" - ")[0]
                    if validar_pin_operario(legajo_qc, pin_qc):
                        datos_qc = (fecha_hoy, hora_actual, maquina, lote_lumen, legajo_qc, tension, visual, obs)
                        if guardar_control_calidad_embalaje(datos_qc):
                            st.success("✅ Control guardado.")
                            st.rerun()
                    else:
                        st.error("❌ PIN incorrecto.")
        
        # Historial del día para que el embalador vea sus controles previos
        st.markdown("##### 📋 Historial de hoy")
        df_historial = cargar_historial_controles(maquina, fecha_hoy)
        if not df_historial.empty:
            st.dataframe(df_historial, use_container_width=True, hide_index=True)
        else:
            st.info("No hay controles registrados hoy para esta máquina.")

    # ==========================================
    # PESTAÑA 2: CIERRE DE PRODUCCIÓN (Al final del turno)
    # ==========================================
    with tab_prod:
        st.info("⚠️ Llenar únicamente al finalizar el turno o cambiar de orden.")
        with st.form(f"form_cierre_{maquina}"):
            turno = st.selectbox("Turno a cerrar", ["Mañana", "Tarde", "Noche"])
            
            col1, col2 = st.columns(2)
            cajas = col1.number_input("Cajas Armadas", min_value=0, step=1)
            unidades_caja = col2.number_input("Unidades por Caja", min_value=0, step=1)
            
            total_unidades = cajas * unidades_caja
            st.info(f"**Producción Total a declarar:** {total_unidades} unidades.")
            
            col3, col4 = st.columns(2)
            descarte = col3.number_input("Descarte (Unidades)", min_value=0, step=1)
            motivo = col4.text_input("Motivo de Descarte (Si aplica)")
            
            st.divider()
            col_op2, col_pin2, col_btn2 = st.columns([2, 1, 1])
            operario_prod = col_op2.selectbox("Operador", lista_operarios, key=f"op_prod_{maquina}")
            pin_prod = col_pin2.text_input("PIN", type="password", key=f"pin_prod_{maquina}")
            btn_prod = col_btn2.form_submit_button("Cerrar Producción", use_container_width=True)

            if btn_prod:
                if operario_prod == "-":
                    st.warning("⚠️ Selecciona un operario.")
                else:
                    legajo_prod = operario_prod.split(" - ")[0]
                    if validar_pin_operario(legajo_prod, pin_prod):
                        datos_prod = (fecha_hoy, turno, maquina, lote_lumen, nombre_producto, legajo_prod, cajas, unidades_caja, total_unidades, descarte, motivo)
                        if guardar_cierre_produccion_embalaje(datos_prod):
                            st.success("📦 Cierre de producción guardado exitosamente.")
                    else:
                        st.error("❌ PIN incorrecto.")