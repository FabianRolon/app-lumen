import streamlit as st
import pandas as pd
from dbfread import DBF
import datetime
import os
import shutil
import sqlite3
from fpdf import FPDF
import io
import re
from streamlit_option_menu import option_menu

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Sistema LumenGlass 4.2", layout="wide")

RUTAS = {
    "asist": {"red": r'C:\Reloj\Bases\ASIGTURN.DBF', "loc": r'C:\proyecto_Asistencia\asistencia_temp.dbf'},
    "bano": {"red": r'\\CALIDAD\Bases\BANODBF.dbf', "loc": r'C:\proyecto_Asistencia\bano_temp.dbf'},
    "lab": r'C:\proyecto_Asistencia\laboratorio.db',
    "pedidos": {"red": r'\\LUMENGLASS\Sistemas\Bases\REMENCA.dbf', "loc": r'C:\proyecto_Asistencia\remenca_temp.dbf'},
    "remitos": {"red": r'\\LUMENGLASS\Sistemas\Bases\REMITOS.dbf', "loc": r'C:\proyecto_Asistencia\remitos_temp.dbf'},
    "produccion": {"red": r'\\LUMENGLASS\Sistemas\Bases\ORDPRODU.dbf', "loc": r'C:\proyecto_Asistencia\ordprodu_temp.dbf'},
    "maestro_clientes": {"red": r'\\LUMENGLASS\Sistemas\Bases\CLIENTES.dbf', "loc": r'C:\proyecto_Asistencia\clientes_temp.dbf'},
    "certificados": r'\\CALIDAD\certificados de calidad',
    "stock_movimientos": {"red": r'\\LUMENGLASS\Sistemas\Bases\STOCKMA.dbf', "loc": r'C:\proyecto_Asistencia\stockma_temp.dbf'},
    "stock_pallets": {"red": r'\\LUMENGLASS\Sistemas\Bases\PALLETS.dbf', "loc": r'C:\proyecto_Asistencia\pallets_temp.dbf'}
}

RESPONSABLES = ["Nahuel Ayala", "Hernan Spataro", "Fabian Rolon", "Lucio Menendez"]
BOCAS = ["Tapa Rosca","20 Normal","20 C/Anclaje","13 Normal","13 C/Anclaje","8 Normal","8 C/Anclaje","10 Normal","Tapa Rosca 9A","Tapa Rosca 9B","Tapa Rosca 10","Perfumero","Boca Spray","Tubo","Cuadrada","N/Aplica"]
MAQUINAS = ["F1", "F2", "F3", "F4"]
HORNOS = ["H1", "H2", "H3", "H4", "H5"]

# --- INICIALIZADOR DE BASE DE DATOS ---
def inicializar_db():
    conn = sqlite3.connect(RUTAS["lab"])
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS analisis_hidrolitica (
            nro_analisis INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT, hora TEXT, responsable TEXT, maquina TEXT, horno TEXT, temperatura TEXT,
            cliente TEXT, medida TEXT, capacidad TEXT, cod TEXT, boca TEXT, color TEXT,
            pared TEXT, impresion TEXT, tratado TEXT, lote_lumen TEXT,
            l_m_prima TEXT, batch TEXT, volumen TEXT, blanco REAL,
            titulacion REAL, resultado_final REAL, maximo REAL, observaciones TEXT
        )
    ''')
    try: cursor.execute("ALTER TABLE analisis_hidrolitica ADD COLUMN capacidad TEXT")
    except: pass 
    try: cursor.execute("ALTER TABLE analisis_hidrolitica ADD COLUMN temperatura TEXT")
    except: pass
    try: cursor.execute("ALTER TABLE analisis_hidrolitica ADD COLUMN nro_certificado INTEGER")
    except: pass

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS registro_temperatura (
                id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, hora TEXT,
                temperatura REAL, responsable TEXT, verificacion TEXT
        )
    ''')                          
    conn.commit()
    conn.close()

inicializar_db()

# --- 2. MOTORES DE LECTURA ---
@st.cache_data(ttl=60)
def cargar_asistencia():
    if not os.path.exists(RUTAS["asist"]["red"]): return pd.DataFrame()
    shutil.copy2(RUTAS["asist"]["red"], RUTAS["asist"]["loc"])
    df = pd.DataFrame(iter(DBF(RUTAS["asist"]["loc"], encoding='latin1')))
    df['LEGAJO'] = pd.to_numeric(df['LEGAJO'], errors='coerce')
    df['FECHA'] = pd.to_datetime(df['FECHA'], errors='coerce').dt.date
    
    e = pd.to_datetime(df['HORAI'], errors='coerce')
    s = pd.to_datetime(df['HORAE'], errors='coerce')
    dif = s - e
    dif = dif.where(dif >= pd.Timedelta(0), dif + pd.Timedelta(days=1))
    df['TOTAL_HS'] = (dif.dt.total_seconds() / 3600).fillna(0).round(2)
    
    if 'ALMUERZOI' in df.columns and 'ALMUERZOF' in df.columns:
        df['SALIDA_DESC'] = df['ALMUERZOI'].astype(str).str.strip().replace(['', 'None', 'nan'], pd.NA)
        df['VUELTA_DESC'] = df['ALMUERZOF'].astype(str).str.strip().replace(['', 'None', 'nan'], pd.NA)
        e_alm = pd.to_datetime(df['SALIDA_DESC'], errors='coerce')
        s_alm = pd.to_datetime(df['VUELTA_DESC'], errors='coerce')
        dif_alm = (s_alm - e_alm).dt.total_seconds() / 60
        dif_alm = dif_alm.where(dif_alm >= 0, dif_alm + (24*60))
        validos = dif_alm.notna() & (dif_alm > 0)
        sin_vuelta = e_alm.notna() & s_alm.isna()
        
        minutos_reales = dif_alm.where(validos, 0)
        minutos_con_tope = minutos_reales.where(minutos_reales <= 90, 90)
        
        df['MIN_DESCANSO'] = 0
        df['DETALLE_DESCANSO'] = "Sin datos"
        df.loc[validos, 'MIN_DESCANSO'] = minutos_con_tope[validos].round(0)
        df.loc[validos & (minutos_reales <= 90), 'DETALLE_DESCANSO'] = "OK"
        df.loc[validos & (minutos_reales > 90), 'DETALLE_DESCANSO'] = "⚠️ Excede 90m"
        df.loc[sin_vuelta, 'MIN_DESCANSO'] = 90
        df.loc[sin_vuelta, 'DETALLE_DESCANSO'] = "⚠️ Sin Vuelta"
        df['SALIDA_DESC'] = df['SALIDA_DESC'].fillna("-")
        df['VUELTA_DESC'] = df['VUELTA_DESC'].fillna("-")
    else:
        df['SALIDA_DESC'], df['VUELTA_DESC'], df['MIN_DESCANSO'], df['DETALLE_DESCANSO'] = "-", "-", 0, "Sin columnas"
    return df

