import streamlit as st
import datetime
import sqlite3
import pandas as pd
from config import RUTAS, MAQUINAS
from modulos.embalaje import interfaz_embalaje, validar_registros_pendientes, obtener_pendientes_ide07
from utils.db_helpers import validar_pin_operario

# --- MOTORES DE BASE DE DATOS ---

def obtener_resumen_turno(maquina, codigo, fecha):
    conn = sqlite3.connect(RUTAS["lab"])
    cursor = conn.cursor()
    cursor.execute('''SELECT SUM(kilos_usados), SUM(tubos_usados), SUM(prod_total), SUM(desc_destruido), SUM(desc_recuperable) FROM consumos_planta WHERE maquina=? AND codigo_mp=? AND fecha=?''', (maquina, codigo, fecha))
    res = cursor.fetchone()
    conn.close()
    return res

def cerrar_linea(maquina, codigo, fecha, legajo):
    conn = sqlite3.connect(RUTAS["lab"])
    cursor = conn.cursor()
    cursor.execute('''UPDATE liberacion_linea SET estado='CERRADO' WHERE maquina=? AND codigo_mp=? AND fecha=? AND estado='LIBERADO' ''', (maquina, codigo, fecha))
    conn.commit()
    conn.close()

def obtener_codigo_tubo_desde_catalogo(cod_frasco):
    if not cod_frasco or cod_frasco in ["-", "NAN", "NONE", ""]: return None
    conn = sqlite3.connect(RUTAS["lab"])
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT CODIGOMP FROM catalogo_articulos WHERE CODPLA = ? OR CODIGO = ?", (cod_frasco, cod_frasco))
        res = cursor.fetchone()
        return str(res[0]).strip().upper() if res and res[0] else None
    except: return None
    finally: conn.close()

def obtener_descripcion_desde_catalogo(cod_frasco):
    if not cod_frasco or cod_frasco in ["-", "NAN", "NONE", ""]: return ""
    conn = sqlite3.connect(RUTAS["lab"])
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT DESCRIP FROM catalogo_articulos WHERE CODPLA = ? OR CODIGO = ?", (cod_frasco, cod_frasco))
        res = cursor.fetchone()
        return str(res[0]).strip().upper() if res and res[0] else ""
    except: return ""
    finally: conn.close()

def guardar_parada_maquina(datos):
    conn = sqlite3.connect(RUTAS["lab"])
    cursor = conn.cursor()
    cursor.execute('INSERT INTO paradas_maquina (fecha, hora_inicio, hora_fin, maquina, causa, intervencion, responsable) VALUES (?,?,?,?,?,?,?)', datos)
    conn.commit()
    conn.close()

def guardar_consumo_idp(datos):
    conn = sqlite3.connect(RUTAS["lab"])
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO consumos_planta (fecha, hora, maquina, codigo_mp, origen, kilos_usados, tubos_usados, prod_total, desc_destruido, desc_recuperable, estado_sync) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDIENTE')''', datos)
    conn.commit()
    conn.close()

