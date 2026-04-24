import streamlit as st
import datetime
import sqlite3
import pandas as pd
from config import RUTAS, MAQUINAS
from modulos.embalaje import interfaz_embalaje

# --- MOTORES DE BASE DE DATOS ---

def obtener_resumen_turno(maquina, codigo, fecha):
    conn = sqlite3.connect(RUTAS["lab"])
    cursor = conn.cursor()
    cursor.execute('''
        SELECT SUM(kilos_usados), SUM(tubos_usados), SUM(prod_total), SUM(desc_destruido), SUM(desc_recuperable)
        FROM consumos_planta WHERE maquina=? AND codigo_mp=? AND fecha=?
    ''', (maquina, codigo, fecha))
    res = cursor.fetchone()
    conn.close()
    return res

def cerrar_linea(maquina, codigo, fecha, legajo):
    conn = sqlite3.connect(RUTAS["lab"])
    cursor = conn.cursor()
    cursor.execute('''UPDATE liberacion_linea SET estado='CERRADO' 
                      WHERE maquina=? AND codigo_mp=? AND fecha=? AND estado='LIBERADO' ''', (maquina, codigo, fecha))
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
    cursor.execute('''INSERT INTO consumos_planta (fecha, hora, maquina, codigo_mp, origen, kilos_usados, tubos_usados, prod_total, desc_destruido, desc_recuperable, estado_sync)
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDIENTE')''', datos)
    conn.commit()
    conn.close()