@st.cache_data(ttl=300) 
def cargar_pedidos_completos():
    if not os.path.exists(RUTAS["pedidos"]["red"]) or not os.path.exists(RUTAS["remitos"]["red"]): 
        return pd.DataFrame()
    
    try:
        shutil.copy2(RUTAS["pedidos"]["red"], RUTAS["pedidos"]["loc"])
        base_red_p = os.path.splitext(RUTAS["pedidos"]["red"])[0]
        base_loc_p = os.path.splitext(RUTAS["pedidos"]["loc"])[0]
        for ext in ['.FPT', '.fpt', '.DBT', '.dbt']:
            if os.path.exists(base_red_p + ext): shutil.copy2(base_red_p + ext, base_loc_p + ext)
            
        df_enc = pd.DataFrame(iter(DBF(RUTAS["pedidos"]["loc"], encoding='latin1', ignore_missing_memofile=True)))
        cols_enc = {'REMITO': 'NOTA_PEDIDO', 'NOMBRE': 'CLIENTE', 'ORDEN': 'ORDEN_COMPRA', 'FECENTRE': 'FECHA_ENTREGA', 'FECHA': 'FECHA_EMISION'}
        df_enc = df_enc[[c for c in cols_enc.keys() if c in df_enc.columns]].rename(columns=cols_enc)

        shutil.copy2(RUTAS["remitos"]["red"], RUTAS["remitos"]["loc"])
        base_red_r = os.path.splitext(RUTAS["remitos"]["red"])[0]
        base_loc_r = os.path.splitext(RUTAS["remitos"]["loc"])[0]
        for ext in ['.FPT', '.fpt', '.DBT', '.dbt']:
            if os.path.exists(base_red_r + ext): shutil.copy2(base_red_r + ext, base_loc_r + ext)
            
        df_det = pd.DataFrame(iter(DBF(RUTAS["remitos"]["loc"], encoding='latin1', ignore_missing_memofile=True)))
        cols_det = {'REMITO': 'NOTA_PEDIDO', 'CODIGO': 'COD_FRASCO', 'DESCRIP': 'DESCRIPCION', 'CANTIDAD': 'CANTIDAD', 'UNIDAD': 'UNIDAD'}
        df_det = df_det[[c for c in cols_det.keys() if c in df_det.columns]].rename(columns=cols_det)

        df_det['CANTIDAD'] = pd.to_numeric(df_det['CANTIDAD'], errors='coerce').fillna(0)
        df_det['UNIDAD'] = pd.to_numeric(df_det['UNIDAD'], errors='coerce').fillna(1) 
        df_det['CANTIDAD_TOTAL'] = (df_det['CANTIDAD'] * df_det['UNIDAD']).astype(int)

        for d in [df_enc, df_det]:
            if 'NOTA_PEDIDO' in d.columns:
                d['NOTA_PEDIDO'] = d['NOTA_PEDIDO'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
            for col in d.select_dtypes(include=['object']):
                d[col] = d[col].astype(str).str.strip()

        df_completo = pd.merge(df_det, df_enc, on='NOTA_PEDIDO', how='left')
        
        columnas_finales = ['NOTA_PEDIDO', 'FECHA_EMISION', 'ORDEN_COMPRA', 'CLIENTE', 'COD_FRASCO', 'CANTIDAD_TOTAL', 'DESCRIPCION', 'FECHA_ENTREGA']
        df_completo = df_completo[[c for c in columnas_finales if c in df_completo.columns]]
        
        # Ordenamiento inteligente
        df_completo['FECHA_EMISION'] = pd.to_datetime(df_completo['FECHA_EMISION'], errors='coerce')
        df_completo = df_completo.sort_values(by=['FECHA_EMISION', 'NOTA_PEDIDO'], ascending=[False, False])
        df_completo['FECHA_EMISION'] = df_completo['FECHA_EMISION'].dt.strftime('%d/%m/%Y')
        
        return df_completo
    except Exception as e:
        st.error(f"Error al cruzar las bases de pedidos: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=600)
def cargar_maestro_clientes():
    if not os.path.exists(RUTAS["maestro_clientes"]["red"]): return pd.DataFrame()
    try:
        shutil.copy2(RUTAS["maestro_clientes"]["red"], RUTAS["maestro_clientes"]["loc"])
        base_r = os.path.splitext(RUTAS["maestro_clientes"]["red"])[0]
        base_l = os.path.splitext(RUTAS["maestro_clientes"]["loc"])[0]
        for ext in ['.FPT', '.fpt']:
            if os.path.exists(base_r + ext): shutil.copy2(base_r + ext, base_l + ext)

        df = pd.DataFrame(iter(DBF(RUTAS["maestro_clientes"]["loc"], encoding='latin1', ignore_missing_memofile=True)))
        cols = {'CODIGO': 'CLIENTE', 'NOMBRE': 'NOMBRE_REAL'} 
        df = df[[c for c in cols.keys() if c in df.columns]].rename(columns=cols)
        for col in df.columns: df[col] = df[col].astype(str).str.strip()
        return df
    except:
        return pd.DataFrame()

@st.cache_data(ttl=300) 
def cargar_produccion():
    if not os.path.exists(RUTAS["produccion"]["red"]): return pd.DataFrame()
    try:
        shutil.copy2(RUTAS["produccion"]["red"], RUTAS["produccion"]["loc"])
        df = pd.DataFrame(iter(DBF(RUTAS["produccion"]["loc"], encoding='latin1', ignore_missing_memofile=True)))
        df = df.rename(columns={'LOTE': 'LOTE_LUMEN', 'PEDIDO': 'NOTA_PEDIDO', 'ORDEN': 'ORDEN_COMPRA', 'CANTPEDIDA': 'CANTIDAD', 'FECENTREGA': 'FECHA_ENTREGA'})

        df_maestro = cargar_maestro_clientes()
        if not df_maestro.empty:
            df['CLIENTE'] = df['CLIENTE'].astype(str).str.strip()
            df = pd.merge(df, df_maestro, on='CLIENTE', how='left')
            df['CLIENTE'] = df['NOMBRE_REAL'].fillna(df['CLIENTE'])
            df = df.drop(columns=['NOMBRE_REAL'])

        for col in df.select_dtypes(include=['object']): df[col] = df[col].astype(str).str.strip()
        return df
    except Exception as e:
        st.error(f"Error en cruce de clientes: {e}")
        return pd.DataFrame()
    
@st.cache_data(ttl=60)
def cargar_bano():
    if not os.path.exists(RUTAS["bano"]["red"]): return pd.DataFrame()
    shutil.copy2(RUTAS["bano"]["red"], RUTAS["bano"]["loc"])
    df = pd.DataFrame(iter(DBF(RUTAS["bano"]["loc"], encoding='latin1')))
    df['LEGAJO'] = pd.to_numeric(df['LEGAJO'], errors='coerce')
    df['FECHA'] = pd.to_datetime(df['FECHA'], errors='coerce').dt.date
    
    total_minutos = pd.Series(0.0, index=df.index)
    veces = pd.Series(0, index=df.index)
    detalle = pd.Series("", index=df.index)
    pares = [('HORAI', 'HORAE'), ('ALMUERZOI', 'ALMUERZOF')]
    for i in range(1, 8): pares.append((f'HINICIO{i}', f'HFINAL{i}'))
        
    for ini, fin in pares:
        if ini in df.columns and fin in df.columns:
            e_str = df[ini].astype(str).str.strip().replace(['', 'None', 'nan'], pd.NA)
            s_str = df[fin].astype(str).str.strip().replace(['', 'None', 'nan'], pd.NA)
            e = pd.to_datetime(e_str, errors='coerce')
            s = pd.to_datetime(s_str, errors='coerce')
            dif = (s - e).dt.total_seconds() / 60
            dif = dif.where(dif >= 0, dif + (24*60))
            validos = dif.notna() & (dif > 0)
            
            minutos_reales = dif.where(validos, 0)
            minutos_con_tope = minutos_reales.where(minutos_reales <= 40, 40)
            total_minutos += minutos_con_tope
            veces += validos.astype(int)
            
            tiempos_str = dif[validos].round(0).astype(int).astype(str) + "m"
            tiempos_str = tiempos_str.where(dif[validos] <= 40, "⚠️ Sin Vuelta")
            detalle[validos] += tiempos_str + " | "
            
    df['MIN_TOTALES'] = total_minutos.round(2)
    df['CANT_VECES'] = veces
    df['DETALLE_VISITAS'] = detalle.str.rstrip(" | ")
    return df[['LEGAJO', 'NOMBRE', 'FECHA', 'DETALLE_VISITAS', 'MIN_TOTALES', 'CANT_VECES']]

@st.cache_data(ttl=300)
def cargar_stock_fusionado():
    if not os.path.exists(RUTAS["stock_movimientos"]["red"]) or not os.path.exists(RUTAS["stock_pallets"]["red"]):
        return pd.DataFrame()
    
    try:
        # 1. Lectura de STOCKMA (La Realidad del Galpón)
        shutil.copy2(RUTAS["stock_movimientos"]["red"], RUTAS["stock_movimientos"]["loc"])
        df_ma = pd.DataFrame(iter(DBF(RUTAS["stock_movimientos"]["loc"], encoding='latin1')))
        
        col_ano = next((c for c in df_ma.columns if c.strip().upper().startswith('A') and c.strip().upper().endswith('O')), None)
        if col_ano:
            df_ma[col_ano] = pd.to_numeric(df_ma[col_ano], errors='coerce').fillna(0).astype(int)
            df_ma = df_ma[df_ma[col_ano] == 2026].copy()
            
        df_ma['CODIGO'] = df_ma['CODIGO'].astype(str).str.strip().str.upper()
        
        cols_ma = ['CODIGO', 'TKGSTOCK', 'TUBOSSTOCK', 'DESCRIP']
        if 'ORIGEN' in df_ma.columns:
            cols_ma.append('ORIGEN')
        # Filtramos solo las columnas que realmente existen para evitar errores
        df_ma = df_ma[[c for c in cols_ma if c in df_ma.columns]]

        # 2. Lectura de PALLETS (El Diccionario)
        shutil.copy2(RUTAS["stock_pallets"]["red"], RUTAS["stock_pallets"]["loc"])
        df_pa = pd.DataFrame(iter(DBF(RUTAS["stock_pallets"]["loc"], encoding='latin1')))
        
        df_pa['CODIGO'] = df_pa['CODIGO'].astype(str).str.strip().str.upper()
        
        # --- EL ANTÍDOTO PARA EL ORIGEN 0 ---
        # Forzamos los pesos a números para poder evaluarlos matemáticamente
        if 'TUBOPALLET' in df_pa.columns:
            df_pa['TUBOPALLET'] = pd.to_numeric(df_pa['TUBOPALLET'], errors='coerce').fillna(0)
        if 'PESOPALLET' in df_pa.columns:
            df_pa['PESOPALLET'] = pd.to_numeric(df_pa['PESOPALLET'], errors='coerce').fillna(0)
            
        # Ordenamos: Los que tienen "0" van arriba, los que tienen datos reales van abajo.
        df_pa = df_pa.sort_values(by=['TUBOPALLET', 'PESOPALLET'])
        
        # Ahora el 'last' siempre va a ser el registro ganador con datos reales
        df_pa = df_pa.drop_duplicates(subset=['CODIGO'], keep='last')
        
        cols_pa = ['CODIGO', 'PESOTUBO', 'TUBOPALLET', 'PESOPALLET']
        df_pa = df_pa[[c for c in cols_pa if c in df_pa.columns]]

        # 3. FUSIÓN
        df_fused = pd.merge(df_ma, df_pa, on='CODIGO', how='left')

        # 4. LIMPIEZA Y TRADUCCIÓN DE ORIGEN
        if 'ORIGEN' in df_fused.columns:
            df_fused['ORIGEN'] = df_fused['ORIGEN'].astype(str).str.strip().replace(r'\.0$', '', regex=True)
            mapa_origen = {'1': 'Brasil', '2': 'China', '3': 'EE.UU.'}
            df_fused['ORIGEN'] = df_fused['ORIGEN'].map(lambda x: mapa_origen.get(x, x))
        else:
            df_fused['ORIGEN'] = "-"

        # 5. CÁLCULO DE PALLETS
        df_fused['TKGSTOCK'] = pd.to_numeric(df_fused['TKGSTOCK'], errors='coerce').fillna(0)
        df_fused['TUBOSSTOCK'] = pd.to_numeric(df_fused['TUBOSSTOCK'], errors='coerce').fillna(0)
        df_fused['TUBOPALLET'] = pd.to_numeric(df_fused['TUBOPALLET'], errors='coerce').fillna(0)
        df_fused['PESOTUBO'] = pd.to_numeric(df_fused['PESOTUBO'], errors='coerce').fillna(0)
        
        df_fused['CANT_PALLETS'] = df_fused.apply(
            lambda row: round(row['TUBOSSTOCK'] / row['TUBOPALLET'], 2) if row['TUBOPALLET'] > 0 else 0.0, 
            axis=1
        )
        
        return df_fused
    except Exception as e:
        st.error(f"Error en Fusión de Stock: {e}")
        return pd.DataFrame()

def guardar_analisis_lab(datos):
    conn = sqlite3.connect(RUTAS["lab"])
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO analisis_hidrolitica (
            nro_analisis, fecha, hora, responsable, maquina, horno, temperatura, cliente, medida, capacidad, cod, boca, 
            color, pared, impresion, tratado, lote_lumen, l_m_prima, batch, volumen, blanco, 
            titulacion, resultado_final, maximo, observaciones
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    ''', datos)
    conn.commit()
    conn.close()

# --- MOTORES LABORATORIO EXTRA ---
def limpiar_comercial(valor):
    if pd.isna(valor) or valor is None: return "-"
    v_str = str(valor).strip()
    if v_str.lower() in ['nan', 'none', '0.0', '0', '', '-']: return "-"
    try:
        return str(int(float(valor)))
    except:
        return v_str

def obtener_siguiente_nro_certificado(nro_analisis):
    conn = sqlite3.connect(RUTAS["lab"])
    cursor = conn.cursor()
    # BLINDAJE 1: Forzamos int() para que SQLite lo reconozca perfecto
    cursor.execute("SELECT nro_certificado FROM analisis_hidrolitica WHERE nro_analisis = ?", (int(nro_analisis),))
    res = cursor.fetchone()
    
    if res and res[0] is not None:
        nro_cert = int(res[0]) # Si ya tiene, devuelve ese
    else:
        # Casteamos a INTEGER por si en algún momento se guardó como texto
        cursor.execute("SELECT MAX(CAST(nro_certificado AS INTEGER)) FROM analisis_hidrolitica")
        max_res = cursor.fetchone()
        nro_cert = (int(max_res[0]) + 1) if max_res and max_res[0] is not None else 1000 
    conn.close()
    return nro_cert

def guardar_certificado_red(nro_analisis, nro_cert, pdf_bytes, nombre_archivo):
    try:
        conn = sqlite3.connect(RUTAS["lab"])
        cursor = conn.cursor()
        # BLINDAJE 2: Forzamos int() acá para asegurar que la base de datos reciba la orden
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
        # Ahora, si falla SQLite o la red, nos va a avisar con un mensaje rojo en la pantalla en vez de fallar en silencio
        st.session_state.msg_cert = f"❌ Error al guardar: {e}"

def registrar_analisis_legado(datos_manuales):
    fecha, responsable, cliente, cod, lote_lumen, resultado_final, maximo, observaciones = datos_manuales
    
    MAPEO_BOCAS = {"1": "Tapa Rosca", "2": "20 Normal", "3": "20 C/Anclaje", "4": "13 Normal", "5": "13 C/Anclaje", "6": "8 Normal", "7": "8 C/Anclaje", "8": "10 Normal", "9": "Tapa Rosca 9A", "10": "Tapa Rosca 9B", "11": "Tapa Rosca 10", "12": "Perfumero", "13": "Boca Spray", "14": "Tubo", "15": "Cuadrada"}
    MAPEO_COLOR = {"1": "Ambar", "2": "Incoloro", "AMBAR": "Ambar", "INCOLORO": "Incoloro"}
    
    medida, capacidad, color, boca, pared = "-", "-", "Ambar", "-", "-"
    maquina, impresion, l_m_prima, batch = "-", "SIN IMPRESION", "-", "-"
    
    # 1. RESCATE DEL CATÁLOGO (Rápido)
    conn_cat = sqlite3.connect(RUTAS["lab"], timeout=10)
    cursor_cat = conn_cat.cursor()
    try:
        cursor_cat.execute("SELECT D1, H1, CAPACIDAD, COLOR, BOCA, ESPESOR FROM catalogo_articulos WHERE CODPLA = ? OR CODIGO = ?", (cod, cod))
        cat = cursor_cat.fetchone()
        if cat:
            d1, h1 = str(cat[0]).strip() if cat[0] else "", str(cat[1]).strip() if cat[1] else ""
            medida = f"{d1} x {h1}" if d1 and h1 else "-"
            capacidad = str(cat[2]).strip() if cat[2] else "-"
            color = MAPEO_COLOR.get(str(cat[3]).strip().upper() if cat[3] else "", "Ambar")
            boca_bd = str(cat[4]).strip() if cat[4] else ""
            boca = MAPEO_BOCAS.get(boca_bd, boca_bd) if boca_bd else "-"
            pared = str(cat[5]).strip() if cat[5] else "-"
    finally:
        conn_cat.close()

    # 2. RESCATE DE PRODUCCIÓN (Tiempo de red)
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

    # 3. GUARDADO CON ID MANUAL
    conn = sqlite3.connect(RUTAS["lab"], timeout=15)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT MAX(nro_analisis) FROM analisis_hidrolitica")
        res_id = cursor.fetchone()
        nro_analisis_manual = (int(res_id[0]) + 1) if res_id and res_id[0] else 8077
        
        # ACÁ ESTABA EL ERROR: Decía nro_certificate 
        cursor.execute("SELECT MAX(CAST(nro_certificado AS INTEGER)) FROM analisis_hidrolitica")
        max_res = cursor.fetchone()
        nro_cert = (int(max_res[0]) + 1) if max_res and max_res[0] is not None else 1000 

        cursor.execute('''
            INSERT INTO analisis_hidrolitica (
                nro_analisis, fecha, responsable, cliente, cod, lote_lumen, resultado_final, maximo, observaciones,
                medida, capacidad, color, boca, pared, maquina, impresion, l_m_prima, batch, nro_certificado
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ''', (nro_analisis_manual, fecha, responsable, cliente, cod, lote_lumen, resultado_final, maximo, observaciones,
              medida, capacidad, color, boca, pared, maquina, impresion, l_m_prima, batch, nro_cert))
        
        conn.commit()
    except Exception as e:
        # Ahora, si llega a fallar, te avisa en la pantalla en lugar de hacerlo en silencio
        import streamlit as st
        st.error(f"Falla crítica al escribir en base de datos: {e}")
        nro_analisis_manual, nro_cert = 0, 0
    finally:
        conn.close()

    return nro_analisis_manual, nro_cert

# --- CALLBACKS ---
def autocompletar_frasco():
    MAPEO_BOCAS = {
                "1": "Tapa Rosca", "2": "20 Normal", "3": "20 C/Anclaje", "4": "13 Normal", "5": "13 C/Anclaje",
                "6": "8 Normal", "7": "8 C/Anclaje", "8": "10 Normal", "9": "Tapa Rosca 9A", "10": "Tapa Rosca 9B",
                "11": "Tapa Rosca 10", "12": "Perfumero", "13": "Boca Spray", "14": "Tubo", "15": "Cuadrada", "14": "N/Aplica"
            }
    cod_ingresado = st.session_state.t_cod.strip().upper()
    
    if cod_ingresado:
        conn = sqlite3.connect(RUTAS["lab"]) 
        cursor = conn.cursor()
        try: cursor.execute("ALTER TABLE catalogo_articulos ADD COLUMN MAXIMO TEXT")
        except: pass 
        
        try:
            cursor.execute('''
                SELECT D1, H1, CAPACIDAD, COLOR, BOCA, ESPESOR, CODIGOMP, MAXIMO 
                FROM catalogo_articulos WHERE CODPLA = ? OR CODIGO = ?
            ''', (cod_ingresado, cod_ingresado))
            registro = cursor.fetchone()
        except: registro = None
        finally: conn.close()

        if registro:
            d1 = str(registro[0]).strip() if registro[0] else ""
            h1 = str(registro[1]).strip() if registro[1] else ""
            st.session_state.t_med = f"{d1} x {h1}"
            st.session_state.t_cap = str(registro[2]).strip() if registro[2] else ""
            
            # Traductor inteligente de color
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
    cursor.execute('''
        UPDATE catalogo_articulos 
        SET CAPACIDAD = ?, COLOR = ?, BOCA = ?, ESPESOR = ?, CODIGOMP = ?, MAXIMO = ?
        WHERE CODIGO = ? OR CODPLA = ?
    ''', (capacidad, color, boca, espesor, codigomp, maximo, codigo, codigo))
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
            cursor.execute('''
                SELECT cliente, maquina, horno, medida, capacidad, cod, boca, color, pared, 
                       impresion, tratado, l_m_prima, batch, volumen, temperatura 
                FROM analisis_hidrolitica WHERE lote_lumen = ? ORDER BY nro_analisis DESC LIMIT 1
            ''', (lote_ingresado,))
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
                        
                        # LIMPIEZA DE Ñ Y CERO
                        if not st.session_state.get("t_med"): 
                            st.session_state.t_med = str(fila.get('MEDIDA', '')).strip().replace('ñ', '±').replace('Ñ', '±')
                        
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

# --- MOTOR GENERADOR DE PDF ---
def generar_certificado_pdf(fila, datos_extra):
    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.add_page()
    pdf.image('plantilla_certificado.jpg', x=0, y=0, w=210, h=297)
    pdf.set_font("helvetica", style="B", size=10)
    
    pdf.set_xy(x=30.7- 2.5, y=196.1- 4.75)
    pdf.cell(w=24.9, h=5, txt=str(fila['nro_analisis']), border=0, align='C')
    
    # Auto-ajuste para el nombre del Cliente (Por si escriben un nombre social muy largo)
    cliente_imprimir = str(datos_extra.get('cliente_editado', fila['cliente'])).upper()
    pdf.set_xy(x=72.8 - 2.5, y=50.5 - 4.75)
    tamano_fuente = 10
    pdf.set_font("helvetica", style="B", size=tamano_fuente)
    while pdf.get_string_width(cliente_imprimir) > 75 and tamano_fuente > 5:
        tamano_fuente -= 1
        pdf.set_font("helvetica", style="B", size=tamano_fuente)
    pdf.cell(w=76.5, h=7.2, txt=cliente_imprimir, border=0, align='C')
    pdf.set_font("helvetica", style="B", size=10) # Reseteamos a 10 para lo que sigue

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
    # Si hay capacidad le suma " ml", si está vacío pone un guión
    cap_texto = str(fila['capacidad']).strip() + " ml" if fila['capacidad'] and str(fila['capacidad']) != "None" else "- ml"
    pdf.cell(w=39.3, h=7.2, txt=cap_texto, border=0, align='C')
    
    # Impresion editada
    texto_impresion = str(datos_extra.get('impresion', fila['impresion'])).upper()
    pdf.set_xy(x=53.7- 2.5, y=110.51- 4.75)
    pdf.cell(w=58.11, h=7.2, txt=texto_impresion, border=0, align='C')
    
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
    # Auto-ajuste severo para la Orden de Compra
    oc_imprimir = str(datos_extra.get('oc', ''))
    pdf.set_xy(x=53.65- 2.5, y=65.15- 4.75)
    tamano_fuente_oc = 10
    pdf.set_font("helvetica", style="B", size=tamano_fuente_oc)
    # 35 es el ancho máximo de tu celda menos un margencito de seguridad
    while pdf.get_string_width(oc_imprimir) > 35 and tamano_fuente_oc > 5:
        tamano_fuente_oc -= 1
        pdf.set_font("helvetica", style="B", size=tamano_fuente_oc)
    pdf.cell(w=36.88, h=7.2, txt=oc_imprimir, border=0, align='C')
    pdf.set_font("helvetica", style="B", size=10) # Reseteamos a 10
    pdf.set_xy(x=53.65- 2.5, y=74.49- 4.75)
    pdf.cell(w=36.88, h=7.2, txt=str(datos_extra.get('np', '')), border=0, align='C') 
    pdf.set_xy(x=53.65- 2.5, y=83.71- 4.75)
    pdf.cell(w=36.88, h=7.2, txt=str(fila['cod']), border=0, align='C') 
    pdf.set_xy(x=172.65- 2.5, y=65.2- 4.75)
    pdf.cell(w=27, h=7.2, txt=str(datos_extra.get('fecha_vto', '')), border=0, align='C') 
    pdf.set_xy(x=12.3- 2.5, y=95.65- 4.75)
    pdf.cell(w=39.3, h=7.2, txt=str(datos_extra.get('cantidad', '')), border=0, align='C') 
    pdf.set_xy(x=53.7- 2.5, y=145.5- 4.75)
    
    # Limpiamos y forzamos a mayúscula solo para encontrar la X y cortar perfecto
    medida_val = str(fila['medida']).strip() if fila['medida'] and str(fila['medida']) != "None" else ""
    if medida_val and medida_val != "-":
        # .upper() convierte temporalmente la "x" en "X" para asegurar el corte
        diametro_texto = medida_val.upper().split('X')[0].strip() + " mm"
    else:
        diametro_texto = "- mm"
        
    pdf.cell(w=36.87, h=5, txt=diametro_texto, border=0, align='C')
    
    # Control de impresion dinámico
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

# --- INTERFAZ MODULAR DE LABORATORIO ---
def renderizar_modulo_laboratorio():
    st.header("🔬 Control de Calidad: Resistencia Hidrolítica")
    
    if 'exito_lab' not in st.session_state: st.session_state.exito_lab = False
    if st.session_state.exito_lab:
        st.success("✅ Análisis guardado exitosamente.")
        st.session_state.exito_lab = False 

    tab_lab1, tab_lab2, tab_lab3 = st.tabs(["📝 Nuevo Análisis", "📚 Historial y Certificados", "🌡️ Registros Temperatura"])

    with tab_lab1:
        nro_actual = obtener_siguiente_nro_analisis()
        st.markdown(f"### Análisis Nro: **{nro_actual}**")
        
        def accion_guardar():
            ahora = datetime.datetime.now()
            v = st.session_state.lab_vol
            b = st.session_state.n_bla
            t = st.session_state.n_tit
            res = (t - b) * 2 if v == "50%" else (t - b)
            
            datos = (
                nro_actual, ahora.strftime("%Y-%m-%d"), ahora.strftime("%H:%M:%S"),
                st.session_state.lab_resp, st.session_state.lab_maq, st.session_state.lab_hor,
                st.session_state.lab_temp, st.session_state.t_cli, st.session_state.t_med, st.session_state.t_cap, st.session_state.t_cod, 
                st.session_state.lab_boc, st.session_state.lab_col, st.session_state.lab_par, 
                st.session_state.t_imp, st.session_state.lab_trat, st.session_state.t_lote, 
                st.session_state.t_lmp, st.session_state.t_batch, v, b, t, res, st.session_state.t_max, st.session_state.t_obs
            )
            guardar_analisis_lab(datos)
            cod_mp_oculto = st.session_state.get('hidden_cod_mp', '')
            enriquecer_catalogo_articulos(
                st.session_state.t_cod, st.session_state.t_cap, st.session_state.lab_col, 
                st.session_state.lab_boc, st.session_state.lab_par, cod_mp_oculto, st.session_state.t_max
            )   
            
            claves_texto = ["t_cli", "t_lote", "t_med", "t_cap", "t_lmp", "t_cod", "t_batch", "t_imp", "t_obs","lab_temp"]
            for k in claves_texto: st.session_state[k] = ""
            for k in ["n_bla", "n_tit", "t_max"]: st.session_state[k] = 0.0
            st.session_state.exito_lab = True

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            resp = st.selectbox("Responsable", RESPONSABLES, key="lab_resp")
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
        
        if "t_max" in st.session_state:
            try: st.session_state["t_max"] = float(str(st.session_state["t_max"]).replace(',', '.'))
            except: st.session_state["t_max"] = 0.0
        else: st.session_state["t_max"] = 0.0
        
        with c_tit3: maximo = st.number_input("Máximo Permitido", min_value=0.0, step=0.01, format="%.2f", key="t_max")
        
        resultado_calc = (titulacion - blanco) * 2 if vol == "50%" else (titulacion - blanco)
            
        with c_tit4:
            if maximo > 0 and resultado_calc > maximo: st.error(f"RESULTADO: {resultado_calc:.2f} (RECHAZADO)")
            else: st.success(f"RESULTADO: {resultado_calc:.2f} (OK)")

        obs = st.text_area("Observaciones", key="t_obs")
        st.button("💾 Guardar Análisis", use_container_width=True, type="primary", on_click=accion_guardar)

    with tab_lab2:
        # --- MODO LEGADO (HISTÓRICO) ---
        with st.expander("⏱️ Cargar Análisis Histórico (Papel a Digital)"):
            st.info("Digitalice un análisis antiguo para asignarle un número de certificado oficial.")
            c_leg1, c_leg2, c_leg3 = st.columns(3)
            with c_leg1:
                leg_lote = st.text_input("Lote Lumen", key="leg_lote")
                leg_cod = st.text_input("Cod. Frasco", key="leg_cod")
                leg_cli = st.text_input("Cliente", key="leg_cli")
            with c_leg2:
                leg_fec = st.date_input("Fecha Original")
                leg_resp = st.selectbox("Analista", RESPONSABLES, key="leg_resp")
            with c_leg3:
                leg_res = st.number_input("Resultado Final", format="%.2f", key="leg_res")
                leg_max = st.number_input("Máximo", format="%.2f", key="leg_max")
                
            if st.button("💾 Asignar Nro. de Certificado", type="primary"):
                datos = (leg_fec.strftime("%Y-%m-%d"), leg_resp, leg_cli, leg_cod, leg_lote, leg_res, leg_max, "CARGA HISTÓRICA")
                id_nuevo, cert_nuevo = registrar_analisis_legado(datos)
                st.success(f"✅ Digitalizado. Nro. de Certificado asignado: {cert_nuevo}. Búsquelo abajo para imprimir.")

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
        else:
            st.info("Aún no hay registros en la base.")

    with tab_lab3:
        st.markdown("### 🌡️ Registro de Temperatura Ambiente")
        col_t1, col_t2, col_t3 = st.columns(3)
        with col_t1: temp_resp = st.selectbox("Firma/Rúbrica", RESPONSABLES, key="t_resp")
        with col_t2: temp_valor = st.number_input("Temperatura (°C)", min_value=0.0, max_value=50.0, step=0.1, format="%.1f", key="t_val")
        with col_t3: temp_verif = st.text_input("Verificación / Observaciones", key="t_verif", placeholder="Ej: OK")

        if st.button("💾 Guardar Temperatura", type="primary"):
            ahora = datetime.datetime.now()
            guardar_temperatura((ahora.strftime("%Y-%m-%d"), ahora.strftime("%H:%M:%S"), temp_valor, temp_resp, temp_verif))
            st.success(f"✅ Temperatura registrada.")

        st.markdown("---")
        df_temp = cargar_historial_temperatura()
        if not df_temp.empty:
            df_temp_mostrar = df_temp.rename(columns={'fecha': 'DÍA', 'hora': 'HORARIO', 'temperatura': 'TEMPERATURA (°C)', 'responsable': 'FIRMA / RÚBRICA', 'verificacion': 'VERIFICACIÓN'})
            st.dataframe(df_temp_mostrar.drop(columns=['id']), use_container_width=True)

# ==========================================
# GESTOR DE PERFILES Y RUTEO DE PANTALLAS
# ==========================================
st.sidebar.markdown("### 👤 Perfil de Acceso")
perfil = st.sidebar.radio("Seleccione Área:", ["Laboratorio", "Administrador"])

if perfil == "Administrador":
    st.sidebar.markdown("---")
    clave = st.sidebar.text_input("🔑 Contraseña:", type="password")
    
    if clave == "admin123":
        st.title("🏭 Nuevo Sistema Lumen Glass")
        tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["🕒 ASISTENCIA", "🚻 BAÑO", "☕ DESCANSO", "🔬 LABORATORIO", "📦 PEDIDOS", "🏭 PRODUCCIÓN", "📦 MATERIA PRIMA"])
        hoy = datetime.date.today()
        datos_maestros = cargar_asistencia()
        
        with tab1:
            if datos_maestros.empty: st.error("No se pudo conectar a la base de Asistencia.")
            else:
                st.markdown("### 🔍 Filtros")
                ca1, ca2, ca3 = st.columns(3)
                with ca1: leg_a = st.number_input("Nº Legajo", min_value=0, value=0, step=1, key="leg_a")
                with ca2: nom_a = st.text_input("Buscar Nombre", key="nom_a")
                with ca3: rang_a = st.date_input("Rango de Fechas", value=(hoy, hoy), key="fec_a")

                df_a = datos_maestros[['LEGAJO', 'NOMBRE', 'FECHA', 'HORAI', 'HORAE', 'TOTAL_HS']].copy()
                if leg_a > 0: df_a = df_a[df_a['LEGAJO'] == leg_a]
                if nom_a: df_a = df_a[df_a['NOMBRE'].str.upper().str.contains(nom_a.upper(), na=False)]
                if len(rang_a) == 2: df_a = df_a[(df_a['FECHA'] >= rang_a[0]) & (df_a['FECHA'] <= rang_a[1])]
                elif len(rang_a) == 1: df_a = df_a[df_a['FECHA'] == rang_a[0]]

                st.bar_chart(data=df_a.groupby('FECHA')['TOTAL_HS'].sum().reset_index(), x='FECHA', y='TOTAL_HS')
                st.dataframe(df_a, use_container_width=True)
                
                col_est1, col_est2 = st.columns(2)
                with col_est1: st.metric(label="🚩 Total de Faltas (Días con 0 hs)", value=len(df_a[df_a['TOTAL_HS'] == 0]))
                with col_est2: st.metric(label="⏱️ Horas Trabajadas (Total)", value=round(df_a['TOTAL_HS'].sum(), 2))
                st.download_button("📥 Exportar Asistencia", df_a.to_csv(index=False, sep=';').encode('utf-8-sig'), "asistencia.csv", "text/csv")

        with tab2:
            datos_b = cargar_bano()
            if datos_b.empty: st.error("No se pudo conectar a la base de Baño.")
            else:
                cb1, cb2, cb3 = st.columns(3)
                with cb1: leg_b = st.number_input("Nº Legajo", min_value=0, value=0, step=1, key="leg_b")
                with cb2: nom_b = st.text_input("Buscar Nombre", key="nom_b")
                with cb3: rang_b = st.date_input("Rango de Fechas", value=(hoy, hoy), key="fec_b")

                df_b = datos_b.copy()
                if leg_b > 0: df_b = df_b[df_b['LEGAJO'] == leg_b]
                if nom_b: df_b = df_b[df_b['NOMBRE'].str.upper().str.contains(nom_b.upper(), na=False)]
                if len(rang_b) == 2: df_b = df_b[(df_b['FECHA'] >= rang_b[0]) & (df_b['FECHA'] <= rang_b[1])]
                elif len(rang_b) == 1: df_b = df_b[df_b['FECHA'] == rang_b[0]]

                col_g1, col_g2 = st.columns(2)
                with col_g1: st.bar_chart(data=df_b.groupby('FECHA')['MIN_TOTALES'].sum().reset_index(), x='FECHA', y='MIN_TOTALES')
                with col_g2: st.bar_chart(data=df_b.groupby('FECHA')['CANT_VECES'].sum().reset_index(), x='FECHA', y='CANT_VECES')

                st.dataframe(df_b, use_container_width=True)
                st.download_button("📥 Exportar Baño", df_b.to_csv(index=False, sep=';').encode('utf-8-sig'), "bano.csv", "text/csv")

        with tab3:
            if datos_maestros.empty: st.error("Esperando datos base...")
            else:
                cd1, cd2, cd3 = st.columns(3)
                with cd1: leg_d = st.number_input("Nº Legajo", min_value=0, value=0, step=1, key="leg_d")
                with cd2: nom_d = st.text_input("Buscar Nombre", key="nom_d")
                with cd3: rang_d = st.date_input("Rango de Fechas", value=(hoy, hoy), key="fec_d")

                df_d = datos_maestros[['LEGAJO', 'NOMBRE', 'FECHA', 'SALIDA_DESC', 'VUELTA_DESC', 'MIN_DESCANSO', 'DETALLE_DESCANSO']].copy()
                if leg_d > 0: df_d = df_d[df_d['LEGAJO'] == leg_d]
                if nom_d: df_d = df_d[df_d['NOMBRE'].str.upper().str.contains(nom_d.upper(), na=False)]
                if len(rang_d) == 2: df_d = df_d[(df_d['FECHA'] >= rang_d[0]) & (df_d['FECHA'] <= rang_d[1])]
                elif len(rang_d) == 1: df_d = df_d[df_d['FECHA'] == rang_d[0]]

                st.bar_chart(data=df_d.groupby('FECHA')['MIN_DESCANSO'].sum().reset_index(), x='FECHA', y='MIN_DESCANSO')
                st.dataframe(df_d, use_container_width=True)
                st.download_button("📥 Exportar Descanso", df_d.to_csv(index=False, sep=';').encode('utf-8-sig'), "descanso.csv", "text/csv")

        with tab4: renderizar_modulo_laboratorio()
        
        with tab5:
            st.markdown("### 📦 Seguimiento de Pedidos (Administración)")
            df_pedidos = cargar_pedidos_completos()
            if df_pedidos.empty: st.warning("No se encontraron datos.")
            else:
                col_p1, col_p2, col_p3 = st.columns(3)
                with col_p1: busq_np = st.text_input("Nota de Pedido / OC", key="busq_np")
                with col_p2: busq_cli = st.text_input("Cliente", key="busq_cli_ped")
                with col_p3: busq_cod = st.text_input("Código de Frasco", key="busq_cod_ped")
                
                df_mostrar = df_pedidos.copy()
                if busq_np: df_mostrar = df_mostrar[df_mostrar['NOTA_PEDIDO'].astype(str).str.contains(busq_np, case=False) | df_mostrar['ORDEN_COMPRA'].astype(str).str.contains(busq_np, case=False)]
                if busq_cli: df_mostrar = df_mostrar[df_mostrar['CLIENTE'].astype(str).str.contains(busq_cli, case=False, na=False)]
                if busq_cod: df_mostrar = df_mostrar[df_mostrar['COD_FRASCO'].astype(str).str.contains(busq_cod, case=False, na=False)]
                
                st.dataframe(df_mostrar.head(1000), use_container_width=True)
                st.download_button("📥 Exportar a Excel", df_mostrar.head(5000).to_csv(index=False, sep=';').encode('utf-8-sig'), "pedidos.csv", "text/csv")

        with tab6:
            st.markdown("### 🏭 Seguimiento de Órdenes de Producción")
            df_prod = cargar_produccion()
            
            if df_prod.empty:
                st.warning("No se encontraron datos de producción o no se pudo acceder a la base.")
            else:
                # --- LIMPIEZA VISUAL PARA LA PANTALLA ---
                # Limpiamos los ".0" y los "nan" para que la tabla se vea 100% profesional
                columnas_a_limpiar = ['LOTE_LUMEN', 'NOTA_PEDIDO', 'ORDEN_COMPRA', 'CANTIDAD', 'MAQUINA', 'BOCA']
                for col in columnas_a_limpiar:
                    if col in df_prod.columns:
                        df_prod[col] = df_prod[col].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
                        df_prod[col] = df_prod[col].replace(['nan', 'None', ''], '-')

                # Forzamos que el Lote sea numérico temporalmente solo para ordenarlo de mayor a menor (los más nuevos arriba)
                df_prod['lote_num'] = pd.to_numeric(df_prod['LOTE_LUMEN'], errors='coerce')
                df_prod = df_prod.sort_values(by='lote_num', ascending=False).drop(columns=['lote_num'])

                # --- FILTROS DE BÚSQUEDA ---
                col_pr1, col_pr2, col_pr3, col_pr4 = st.columns(4)
                with col_pr1: busq_lote_pr = st.text_input("Buscar por Lote Lumen", key="busq_lote_pr")
                with col_pr2: busq_cli_pr = st.text_input("Buscar por Cliente", key="busq_cli_pr")
                with col_pr3: busq_maq_pr = st.text_input("Filtrar por Máquina (Ej: F1)", key="busq_maq_pr")
                with col_pr4: busq_np_pr = st.text_input("Buscar Nota de Pedido", key="busq_np_pr")

                df_mostrar_pr = df_prod.copy()
                
                # Aplicamos los filtros si el usuario escribió algo
                if busq_lote_pr: 
                    df_mostrar_pr = df_mostrar_pr[df_mostrar_pr['LOTE_LUMEN'].astype(str).str.contains(busq_lote_pr, case=False, na=False)]
                if busq_cli_pr: 
                    df_mostrar_pr = df_mostrar_pr[df_mostrar_pr['CLIENTE'].astype(str).str.contains(busq_cli_pr, case=False, na=False)]
                if busq_maq_pr: 
                    # Búsqueda exacta para la máquina (para que F1 no traiga F10)
                    df_mostrar_pr = df_mostrar_pr[df_mostrar_pr['MAQUINA'].astype(str).str.upper() == busq_maq_pr.upper()]
                if busq_np_pr: 
                    df_mostrar_pr = df_mostrar_pr[df_mostrar_pr['NOTA_PEDIDO'].astype(str).str.contains(busq_np_pr, case=False, na=False)]

                # Mostramos la tabla y el botón de exportar
                st.dataframe(df_mostrar_pr.head(1000), use_container_width=True)
                
                st.download_button(
                    label="📥 Exportar Producción a Excel", 
                    data=df_mostrar_pr.head(5000).to_csv(index=False, sep=';').encode('utf-8-sig'), 
                    file_name="ordenes_produccion.csv", 
                    mime="text/csv"
                )

        with tab7:
            st.markdown("### 📦 Inventario de Materia Prima (Año 2026)")
            df_st = cargar_stock_fusionado()
            
            if df_st.empty:
                st.warning("No hay datos de stock disponibles.")
            else:
                # --- FILTROS ---
                cs1, cs2, cs3 = st.columns(3)
                with cs1: b_cod = st.text_input("🔍 Buscar Código", key="st_b_cod")
                with cs2: b_desc = st.text_input("📝 Buscar por Descripción", key="st_b_desc")
                with cs3: 
                    origenes_disp = ["Todos"] + sorted([o for o in df_st['ORIGEN'].unique() if o not in ["-", "nan", ""]])
                    b_ori = st.selectbox("🌍 Filtrar por Origen", origenes_disp, key="st_b_ori")
                
                # Aplicar Filtros
                df_st_f = df_st.copy()
                if b_cod: df_st_f = df_st_f[df_st_f['CODIGO'].str.contains(b_cod.upper(), case=False)]
                if b_desc: df_st_f = df_st_f[df_st_f['DESCRIP'].str.contains(b_desc.upper(), case=False)]
                if b_ori != "Todos": df_st_f = df_st_f[df_st_f['ORIGEN'] == b_ori]

                # --- REORDENAMIENTO DE COLUMNAS (Prioridad: Código y Descrip) ---
                columnas_deseadas = [
                    'CODIGO', 'DESCRIP', 'ORIGEN', 'TKGSTOCK', 
                    'TUBOSSTOCK', 'CANT_PALLETS', 'TUBOPALLET', 'PESOTUBO'
                ]
                columnas_finales = [c for c in columnas_deseadas if c in df_st_f.columns]
                columnas_resto = [c for c in df_st_f.columns if c not in columnas_finales]
                df_st_f = df_st_f[columnas_finales + columnas_resto]

                # --- MÉTRICAS DE RESUMEN ---
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Kilos Totales", f"{df_st_f['TKGSTOCK'].sum():,.2f} kg")
                m2.metric("Unidades de Tubos", f"{int(df_st_f['TUBOSSTOCK'].sum()):,}")
                m3.metric("Pallets Totales", f"{df_st_f['CANT_PALLETS'].sum():,.2f}")
                m4.metric("Códigos", len(df_st_f))

                # --- VISTA DE TABLA ---
                # Renombramos para la vista de usuario
                df_vista = df_st_f.rename(columns={
                    'CODIGO': 'CÓDIGO', 'DESCRIP': 'DESCRIPCIÓN', 'ORIGEN': 'ORIGEN',
                    'TKGSTOCK': 'STOCK (KG)', 'TUBOSSTOCK': 'STOCK (TUBOS)',
                    'CANT_PALLETS': 'PALLETS', 'TUBOPALLET': 'TUB/PALLET', 'PESOTUBO': 'PESO/TUBO'
                })
                
                st.dataframe(df_vista, use_container_width=True, hide_index=True)

                # --- BOTÓN DE EXPORTACIÓN A EXCEL (CSV optimizado) ---
                st.markdown("---")
                fecha_hoy = datetime.datetime.now().strftime("%Y-%m-%d")
                
                # Preparamos el archivo para descarga
                # utf-8-sig añade el BOM para que Excel detecte los acentos automáticamente
                csv_data = df_vista.to_csv(index=False, sep=';', encoding='utf-8-sig').encode('utf-8-sig')
                
                st.download_button(
                    label="📥 DESCARGAR INFORME PARA DIRECCIÓN (EXCEL)",
                    data=csv_data,
                    file_name=f"Informe_Stock_Materia_Prima_{fecha_hoy}.csv",
                    mime="text/csv",
                    use_container_width=True
                )

    elif clave != "": st.sidebar.error("Contraseña incorrecta")
    else: st.warning("🔒 Ingrese la contraseña en el menú lateral.")

elif perfil == "Laboratorio":
    renderizar_modulo_laboratorio()

st.sidebar.markdown("---")
st.sidebar.markdown("### ⚙️ Sistema")
if st.sidebar.button("🔄 Sincronizar Todo"):
    st.cache_data.clear()
    st.rerun()