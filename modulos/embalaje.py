import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
from utils.db_helpers import obtener_operarios_habilitados, validar_pin_operario
from config import RUTAS

# --- MOTOR DE BASE DE DATOS ---

def guardar_registro_clt02(datos):
    try:
        conn = sqlite3.connect(RUTAS["lab"])
        cursor = conn.cursor()
        
        # 1. Creamos la tabla limpia (sin los campos de cajas/producción)
        cursor.execute(''' 
            CREATE TABLE IF NOT EXISTS registro_clt02 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT, 
                maquina TEXT, 
                op TEXT, 
                producto TEXT,
                embalador TEXT, 
                c_medidas TEXT, 
                c_impresion TEXT, 
                c_tensiones TEXT, 
                c_aspecto TEXT,
                obs TEXT
            )
        ''')
        
        # 2. El INSERT ahora solo tiene 10 campos para coincidir con tus datos
        cursor.execute(''' 
            INSERT INTO registro_clt02 
            (fecha, maquina, op, producto, embalador, 
             c_medidas, c_impresion, c_tensiones, c_aspecto, obs) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) 
        ''', datos)
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Error al guardar CLT02: {e}")
        return False

def obtener_historial_clt02(maquina):
    try:
        conn = sqlite3.connect(RUTAS["lab"])
        # Volvemos a poner el WHERE, pero ajustando la fecha a formato Día/Mes/Año
        query = f"""
            SELECT fecha, maquina, op, producto, 
                   c_medidas as MEDIDAS, c_impresion as IMPRESION, c_aspecto as ASPECTO, obs as OBSERVACIONES 
            FROM registro_clt02 
            WHERE maquina = '{maquina}' AND fecha = '{datetime.now().strftime('%d/%m/%Y')}' 
            ORDER BY id DESC
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except Exception as e:
        st.error(f"Error al buscar historial CLT02: {e}") 
        return pd.DataFrame()
    
def guardar_registro_ide07(datos):   
    try:
        # Nos conectamos a la base de datos configurada
        conn = sqlite3.connect(RUTAS["lab"])
        cursor = conn.cursor()
        
        # Insertamos los 14 datos en el orden exacto del formulario
        cursor.execute(''' 
            INSERT INTO registro_embalaje (
                fecha, turno, maquina, op, producto, embalador, 
                cajas, unidades_caja, total, descarte, motivo, 
                tension, visual, obs
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) 
        ''', datos)
        
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        # Si algo falla, lo mostramos en pantalla sin que se rompa la app
        st.error(f"❌ Error al guardar el informe IDE 07: {e}")
        return False
    
def obtener_historial_ide07(maquina):    
    conn = sqlite3.connect(RUTAS["lab"])
    query = """
        SELECT fecha as FECHA, turno as TURNO, embalador as OPERARIO, 
               producto as PRODUCTO, cajas as CAJAS, total as TOTAL_UNIDADES, 
               descarte as DESCARTE
        FROM registro_embalaje 
        WHERE maquina = ? 
        ORDER BY id DESC LIMIT 5
    """
    df = pd.read_sql_query(query, conn, params=(maquina,))
    conn.close()
    return df


# --- INTERFAZ DE USUARIO ---

def interfaz_embalaje(maquina, lote, producto):
    st.markdown("### 📦 Control de Embalaje - Formulario CLT02")
    
    # Cabecera informativa
    st.info(f"**Máquina:** {maquina} | **Lote/OP:** {lote} | **Producto:** {producto}")

    lista_operarios = obtener_operarios_habilitados()
    opciones_check = ["Conforme", "No Conforme"]
    opciones_check_1 = ["Conforme", "No Conforme", "N/A"]

    # 📑 Creamos las pestañas a nivel de diseño, NO dentro del formulario
    tab_prod, tab_cc = st.tabs(["📦 Producción (IDE07)", "🧪 Calidad (CLT02)"])

    # ==========================================
    # 📦 FORMULARIO 1: PRODUCCIÓN Y DESCARTE (IDE07)
    # ==========================================
    with tab_prod:
        with st.form(f"form_ide07_{maquina}", clear_on_submit=True):
            st.markdown("#### Informe de Embalaje y Descarte")
            
            p1, p2, p3 = st.columns(3)
            with p1:
                # Agregamos 'key' únicos para evitar choques con el otro formulario
                embalador_sel = st.selectbox("👷‍♂️ Embalador", lista_operarios, key=f"emb_ide07_{maquina}")
                cajas = st.number_input("Packs Armados", min_value=0, step=1, key=f"cajas_ide07_{maquina}")
            with p2:
                unidades_caja = st.number_input("Frascos x Pack", min_value=0, step=1, key=f"uni_ide07_{maquina}")
                descarte = st.number_input("Descarte (Kg)", min_value=0, step=1, key=f"desc_ide07_{maquina}")
            with p3:
                motivo = st.selectbox("Motivo Descarte", ["-", "Rotura", "Manchas", "Falla Impresión", "Mal Formado", "Otro"], key=f"mot_ide07_{maquina}")
                obs = st.text_area("Observaciones del turno", key=f"obs_ide07_{maquina}")

            st.markdown("---")
            
            # 🔐 Zona de validación y guardado IDE07
            col_firma1, col_firma2 = st.columns([1, 2])
            with col_firma1:
                pin_ide07 = st.text_input("🔑 PIN de Firma", type="password", key=f"pin_ide07_{maquina}")
            with col_firma2:
                st.write("") 
                st.write("")
                submit_ide07 = st.form_submit_button("💾 Validar y Guardar IDE07")

            if submit_ide07:
                legajo_ide07 = str(embalador_sel).split("-")[0].strip()
                
                if not validar_pin_operario(legajo_ide07, pin_ide07):
                    st.error("❌ PIN Incorrecto. El registro IDE07 no fue firmado.")
                elif cajas == 0 and descarte == 0:
                    st.warning("⚠️ Debe ingresar producción o descarte para guardar.")
                else:
                    ahora = datetime.now()
                    total_ok = cajas * unidades_caja
                    
                    # Datos exclusivos para la DB de Producción
                    datos_ide07 = (
                        ahora.strftime("%Y-%m-%d"), ahora.strftime("%H:%M:%S"),
                        maquina, lote, producto, legajo_ide07,
                        cajas, unidades_caja, total_ok, descarte, motivo, obs
                    )
                    
                    # Deberás crear/asegurar que exista esta función específica
                    if guardar_registro_ide07(datos_ide07):
                        st.success("✅ Formulario IDE07 Guardado y Firmado.")
                        st.rerun()

        # Historial visible solo para IDE07 dentro de su pestaña
        st.markdown(f"##### 📋 Últimos Registros IDE07 - {maquina}")
        historial_ide07 = obtener_historial_ide07(maquina)
        if not historial_ide07.empty:
            st.dataframe(historial_ide07, use_container_width=True, hide_index=True)
        else:
            st.caption("No hay registros IDE07 cargados en este turno.")


    # ==========================================
    # 🧪 FORMULARIO 2: CONTROLES DE CALIDAD (CLT02)
    # ==========================================
    with tab_cc:
        with st.form(f"form_clt02_{maquina}", clear_on_submit=True):
            st.markdown("#### Control de Calidad de Fin de Línea")
            
            # El inspector podría ser distinto al embalador, le damos su propio campo
            inspector_sel = st.selectbox("👷‍♂️ Inspector / Embalador", lista_operarios, key=f"insp_clt02_{maquina}")
            
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                check_medidas = st.radio("📏 Medidas", opciones_check, horizontal=True, key=f"chk_med_{maquina}")
            with c2:
                check_impresion = st.radio("🎨 Impresión", opciones_check_1, horizontal=True, key=f"chk_imp_{maquina}")
            with c3:
                check_tensiones = st.radio("⚡ Tensiones", opciones_check, horizontal=True, key=f"chk_ten_{maquina}")
            with c4:
                check_aspecto = st.radio("👁️ Aspecto Gral.", opciones_check, horizontal=True, key=f"chk_asp_{maquina}")

            st.markdown("---")
            obs = st.text_area("Observaciones del turno", key=f"obs_clt02_{maquina}")
            st.markdown("---")
            
            # 🔐 Zona de validación y guardado CLT02
            col_firma1, col_firma2 = st.columns([1, 2])
            with col_firma1:
                pin_clt02 = st.text_input("🔑 PIN de Firma", type="password", key=f"pin_clt02_{maquina}")
            with col_firma2:
                st.write("") 
                st.write("")
                submit_clt02 = st.form_submit_button("💾 Validar y Guardar CLT02")

            if submit_clt02:
                legajo_clt02 = str(inspector_sel).split("-")[0].strip()
                
                if not validar_pin_operario(legajo_clt02, pin_clt02):
                    st.error("❌ PIN Incorrecto. El registro CLT02 no fue firmado.")
                else:
                    ahora = datetime.now()
                    
                    # Datos exclusivos para la DB de Calidad
                    datos_clt02 = (
                        (datetime.now().strftime("%d/%m/%Y %H:%M")),
                        maquina, inspector_sel, producto, legajo_clt02,
                        check_medidas, check_impresion, check_tensiones, check_aspecto, obs
                    )
                    
                    if guardar_registro_clt02(datos_clt02):
                        st.success("✅ Formulario CLT02 Guardado y Firmado.")
                        st.rerun()

        # Historial visible solo para CLT02 dentro de su pestaña
        st.markdown(f"##### 📋 Últimos Registros CLT02 - {maquina}")
        historial_clt02 = obtener_historial_clt02(maquina)
        if not historial_clt02.empty:
            st.dataframe(historial_clt02, use_container_width=True, hide_index=True)
        else:
            st.caption("No hay registros CLT02 cargados en este turno.")