def guardar_control_cp71(datos):
    conn = sqlite3.connect(RUTAS["lab"])
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO controles_proceso (fecha, hora, maquina, codigo_mp, legajo_operario, largo, diam_int_boca, diam_ext_boca, altura_labio, espesor_fondo, defecto_visual, estado, accion_correctiva) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''', datos)
    conn.commit()
    conn.close()

def verificar_liberacion(maquina, codigo, fecha):
    conn = sqlite3.connect(RUTAS["lab"])
    cursor = conn.cursor()
    cursor.execute("SELECT legajo_firma, hora FROM liberacion_linea WHERE maquina=? AND codigo_mp=? AND fecha=? AND estado='LIBERADO'", (maquina, codigo, fecha))
    resultado = cursor.fetchone()
    conn.close()
    return resultado

def firmar_liberacion(maquina, codigo, legajo):
    ahora = datetime.datetime.now()
    conn = sqlite3.connect(RUTAS["lab"])
    cursor = conn.cursor()
    cursor.execute("INSERT INTO liberacion_linea (fecha, hora, maquina, codigo_mp, legajo_firma, estado) VALUES (?, ?, ?, ?, ?, ?)", (ahora.strftime("%Y-%m-%d"), ahora.strftime("%H:%M:%S"), maquina, codigo, legajo, "LIBERADO"))
    conn.commit()
    conn.close()

def cargar_controles_hoy(maquina, codigo, fecha):
    conn = sqlite3.connect(RUTAS["lab"])
    df = pd.read_sql_query('''SELECT hora as HORA, legajo_operario as FIRMA, largo as L_MM, diam_int_boca as D_INT, diam_ext_boca as D_EXT, altura_labio as LABIO, espesor_fondo as FONDO, estado as ESTADO FROM controles_proceso WHERE maquina=? AND codigo_mp=? AND fecha=? ORDER BY hora DESC''', conn, params=(maquina, codigo, fecha))
    conn.close()
    return df

def guardar_corte_tubo(datos):
    conn = sqlite3.connect(RUTAS["lab"])
    cursor = conn.cursor()
    cursor.execute('INSERT INTO proceso_corte_tubos (fecha, hora, maquina, lote_lumen, legajo_operario, kg_vidrio_bruto, kg_cortados, descarte) VALUES (?,?,?,?,?,?,?,?)', datos)
    conn.commit()
    conn.close()

def guardar_maquina_tubo(datos):
    conn = sqlite3.connect(RUTAS["lab"])
    cursor = conn.cursor()
    cursor.execute('INSERT INTO proceso_maquina_tubos (fecha, hora, maquina, lote_lumen, legajo_operario, kg_cortados_usados, unidades_ok, desc_destruido, desc_recuperable) VALUES (?,?,?,?,?,?,?,?,?)', datos)
    conn.commit()
    conn.close()    

# --- INTERFAZ VISUAL ---
def renderizar_planta(df_st, df_prod):
    st.title("🏭 Sector Producción (Producción y Calidad)")
    fecha_hoy = datetime.datetime.now().strftime("%Y-%m-%d")
    
    # --- CARGA DE OPERARIOS DESDE CREDENCIALES ---
    lista_operarios = ["-"]
    try:
        conn = sqlite3.connect(RUTAS["lab"])
        # Sacamos el WHERE estado='Activo' para ver si trae la lista completa
        df_credenciales = pd.read_sql_query("SELECT legajo, nombre FROM credenciales_empleados", conn)
        conn.close()

        if not df_credenciales.empty:
            operarios_format = (df_credenciales['legajo'].astype(str) + " - " + df_credenciales['nombre']).tolist()
            lista_operarios.extend(operarios_format)
        else:
            st.warning("⚠️ La tabla credenciales_empleados parece estar vacía o no tiene registros.")
    except Exception as e:
        st.error(f"Error SQL al cargar credenciales: {e}")

    with st.container(border=True):
        col_m1, col_m2 = st.columns([1, 3])
        with col_m1:
            maq_sel = st.selectbox("🎯 Máquina", MAQUINAS, key="maq_planta")
        
        mapeo_maquinas = {"F1": "1", "F2": "2", "F3": "3", "F4": "4", "P1": "1", "P2": "2", "P3": "3"}
        id_busqueda = mapeo_maquinas.get(maq_sel, maq_sel)
        
        orden_activa = None
        cod_material = ""
        lote_mp_fisico = "-"
        desc_prod = "Buscando orden..."
        lote_lumen = "-"
        nombre_producto_oficial = ""    

        if not df_prod.empty:
            df_prod['MAQUINA_N'] = pd.to_numeric(df_prod['MAQUINA'], errors='coerce').fillna(-1).astype(int)
            df_maq = df_prod[(df_prod['MAQUINA_N'] == int(id_busqueda)) & (df_prod['MAQUINA_N'] != 0)].copy()
            
            if not df_maq.empty:
                df_maq['lote_n'] = pd.to_numeric(df_maq['LOTE_LUMEN'], errors='coerce').fillna(0)
                df_maq = df_maq.sort_values('lote_n', ascending=False)
                
                for idx, fila in df_maq.iterrows():
                    frasco_cod = str(fila.get('CODPLANO', '')).strip().upper()
                    if frasco_cod in ["", "NAN", "NONE"]: frasco_cod = str(fila.get('CODIGO', '')).strip().upper()
                    desc_catalogo = obtener_descripcion_desde_catalogo(frasco_cod)
                    desc_final = desc_catalogo if desc_catalogo else str(fila.get('DESCRIP', 'Frasco')).upper()
                    es_tubo = "TUBO" in desc_final
                    
                    if maq_sel.startswith("P") and es_tubo:
                        orden_activa = fila; nombre_producto_oficial = desc_final; break
                    elif maq_sel.startswith("F") and not es_tubo:
                        orden_activa = fila; nombre_producto_oficial = desc_final; break
                
                if orden_activa is not None:
                    lote_lumen = str(orden_activa['LOTE_LUMEN']).replace(".0", "").strip()
                    lote_mp_fisico = str(orden_activa.get('LOTEMP', '-')).strip()
                    cod_material = str(orden_activa.get('CODIGOMP', '')).strip().upper()
                    
                    if cod_material in ["", "NAN", "NONE", "-", "0", "0.0"]:
                        cod_material = obtener_codigo_tubo_desde_catalogo(frasco_cod)
                    
                    if not cod_material:
                        for campo in ['CODIGO', 'CODART', 'LOTEMP']:
                            val = str(orden_activa.get(campo, '')).strip().upper()
                            if val.startswith('Z'): cod_material = val; break
                    
                    desc_prod = f"Lote: {lote_lumen} | Producto: {nombre_producto_oficial}"
                else: desc_prod = f"⚠️ Sin orden compatible en Máquina {id_busqueda}"
            else: desc_prod = f"⚠️ Sin orden de fabricación en Máquina {id_busqueda}"
        
        with col_m2: st.markdown(f"### 📋 {desc_prod}")

    if orden_activa is None:
        st.warning(f"No hay una orden activa detectada en {maq_sel}.")
        return

    with st.container(border=True):
        origenes_disp = ["-"]
        peso_tubo_ref = 0.0
        desc_tubo = "" 
        
        if cod_material and cod_material not in ["", "NAN"]:
            df_st_f = df_st[df_st['CODIGO'].astype(str).str.strip().str.upper() == cod_material]
            if not df_st_f.empty:
                origenes_disp = sorted([str(o) for o in df_st_f['ORIGEN'].unique() if str(o).strip() not in ["-", "nan", ""]])
                peso_tubo_ref = float(df_st_f.iloc[0].get('PESOTUBO', 0))
                desc_tubo = str(df_st_f.iloc[0].get('DESCRIP', '')).strip() 
        
        titulo_mp = f"{cod_material} - {desc_tubo}" if desc_tubo else cod_material if cod_material else "No detectado"

        st.markdown(f"#### 📦 Materia Prima: **{titulo_mp}**")
        st.caption(f"Lote Físico (LOTEMP): {lote_mp_fisico}")
        
        col_o1, col_o2 = st.columns(2)
        with col_o1: ori_sel = st.selectbox("🌍 Confirmar Origen", origenes_disp, key="ori_planta")
        with col_o2: st.metric("Peso Tubo (Ref.)", f"{peso_tubo_ref} g")

    id_lib = cod_material if cod_material else lote_lumen
    est_lib = verificar_liberacion(maq_sel, id_lib, fecha_hoy)

    if not est_lib:
        st.error("🛑 BLOQUEO: Se requiere Liberación de Línea (ISO 9001)")
        with st.container(border=True):
            st.markdown("### 📝 Checklist de Inicio")
            c_puntos = st.columns(3)
            with c_puntos[0]:
                c1 = st.checkbox("Diámetro de vidrio correcto")
                c2 = st.checkbox("Color de vidrio correcto")
                c3 = st.checkbox("Lote MP correcto")
            with c_puntos[1]:
                c4 = st.checkbox("Temperatura horno correcto")
                c5 = st.checkbox("Elementos de medición")
                c6 = st.checkbox("Elementos de seguridad")
            with c_puntos[2]:
                c7 = st.checkbox("Frascos otras producciones")
                c8 = st.checkbox("Limpieza de máquina correcta")
                c9 = st.checkbox("Apto para liberación")
            
            st.markdown("---")
            col_f1, col_col2 = st.columns(2)
            
            with col_f1: pin_sel = st.selectbox("👷 Operario Autorizante", lista_operarios, key="pin_lib")
            with col_col2: pin_pass = st.text_input("🔑 PIN", type="password", key="pin_lib_pass")
            
            todos = all([c1,c2,c3,c4,c5,c6,c7,c8,c9])
            if st.button("✍️ FIRMAR LIBERACIÓN", type="primary", disabled=not todos, use_container_width=True):
                if pin_sel != "-":
                    legajo_limpio = pin_sel.split(" - ")[0]
                    if validar_pin_operario(legajo_limpio, pin_pass):
                        firmar_liberacion(maq_sel, id_lib, legajo_limpio)
                        st.rerun()
                    else: st.error("❌ PIN incorrecto.")
    else:
        es_proceso_tubo = "TUBO" in nombre_producto_oficial

        if es_proceso_tubo:
            st.info(f"🧬 **MODO TUBOS ACTIVADO**")
            tab_corte, tab_maq_tubo, tab_emb, tab_cierre_t = st.tabs(["🔪 1. Corte", "⚙️ 2. Máquina", "📦 3. Embalaje", "🏁 Cierre"])
            
            with tab_corte:
                st.markdown("#### Registro de Corte de Caña")
                with st.container(border=True):
                    c_c1, c_c2, c_c3 = st.columns(3)
                    with c_c1: v_bruto = st.number_input("Kg Vidrio Bruto (Caña)", min_value=0.0)
                    with c_c2: v_neto = st.number_input("Kg Cortados (Útiles)", min_value=0.0)
                    with c_c3: v_desc = st.number_input("Descarte Corte (Kg)", min_value=0.0)
                    
                    cf1, cf2 = st.columns(2)
                    with cf1: v_pin_sel = st.selectbox("👷 Firma Cortador", lista_operarios, key="p_corte")
                    with cf2: v_pin_pass = st.text_input("🔑 PIN", type="password", key="p_corte_pass")
                    
                    if st.button("💾 REGISTRAR CORTE", type="primary", use_container_width=True):
                        if v_pin_sel != "-":
                            legajo_limpio = v_pin_sel.split(" - ")[0]
                            if validar_pin_operario(legajo_limpio, v_pin_pass):
                                guardar_corte_tubo((fecha_hoy, datetime.datetime.now().strftime("%H:%M:%S"), maq_sel, lote_lumen, legajo_limpio, v_bruto, v_neto, v_desc))
                                st.success("Corte registrado.")
                            else: st.error("❌ PIN incorrecto.")

            with tab_maq_tubo:
                st.markdown("#### Registro de Formado")
                with st.container(border=True):
                    m_c1, m_c2 = st.columns(2)
                    with m_c1: v_usado = st.number_input("Kg Tubos Cortados Usados", min_value=0.0)
                    with m_c2: v_unid = st.number_input("Total Fabricado (Unidades)", min_value=0)
                    
                    st.markdown("**Descarte en Máquina (Kg)**")
                    d_c1, d_c2 = st.columns(2)
                    with d_c1: v_dest = st.number_input("Destruido (Scrap)", min_value=0.0)
                    with d_c2: v_recu = st.number_input("Recuperable", min_value=0.0)
                    
                    cm1, cm2 = st.columns(2)
                    with cm1: m_pin_sel = st.selectbox("👷 Firma Maquinista", lista_operarios, key="p_maq_t")
                    with cm2: m_pin_pass = st.text_input("🔑 PIN", type="password", key="p_maq_pass")

                    if st.button("💾 REGISTRAR PRODUCCIÓN", type="primary", use_container_width=True):
                        if m_pin_sel != "-":
                            legajo_limpio = m_pin_sel.split(" - ")[0]
                            if validar_pin_operario(legajo_limpio, m_pin_pass):
                                guardar_maquina_tubo((fecha_hoy, datetime.datetime.now().strftime("%H:%M:%S"), maq_sel, lote_lumen, legajo_limpio, v_usado, v_unid, v_dest, v_recu))
                                st.success("Producción guardada.")
                            else: st.error("❌ PIN incorrecto.")

            with tab_emb:
                interfaz_embalaje(maq_sel, lote_lumen, nombre_producto_oficial)

            with tab_cierre_t:
                st.markdown("#### 📊 Cierre de Línea (Tubos)")
                ct1, ct2 = st.columns(2)
                with ct1: pin_fuerza_t_sel = st.selectbox("🔒 Supervisor", lista_operarios, key="pin_fuerza_t")
                with ct2: pin_fuerza_t_pass = st.text_input("🔑 PIN", type="password", key="pft_pass")
                if st.button("🛑 CERRAR LÍNEA", use_container_width=True):
                    if pin_fuerza_t_sel != "-":
                        legajo_limpio = pin_fuerza_t_sel.split(" - ")[0]
                        if validar_pin_operario(legajo_limpio, pin_fuerza_t_pass):
                            cerrar_linea(maq_sel, id_lib, fecha_hoy, legajo_limpio)
                            st.rerun()
                        else: st.error("❌ PIN incorrecto.")

        else:
            st.success(f"🧪 **MODO VIALES ACTIVADO**")
            tab_cp, tab_idp, tab_stop, tab_emb, tab_cierre = st.tabs(["📏 Control (CP 71)", "⚖️ Informe (IDP 71)", "⚠️ Paradas", "📦 Embalaje", "🏁 Cierre de Turno"])
            
            with tab_cp:
                st.markdown("#### Registro de Mediciones (REV 3)")
                col_form, col_hist = st.columns([3, 2])
                with col_form:
                    with st.container(border=True):
                        m_c1, m_c2, m_c3 = st.columns(3)
                        with m_c1: v_largo = st.number_input("Largo Total (mm)", step=0.01, format="%.2f")
                        with m_c2: v_d_int = st.number_input("Ø Int. Boca (mm)", step=0.01, format="%.2f")
                        with m_c3: v_d_ext = st.number_input("Ø Ext. Boca (mm)", step=0.01, format="%.2f")
                        
                        m_c4, m_c5, m_c6 = st.columns(3)
                        with m_c4: v_labio = st.number_input("Altura Labio (mm)", step=0.01, format="%.2f")
                        with m_c5: v_fondo = st.number_input("Espesor Fondo (mm)", step=0.01, format="%.2f")
                        with m_c6: v_eval = st.radio("Evaluación", ["Conforme", "No Conforme"], horizontal=True)
                        
                        v_accion = st.text_input("Acción Correctiva") if v_eval == "No Conforme" else "-"
                        
                        ccp1, ccp2 = st.columns(2)
                        with ccp1: v_pin_sel = st.selectbox("👷 Maquinista", lista_operarios, key="p_cp")
                        with ccp2: v_pin_pass = st.text_input("🔑 PIN", type="password", key="p_cp_pass")
                        
                        if st.button("💾 GUARDAR MEDICIÓN CP 71", type="primary", use_container_width=True):
                            if v_pin_sel != "-":
                                legajo_limpio = v_pin_sel.split(" - ")[0]
                                if validar_pin_operario(legajo_limpio, v_pin_pass):
                                    guardar_control_cp71((fecha_hoy, datetime.datetime.now().strftime("%H:%M:%S"), maq_sel, id_lib, legajo_limpio, v_largo, v_d_int, v_d_ext, v_labio, v_fondo, "OK", v_eval, v_accion))
                                    st.rerun()
                                else: st.error("❌ PIN incorrecto.")
                with col_hist:
                    df_hist = cargar_controles_hoy(maq_sel, id_lib, fecha_hoy)
                    if not df_hist.empty:
                        st.dataframe(df_hist, use_container_width=True, hide_index=True)

            with tab_idp:
                st.markdown("#### Balance de Producción y Consumos")
                with st.container(border=True):
                    b_c1, b_c2 = st.columns(2)
                    with b_c1:
                        i_kg = st.number_input("Vidrio Usado (Kg)", min_value=0.0)
                        i_tub = st.number_input("Tubos Usados (u)", min_value=0)
                    with b_c2:
                        i_prod = st.number_input("Producción Total (Buenos)", min_value=0)
                    
                    st.markdown("**Descarte / Rotura (Kg)**")
                    d_c1, d_c2 = st.columns(2)
                    with d_c1: i_dest = st.number_input("Destruido", min_value=0.0)
                    with d_c2: i_recu = st.number_input("Recuperable", min_value=0.0)
                    
                    cip1, cip2 = st.columns(2)
                    with cip1: i_pin_sel = st.selectbox("👷 Confirmar Operario", lista_operarios, key="p_idp")
                    with cip2: i_pin_pass = st.text_input("🔑 PIN", type="password", key="p_idp_pass")
                    
                    if st.button("💾 GUARDAR REPORTE IDP 71", type="primary", use_container_width=True):
                        if i_pin_sel != "-":
                            legajo_limpio = i_pin_sel.split(" - ")[0]
                            if validar_pin_operario(legajo_limpio, i_pin_pass):
                                guardar_consumo_idp((fecha_hoy, datetime.datetime.now().strftime("%H:%M:%S"), maq_sel, id_lib, ori_sel, i_kg, i_tub, i_prod, i_dest, i_recu))
                                st.success("Informe registrado.")
                            else: st.error("❌ PIN incorrecto.")

            with tab_stop:
                st.markdown("#### Registro de Paradas")
                with st.container(border=True):
                    p_c1, p_c2 = st.columns(2)
                    with p_c1: p_ini = st.time_input("Hora Inicio")
                    with p_c2: p_fin = st.time_input("Hora Fin")
                    p_causa = st.text_area("Causa de la Parada")
                    p_inter = st.text_area("Intervención Realizada")
                    
                    cstp1, cstp2 = st.columns(2)
                    with cstp1: p_pin_sel = st.selectbox("👷 Responsable", lista_operarios, key="p_stop")
                    with cstp2: p_pin_pass = st.text_input("🔑 PIN", type="password", key="p_stop_pass")
                    
                    if st.button("💾 REGISTRAR PARADA", use_container_width=True):
                        if p_pin_sel != "-":
                            legajo_limpio = p_pin_sel.split(" - ")[0]
                            if validar_pin_operario(legajo_limpio, p_pin_pass):
                                guardar_parada_maquina((fecha_hoy, p_ini.strftime("%H:%M"), p_fin.strftime("%H:%M"), maq_sel, p_causa, p_inter, legajo_limpio))
                                st.warning("Parada registrada.")
                            else: st.error("❌ PIN incorrecto.")

            with tab_emb:
                interfaz_embalaje(maq_sel, lote_lumen, nombre_producto_oficial)

            with tab_cierre:
                st.markdown("#### 📊 Balance Final y Cierre")
                resumen = obtener_resumen_turno(maq_sel, id_lib, fecha_hoy)
                if resumen and resumen[0] is not None:
                    tot_kg, tot_tub, tot_prod, tot_dest, tot_recu = resumen
                    tot_kg, tot_tub, tot_prod, tot_dest, tot_recu = tot_kg or 0.0, tot_tub or 0, tot_prod or 0, tot_dest or 0.0, tot_recu or 0.0
                    tot_descarte = tot_dest + tot_recu
                    pct_descarte = (tot_descarte / tot_kg * 100) if tot_kg > 0 else 0.0
                    
                    with st.container(border=True):
                        c1, c2, c3 = st.columns(3)
                        c1.metric("Vidrio Usado", f"{tot_kg:.1f} kg")
                        c2.metric("Producción", f"{tot_prod} u.")
                        c3.metric("Descarte", f"{tot_descarte:.1f} kg", f"{pct_descarte:.1f}% pérdida", delta_color="inverse")
                    
                    c_pin1, c_pin2, c_pin3 = st.columns([2, 1, 1])
                    with c_pin1: pin_cierre_sel = st.selectbox("🔒 Supervisor", lista_operarios, key="pin_cierre")
                    with c_pin2: pin_cierre_pass = st.text_input("🔑 PIN", type="password", key="p_cierre_pass")
                    with c_pin3:
                        st.write("") 
                        if st.button("🛑 CERRAR LÍNEA", type="primary", use_container_width=True):
                            if pin_cierre_sel != "-":
                                legajo_limpio = pin_cierre_sel.split(" - ")[0]
                                if validar_pin_operario(legajo_limpio, pin_cierre_pass):
                                    cerrar_linea(maq_sel, id_lib, fecha_hoy, legajo_limpio)
                                    st.rerun()
                                else: st.error("❌ PIN incorrecto.")
                else:
                    st.info("No hay registros para este turno.")
                    c_p1, c_p2 = st.columns(2)
                    with c_p1: pin_fuerza_sel = st.selectbox("🔒 Supervisor", lista_operarios, key="pin_fuerza")
                    with c_p2: pin_fuerza_pass = st.text_input("🔑 PIN", type="password", key="pf_pass")
                    
                    if st.button("🛑 CERRAR LÍNEA (Sin Producción)", use_container_width=True):
                        if pin_fuerza_sel != "-":
                            legajo_limpio = pin_fuerza_sel.split(" - ")[0]
                            if validar_pin_operario(legajo_limpio, pin_fuerza_pass):
                                cerrar_linea(maq_sel, id_lib, fecha_hoy, legajo_limpio)
                                st.rerun()
                            else: st.error("❌ PIN incorrecto.")
                st.markdown("#### 🛡️ Validación de Supervisor (ISO 9001)")
                # Traemos lo que cargaron los embaladores hoy que aún no está firmado
                df_pendientes = obtener_pendientes_ide07(maq_sel)
                    
                if not df_pendientes.empty:
                    st.warning(f"Hay {len(df_pendientes)} registros esperando validación.")
                    st.dataframe(df_pendientes.drop(columns=['id']), use_container_width=True, hide_index=True)
                    
                    with st.expander("🔐 Firmar y Aprobar todo el lote"):
                        with st.form("form_validacion_supervisor"):
                            col1, col2 = st.columns(2)
                            with col1:
                                # Usamos la misma lista general de operarios
                                sup_sel = st.selectbox("Supervisor / Responsable", lista_operarios, key="sup_val_ide07")
                            with col2:
                                pin_sup = st.text_input("PIN de Supervisor", type="password", key="pin_val_ide07")
                            
                            btn_aprobar = st.form_submit_button("✅ Aprobar Registros", use_container_width=True)
                            
                            if btn_aprobar:
                                legajo_sup = str(sup_sel).split("-")[0].strip()
                                
                                # Validamos PIN
                                if validar_pin_operario(legajo_sup, pin_sup):
                                    if validar_registros_pendientes(maq_sel, legajo_sup):
                                        st.success(f"✅ Registros validados por {legajo_sup}.")
                                        st.rerun()
                                else:
                                    st.error("❌ PIN de supervisor incorrecto.")
                else:
                    st.success("🙌 No hay registros pendientes de validación para hoy.")
                