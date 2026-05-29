import streamlit as st
import pandas as pd
import datetime
import os
import sqlite3
import re
from fpdf import FPDF
from config import RUTAS, RESPONSABLES, BOCAS, MAQUINAS, HORNOS
from utils.data_core import cargar_produccion, cargar_pedidos_completos
from utils.db_helpers import obtener_operarios_habilitados
from modulos.embalaje import validar_pin_operario

def guardar_analisis_lab(datos):
    try:
        conn = sqlite3.connect(RUTAS["lab"])
        cursor = conn.cursor()
        
        # Ahora usamos 27 campos (25 originales + 2 de auditoría)
        query = '''
            INSERT INTO analisis_hidrolitica (
                nro_analisis, fecha, hora, responsable, maquina, horno, temperatura, 
                cliente, medida, capacidad, cod, boca, color, pared, impresion, 
                tratado, lote_lumen, l_m_prima, batch, volumen, blanco, 
                titulacion, resultado_final, maximo, observaciones,
                sup_valida, estado
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        '''
        # Añadimos (None, 'PENDIENTE') al final de la tupla de datos que recibimos
        cursor.execute(query, datos + (None, 'PENDIENTE'))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Error al registrar análisis: {e}")
        return False
    

def obtener_analisis_pendientes():
    try:
        conn = sqlite3.connect(RUTAS["lab"])
        # Traemos datos clave para que el supervisor decida
        query = """
            SELECT nro_analisis, fecha, responsable, lote_lumen, resultado_final, maximo
            FROM analisis_hidrolitica 
            WHERE estado = 'PENDIENTE'
            ORDER BY nro_analisis ASC
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except:
        return pd.DataFrame()

def aprobar_analisis_laboratorio(lista_nros, legajo_sup):
    try:
        conn = sqlite3.connect(RUTAS["lab"])
        cursor = conn.cursor()
        for nro in lista_nros:
            cursor.execute('''
                UPDATE analisis_hidrolitica 
                SET sup_valida = ?, estado = 'APROBADO'
                WHERE nro_analisis = ?
            ''', (legajo_sup, nro))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Error en validación técnica: {e}")
        return False

def limpiar_comercial(valor):
    if pd.isna(valor) or valor is None: return "-"
    v_str = str(valor).strip()
    if v_str.lower() in ['nan', 'none', '0.0', '0', '', '-']: return "-"
    try: return str(int(float(valor)))
    except: return v_str

def obtener_siguiente_nro_certificado(nro_analisis):
    conn = sqlite3.connect(RUTAS["lab"])
    cursor = conn.cursor()
    cursor.execute("SELECT nro_certificado FROM analisis_hidrolitica WHERE nro_analisis = ?", (int(nro_analisis),))
    res = cursor.fetchone()
    if res and res[0] is not None:
        nro_cert = int(res[0]) 
    else:
        cursor.execute("SELECT MAX(CAST(nro_certificado AS INTEGER)) FROM analisis_hidrolitica")
        max_res = cursor.fetchone()
        nro_cert = (int(max_res[0]) + 1) if max_res and max_res[0] is not None else 1000 
    conn.close()
    return nro_cert

def guardar_certificado_red(nro_analisis, nro_cert, pdf_bytes, nombre_archivo):
    try:
        conn = sqlite3.connect(RUTAS["lab"])
        cursor = conn.cursor()
        cursor.execute("UPDATE analisis_hidrolitica SET nro_certificado = ? WHERE nro_analisis = ?", (int(nro_cert), int(nro_analisis)))
        conn.commit()
        conn.close()
        ruta_base = RUTAS.get("certificados", r"C:\proyecto_Asistencia\certificados_temp")
        os.makedirs(ruta_base, exist_ok=True) 
        ruta_completa = os.path.join(ruta_base, nombre_archivo)
        with open(ruta_completa, "wb") as f: 
            f.write(pdf_bytes)
        st.session_state.msg_cert = f"✅ Guardado en red como: {nombre_archivo}"
    except Exception as e:
        st.session_state.msg_cert = f"❌ Error al guardar: {e}"

def registrar_analisis_legado(datos_manuales):
    # 1. Agregamos 'maquina_input' y 'capacidad_input' a la recepción de datos
    fecha, responsable, cliente, cod, lote_lumen, resultado_final, maximo, observaciones, maquina_input, capacidad_input = datos_manuales
    
    MAPEO_BOCAS = {"1": "Tapa Rosca", "2": "20 Normal", "3": "20 C/Anclaje", "4": "13 Normal", "5": "13 C/Anclaje", "6": "8 Normal", "7": "8 C/Anclaje", "8": "10 Normal", "9": "Tapa Rosca 9A", "10": "Tapa Rosca 9B", "11": "Tapa Rosca 10", "12": "Perfumero", "13": "Boca Spray", "14": "Tubo", "15": "Cuadrada"}
    MAPEO_COLOR = {"1": "Ambar", "2": "Incoloro", "AMBAR": "Ambar", "INCOLORO": "Incoloro"}
    
    # 2. Inicializamos con lo que el analista escribió (si no escribió nada, queda "-")
    medida, color, boca, pared = "-", "Ambar", "-", "-"
    capacidad = capacidad_input.strip() if capacidad_input else "-"
    maquina = str(maquina_input).strip() if maquina_input else "-"
    impresion, l_m_prima, batch = "SIN IMPRESION", "-", "-"
    
    conn_cat = sqlite3.connect(RUTAS["lab"], timeout=10)
    cursor_cat = conn_cat.cursor()
    try:
        cursor_cat.execute("SELECT D1, H1, CAPACIDAD, COLOR, BOCA, ESPESOR FROM catalogo_articulos WHERE CODPLA = ? OR CODIGO = ?", (cod, cod))
        cat = cursor_cat.fetchone()
        if cat:
            d1, h1 = str(cat[0]).strip() if cat[0] else "", str(cat[1]).strip() if cat[1] else ""
            medida = f"{d1} x {h1}" if d1 and h1 else "-"
            # Si el usuario NO cargó la capacidad, probamos leerla del catálogo
            if capacidad == "-" and cat[2]: 
                capacidad = str(cat[2]).strip()
            color = MAPEO_COLOR.get(str(cat[3]).strip().upper() if cat[3] else "", "Ambar")
            boca_bd = str(cat[4]).strip() if cat[4] else ""
            boca = MAPEO_BOCAS.get(boca_bd, boca_bd) if boca_bd else "-"
            pared = str(cat[5]).strip() if cat[5] else "-"
    finally: conn_cat.close()

    try:
        df_p = cargar_produccion()
        if not df_p.empty:
            lotes_limpios = df_p['LOTE_LUMEN'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
            datos_p = df_p[lotes_limpios == str(lote_lumen).strip()]
            if not datos_p.empty:
                fila = datos_p.iloc[0]
                def lim_cer(v):
                    s = str(v).strip()
                    return s[:-2] if s.endswith('.0') else s
                
                # Si el usuario NO seleccionó máquina, probamos leerla del DBF
                if maquina == "-" or maquina == "":
                    maquina = lim_cer(fila.get('MAQUINA', '-'))
                    
                l_m_prima = lim_cer(fila.get('LOTEMP', '-'))
                batch = lim_cer(fila.get('BATCH', '-'))
                med_val = str(fila.get('MEDIDA', '')).strip()
                if med_val not in ['nan', 'None', '']: medida = med_val.replace('ñ', '±').replace('Ñ', '±')
                boc_val = lim_cer(fila.get('BOCA', '-'))
                boca = MAPEO_BOCAS.get(boc_val, boc_val)
                col_val = lim_cer(fila.get('COLOR', '1')).upper()
                color = MAPEO_COLOR.get(col_val, "Ambar")
                pared = lim_cer(fila.get('PARED', '-'))
    except: pass

    conn = sqlite3.connect(RUTAS["lab"], timeout=15)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT MAX(nro_analisis) FROM analisis_hidrolitica")
        res_id = cursor.fetchone()
        nro_analisis_manual = (int(res_id[0]) + 1) if res_id and res_id[0] else 8077
        cursor.execute("SELECT MAX(CAST(nro_certificado AS INTEGER)) FROM analisis_hidrolitica")
        max_res = cursor.fetchone()
        nro_cert = (int(max_res[0]) + 1) if max_res and max_res[0] is not None else 1000 
        cursor.execute('''
            INSERT INTO analisis_hidrolitica (
                nro_analisis, fecha, responsable, cliente, cod, lote_lumen, resultado_final, maximo, observaciones,
                medida, capacidad, color, boca, pared, maquina, impresion, l_m_prima, batch, nro_certificado,
                sup_valida, estado
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ''', (nro_analisis_manual, fecha, responsable, cliente, cod, lote_lumen, resultado_final, maximo, observaciones,
              medida, capacidad, color, boca, pared, maquina, impresion, l_m_prima, batch, nro_cert, 
              None, 'PENDIENTE'))
        conn.commit()
    except Exception as e:
        st.error(f"Falla crítica al escribir en base de datos: {e}")
        nro_analisis_manual, nro_cert = 0, 0
    finally: conn.close()
    return nro_analisis_manual, nro_cert

def autocompletar_frasco():
    MAPEO_BOCAS = {"1": "Tapa Rosca", "2": "20 Normal", "3": "20 C/Anclaje", "4": "13 Normal", "5": "13 C/Anclaje", "6": "8 Normal", "7": "8 C/Anclaje", "8": "10 Normal", "9": "Tapa Rosca 9A", "10": "Tapa Rosca 9B", "11": "Tapa Rosca 10", "12": "Perfumero", "13": "Boca Spray", "14": "Tubo", "15": "Cuadrada", "14": "N/Aplica"}
    cod_ingresado = st.session_state.t_cod.strip().upper()
    if cod_ingresado:
        conn = sqlite3.connect(RUTAS["lab"]) 
        cursor = conn.cursor()
        try: cursor.execute("ALTER TABLE catalogo_articulos ADD COLUMN MAXIMO TEXT")
        except: pass 
        try:
            cursor.execute('SELECT D1, H1, CAPACIDAD, COLOR, BOCA, ESPESOR, CODIGOMP, MAXIMO FROM catalogo_articulos WHERE CODPLA = ? OR CODIGO = ?', (cod_ingresado, cod_ingresado))
            registro = cursor.fetchone()
        except: registro = None
        finally: conn.close()

        if registro:
            d1 = str(registro[0]).strip() if registro[0] else ""
            h1 = str(registro[1]).strip() if registro[1] else ""
            st.session_state.t_med = f"{d1} x {h1}"
            st.session_state.t_cap = str(registro[2]).strip() if registro[2] else ""
            MAPEO_COLOR = {"1": "Ambar", "1.0": "Ambar", "2": "Incoloro", "2.0": "Incoloro", "AMBAR": "Ambar", "INCOLORO": "Incoloro"}
            color_bd = str(registro[3]).strip().upper() if registro[3] else ""
            st.session_state.lab_col = MAPEO_COLOR.get(color_bd, "Ambar")
            codigo_boca_bd = str(registro[4]).strip() if registro[4] else ""
            st.session_state.lab_boc = MAPEO_BOCAS.get(codigo_boca_bd, codigo_boca_bd)
            st.session_state.lab_par = str(registro[5]).strip() if registro[5] else ""
            st.session_state.hidden_cod_mp = str(registro[6]).strip() if registro[6] else ""
            try: valor_maximo = float(registro[7]) if registro[7] else 0.0
            except: valor_maximo = 0.0
            st.session_state.t_max = str(registro[7]).strip() if registro[7] else ""

def enriquecer_catalogo_articulos(codigo, capacidad, color, boca, espesor, codigomp, maximo):
    conn = sqlite3.connect(RUTAS["lab"])
    cursor = conn.cursor()
    try: cursor.execute("ALTER TABLE catalogo_articulos ADD COLUMN MAXIMO TEXT")
    except: pass 
    cursor.execute('''UPDATE catalogo_articulos SET CAPACIDAD = ?, COLOR = ?, BOCA = ?, ESPESOR = ?, CODIGOMP = ?, MAXIMO = ? WHERE CODIGO = ? OR CODPLA = ?''', (capacidad, color, boca, espesor, codigomp, maximo, codigo, codigo))
    conn.commit()
    conn.close()

def autocompletar_por_lote():
    MAPEO_BOCAS = {"1": "Tapa Rosca", "2": "20 Normal", "3": "20 C/Anclaje", "4": "13 Normal", "5": "13 C/Anclaje", "6": "8 Normal", "7": "8 C/Anclaje", "8": "10 Normal", "9": "Tapa Rosca 9A", "10": "Tapa Rosca 9B", "11": "Tapa Rosca 10", "12": "Perfumero", "13": "Boca Spray", "14": "Tubo", "15": "Cuadrada"}
    MAPEO_COLOR = {"1": "Ambar", "2": "Incoloro", "AMBAR": "Ambar", "INCOLORO": "Incoloro"}
    lote_ingresado = st.session_state.t_lote.strip()
    if lote_ingresado:
        conn = sqlite3.connect(RUTAS["lab"])
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT cliente, maquina, horno, medida, capacidad, cod, boca, color, pared, impresion, tratado, l_m_prima, batch, volumen, temperatura FROM analisis_hidrolitica WHERE lote_lumen = ? ORDER BY nro_analisis DESC LIMIT 1', (lote_ingresado,))
            registro = cursor.fetchone()
            if registro:
                st.session_state.t_cli = registro[0]
                st.session_state.lab_maq = registro[1]
                st.session_state.lab_hor = registro[2]
                st.session_state.t_med = registro[3]
                st.session_state.t_cap = registro[4]
                st.session_state.t_cod = registro[5]
                st.session_state.lab_boc = registro[6]
                st.session_state.lab_col = registro[7]
                st.session_state.lab_par = registro[8]
                st.session_state.t_imp = registro[9]
                st.session_state.lab_trat = registro[10]
                st.session_state.t_lmp = registro[11]
                st.session_state.t_batch = registro[12]
                st.session_state.lab_vol = registro[13]
                st.session_state.lab_temp = str(registro[14]).strip() if registro[14] else ""
                codigo_frasco = registro[5]
                if codigo_frasco:
                    cursor.execute("SELECT MAXIMO FROM catalogo_articulos WHERE CODIGO = ?", (codigo_frasco,))
                    res_max = cursor.fetchone()
                    if res_max and res_max[0]: st.session_state.t_max = res_max[0]
            else:
                df_p = cargar_produccion()
                if not df_p.empty:
                    lotes_limpios = df_p['LOTE_LUMEN'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
                    datos_p = df_p[lotes_limpios == lote_ingresado]
                    if not datos_p.empty:
                        fila = datos_p.iloc[0]
                        if not st.session_state.get("t_cli"): st.session_state.t_cli = str(fila.get('CLIENTE', '')).strip()
                        if not st.session_state.get("t_cod"): 
                            st.session_state.t_cod = str(fila.get('CODPLANO', '')).strip()
                            codigo_cat = st.session_state.t_cod
                            if codigo_cat:
                                cursor.execute("SELECT MAXIMO FROM catalogo_articulos WHERE CODIGO = ?", (codigo_cat,))
                                res_cat = cursor.fetchone()
                                if res_cat and res_cat[0]: st.session_state.t_max = res_cat[0]
                        if not st.session_state.get("t_med"): st.session_state.t_med = str(fila.get('MEDIDA', '')).strip().replace('ñ', '±').replace('Ñ', '±')
                        boc_prod = str(fila.get('BOCA', '')).strip()
                        if boc_prod.endswith('.0'): boc_prod = boc_prod[:-2]
                        if not st.session_state.get("lab_boc"): st.session_state.lab_boc = MAPEO_BOCAS.get(boc_prod, boc_prod)
                        col_prod = str(fila.get('COLOR', '')).strip().upper()
                        if col_prod.endswith('.0'): col_prod = col_prod[:-2]
                        if not st.session_state.get("lab_col"): st.session_state.lab_col = MAPEO_COLOR.get(col_prod, "Ambar")
                        par_prod = str(fila.get('PARED', '')).strip()
                        if par_prod.endswith('.0'): par_prod = par_prod[:-2]
                        if not st.session_state.get("lab_par"): st.session_state.lab_par = par_prod
                        if not st.session_state.get("t_lmp"): st.session_state.t_lmp = str(fila.get('LOTEMP', '')).strip()
                        if not st.session_state.get("t_batch"): st.session_state.t_batch = str(fila.get('BATCH', '')).strip()
                        maq_prod = str(fila.get('MAQUINA', '')).strip()
                        if maq_prod.endswith('.0'): maq_prod = maq_prod[:-2]
                        if maq_prod: st.session_state.lab_maq = maq_prod
        except Exception as e: print(f"Error en autocompletado: {e}")
        finally: conn.close()

def guardar_temperatura(datos):
    conn = sqlite3.connect(RUTAS["lab"])
    cursor = conn.cursor()
    cursor.execute('INSERT INTO registro_temperatura (fecha, hora, temperatura, responsable, verificacion) VALUES (?, ?, ?, ?, ?)', datos)
    conn.commit()
    conn.close()

def cargar_historial_temperatura():
    conn = sqlite3.connect(RUTAS["lab"])
    df = pd.read_sql_query("SELECT * FROM registro_temperatura ORDER BY id DESC LIMIT 50", conn)
    conn.close()
    return df

def cargar_historial_lab():
    if not os.path.exists(RUTAS["lab"]): return pd.DataFrame()
    conn = sqlite3.connect(RUTAS["lab"])
    df = pd.read_sql_query("SELECT * FROM analisis_hidrolitica ORDER BY nro_analisis DESC", conn)
    conn.close()
    return df

def generar_certificado_pdf(fila, datos_extra):
    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.add_page()
    pdf.image('plantilla_certificado.jpg', x=0, y=0, w=210, h=297)
    pdf.set_font("helvetica", style="B", size=10)
    
    pdf.set_xy(x=30.7- 2.5, y=196.1- 4.75)
    pdf.cell(w=24.9, h=5, txt=str(fila['nro_analisis']), border=0, align='C')
    cliente_imprimir = str(datos_extra.get('cliente_editado', fila['cliente'])).upper()
    pdf.set_xy(x=72.8 - 2.5, y=50.5 - 4.75)
    tamano_fuente = 10
    pdf.set_font("helvetica", style="B", size=tamano_fuente)
    while pdf.get_string_width(cliente_imprimir) > 75 and tamano_fuente > 5:
        tamano_fuente -= 1
        pdf.set_font("helvetica", style="B", size=tamano_fuente)
    pdf.cell(w=76.5, h=7.2, txt=cliente_imprimir, border=0, align='C')
    pdf.set_font("helvetica", style="B", size=10)

    pdf.set_xy(x=172.6- 2.5, y=50.5- 4.75)
    pdf.cell(w=27, h=7.2, txt=str(fila['maquina']), border=0, align='C')
    pdf.set_xy(x=146.6- 2.5, y=74.48- 4.75)
    pdf.cell(w=25.9, h=7.2, txt=str(fila['lote_lumen']), border=0, align='C')
    pdf.set_xy(x=53.65- 2.5, y=95.65- 4.75)
    pdf.cell(w=58.13, h=7.2, txt=str(fila['medida']), border=0, align='C')         
    pdf.set_xy(x=114.5- 2.5, y=95.65- 4.75)
    pdf.cell(w=32.04, h=7.2, txt=str(fila['boca']).upper(), border=0, align='C')
    pdf.set_xy(x=149.42- 2.5, y=95.65- 4.75)
    pdf.cell(w=50.23, h=7.2, txt=str(fila['color']).upper(), border=0, align='C')
    pdf.set_xy(x=12.3- 2.5, y=110.51- 4.75)
    cap_texto = str(fila['capacidad']).strip() + " ml" if fila['capacidad'] and str(fila['capacidad']) != "None" else "- ml"
    pdf.cell(w=39.3, h=7.2, txt=cap_texto, border=0, align='C')
    
    texto_impresion = str(datos_extra.get('impresion', fila['impresion'])).upper()

    pdf.set_xy(x=53.7- 2.5, y=110.51- 4.75)
    tamano_fuente_impresion = 10
    pdf.set_font("helvetica", style="B", size=tamano_fuente_impresion)
    while pdf.get_string_width(texto_impresion) > 56 and tamano_fuente_impresion > 5:
        tamano_fuente_impresion -= 1
        pdf.set_font("helvetica", style="B", size=tamano_fuente_impresion)
    pdf.cell(w=58.11, h=7.2, txt=texto_impresion, border=0, align='C')
    pdf.set_font("helvetica", style="B", size=10) 
    

    pdf.set_xy(x=114.5- 2.5, y=110.51- 4.75)
    pdf.cell(w=35, h=7.2, txt=str(fila['cod']), border=0, align='C')
    pdf.set_xy(x=53.7- 2.5, y=131.5- 4.75)
    pdf.cell(w=36.87, h=5, txt=str(fila['l_m_prima']), border=0, align='C')
    pdf.set_xy(x=53.7- 2.5, y=138.25- 4.75)
    pdf.cell(w=36.87, h=5,txt=str(fila['batch']), border=0, align='C')
    pdf.set_xy(x=53.7- 2.5, y=152.4- 4.75)
    pdf.cell(w=36.87, h=5, txt=str(fila['pared']).replace(".", ",") + " mm", border=0, align='C')
    
    res_str = f"{fila['resultado_final']:.2f}".replace(".", ",")
    pdf.set_xy(x=95- 2.5, y=196.1- 4.75)
    pdf.cell(w=20.3, h=5, txt=res_str, border=0, align='C')
    max_str = f"{fila['maximo']:.2f}".replace(".", ",")
    pdf.set_xy(x=172.2- 2.5, y=196.1- 4.75)
    pdf.cell(w=20.3, h=5, txt=max_str, border=0, align='C')
    
    try: fecha_ar = datetime.datetime.now().strftime("%d/%m/%Y")
    except: fecha_ar = fila['fecha']

    pdf.set_xy(x=12.1- 2.5, y=50.5- 4.75)
    pdf.cell(w=39.5- 2.5, h=7.2, txt=fecha_ar, border=0, align='C')
    pdf.set_xy(x=90.8- 2.5, y=260.4- 4.75)
    pdf.cell(w=20, h=5, txt=fecha_ar, border=0, align='C')
    pdf.set_xy(x=183.5- 2.5, y=260.4- 4.75)
    pdf.cell(w=18, h=5, txt=fecha_ar, border=0, align='C')
    pdf.set_xy(x=149.4- 2.5, y=14.6- 4.75)
    pdf.cell(w=23.3, h=10.1, txt=str(datos_extra.get('nro_cert', '')), border=0, align='C') 
    
    oc_imprimir = str(datos_extra.get('oc', ''))
    pdf.set_xy(x=53.65- 2.5, y=65.15- 4.75)
    tamano_fuente_oc = 10
    pdf.set_font("helvetica", style="B", size=tamano_fuente_oc)
    while pdf.get_string_width(oc_imprimir) > 35 and tamano_fuente_oc > 5:
        tamano_fuente_oc -= 1
        pdf.set_font("helvetica", style="B", size=tamano_fuente_oc)
    pdf.cell(w=36.88, h=7.2, txt=oc_imprimir, border=0, align='C')
    pdf.set_font("helvetica", style="B", size=10) 
    
    pdf.set_xy(x=53.65- 2.5, y=74.49- 4.75)
    pdf.cell(w=36.88, h=7.2, txt=str(datos_extra.get('np', '')), border=0, align='C') 
    pdf.set_xy(x=53.65- 2.5, y=83.71- 4.75)
    pdf.cell(w=36.88, h=7.2, txt=str(fila['cod']), border=0, align='C') 
    pdf.set_xy(x=172.65- 2.5, y=65.2- 4.75)
    pdf.cell(w=27, h=7.2, txt=str(datos_extra.get('fecha_vto', '')), border=0, align='C') 
    pdf.set_xy(x=12.3- 2.5, y=95.65- 4.75)
    pdf.cell(w=39.3, h=7.2, txt=str(datos_extra.get('cantidad', '')), border=0, align='C') 
    
    medida_val = str(fila['medida']).strip() if fila['medida'] and str(fila['medida']) != "None" else ""
    if medida_val and medida_val != "-": diametro_texto = medida_val.upper().split('X')[0].strip() + " mm"
    else: diametro_texto = "- mm"
    pdf.set_xy(x=53.7- 2.5, y=145.5- 4.75)    
    pdf.cell(w=36.87, h=5, txt=diametro_texto, border=0, align='C')
    pdf.set_xy(x=172.61- 2.5, y=159.31- 4.75)
    pdf.cell(w=24.9, h=5, txt=str(datos_extra.get('imp_control', 'N/A')), border=0, align='C') 
    
    pdf_bytes = pdf.output()
    return bytes(pdf_bytes)

def obtener_siguiente_nro_analisis():
    if not os.path.exists(RUTAS["lab"]): return 8077
    conn = sqlite3.connect(RUTAS["lab"])
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(nro_analisis) FROM analisis_hidrolitica")
    resultado = cursor.fetchone()[0]
    conn.close()
    return (resultado + 1) if resultado else 8077

def renderizar_modulo_laboratorio():
    st.header("🔬 Control de Calidad: Resistencia Hidrolítica")
    if 'exito_lab' not in st.session_state: st.session_state.exito_lab = False
    if st.session_state.exito_lab:
        st.success("✅ Análisis guardado exitosamente.")
        st.session_state.exito_lab = False 

    tab_lab1, tab_lab2, tab_lab3, tab_lab4 = st.tabs(["📝 Nuevo Análisis", "📚 Historial y Certificados", "🌡️ Registros Temperatura", "Validacion"])
    lista_operarios = obtener_operarios_habilitados()
    with tab_lab1:
        nro_actual = obtener_siguiente_nro_analisis()
        st.markdown(f"### Análisis Nro: **{nro_actual}**")
        
        def accion_guardar():
            # 1. Extraemos el legajo del responsable seleccionado
            legajo_analista = str(st.session_state.lab_resp).split("-")[0].strip()
            pin_ingresado = st.session_state.pin_lab_analista
            
            # 2. VALIDACIÓN DE IDENTIDAD (ISO 9001)
            if not validar_pin_operario(legajo_analista, pin_ingresado):
                st.error("❌ PIN de analista incorrecto. El análisis no se puede registrar.")
                return # Cortamos la ejecución aquí
                
            ahora = datetime.datetime.now()
            v = st.session_state.lab_vol
            b = st.session_state.n_bla
            t = st.session_state.n_tit
            res = (t - b) * 2 if v == "50%" else (t - b)
            
            # 3. Preparamos los 25 datos originales
            datos = (
                nro_actual, ahora.strftime("%Y-%m-%d"), ahora.strftime("%H:%M:%S"),
                legajo_analista, st.session_state.lab_maq, st.session_state.lab_hor,
                st.session_state.lab_temp, st.session_state.t_cli, st.session_state.t_med, st.session_state.t_cap, st.session_state.t_cod, 
                st.session_state.lab_boc, st.session_state.lab_col, st.session_state.lab_par, 
                st.session_state.t_imp, st.session_state.lab_trat, st.session_state.t_lote, 
                st.session_state.t_lmp, st.session_state.t_batch, v, b, t, res, st.session_state.t_max, st.session_state.t_obs
            )
            
            # 4. Guardamos (la función interna agregará None y 'PENDIENTE')
            if guardar_analisis_lab(datos):
                cod_mp_oculto = st.session_state.get('hidden_cod_mp', '')
                enriquecer_catalogo_articulos(
                    st.session_state.t_cod, st.session_state.t_cap, st.session_state.lab_col, 
                    st.session_state.lab_boc, st.session_state.lab_par, cod_mp_oculto, st.session_state.t_max
                )   
                
                # Limpieza de campos
                claves_texto = ["t_cli", "t_lote", "t_med", "t_cap", "t_lmp", "t_cod", "t_batch", "t_imp", "t_obs","lab_temp", "pin_lab_analista"]
                for k in claves_texto: st.session_state[k] = ""
                for k in ["n_bla", "n_tit", "t_max"]: st.session_state[k] = 0.0
                
                st.success(f"✅ Análisis {nro_actual} registrado correctamente y pendiente de validación.")
                st.session_state.exito_lab = True
                st.rerun()

        # --- INTERFAZ DE CARGA ---
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            # USAMOS LA LISTA GENERAL DE OPERARIOS
            resp = st.selectbox("Analista Responsable", lista_operarios, key="lab_resp")
            # CAMPO PARA PIN
            pin_analista = st.text_input("Confirmar con PIN", type="password", key="pin_lab_analista")
            
            cod = st.text_input("Cod. Frasco (Enter para autocompletar)", key="t_cod", on_change=autocompletar_frasco) 
            lote_lum = st.text_input("Lote Lumen", key="t_lote", on_change=autocompletar_por_lote)
        
        with col2:
            cli = st.text_input("Cliente", key="t_cli")
            maq = st.selectbox("Máquina", MAQUINAS, key="lab_maq")
            l_mp = st.text_input("L.M.Prima", key="t_lmp")
        
        with col3:
            hor = st.selectbox("Horno", HORNOS, key="lab_hor")
            temp = st.text_input("Temp. Horno (°C)", key="lab_temp")
            med = st.text_input("Medida (mm)", key="t_med")
            cap = st.text_input("Capacidad (ml)", key="t_cap")
            batch = st.text_input("Batch", key="t_batch")
        
        with col4:
            boc = st.selectbox("Boca", BOCAS, key="lab_boc") 
            col_vid = st.selectbox("Color", ["Ambar", "Incoloro"], key="lab_col") 
            par = st.text_input("Pared (mm)", key="lab_par") 
            
        col_c1, col_c2, col_c3 = st.columns(3)
        with col_c1: imp = st.text_input("Impresión", key="t_imp")
        with col_c2: trat = st.radio("Tratado", ["Si", "No"], horizontal=True, key="lab_trat")
        with col_c3: vol = st.radio("Vol. Analizado", ["50%", "100%"], horizontal=True, key="lab_vol")

        st.markdown("---")
        st.markdown("#### 🧪 Resultados de Titulación")
        c_tit1, c_tit2, c_tit3, c_tit4 = st.columns(4)
        
        with c_tit1: blanco = st.number_input("Blanco (ml de HCL 0,01 M)", min_value=0.0, step=0.01, format="%.2f", key="n_bla")
        with c_tit2: titulacion = st.number_input("Titulación (ml de HCL 0,01 M)", min_value=0.0, step=0.01, format="%.2f", key="n_tit")
        
        # --- LÓGICA SIN PARPADEOS ---
        val_maximo = 0.0
        if "t_max" in st.session_state:
            try: val_maximo = float(str(st.session_state["t_max"]).replace(',', '.'))
            except: pass
        
        with c_tit3: 
            maximo = st.number_input("Máximo Permitido", min_value=0.0, value=val_maximo, step=0.01, format="%.2f")
            st.session_state["t_max"] = maximo # Actualizamos el estado silenciosamente
            
        resultado_calc = (titulacion - blanco) * 2 if vol == "50%" else (titulacion - blanco)
            
        with c_tit4:
            if maximo > 0 and resultado_calc > maximo: st.error(f"RESULTADO: {resultado_calc:.2f} (RECHAZADO)")
            else: st.success(f"RESULTADO: {resultado_calc:.2f} (OK)")

        obs = st.text_area("Observaciones", key="t_obs")
        st.button("💾 Guardar Análisis", use_container_width=True, type="primary", on_click=accion_guardar)

    with tab_lab2:
        with st.expander("⏱️ Cargar Análisis Histórico (Papel a Digital)"):
            st.info("Digitalice un análisis antiguo para asignarle un número de certificado oficial.")

            df_empleados = obtener_operarios_habilitados()

            c_leg1, c_leg2, c_leg3 = st.columns(3)
            with c_leg1:
                leg_lote = st.text_input("Lote Lumen", key="leg_lote")
                leg_cod = st.text_input("Cod. Frasco", key="leg_cod")
                leg_cli = st.text_input("Cliente", key="leg_cli")
                h_maquina = st.selectbox("Máquina", [""] + MAQUINAS)
                h_capacidad = st.text_input("Capacidad (ml)", placeholder="Ej: 10ml")
            with c_leg2:
                leg_fec = st.date_input("Fecha Original")
                
                st.markdown("---")
                st.markdown("🔒 **Firma Digital del Analista**")
                # Reemplazamos el selectbox plano por el formato normalizado con Legajo + Nombre
                operario_sel = st.selectbox("Seleccione su Nombre", df_empleados, key="leg_resp_sel")
                # Extraemos el legajo puro para enviarlo a la base de datos y validarlo
                leg_resp = operario_sel.split(" - ")[0] if " - " in operario_sel else operario_sel
                
                # Agregamos la entrada segura para el PIN
                pin_operario = st.text_input("Ingrese su PIN", type="password", key="leg_pin_cargador")
            with c_leg3:
                leg_res = st.number_input("Resultado Final", format="%.2f", key="leg_res")
                leg_max = st.number_input("Máximo", format="%.2f", key="leg_max")
                leg_obs = st.text_area("Observaciones", value="CARGA HISTÓRICA", key="leg_obs")
                
            if st.button("💾 Asignar Nro. de Certificado", type="primary"):
                # 2. Validación de seguridad con PIN antes de procesar el guardado
                if " - " in operario_sel and not pin_operario:
                    st.error("❌ Debe ingresar su PIN para firmar digitalmente la carga.")
                elif " - " in operario_sel and not validar_pin_operario(leg_resp, pin_operario):
                    st.error("❌ PIN de operario incorrecto. Registro denegado por auditoría.")
                else:
                    # Si pasa las validaciones, armamos la tupla y registramos
                    datos = (leg_fec.strftime("%Y-%m-%d"), leg_resp, leg_cli, leg_cod, leg_lote, leg_res, leg_max, leg_obs, h_maquina, h_capacidad)
                    id_nuevo, cert_nuevo = registrar_analisis_legado(datos)
                    
                    if id_nuevo > 0:
                        st.success(f"✅ Digitalizado. Enviado en estado PENDIENTE. Nro. de Certificado asignado: {cert_nuevo}. Búsquelo abajo para imprimir.")
                        st.rerun()

        st.markdown("---")

        st.markdown("---")
        df_lab = cargar_historial_lab()
        if not df_lab.empty:
            st.markdown("### 📚 Búsqueda de Historial")
            col_b1, col_b2 = st.columns(2)
            with col_b1: buscar_lote = st.text_input("🔍 Buscar por Lote Lumen", key="busq_lote")
            with col_b2: buscar_cli = st.text_input("🔍 Buscar por Cliente", key="busq_cli")
            
            df_mostrar = df_lab.copy()
            if buscar_lote: df_mostrar = df_mostrar[df_mostrar['lote_lumen'].str.contains(buscar_lote, case=False, na=False)]
            if buscar_cli: df_mostrar = df_mostrar[df_mostrar['cliente'].str.contains(buscar_cli, case=False, na=False)]
            st.dataframe(df_mostrar, use_container_width=True)

            st.markdown("### 🖨️ Generador de Certificados (PDF)")
            analisis_disponibles = df_mostrar['nro_analisis'].tolist()
            if analisis_disponibles:
                col_pdf_izq, col_pdf_der = st.columns([1, 2])
                with col_pdf_izq:
                    st.info("1. Seleccione el análisis:")
                    analisis_a_imprimir = st.selectbox("Nro. Análisis", analisis_disponibles, key="sel_pdf")
                with col_pdf_der:
                    st.warning("2. Datos comerciales y de control (Autocompletados):")
                    fila_elegida = df_mostrar[df_mostrar['nro_analisis'] == analisis_a_imprimir].iloc[0]
                    lote_actual = str(fila_elegida['lote_lumen']).strip()
                    df_prod = cargar_produccion()
                    datos_prod = pd.DataFrame()
                    if not df_prod.empty:
                        lotes_limpios = df_prod['LOTE_LUMEN'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
                        datos_prod = df_prod[lotes_limpios == lote_actual]
                    
                    def_np = limpiar_comercial(datos_prod.iloc[0].get('NOTA_PEDIDO', '-')) if not datos_prod.empty else "-"
                    def_oc = "-"
                    df_pedidos = cargar_pedidos_completos()
                    if def_np != "-" and not df_pedidos.empty:
                        np_limpios = df_pedidos['NOTA_PEDIDO'].apply(limpiar_comercial)
                        datos_ped = df_pedidos[np_limpios == def_np]
                        if not datos_ped.empty:
                            def_oc = limpiar_comercial(datos_ped.iloc[0].get('ORDEN_COMPRA', '-'))
                    if def_oc == "-" and not datos_prod.empty:
                        def_oc = limpiar_comercial(datos_prod.iloc[0].get('ORDEN_COMPRA', '-'))
                    
                    siguiente_cert = obtener_siguiente_nro_certificado(fila_elegida['nro_analisis'])
                    doc_cliente = st.text_input("Nombre del Cliente (Editable)", value=str(fila_elegida['cliente']).strip())

                    cx1, cx2, cx3 = st.columns(3)
                    with cx1:
                        doc_nro_cert = st.number_input("Nro. Certificado", value=siguiente_cert, step=1)
                        doc_oc = st.text_input("Orden de Compra", value=def_oc)
                        doc_np = st.text_input("Nota de Pedido", value=def_np)
                    with cx2:
                        doc_imp = st.text_input("Texto de Impresión", value=str(fila_elegida['impresion']))
                        doc_cant = st.text_input("Cantidad", value=limpiar_comercial(datos_prod.iloc[0].get('CANTIDAD', '0')) if not datos_prod.empty else "0")
                    with cx3:
                        estado_imp = "CORRECTO" if doc_imp.upper() not in ["SIN IMPRESION", "N/A", ""] else "N/A"
                        doc_ctrl_imp = st.selectbox("Control Impresión", ["N/A", "CORRECTO", "INCORRECTO"], index=0 if estado_imp == "N/A" else 1)
                        doc_vto = st.text_input("Fecha Entrega", value=str(datos_prod.iloc[0].get('FECHA_ENTREGA', '-')) if not datos_prod.empty else "-")

                    diccionario_extra = {
                        'cliente_editado': doc_cliente, 
                        'nro_cert': doc_nro_cert, 'oc': doc_oc, 'np': doc_np, 'cantidad': doc_cant, 
                        'fecha_vto': doc_vto, 'impresion': doc_imp, 'imp_control': doc_ctrl_imp  
                    }
                    
                    cliente_str = doc_cliente.strip().upper()
                    imp_str = doc_imp.strip().upper()
                    imp_parte = f" {imp_str}" if imp_str not in ["", "N/A", "SIN IMPRESION", "SIN IMPRESIÓN", "-"] else ""
                    lote_str = str(fila_elegida['lote_lumen']).strip().upper()
                    cod_str = str(fila_elegida['cod']).strip().upper()
                    
                    nombre_dinamico = f"CERTIFICADO DE CALIDAD NRO {doc_nro_cert} {cliente_str}{imp_parte} LOTE {lote_str} {cod_str}.pdf"
                    nombre_limpio = re.sub(r'[\\/*?:"<>|]', "", nombre_dinamico) 

                    st.write("") 
                    pdf_listo = generar_certificado_pdf(fila_elegida, diccionario_extra)
                    
                    if 'msg_cert' in st.session_state:
                        if "✅" in st.session_state.msg_cert: st.success(st.session_state.msg_cert)
                        else: st.error(st.session_state.msg_cert)
                        del st.session_state.msg_cert 
                    
                    st.download_button(
                        label=f"💾 GUARDAR EN RED Y DESCARGAR",
                        data=pdf_listo, file_name=nombre_limpio, mime="application/pdf",
                        type="primary", use_container_width=True, key=f"btn_pdf_vfinal_{fila_elegida['nro_analisis']}",
                        on_click=guardar_certificado_red,
                        args=(fila_elegida['nro_analisis'], doc_nro_cert, pdf_listo, nombre_limpio)
                    )
        else: st.info("Aún no hay registros en la base.")

    with tab_lab3:
        st.markdown("### 🌡️ Registro de Temperatura Ambiente")
        df_empleados = obtener_operarios_habilitados()
        col_t1, col_t2, col_t3 = st.columns(3)
        with col_t1: 
            temp_resp = st.selectbox("Firma/Rúbrica", df_empleados, key="t_resp")
            pin_operario = st.text_input("Ingrese su PIN", type="password", key="temp_resp")
        with col_t2: temp_valor = st.number_input("Temperatura (°C)", min_value=0.0, max_value=50.0, step=0.1, format="%.1f", key="t_val")
        with col_t3: temp_verif = st.text_input("Verificación / Observaciones", key="t_verif", placeholder="Ej: OK")
        # Extraemos el legajo puro para enviarlo a la base de datos y validarlo
        leg_resp = temp_resp.split(" - ")[0] if " - " in operario_sel else operario_sel



        if st.button("💾 Guardar Temperatura", type="primary"):
                # 2. Validación de seguridad con PIN antes de procesar el guardado
                if " - " in temp_resp and not pin_operario:
                    st.error("❌ Debe ingresar su PIN para firmar digitalmente la carga.")
                elif " - " in temp_resp and not validar_pin_operario(leg_resp, pin_operario):
                    st.error("❌ PIN de operario incorrecto. Registro denegado por auditoría.")
                else:
                    # Si pasa las validaciones, armamos la tupla y registramos
                    ahora = datetime.datetime.now()
                    guardar_temperatura((ahora.strftime("%Y-%m-%d"), ahora.strftime("%H:%M:%S"), temp_valor, temp_resp, temp_verif))
                    st.success(f"✅ Temperatura registrada.")

        st.markdown("---")
        df_temp = cargar_historial_temperatura()
        if not df_temp.empty:
            df_temp_mostrar = df_temp.rename(columns={'fecha': 'DÍA', 'hora': 'HORARIO', 'temperatura': 'TEMPERATURA (°C)', 'responsable': 'FIRMA / RÚBRICA', 'verificacion': 'VERIFICACIÓN'})
            st.dataframe(df_temp_mostrar.drop(columns=['id']), use_container_width=True)

    with tab_lab4:
        st.title("🔬 Validación Técnica de Laboratorio")

        df_pend = obtener_analisis_pendientes()

        if not df_pend.empty:
            st.warning(f"Hay {len(df_pend)} protocolos de Hidrolítica esperando validación.")
            
            # El supervisor selecciona cuáles aprueba (por defecto todos)
            seleccion = st.multiselect(
                "Protocolos a validar:",
                options=df_pend['nro_analisis'].tolist(),
                default=df_pend['nro_analisis'].tolist()
            )
            
            st.dataframe(df_pend[df_pend['nro_analisis'].isin(seleccion)], use_container_width=True)

            with st.form("firma_jefe_lab"):
                col1, col2 = st.columns(2)
                with col1:
                    sup_lab = st.selectbox("Jefe de Laboratorio", lista_operarios)
                with col2:
                    pin_sup = st.text_input("PIN de Firma Digital", type="password")
                
                if st.form_submit_button("🛡️ Validar Protocolos Seleccionados"):
                    legajo_s = str(sup_lab).split("-")[0].strip()
                    if validar_pin_operario(legajo_s, pin_sup):
                        if aprobar_analisis_laboratorio(seleccion, legajo_s):
                            st.success("✅ Análisis validados y cerrados para protocolo.")
                            st.rerun()
                    else:
                        st.error("PIN de autoridad incorrecto.")
        else:
            st.success("🎉 Todos los análisis de laboratorio están validados.")