def guardar_control_cp71(datos):
    conn = sqlite3.connect(RUTAS["lab"])
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO controles_proceso (fecha, hora, maquina, codigo_mp, legajo_operario, largo, diam_int_boca, diam_ext_boca, altura_labio, espesor_fondo, defecto_visual, estado, accion_correctiva)
                      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''', datos)
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
    cursor.execute("INSERT INTO liberacion_linea (fecha, hora, maquina, codigo_mp, legajo_firma, estado) VALUES (?, ?, ?, ?, ?, ?)", 
                  (ahora.strftime("%Y-%m-%d"), ahora.strftime("%H:%M:%S"), maquina, codigo, legajo, "LIBERADO"))
    conn.commit()
    conn.close()

def cargar_controles_hoy(maquina, codigo, fecha):
    conn = sqlite3.connect(RUTAS["lab"])
    df = pd.read_sql_query('''SELECT hora as HORA, legajo_operario as FIRMA, largo as L_MM, diam_int_boca as D_INT, diam_ext_boca as D_EXT, altura_labio as LABIO, espesor_fondo as FONDO, estado as ESTADO 
                              FROM controles_proceso WHERE maquina=? AND codigo_mp=? AND fecha=? ORDER BY hora DESC''', conn, params=(maquina, codigo, fecha))
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
    
    # 1. SELECCIÓN DE MÁQUINA Y AUTO-DETECCIÓN
    with st.container(border=True):
        col_m1, col_m2 = st.columns([1, 3])
        with col_m1:
            maq_sel = st.selectbox("🎯 Máquina", MAQUINAS, key="maq_planta")
        
        # MAPEO COMPARTIDO: F1 y P1 buscan el número 1. F2 y P2 buscan el 2.
        mapeo_maquinas = {
            "F1": "1", "F2": "2", "F3": "3", "F4": "4",
            "P1": "1", "P2": "2", "P3": "3"
        }
        id_busqueda = mapeo_maquinas.get(maq_sel, maq_sel)
        
        orden_activa = None
        cod_material = ""
        lote_mp_fisico = "-"
        desc_prod = "Buscando orden..."
        lote_lumen = "-"
        nombre_producto_oficial = ""    

        if not df_prod.empty:
            df_prod['MAQUINA_N'] = pd.to_numeric(df_prod['MAQUINA'], errors='coerce').fillna(-1).astype(int)
            # Traemos TODAS las órdenes de ese número (ej: todas las de la Máquina 1)
            df_maq = df_prod[(df_prod['MAQUINA_N'] == int(id_busqueda)) & (df_prod['MAQUINA_N'] != 0)].copy()
            
            if not df_maq.empty:
                df_maq['lote_n'] = pd.to_numeric(df_maq['LOTE_LUMEN'], errors='coerce').fillna(0)
                df_maq = df_maq.sort_values('lote_n', ascending=False)
                
                # --- BÚSQUEDA INTELIGENTE CON FILTRO CRUZADO ---
                for idx, fila in df_maq.iterrows():
                    frasco_cod = str(fila.get('CODPLANO', '')).strip().upper()
                    if frasco_cod in ["", "NAN", "NONE"]:
                        frasco_cod = str(fila.get('CODIGO', '')).strip().upper()
                    
                    desc_catalogo = obtener_descripcion_desde_catalogo(frasco_cod)
                    desc_final = desc_catalogo if desc_catalogo else str(fila.get('DESCRIP', 'Frasco')).upper()
                    
                    es_tubo = "TUBO" in desc_final
                    
                    # Si el maquinista eligió "P" (Plana) y la orden ES de Tubo -> MATCH
                    if maq_sel.startswith("P") and es_tubo:
                        orden_activa = fila
                        nombre_producto_oficial = desc_final
                        break
                    # Si el maquinista eligió "F" (Vial) y la orden NO ES de Tubo -> MATCH
                    elif maq_sel.startswith("F") and not es_tubo:
                        orden_activa = fila
                        nombre_producto_oficial = desc_final
                        break
                
                # Si encontró la orden correcta para esa máquina, procesa los datos
                if orden_activa is not None:
                    lote_lumen = str(orden_activa['LOTE_LUMEN']).replace(".0", "").strip()
                    lote_mp_fisico = str(orden_activa.get('LOTEMP', '-')).strip()
                    
                    cod_material = str(orden_activa.get('CODIGOMP', '')).strip().upper()
                    if cod_material in ["", "NAN", "NONE", "-", "0", "0.0"]:
                        cod_material = obtener_codigo_tubo_desde_catalogo(frasco_cod)
                    
                    if not cod_material:
                        for campo in ['CODIGO', 'CODART', 'LOTEMP']:
                            val = str(orden_activa.get(campo, '')).strip().upper()
                            if val.startswith('Z'):
                                cod_material = val
                                break
                    
                    desc_prod = f"Lote: {lote_lumen} | Producto: {nombre_producto_oficial}"
                else:
                    tipo_req = "Tubos" if maq_sel.startswith("P") else "Viales"
                    desc_prod = f"⚠️ Sin orden de {tipo_req} en Máquina {id_busqueda}"
            else:
                desc_prod = f"⚠️ Sin orden de fabricación en Máquina {id_busqueda}"
        
        with col_m2:
            st.markdown(f"### 📋 {desc_prod}")

    if orden_activa is None:
        st.warning(f"No hay una orden activa detectada en {maq_sel}.")
        return

    # 2. PANEL DE MATERIALES Y ORIGEN
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
        with col_o1:
            ori_sel = st.selectbox("🌍 Confirmar Origen", origenes_disp, key="ori_planta")
        with col_o2:
            st.metric("Peso Tubo (Ref.)", f"{peso_tubo_ref} g")

    # 3. FLUJO DE TRABAJO (Liberación ISO 9001)
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
            pin = st.text_input("🔑 Legajo de Autorización", type="password")
            todos = all([c1,c2,c3,c4,c5,c6,c7,c8,c9])
            if st.button("✍️ FIRMAR LIBERACIÓN", type="primary", disabled=not (todos and len(pin)>0), use_container_width=True):
                firmar_liberacion(maq_sel, id_lib, pin)
                st.rerun()
    else:
        # =========================================================
        # EL SEMÁFORO: DIRECCIONA LAS PESTAÑAS
        # =========================================================
        es_proceso_tubo = "TUBO" in nombre_producto_oficial

        if es_proceso_tubo:
            st.info(f"🧬 **MODO TUBOS ACTIVADO**")
            tab_corte, tab_maq_tubo, tab_emb, tab_cierre_t = st.tabs(["🔪 1. Corte", "⚙️ 2. Máquina (Soplado)", "📦 3. Embalaje", "🏁 Cierre"])
            
            with tab_corte:
                st.markdown("#### Registro de Corte de Tubos")
                with st.container(border=True):
                    c_c1, c_c2, c_c3 = st.columns(3)
                    with c_c1: v_bruto = st.number_input("Kg Vidrio Bruto", min_value=0.0)
                    with c_c2: v_neto = st.number_input("Kg Cortados (Útiles)", min_value=0.0)
                    with c_c3: v_desc = st.number_input("Descarte Corte (Kg)", min_value=0.0)
                    
                    v_pin = st.text_input("Firma Cortador", type="password", key="p_corte")
                    if st.button("💾 REGISTRAR CORTE", type="primary", use_container_width=True, disabled=len(v_pin)==0):
                        hora_act = datetime.datetime.now().strftime("%H:%M:%S")
                        
                        # 1. Guardamos el proceso específico de corte (Trazabilidad)
                        guardar_corte_tubo((fecha_hoy, hora_act, maq_sel, lote_lumen, v_pin, v_bruto, v_neto, v_desc))
                        
                        # 2. ENVIAMOS EL CONSUMO PARA DESCONTAR DEL STOCK DBF (Igual que los viales)
                        # Le pasamos v_bruto (lo que sacaron del almacén) y v_desc (el descarte)
                        guardar_consumo_idp((fecha_hoy, hora_act, maq_sel, cod_material, ori_sel, v_bruto, 0, 0, v_desc, 0))
                        
                        st.success("✅ Corte registrado y consumo enviado para descuento de stock.")

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
                    
                    m_pin = st.text_input("Firma Maquinista", type="password", key="p_maq_t")
                    if st.button("💾 REGISTRAR PRODUCCIÓN TUBOS", type="primary", use_container_width=True, disabled=len(m_pin)==0):
                        guardar_maquina_tubo((fecha_hoy, datetime.datetime.now().strftime("%H:%M:%S"), maq_sel, lote_lumen, m_pin, v_usado, v_unid, v_dest, v_recu))
                        st.success("Producción guardada.")

            with tab_emb:
                # Convertimos la orden activa a un DataFrame (tabla) para que el módulo de embalaje lo lea correctamente
                df_orden = pd.DataFrame([orden_activa]) if orden_activa is not None else pd.DataFrame()
                
                # Llamamos a la interfaz que creamos en modulos/embalaje.py
                interfaz_embalaje(maq_sel, df_orden)

            with tab_cierre_t:
                st.markdown("#### 📊 Cierre de Línea (Tubos)")
                pin_fuerza_t = st.text_input("🔑 Legajo Supervisor", type="password", key="pin_fuerza_t")
                if st.button("🔒 CERRAR LÍNEA", use_container_width=True, disabled=len(pin_fuerza_t)==0):
                    cerrar_linea(maq_sel, id_lib, fecha_hoy, pin_fuerza_t)
                    st.rerun()

        else:
            st.success(f"🧪 **MODO VIALES ACTIVADO**")
            tab_cp, tab_idp, tab_stop, tab_cierre = st.tabs(["📏 Control (CP 71)", "⚖️ Informe (IDP 71)", "⚠️ Paradas", "🏁 Cierre de Turno"])
            
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
                        v_pin = st.text_input("Firma Maquinista", type="password", key="p_cp")
                        
                        if st.button("💾 GUARDAR MEDICIÓN CP 71", type="primary", use_container_width=True, disabled=len(v_pin)==0):
                            guardar_control_cp71((fecha_hoy, datetime.datetime.now().strftime("%H:%M:%S"), maq_sel, id_lib, v_pin, v_largo, v_d_int, v_d_ext, v_labio, v_fondo, "OK", v_eval, v_accion))
                            st.rerun()
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
                    
                    i_pin = st.text_input("Confirmar Legajo", type="password", key="p_idp")
                    if st.button("💾 GUARDAR REPORTE IDP 71", type="primary", use_container_width=True, disabled=len(i_pin)==0):
                        guardar_consumo_idp((fecha_hoy, datetime.datetime.now().strftime("%H:%M:%S"), maq_sel, id_lib, ori_sel, i_kg, i_tub, i_prod, i_dest, i_recu))
                        st.success("Informe registrado.")

            with tab_stop:
                st.markdown("#### Registro de Paradas")
                with st.container(border=True):
                    p_c1, p_c2 = st.columns(2)
                    with p_c1: p_ini = st.time_input("Hora Inicio")
                    with p_c2: p_fin = st.time_input("Hora Fin")
                    p_causa = st.text_area("Causa de la Parada")
                    p_inter = st.text_area("Intervención Realizada")
                    p_pin = st.text_input("Responsable (Legajo)", type="password", key="p_stop")
                    if st.button("💾 REGISTRAR PARADA", use_container_width=True):
                        guardar_parada_maquina((fecha_hoy, p_ini.strftime("%H:%M"), p_fin.strftime("%H:%M"), maq_sel, p_causa, p_inter, p_pin))
                        st.warning("Parada registrada.")

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
                    
                    c_pin1, c_pin2 = st.columns([1, 2])
                    with c_pin1: pin_cierre = st.text_input("🔑 Legajo Supervisor", type="password", key="pin_cierre")
                    with c_pin2:
                        st.write("") 
                        if st.button("🔒 CERRAR LÍNEA", type="primary", use_container_width=True, disabled=len(pin_cierre)==0):
                            cerrar_linea(maq_sel, id_lib, fecha_hoy, pin_cierre)
                            st.rerun()
                else:
                    st.info("No hay registros para este turno.")
                    pin_fuerza = st.text_input("🔑 Legajo", type="password", key="pin_fuerza")
                    if st.button("🔒 CERRAR LÍNEA (Sin Producción)", use_container_width=True, disabled=len(pin_fuerza)==0):
                        cerrar_linea(maq_sel, id_lib, fecha_hoy, pin_fuerza)
                        st.rerun()