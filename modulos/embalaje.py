import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
from config import RUTAS
from utils.db_helpers import obtener_operarios_habilitados, validar_pin_operario
from utils.data_core import cargar_asistencia

# --- MOTORES DE BASE DE DATOS ---
def guardar_embalaje(datos):
    try:
        conn = sqlite3.connect(RUTAS["lab"])
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO registro_embalaje 
            (fecha, hora, turno, maquina, op, producto, embalador, cajas, unidades_caja, total, descarte, motivo, tension, visual, obs) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', datos)
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Error al guardar: {e}")
        return False

def cargar_historial_embalaje(maquina, op, fecha):
    conn = sqlite3.connect(RUTAS["lab"])
    df = pd.read_sql_query('''
        SELECT hora as Hora, embalador as Legajo, cajas as Cajas, unidades_caja as "U/Caja", descarte as "Desc(Kg)"
        FROM registro_embalaje 
        WHERE maquina=? AND op=? AND fecha=? ORDER BY hora DESC
    ''', conn, params=(maquina, op, fecha))
    conn.close()
    return df

def cerrar_embalaje(maquina, op, fecha):
    try:
        conn = sqlite3.connect(RUTAS["lab"])
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE registro_embalaje SET estado = 'CERRADO' 
            WHERE maquina = ? AND op = ? AND fecha = ?
        ''', (maquina, op, fecha))
        conn.commit()
        conn.close()
        return True
    except:
        return False

# --- INTERFAZ VISUAL ---
def interfaz_embalaje(maquina, op_actual, prod_actual):
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
    
    # --- 1. ARREGLO DE OPERARIOS ---
    # Protegemos la consulta para asegurarnos de que nunca falle y siempre tenga el "-"
    operarios_db = cargar_asistencia()
    if not operarios_db.empty:
            # Extraemos los legajos, quitamos nulos y los convertimos a texto limpio
            lista_operarios = operarios_db['LEGAJO'].dropna().unique().tolist()
            lista_operarios = [str(int(x)) for x in lista_operarios]
    else:
        lista_operarios = []

    try:
        conn = sqlite3.connect(RUTAS["lab"])
        # Traemos legajo y nombre de la tabla de credenciales
        df_credenciales = pd.read_sql_query("SELECT legajo, nombre FROM credenciales_empleados", conn)
        conn.close()

        if not df_credenciales.empty:
            # Combinamos las columnas para armar el formato "1234 - Juan Perez"
            lista_operarios = (df_credenciales['legajo'].astype(str) + " - " + df_credenciales['nombre']).tolist()
    except Exception as e:
        st.error(f"Error al cargar credenciales: {e}")

    st.markdown("#### Registro Horario de Embalaje")
    col_form, col_hist = st.columns([3, 2])
    
    with col_form:
        with st.container(border=True):
            # 1. FORMULARIO DE CONTROL HORARIO
            with st.form(f"form_embalaje_{maquina}", clear_on_submit=True):
                
                # --- 2. VOLAMOS LA HORA ---
                # Pasamos de 4 a 3 columnas
                c1, c2, c3 = st.columns([2, 1, 1])
                with c1: embalador = st.selectbox("🧑‍🔧 Legajo Embalador", options=["Seleccionar..."] + lista_operarios)
                with c2: pin_emb = st.text_input("🔑 PIN", type="password")
                with c3: cajas = st.number_input("Cajas", min_value=0, step=1)
                    
                c5, c6 = st.columns(2)
                with c5: unidades_caja = st.number_input("Unidades por Caja", min_value=0, step=1)
                with c6: descarte = st.number_input("Descarte (Kg)", min_value=0.0, step=0.1)

                st.markdown("**🔍 Inspección de Calidad (Tubos)**")
                col_ctrl1, col_ctrl2, col_ctrl3 = st.columns(3)
                with col_ctrl1: tension = st.selectbox("Tensión / Polariscopio", ["OK", "Rechazo", "-"])
                with col_ctrl2: visual = st.selectbox("Inspección Visual", ["OK", "Rechazo", "-"])
                with col_ctrl3: motivo_desc = st.text_input("Motivo Descarte")

                obs = st.text_input("Observaciones")
                
                if st.form_submit_button("💾 Guardar Control", use_container_width=True):
                    if embalador == "-":
                        st.warning("⚠️ Debes seleccionar un operario válido.")
                    else:
                        legajo_limpio = embalador.split(" - ")[0]
                        
                        # --- VALIDACIÓN DE PIN ---
                        if validar_pin_operario(legajo_limpio, pin_emb):
                            
                            # --- 3. HORA AUTOMÁTICA DEL SISTEMA ---
                            hora_str = datetime.now().strftime("%H:%M:%S")

                            # Calculamos el total (si no lo tenías ya calculado más arriba en tu interfaz)
                            total_unidades = cajas * unidades_caja
                            
                            datos_insert = (fecha_hoy, hora_str, maquina, op_actual, prod_actual, legajo_limpio, cajas, unidades_caja, total_unidades, descarte, motivo_desc, tension, visual, obs)
                            if guardar_embalaje(datos_insert):
                                st.rerun()
                        else:
                            st.error("❌ PIN incorrecto. Intenta de nuevo.")

            # 2. CIERRE DE LÍNEA DE EMBALAJE
            st.markdown("---")
            c_pin1, c_pin2, c_pin3 = st.columns([2, 1, 1])
            with c_pin1: 
                pin_cierre_sel = st.selectbox("🔒 Supervisor Cierre", lista_operarios, key=f"cierre_{maquina}")
            with c_pin2:
                pin_cierre_pass = st.text_input("🔑 PIN", type="password", key=f"c_pass_{maquina}")
            with c_pin3:
                st.write("") 
                if st.button("🛑 CERRAR OP", type="primary", use_container_width=True):
                    if pin_cierre_sel == "-":
                        st.warning("⚠️ Selecciona un supervisor.")
                    else:
                        legajo_cierre = pin_cierre_sel.split(" - ")[0]
                        if validar_pin_operario(legajo_cierre, pin_cierre_pass):
                            if cerrar_embalaje(maquina, op_actual, fecha_hoy):
                                st.success(f"✅ La orden {op_actual} ha sido cerrada.")
                                st.rerun()
                        else:
                            st.error("❌ PIN incorrecto.")
                    
    # MOSTRAR EL HISTORIAL DEL DÍA
    with col_hist:
        df_hist = cargar_historial_embalaje(maquina, op_actual, fecha_hoy)
        if not df_hist.empty:
            st.dataframe(df_hist, use_container_width=True, hide_index=True)
        else:
            st.info("Aún no hay cajas registradas para esta orden.")