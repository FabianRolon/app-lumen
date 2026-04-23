import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
from config import RUTAS

# --- FUNCIONES DE BASE DE DATOS ---

def guardar_control_horario(datos):
    try:
        conn = sqlite3.connect(RUTAS["lab"])
        cursor = conn.cursor()
        # Crea la tabla automáticamente si no existe en la base de datos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS embalaje_controles_horarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT,
                hora TEXT,
                maquina TEXT,
                op TEXT,
                embalador TEXT,
                tension TEXT,
                visual TEXT,
                obs TEXT
            )
        ''')
        cursor.execute(''' 
            INSERT INTO embalaje_controles_horarios 
            (fecha, hora, maquina, op, embalador, tension, visual, obs) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?) 
        ''', datos)
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Error al guardar control horario: {e}")
        return False

def guardar_cierre_embalaje(datos):
    try:
        conn = sqlite3.connect(RUTAS["lab"])
        cursor = conn.cursor()
        # Crea la tabla automáticamente si no existe en la base de datos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS embalaje_cierre_turno (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT,
                turno TEXT,
                maquina TEXT,
                op TEXT,
                producto TEXT,
                embalador TEXT,
                cajas INTEGER,
                unidades_caja INTEGER,
                total INTEGER,
                descarte REAL,
                motivo TEXT,
                obs TEXT
            )
        ''')
        cursor.execute(''' 
            INSERT INTO embalaje_cierre_turno 
            (fecha, turno, maquina, op, producto, embalador, cajas, unidades_caja, total, descarte, motivo, obs) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) 
        ''', datos)
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Error al guardar cierre de embalaje: {e}")
        return False

def cargar_controles_hoy(maquina, op, fecha):
    try:
        conn = sqlite3.connect(RUTAS["lab"])
        df = pd.read_sql_query(f'''
            SELECT hora as HORA, embalador as LEGAJO, tension as TENSION, visual as VISUAL, obs as OBS 
            FROM embalaje_controles_horarios 
            WHERE maquina='{maquina}' AND op='{op}' AND fecha='{fecha}' 
            ORDER BY hora DESC
        ''', conn)
        conn.close()
        return df
    except:
        return pd.DataFrame() # Si la tabla no existe aún, devuelve dataframe vacío

# --- INTERFAZ VISUAL ---

def interfaz_embalaje(maquina, datos_orden):
    st.markdown(f"### 📦 Módulo de Embalaje - {maquina}")
    
    # 1. Extraer datos de la orden activa con seguridad (Manejo de nulos)
    if not datos_orden.empty:
        fila = datos_orden.iloc[0]
        op_activa = str(fila.get("LOTE_LUMEN", "-")).replace(".0", "").strip()
        # Busca DESCRIP, si no está usa ARTICULO, si no, un guión.
        producto_activo = str(fila.get("DESCRIP", fila.get("ARTICULO", "-"))).strip()
    else:
        op_activa = "-"
        producto_activo = "-"

    st.info(f"**Orden Activa:** {op_activa} | **Producto:** {producto_activo}")

    # 2. Dividimos el módulo en las dos instancias del mundo real
    tab_ctrl, tab_cierre = st.tabs(["⏱️ Controles por Hora", "📊 Cierre de Embalaje (Turno)"])
    fecha_actual = datetime.now().strftime("%Y-%m-%d")

    # ==========================================
    # PESTAÑA 1: CONTROLES POR HORA
    # ==========================================
    with tab_ctrl:
        st.markdown("#### Registro de Calidad en Línea")
        col_form, col_hist = st.columns([1, 1])
        
        with col_form:
            with st.form(key=f"form_ctrl_{maquina}"):
                embalador_ctrl = st.text_input("Nº Embalador / Legajo", key=f"leg_ctrl_{maquina}")
                
                st.markdown("**Inspección**")
                tension = st.radio("Tensión (Polariscopio)", ["Conforme", "No Conforme"], horizontal=True)
                visual = st.radio("Control Visual", ["Conforme", "No Conforme"], horizontal=True)
                
                obs_ctrl = st.text_input("Observaciones (Opcional)", key=f"obs_ctrl_{maquina}")
                
                submit_ctrl = st.form_submit_button("💾 Guardar Control Horario", use_container_width=True)
                
                if submit_ctrl:
                    if not embalador_ctrl:
                        st.warning("⚠️ Ingrese su legajo para firmar el control.")
                    else:
                        hora_actual = datetime.now().strftime("%H:%M:%S")
                        datos_ctrl = (fecha_actual, hora_actual, maquina, op_activa, embalador_ctrl, tension, visual, obs_ctrl)
                        if guardar_control_horario(datos_ctrl):
                            st.success("✅ Control guardado correctamente.")
                            st.rerun()

        with col_hist:
            df_hist = cargar_controles_hoy(maquina, op_activa, fecha_actual)
            if not df_hist.empty:
                st.dataframe(df_hist, use_container_width=True, hide_index=True)
            else:
                st.info("No hay controles registrados hoy para esta orden.")

    # ==========================================
    # PESTAÑA 2: CIERRE DE TURNO
    # ==========================================
    with tab_cierre:
        st.markdown("#### Informe Final (Cantidades y Descarte)")
        with st.form(key=f"form_cierre_{maquina}"):
            c1, c2, c3 = st.columns(3)
            with c1:
                turno = st.selectbox("Turno", ["Mañana", "Tarde", "Noche"])
                embalador_cierre = st.text_input("Nº Embalador / Legajo", key=f"leg_cierre_{maquina}")
            with c2:
                cajas = st.number_input("Cajas Armadas", min_value=0, step=1)
                unidades_caja = st.number_input("Unidades por Caja", min_value=0, step=1)
            with c3:
                descarte = st.number_input("Descarte (Kg o Unidades)", min_value=0.0, step=0.1)
                motivo = st.text_input("Motivo del Descarte")

            obs_cierre = st.text_area("Observaciones generales del turno")
            
            submit_cierre = st.form_submit_button("💾 Guardar Cierre de Embalaje", use_container_width=True, type="primary")

            if submit_cierre:
                if not embalador_cierre:
                    st.warning("⚠️ Por favor, ingrese el legajo del embalador.")
                elif cajas == 0:
                    st.warning("⚠️ La cantidad de cajas armadas debe ser mayor a 0 para el cierre.")
                else:
                    total_unidades = cajas * unidades_caja
                    datos_cierre = (
                        fecha_actual, turno, maquina, op_activa, producto_activo, 
                        embalador_cierre, cajas, unidades_caja, total_unidades, 
                        descarte, motivo, obs_cierre
                    )
                    if guardar_cierre_embalaje(datos_cierre):
                        st.success(f"✅ ¡Cierre de turno guardado! Total embalado: **{total_unidades}** unidades.")
                        st.balloons() # Pequeña animación de éxito
                        # No hacemos rerun de inmediato para que puedan leer el mensaje de éxito y ver el cálculo total