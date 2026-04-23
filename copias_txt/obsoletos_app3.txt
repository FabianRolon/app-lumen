import streamlit as st
import pandas as pd
from dbfread import DBF
import datetime
import os
import shutil
import sqlite3
from fpdf import FPDF
import io

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Sistema LumenGlass 4.1", layout="wide")

RUTAS = {
    "asist": {"red": r'C:\Reloj\Bases\ASIGTURN.DBF', "loc": r'C:\proyecto_Asistencia\asistencia_temp.dbf'},
    "bano": {"red": r'\\CALIDAD\Bases\BANODBF.dbf', "loc": r'C:\proyecto_Asistencia\bano_temp.dbf'},
    "lab": r'C:\proyecto_Asistencia\laboratorio.db',
    "pedidos": {"red": r'\\LUMENGLASS\Sistemas\Bases\REMENCA.dbf', "loc": r'C:\proyecto_Asistencia\remenca_temp.dbf'},
    "remitos": {"red": r'\\LUMENGLASS\Sistemas\Bases\REMITOS.dbf', "loc": r'C:\proyecto_Asistencia\remitos_temp.dbf'},
    "produccion": {"red": r'\\LUMENGLASS\Sistemas\Bases\ORDPRODU.dbf', "loc": r'C:\proyecto_Asistencia\ordprodu_temp.dbf'},
    "maestro_clientes": {"red": r'\\LUMENGLASS\Sistemas\Bases\CLIENTES.dbf', "loc": r'C:\proyecto_Asistencia\clientes_temp.dbf'}
}

RESPONSABLES = ["Nahuel Ayala", "Hernan Spataro", "Fabian Rolon"]
BOCAS = ["Tapa Rosca","20 Normal","20 C/Anclaje","13 Normal","13 C/Anclaje","8 Normal","8 C/Anclaje","10 Normal","Tapa Rosca 9A","Tapa Rosca 9B","Tapa Rosca 10","Perfumero","Boca Spray","Tubo","Cuadrada","N/Aplica"]
#PAREDES = ["0.5", "0.75", "0.80", "0.90", "1.00", "1.10", "1.20"]
MAQUINAS = ["F1", "F2", "F3", "F4"]
HORNOS = ["H1", "H2", "H3", "H4", "H5"]

# --- INICIALIZADOR DE BASE DE DATOS (AUTO-REPARACIÓN) ---
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
    
    # Trucos para agregar las columnas a la base que ya existe sin borrar datos
    try:
        cursor.execute("ALTER TABLE analisis_hidrolitica ADD COLUMN capacidad TEXT")
    except:
        pass 
    try:
        # EL NUEVO PARCHE PARA LA TEMPERATURA
        cursor.execute("ALTER TABLE analisis_hidrolitica ADD COLUMN temperatura TEXT")
    except:
        pass

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS registro_temperatura (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT,
                hora TEXT,
                temperatura REAL,
                responsable TEXT,
                verificacion TEXT
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
        # --- 1. PROCESO DE COPIADO ---
        for r in ["pedidos", "remitos"]:
            shutil.copy2(RUTAS[r]["red"], RUTAS[r]["loc"])
            base_r = os.path.splitext(RUTAS[r]["red"])[0]
            base_l = os.path.splitext(RUTAS[r]["loc"])[0]
            for ext in ['.FPT', '.fpt', '.DBT', '.dbt']:
                if os.path.exists(base_r + ext): shutil.copy2(base_r + ext, base_l + ext)
            
        # --- 2. LECTURA Y LIMPIEZA ---
        df_enc = pd.DataFrame(iter(DBF(RUTAS["pedidos"]["loc"], encoding='latin1', ignore_missing_memofile=True)))
        cols_enc = {'REMITO': 'NOTA_PEDIDO', 'NOMBRE': 'CLIENTE', 'ORDEN': 'ORDEN_COMPRA', 'FECENTRE': 'FECHA_ENTREGA', 'FECHA': 'FECHA_EMISION'}
        df_enc = df_enc[[c for c in cols_enc.keys() if c in df_enc.columns]].rename(columns=cols_enc)

        df_det = pd.DataFrame(iter(DBF(RUTAS["remitos"]["loc"], encoding='latin1', ignore_missing_memofile=True)))
        cols_det = {'REMITO': 'NOTA_PEDIDO', 'CODIGO': 'COD_FRASCO', 'DESCRIP': 'DESCRIPCION', 'CANTIDAD': 'CANTIDAD', 'UNIDAD': 'UNIDAD'}
        df_det = df_det[[c for c in cols_det.keys() if c in df_det.columns]].rename(columns=cols_det)

        # --- 3. FUSIÓN Y ORDENAMIENTO (EL CAMBIO CLAVE) ---
        # Aseguramos que la Nota de Pedido sea texto para el cruce
        df_enc['NOTA_PEDIDO'] = df_enc['NOTA_PEDIDO'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
        df_det['NOTA_PEDIDO'] = df_det['NOTA_PEDIDO'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

        df_completo = pd.merge(df_det, df_enc, on='NOTA_PEDIDO', how='left')

        # Convertimos FECHA_EMISION a formato fecha real para ordenar bien
        df_completo['FECHA_EMISION'] = pd.to_datetime(df_completo['FECHA_EMISION'], errors='coerce')
        
        # Ordenamos por FECHA_EMISION descendente (lo más nuevo primero)
        # Si la fecha es igual, ordena por número de nota de pedido
        df_completo = df_completo.sort_values(by=['FECHA_EMISION', 'NOTA_PEDIDO'], ascending=[False, False])

        # Formateamos la fecha para que se vea linda (DD/MM/AAAA) después de haber ordenado
        df_completo['FECHA_EMISION'] = df_completo['FECHA_EMISION'].dt.strftime('%d/%m/%Y')

        return df_completo
        
    except Exception as e:
        st.error(f"Error al cargar pedidos: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300) 
def cargar_produccion():
    if not os.path.exists(RUTAS["produccion"]["red"]): return pd.DataFrame()
    try:
        # ... (código de copiado de ORDPRODU que ya tenés) ...
        shutil.copy2(RUTAS["produccion"]["red"], RUTAS["produccion"]["loc"])
        df = pd.DataFrame(iter(DBF(RUTAS["produccion"]["loc"], encoding='latin1', ignore_missing_memofile=True)))
        
        # Traductor de columnas comerciales
        df = df.rename(columns={'LOTE': 'LOTE_LUMEN', 'PEDIDO': 'NOTA_PEDIDO', 'ORDEN': 'ORDEN_COMPRA', 'CANTPEDIDA': 'CANTIDAD', 'FECENTREGA': 'FECHA_ENTREGA'})

        # --- AQUÍ LA EFICIENCIA ---
        df_maestro = cargar_maestro_clientes()
        if not df_maestro.empty:
            # Limpiamos la columna CLIENTE de producción para asegurar el cruce
            df['CLIENTE'] = df['CLIENTE'].astype(str).str.strip()
            # Cruzamos: trae NOMBRE_REAL donde el código coincida
            df = pd.merge(df, df_maestro, on='CLIENTE', how='left')
            # Reemplazamos el código por el nombre real (si existe el nombre)
            df['CLIENTE'] = df['NOMBRE_REAL'].fillna(df['CLIENTE'])
            df = df.drop(columns=['NOMBRE_REAL']) # Borramos la columna auxiliar

        # Limpieza final de strings
        for col in df.select_dtypes(include=['object']):
            df[col] = df[col].astype(str).str.strip()
            
        return df
    except Exception as e:
        st.error(f"Error en cruce de clientes: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=600) # Cache de 10 minutos
def cargar_maestro_clientes():
    if not os.path.exists(RUTAS["maestro_clientes"]["red"]): return pd.DataFrame()
    try:
        shutil.copy2(RUTAS["maestro_clientes"]["red"], RUTAS["maestro_clientes"]["loc"])
        # Copiamos mochila si existe
        base_r = os.path.splitext(RUTAS["maestro_clientes"]["red"])[0]
        base_l = os.path.splitext(RUTAS["maestro_clientes"]["loc"])[0]
        for ext in ['.FPT', '.fpt']:
            if os.path.exists(base_r + ext): shutil.copy2(base_r + ext, base_l + ext)

        df = pd.DataFrame(iter(DBF(RUTAS["maestro_clientes"]["loc"], encoding='latin1', ignore_missing_memofile=True)))
        
        # Ajustá estos nombres según lo que diga tu DBF de clientes
        cols = {'CODIGO': 'CLIENTE', 'NOMBRE': 'NOMBRE_REAL'} 
        df = df[[c for c in cols.keys() if c in df.columns]].rename(columns=cols)
        
        # Limpieza de espacios
        for col in df.columns:
            df[col] = df[col].astype(str).str.strip()
        return df
    except:
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

    # --- CALLBACK: AUTOCOMPLETAR FRASCO ---
# --- CALLBACK: AUTOCOMPLETAR DESDE LA BASE MIGRADA (Tabla: catalogo_articulos) ---
def autocompletar_frasco():
    MAPEO_BOCAS = {
                "1": "Tapa Rosca",
                "2": "20 Normal",
                "3": "20 C/Anclaje",
                "4": "13 Normal",
                "5": "13 C/Anclaje",
                "6": "8 Normal",
                "7": "8 C/Anclaje",
                "8": "10 Normal",
                "9": "Tapa Rosca 9A",
                "10": "Tapa Rosca 9B",
                "11": "Tapa Rosca 10",
                "12": "Perfumero",
                "13": "Boca Spray",
                "14": "Tubo",
                "15": "Cuadrada",
                "14": "N/Aplica"
            }
    cod_ingresado = st.session_state.t_cod.strip().upper()
    
    if cod_ingresado:
        conn = sqlite3.connect(RUTAS["lab"]) 
        cursor = conn.cursor()
        
        try:
            cursor.execute("ALTER TABLE catalogo_articulos ADD COLUMN MAXIMO TEXT")
        except:
            pass # Si ya existe, pasa de largo
        
        try:
            # Buscamos en 'catalogo_articulos' pero pedimos las columnas de los planos
            cursor.execute('''
                SELECT D1, H1, CAPACIDAD, COLOR, BOCA, ESPESOR, CODIGOMP, MAXIMO 
                FROM catalogo_articulos 
                WHERE CODPLA = ? OR CODIGO = ?
            ''', (cod_ingresado, cod_ingresado))
            registro = cursor.fetchone()
        except Exception as e:
            registro = None
        finally:
            conn.close()

        if registro:
            # Desempaquetamos los datos
            # registro = (D1, H1, CAPACIDAD, COLOR, BOCA, ESPESOR)
            
            # 1. Armamos la 'Medida' juntando D1 (Diámetro) y H1 (Alto)
            d1 = str(registro[0]).strip() if registro[0] else ""
            h1 = str(registro[1]).strip() if registro[1] else ""
            st.session_state.t_med = f"{d1} x {h1}"
            
            # 2. Capacidad
            st.session_state.t_cap = str(registro[2]).strip() if registro[2] else ""
            
            # 3. Color del vidrio (con traductor inteligente y anti-fantasmas)
            MAPEO_COLOR = {
                "1": "Ambar", 
                "1.0": "Ambar",  # <-- Atrapamos el 1 con decimal
                "2": "Incoloro",
                "2.0": "Incoloro", # <-- Atrapamos el 2 con decimal
                "AMBAR": "Ambar",
                "INCOLORO": "Incoloro"
            }
            # Eliminamos cualquier espacio raro y lo pasamos a mayúsculas
            color_bd = str(registro[3]).strip().upper() if registro[3] else ""
            
            # Buscamos en el diccionario, si no encuentra nada raro, pone Ambar
            st.session_state.lab_col = MAPEO_COLOR.get(color_bd, "Ambar")
            
            # Si el dato está en el diccionario, lo traduce. Si no (ej: si está vacío), por defecto pone "Ambar".
            st.session_state.lab_col = MAPEO_COLOR.get(color_bd, "Ambar")
            
            # 4. Tipo de Boca
            codigo_boca_bd = str(registro[4]).strip() if registro[4] else ""
            st.session_state.lab_boc = MAPEO_BOCAS.get(codigo_boca_bd, codigo_boca_bd)

            # 5. Pared (Espesor)
            st.session_state.lab_par = str(registro[5]).strip() if registro[5] else ""

            # 6. Código de Materia Prima (SILENCIOSO: va a la mochila, no a la pantalla)
            st.session_state.hidden_cod_mp = str(registro[6]).strip() if registro[6] else ""

            # 7. Máximo Permitido (¡NUEVO!)
            try:
                # Intentamos convertir el dato de la BD a decimal
                valor_maximo = float(registro[7]) if registro[7] else 0.0
            except (ValueError, TypeError):
                # Si viene con basura o letras, le ponemos 0.0 por seguridad
                valor_maximo = 0.0
            st.session_state.t_max = str(registro[7]).strip() if registro[7] else ""

def enriquecer_catalogo_articulos(codigo, capacidad, color, boca, espesor, codigomp, maximo):
    conn = sqlite3.connect(RUTAS["lab"])
    cursor = conn.cursor()
    
    # 1. Truco: Creamos la columna MAXIMO en el catálogo si es que todavía no existe
    try:
        cursor.execute("ALTER TABLE catalogo_articulos ADD COLUMN MAXIMO TEXT")
    except:
        pass # Si la columna ya existe, pasa de largo sin chistar
    
    # 2. Pisamos los datos del catálogo con lo nuevo que aprendimos, sumando el MAXIMO
    cursor.execute('''
        UPDATE catalogo_articulos 
        SET CAPACIDAD = ?, COLOR = ?, BOCA = ?, ESPESOR = ?, CODIGOMP = ?, MAXIMO = ?
        WHERE CODIGO = ? OR CODPLA = ?
    ''', (capacidad, color, boca, espesor, codigomp, maximo, codigo, codigo))
    
    conn.commit()
    conn.close()

# --- CALLBACK: AUTOCOMPLETAR POR LOTE HISTÓRICO ---
def autocompletar_por_lote():
    lote_ingresado = st.session_state.t_lote.strip()
    
    if lote_ingresado:
        # 1. PASO A: BUSCAMOS EN EL HISTORIAL DE LABORATORIO (Prioridad 1 - Base Histórica)
        conn = sqlite3.connect(RUTAS["lab"])
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT cliente, maquina, horno, medida, capacidad, cod, boca, color, pared, 
                       impresion, tratado, l_m_prima, batch, volumen, temperatura 
                FROM analisis_hidrolitica 
                WHERE lote_lumen = ? 
                ORDER BY nro_analisis DESC LIMIT 1
            ''', (lote_ingresado,))
            registro = cursor.fetchone()

            if registro:
                # Si es un lote viejo, sobreescribimos todo porque el historial del laboratorio es la verdad absoluta
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
                
                # Buscamos también el máximo en el catálogo
                codigo_frasco = registro[5]
                if codigo_frasco:
                    cursor.execute("SELECT MAXIMO FROM catalogo_articulos WHERE CODIGO = ?", (codigo_frasco,))
                    res_max = cursor.fetchone()
                    if res_max and res_max[0]:
                        st.session_state.t_max = res_max[0]
            
            else:
                # 2. PASO B: PRODUCCIÓN (Prioridad 2 - Lotes Nuevos)
                df_p = cargar_produccion()
                
                if not df_p.empty:
                    # Aplicamos el filtro a prueba de ".0"
                    lotes_limpios = df_p['LOTE_LUMEN'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
                    datos_p = df_p[lotes_limpios == lote_ingresado]
                    
                    if not datos_p.empty:
                        fila = datos_p.iloc[0]
                        
                        # --- LA NUEVA MAGIA: RELLENADO CONDICIONAL ---
                        # Solo escribimos si el campo en la pantalla está vacío ("")
                        
                        if not st.session_state.get("t_cli"): 
                            st.session_state.t_cli = str(fila.get('CLIENTE', '')).strip()
                            
                        # Si el código de frasco está vacío, lo traemos de producción y buscamos su límite
                        if not st.session_state.get("t_cod"): 
                            st.session_state.t_cod = str(fila.get('CODPLANO', '')).strip()
                            codigo_cat = st.session_state.t_cod
                            if codigo_cat:
                                cursor.execute("SELECT MAXIMO FROM catalogo_articulos WHERE CODIGO = ?", (codigo_cat,))
                                res_cat = cursor.fetchone()
                                if res_cat and res_cat[0]:
                                    st.session_state.t_max = res_cat[0]
                                    
                        # Respetamos las especificaciones técnicas si ya las trajo el catálogo
                        if not st.session_state.get("t_med"): st.session_state.t_med = str(fila.get('MEDIDA', '')).strip()
                        if not st.session_state.get("lab_boc"): st.session_state.lab_boc = str(fila.get('BOCA', '')).strip()
                        if not st.session_state.get("lab_col"): st.session_state.lab_col = str(fila.get('COLOR', '')).strip()
                        if not st.session_state.get("lab_par"): st.session_state.lab_par = str(fila.get('PARED', '')).strip()
                        
                        # Datos de materia prima (casi siempre vienen de producción)
                        if not st.session_state.get("t_lmp"): st.session_state.t_lmp = str(fila.get('LOTEMP', '')).strip()
                        if not st.session_state.get("t_batch"): st.session_state.t_batch = str(fila.get('BATCH', '')).strip()
                        
                        # Máquina la reescribimos si producción nos dice en cuál se está haciendo
                        maq_prod = str(fila.get('MAQUINA', '')).strip()
                        if maq_prod: 
                            st.session_state.lab_maq = maq_prod

        except Exception as e:
            print(f"Error en autocompletado híbrido: {e}")
        finally:
            conn.close()

#Funcion del resgistro de temperatura
def guardar_temperatura(datos):
    conn = sqlite3.connect(RUTAS["lab"])
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO registro_temperatura (fecha, hora, temperatura, responsable, verificacion)
        VALUES (?, ?, ?, ?, ?)
    ''', datos)
    conn.commit()
    conn.close()
#Funcion del resgistro de temperatura
def cargar_historial_temperatura():
    conn = sqlite3.connect(RUTAS["lab"])
    # Traemos los últimos 50 registros para no sobrecargar la pantalla
    df = pd.read_sql_query("SELECT * FROM registro_temperatura ORDER BY id DESC LIMIT 50", conn)
    conn.close()
    return df

def cargar_historial_lab():
    conn = sqlite3.connect(RUTAS["lab"])
    df = pd.read_sql_query("SELECT * FROM analisis_hidrolitica ORDER BY nro_analisis DESC", conn)
    conn.close()
    return df

from fpdf import FPDF
import io
import datetime

# --- MOTOR GENERADOR DE PDF ---
def generar_certificado_pdf(fila, datos_extra):
    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.add_page()
    
    # Imagen de fondo
    pdf.image('plantilla_certificado.jpg', x=0, y=0, w=210, h=297)
    pdf.set_font("helvetica", style="B", size=10)
    
    # --- DATOS AUTOMÁTICOS DE LA BASE DE DATOS ---
    
    # Nro análisis
    pdf.set_xy(x=30.7- 2.5, y=196.1- 4.75)
    pdf.cell(w=24.9, h=5, txt=str(fila['nro_analisis']), border=0, align='C')
    
    # Cliente
    pdf.set_xy(x=72.8 - 2.5, y=50.5 - 4.75)
    pdf.cell(w=76.5, h=7.2, txt=str(fila['cliente']).upper(), border=0, align='C')
    
    # Máquina
    pdf.set_xy(x=172.6- 2.5, y=50.5- 4.75)
    pdf.cell(w=27, h=7.2, txt=str(fila['maquina']), border=0, align='C')
    
    # Lote Lumen
    pdf.set_xy(x=146.6- 2.5, y=74.48- 4.75)
    pdf.cell(w=25.9, h=7.2, txt=str(fila['lote_lumen']), border=0, align='C')
    
    # Medida
    pdf.set_xy(x=53.65- 2.5, y=95.65- 4.75)
    pdf.cell(w=58.13, h=7.2, txt=str(fila['medida']), border=0, align='C')
    
    # Tipo Boca
    pdf.set_xy(x=114.5- 2.5, y=95.65- 4.75)
    pdf.cell(w=32.04, h=7.2, txt=str(fila['boca']).upper(), border=0, align='C')
    
    # Color vidrio
    pdf.set_xy(x=149.42- 2.5, y=95.65- 4.75)
    pdf.cell(w=50.23, h=7.2, txt=str(fila['color']).upper(), border=0, align='C')
    
    # Capacidad
    pdf.set_xy(x=12.3- 2.5, y=110.51- 4.75)
    pdf.cell(w=39.3, h=7.2, txt=str(fila['capacidad'] + " ml"), border=0, align='C')
    
    # Impresion
    texto_impresion = str(datos_extra.get('impresion', fila['impresion'])).upper()
    pdf.set_xy(x=53.7- 2.5, y=110.51- 4.75)
    pdf.cell(w=58.11, h=7.2, txt=texto_impresion, border=0, align='C')
    
    # Codigo Plano
    pdf.set_xy(x=114.5- 2.5, y=110.51- 4.75)
    pdf.cell(w=35, h=7.2, txt=str(fila['cod']), border=0, align='C')
    
    # Lote Materia Prima
    pdf.set_xy(x=53.7- 2.5, y=131.5- 4.75)
    pdf.cell(w=36.87, h=5, txt=str(fila['l_m_prima']), border=0, align='C')

    #Batch Materia Prima
    pdf.set_xy(x=53.7- 2.5, y=138.25- 4.75)
    pdf.cell(w=36.87, h=5,txt=str(fila['batch']), border=0, align='C')
    
    # Pared
    pdf.set_xy(x=53.7- 2.5, y=152.4- 4.75)
    pdf.cell(w=36.87, h=5, txt=str(fila['pared']).replace(".", ",") + " mm", border=0, align='C')
    
    # Resultado (Titulación) - Formato con coma
    res_str = f"{fila['resultado_final']:.2f}".replace(".", ",")
    pdf.set_xy(x=95- 2.5, y=196.1- 4.75)
    pdf.cell(w=20.3, h=5, txt=res_str, border=0, align='C')
    
    # Maximo Permitido - Formato con coma
    max_str = f"{fila['maximo']:.2f}".replace(".", ",")
    pdf.set_xy(x=172.2- 2.5, y=196.1- 4.75)
    pdf.cell(w=20.3, h=5, txt=max_str, border=0, align='C')
    
    # Fechas (Formateamos de AAAA-MM-DD a DD/MM/AAAA)
    try:
        fecha_ar = datetime.datetime.now().strftime("%d/%m/%Y")
    except:
        fecha_ar = fila['fecha']

    pdf.set_xy(x=12.1- 2.5, y=50.5- 4.75)
    pdf.cell(w=39.5- 2.5, h=7.2, txt=fecha_ar, border=0, align='C')
    pdf.set_xy(x=90.8- 2.5, y=260.4- 4.75)
    pdf.cell(w=20, h=5, txt=fecha_ar, border=0, align='C')
    pdf.set_xy(x=183.5- 2.5, y=260.4- 4.75)
    pdf.cell(w=18, h=5, txt=fecha_ar, border=0, align='C')
    
    # --- DATOS EXTRA (Ingresados a mano al imprimir) ---
    pdf.set_xy(x=149.4- 2.5, y=14.6- 4.75)
    pdf.cell(w=23.3, h=10.1, txt=str(datos_extra.get('nro_cert', '')), border=0, align='C') # Nro Certificado

    pdf.set_xy(x=53.65- 2.5, y=65.15- 4.75)
    pdf.cell(w=36.88, h=7.2, txt=str(datos_extra.get('oc', '')), border=0, align='C') # Orden de compra
    
    pdf.set_xy(x=53.65- 2.5, y=74.49- 4.75)
    pdf.cell(w=36.88, h=7.2, txt=str(datos_extra.get('np', '')), border=0, align='C') # Nota de pedido
    
    pdf.set_xy(x=53.65- 2.5, y=83.71- 4.75)
    pdf.cell(w=36.88, h=7.2, txt=str(fila['cod']), border=0, align='C') # Cod. Frasco/F2237
    
    pdf.set_xy(x=172.65- 2.5, y=65.2- 4.75)
    pdf.cell(w=27, h=7.2, txt=str(datos_extra.get('fecha_vto', '')), border=0, align='C') # Fecha Vto
    
    pdf.set_xy(x=12.3- 2.5, y=95.65- 4.75)
    pdf.cell(w=39.3, h=7.2, txt=str(datos_extra.get('cantidad', '')), border=0, align='C') # Cantidad
    
    pdf.set_xy(x=53.7- 2.5, y=145.5- 4.75)
    pdf.cell(w=36.87, h=5, txt=str(fila['medida'].split('x')[0] + " mm" ), border=0, align='C') # Diametro
    
    pdf.set_xy(x=172.61- 2.5, y=159.31- 4.75)
    pdf.cell(w=24.9, h=5, txt=str(datos_extra.get('imp_control', 'N/A')), border=0, align='C') # Imp. Control
    
    # Guardamos el PDF en memoria y lo retornamos
    pdf_bytes = pdf.output()
    return bytes(pdf_bytes)

# --- MOTORES LABORATORIO ---
def obtener_siguiente_nro_analisis():
    if not os.path.exists(RUTAS["lab"]): return 8077
    conn = sqlite3.connect(RUTAS["lab"])
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(nro_analisis) FROM analisis_hidrolitica")
    resultado = cursor.fetchone()[0]
    conn.close()
    return (resultado + 1) if resultado else 8077

def cargar_historial_lab():
    if not os.path.exists(RUTAS["lab"]): return pd.DataFrame()
    conn = sqlite3.connect(RUTAS["lab"])
    df = pd.read_sql_query("SELECT * FROM analisis_hidrolitica ORDER BY nro_analisis DESC", conn)
    conn.close()
    return df

# --- INTERFAZ MODULAR DE LABORATORIO ---
def renderizar_modulo_laboratorio():
    st.header("🔬 Control de Calidad: Resistencia Hidrolítica")
    
    # Inicializador seguro del mensaje de éxito
    if 'exito_lab' not in st.session_state:
        st.session_state.exito_lab = False
        
    if st.session_state.exito_lab:
        st.success("✅ Análisis guardado exitosamente. Formulario limpio para el siguiente registro.")
        st.session_state.exito_lab = False # Lo apagamos para que no quede fijo siempre

    tab_lab1, tab_lab2, tab_lab3 = st.tabs(["📝 Nuevo Análisis", "📚 Historial de Registros", "🌡️ Registros Temperatura (RT Rev.1)"])

    with tab_lab1:
        nro_actual = obtener_siguiente_nro_analisis()
        st.markdown(f"### Análisis Nro: **{nro_actual}**")
        
        # --- LA MAGIA: CALLBACK PARA GUARDAR Y VACIAR ---
        def accion_guardar():
            ahora = datetime.datetime.now()
            
            # Calculamos el resultado leyendo directamente el estado temporal
            v = st.session_state.lab_vol
            b = st.session_state.n_bla
            t = st.session_state.n_tit
            res = (t - b) * 2 if v == "50%" else (t - b)
            
            datos = (
                nro_actual, ahora.strftime("%Y-%m-%d"), ahora.strftime("%H:%M:%S"),
                st.session_state.lab_resp, st.session_state.lab_maq, st.session_state.lab_hor,
                st.session_state.lab_temp, 
                st.session_state.t_cli, st.session_state.t_med, st.session_state.t_cap, st.session_state.t_cod, 
                st.session_state.lab_boc, st.session_state.lab_col, st.session_state.lab_par, 
                st.session_state.t_imp, st.session_state.lab_trat, st.session_state.t_lote, 
                st.session_state.t_lmp, st.session_state.t_batch, v, 
                b, t, res, st.session_state.t_max, st.session_state.t_obs
            )
            cod_mp_oculto = st.session_state.get('hidden_cod_mp', '')
            guardar_analisis_lab(datos)
            enriquecer_catalogo_articulos(
                st.session_state.t_cod,        # Código del frasco
                st.session_state.t_cap,        # Capacidad (ingresada/confirmada)
                st.session_state.lab_col,      # Color (ingresado/confirmado por operario)
                st.session_state.lab_boc,      # Boca
                st.session_state.lab_par,      # Espesor
                cod_mp_oculto,                  # El CODIGOMP invisible
                st.session_state.t_max
            )   
            
            # Vaciado seguro de campos (esto ya no tira error)
            claves_texto = ["t_cli", "t_lote", "t_med", "t_cap", "t_lmp", "t_cod", "t_batch", "t_imp", "t_obs","lab_temp"]
            for k in claves_texto:
                st.session_state[k] = ""
            claves_num = ["n_bla", "n_tit", "t_max"]
            for k in claves_num:
                st.session_state[k] = 0.0
                
            st.session_state.exito_lab = True

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            resp = st.selectbox("Responsable", RESPONSABLES, key="lab_resp")
            cod = st.text_input("Cod. Frasco (Enter para autocompletar)", key="t_cod", on_change=autocompletar_frasco) 
            lote_lum = st.text_input("Lote Lumen", key="t_lote", on_change=autocompletar_por_lote)
        with col2:
            # MOVIDO ACÁ Y CONECTADO AL CALLBACK
            cli = st.text_input("Cliente", key="t_cli")
            maq = st.selectbox("Máquina", MAQUINAS, key="lab_maq")
            l_mp = st.text_input("L.M.Prima", key="t_lmp")
        with col3:
            hor = st.selectbox("Horno", HORNOS, key="lab_hor")
            temp = st.text_input("Temp. Horno (°C)", key="lab_temp")
            med = st.text_input("Medida (mm)", key="t_med") # Se llena solo
            cap = st.text_input("Capacidad (ml)", key="t_cap")
            batch = st.text_input("Batch", key="t_batch")
        with col4:
            boc = st.selectbox("Boca", BOCAS, key="lab_boc") # Se llena solo
            col_vid = st.selectbox("Color", ["Ambar", "Incoloro"], key="lab_col") # Se llena solo
            par = st.text_input("Pared (mm)", key="lab_par") # Se llena solo
            
        col_c1, col_c2, col_c3 = st.columns(3)
        with col_c1:
            imp = st.text_input("Impresión", key="t_imp")
        with col_c2:
            trat = st.radio("Tratado", ["Si", "No"], horizontal=True, key="lab_trat")
        with col_c3:
            vol = st.radio("Vol. Analizado", ["50%", "100%"], horizontal=True, key="lab_vol")

        st.markdown("---")
        st.markdown("#### 🧪 Resultados de Titulación")
        c_tit1, c_tit2, c_tit3, c_tit4 = st.columns(4)
        
        with c_tit1: blanco = st.number_input("Blanco (ml de HCL 0,01 M)", min_value=0.0, step=0.01, format="%.2f", key="n_bla")
        with c_tit2: titulacion = st.number_input("Titulación (ml de HCL 0,01 M)", min_value=0.0, step=0.01, format="%.2f", key="n_tit")
        # --- ESCUDO ANTIFANTASMAS PARA T_MAX ---
        if "t_max" in st.session_state:
            try:
                # Si es un texto con coma o punto, lo forzamos a decimal puro
                valor_limpio = str(st.session_state["t_max"]).replace(',', '.')
                st.session_state["t_max"] = float(valor_limpio)
            except (ValueError, TypeError):
                # Si está vacío ("") o trae letras, lo matamos a cero
                st.session_state["t_max"] = 0.0
        else:
            st.session_state["t_max"] = 0.0
        # ---------------------------------------
        
        with c_tit3: 
            maximo = st.number_input("Máximo Permitido (ml de HCL 0,01 M)", min_value=0.0, step=0.01, format="%.2f", key="t_max")
        
        # El cálculo visual en vivo sigue funcionando independiente
        resultado_calc = 0.0
        if vol == "50%":
            resultado_calc = (titulacion - blanco) * 2
        else:
            resultado_calc = titulacion - blanco
            
        with c_tit4:
            if maximo > 0 and resultado_calc > maximo:
                st.error(f"RESULTADO: {resultado_calc:.2f} (RECHAZADO)")
            else:
                st.success(f"RESULTADO: {resultado_calc:.2f} (OK)")

        obs = st.text_area("Observaciones", key="t_obs")

        # FIJATE ACÁ: Le conectamos la función al botón usando on_click
        st.button("💾 Guardar Análisis", use_container_width=True, type="primary", on_click=accion_guardar)

    with tab_lab2:
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
                    st.info("1. Seleccione el análisis a certificar:")
                    analisis_a_imprimir = st.selectbox("Nro. Análisis", analisis_disponibles, key="sel_pdf")
                
                with col_pdf_der:
                    st.warning("2. Datos comerciales del envío (Autocompletados):")
                    
                    # --- FUNCIÓN DE LIMPIEZA DEFINITIVA ---
                    def limpiar_comercial(valor):
                        if pd.isna(valor) or valor is None: return "-"
                        v_str = str(valor).strip()
                        if v_str.lower() in ['nan', 'none', '0.0', '0', '', '-']: return "-"
                        try:
                            # Esto elimina notación científica y el .0 de números largos
                            return str(int(float(valor)))
                        except:
                            return v_str
                    # ---------------------------------------

                    # 1. Identificamos el lote
                    fila_elegida = df_mostrar[df_mostrar['nro_analisis'] == analisis_a_imprimir].iloc[0]
                    lote_actual = str(fila_elegida['lote_lumen']).strip()
                    
                    # 2. Buscamos el lote en Producción
                    df_prod = cargar_produccion()
                    datos_prod = pd.DataFrame()
                    if not df_prod.empty:
                        # Limpieza del lote para la comparación
                        l_limpios = df_prod['LOTE_LUMEN'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
                        datos_prod = df_prod[l_limpios == lote_actual]
                    
                    # 3. Rescatamos la NOTA DE PEDIDO (nuestro puente)
                    np_cruda = datos_prod.iloc[0].get('NOTA_PEDIDO', '-') if not datos_prod.empty else "-"
                    def_np = limpiar_comercial(np_cruda)

                    # 4. BUSCAMOS LA ORDEN DE COMPRA EN REMENCA
                    def_oc = "-"
                    df_pedidos = cargar_pedidos_completos()
                    
                    if def_np != "-" and not df_pedidos.empty:
                        # Buscamos la NP limpia en la base de pedidos
                        # (Como ya limpiamos cargar_pedidos_completos, el cruce es directo)
                        datos_ped = df_pedidos[df_pedidos['NOTA_PEDIDO'] == def_np]
                        
                        if not datos_ped.empty:
                            oc_cruda = datos_ped.iloc[0].get('ORDEN_COMPRA', '-')
                            def_oc = limpiar_comercial(oc_cruda)
                    
                    # Si no estaba en Remenca, probamos lo que diga Producción por si acaso
                    if def_oc == "-" and not datos_prod.empty:
                        oc_prod = datos_prod.iloc[0].get('ORDEN_COMPRA', '-')
                        def_oc = limpiar_comercial(oc_prod)

                    # 5. Cantidad y Fecha
                    try:
                        def_cant = str(int(float(datos_prod.iloc[0]['CANTIDAD']))) if not datos_prod.empty else "0"
                    except:
                        def_cant = str(datos_prod.iloc[0].get('CANTIDAD', '0')).strip() if not datos_prod.empty else "0"
                        
                    def_vto = str(datos_prod.iloc[0].get('FECHA_ENTREGA', '-')).strip() if not datos_prod.empty else "-"
                    if def_vto in ['nan', 'None', '0.0', '']: def_vto = "-"

                    # 6. Interfaz de usuario
                    cx1, cx2, cx3 = st.columns(3)
                    with cx1:
                        doc_oc = st.text_input("Orden de Compra", value=def_oc)
                        doc_np = st.text_input("Nota de Pedido", value=def_np)
                    with cx2:
                        doc_imp = st.text_input("Texto de Impresión", value=str(fila_elegida['impresion']))
                        doc_cant = st.text_input("Cantidad", value=def_cant)
                        doc_nro_cert = st.text_input("Nro Certificado", value="-")
                    with cx3:
                        estado_imp = "Correcto" if doc_imp.upper() != "SIN IMPRESION" and doc_imp.upper() != "N/A" else "N/A"
                        doc_ctrl_imp = st.selectbox("Control Impresión", ["N/A", "CORRECTO", "INCORRECTO"], index=0 if estado_imp == "N/A" else 1)
                        doc_vto = st.text_input("Fecha Entrega", value=def_vto)
                        
                    diccionario_extra = {
                        'oc': doc_oc, 'np': doc_np, 
                        'cantidad': doc_cant, 'fecha_vto': doc_vto,
                        'nro_cert': doc_nro_cert, 'impresion': doc_imp, 'imp_control': doc_ctrl_imp
                    }

                     # 7. Empaquetamos para el PDF
                    st.write("") 
                    pdf_listo = generar_certificado_pdf(fila_elegida, diccionario_extra)
                    
                    st.download_button(
                        label=f"📄 DESCARGAR CERTIFICADO APROBADO",
                        data=pdf_listo,
                        file_name=f"Certificado_Lumen_Lote_{fila_elegida['lote_lumen']}.pdf",
                        mime="application/pdf",
                        type="primary",
                        use_container_width=True,
                        key=f"btn_pdf_vfinal_{fila_elegida['nro_analisis']}"
                    )
    
    with tab_lab3:
        st.markdown("### 🌡️ Registro de Temperatura Ambiente")
        
        # Formulario de carga
        col_t1, col_t2, col_t3 = st.columns(3)
        with col_t1:
            temp_resp = st.selectbox("Firma/Rúbrica (Analista)", RESPONSABLES, key="t_resp")
        with col_t2:
            # Ponemos límites lógicos (ej: 0 a 50 grados)
            temp_valor = st.number_input("Temperatura (°C)", min_value=0.0, max_value=50.0, step=0.1, format="%.1f", key="t_val")
        with col_t3:
            temp_verif = st.text_input("Verificación / Observaciones", key="t_verif", placeholder="Ej: OK, o firma supervisor")

        if st.button("💾 Guardar Temperatura", type="primary"):
            ahora = datetime.datetime.now()
            datos_temp = (
                ahora.strftime("%Y-%m-%d"),
                ahora.strftime("%H:%M:%S"),
                temp_valor,
                temp_resp,
                temp_verif
            )
            guardar_temperatura(datos_temp)
            st.success(f"✅ Temperatura de {temp_valor}°C registrada a las {ahora.strftime('%H:%M')}.")

        st.markdown("---")
        st.markdown("#### 📋 Últimos Registros")
        df_temp = cargar_historial_temperatura()
        
        if not df_temp.empty:
            # Renombramos las columnas para que se vean lindas como en tu papel
            df_temp_mostrar = df_temp.rename(columns={
                'fecha': 'DÍA', 
                'hora': 'HORARIO', 
                'temperatura': 'TEMPERATURA (°C)', 
                'responsable': 'FIRMA / RÚBRICA', 
                'verificacion': 'VERIFICACIÓN'
            })
            # Ocultamos la columna ID interna
            st.dataframe(df_temp_mostrar.drop(columns=['id']), use_container_width=True)
        else:
            st.info("Aún no hay registros de temperatura en la base de datos.")

# ==========================================
# GESTOR DE PERFILES Y RUTEO DE PANTALLAS
# ==========================================
st.sidebar.markdown("### 👤 Perfil de Acceso")
perfil = st.sidebar.radio("Seleccione Área:", ["Laboratorio", "Administrador"])

if perfil == "Administrador":
    # MODO PRIVADO PARA RRHH
    st.sidebar.markdown("---")
    clave = st.sidebar.text_input("🔑 Contraseña:", type="password")
    
    if clave == "admin123": # <--- CAMBIÁ ESTA CONTRASEÑA SI QUERÉS
        st.title("🏭 Nuevo Sistema Lumen Glass")
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["🕒 ASISTENCIA", "🚻 BAÑO", "☕ DESCANSO", "🔬 LABORATORIO", "📦 PEDIDOS"])
        hoy = datetime.date.today()
        datos_maestros = cargar_asistencia()
        
# ==========================================
# PESTAÑA 1: ASISTENCIA
# ==========================================
        with tab1:
            if datos_maestros.empty:
                st.error("No se pudo conectar a la base de Asistencia.")
            else:
                st.markdown("### 🔍 Filtros")
                ca1, ca2, ca3 = st.columns(3)
                with ca1: leg_a = st.number_input("Nº Legajo", min_value=0, value=0, step=1, key="leg_a")
                with ca2: nom_a = st.text_input("Buscar Nombre", key="nom_a")
                # MODIFICACIÓN: Inicia solo con la fecha de hoy
                with ca3: rang_a = st.date_input("Rango de Fechas", value=(hoy, hoy), key="fec_a")

                df_a = datos_maestros[['LEGAJO', 'NOMBRE', 'FECHA', 'HORAI', 'HORAE', 'TOTAL_HS']].copy()
                if leg_a > 0: df_a = df_a[df_a['LEGAJO'] == leg_a]
                if nom_a: df_a = df_a[df_a['NOMBRE'].str.upper().str.contains(nom_a.upper(), na=False)]
                
                # Filtro de fecha dinámico (soporta 1 día o un rango)
                if len(rang_a) == 2:
                    df_a = df_a[(df_a['FECHA'] >= rang_a[0]) & (df_a['FECHA'] <= rang_a[1])]
                elif len(rang_a) == 1:
                    df_a = df_a[df_a['FECHA'] == rang_a[0]]

                st.bar_chart(data=df_a.groupby('FECHA')['TOTAL_HS'].sum().reset_index(), x='FECHA', y='TOTAL_HS')
                st.dataframe(df_a, use_container_width=True)
                
                # --- NUEVO: ESTADÍSTICAS ---
                st.markdown("---")
                st.markdown("#### 📊 Estadísticas del Período Seleccionado")
                col_est1, col_est2 = st.columns(2)
                with col_est1:
                    faltas = len(df_a[df_a['TOTAL_HS'] == 0])
                    st.metric(label="🚩 Total de Faltas (Días con 0 hs)", value=faltas)
                with col_est2:
                    horas_totales = df_a['TOTAL_HS'].sum()
                    st.metric(label="⏱️ Horas Trabajadas (Total)", value=round(horas_totales, 2))
                
                st.markdown("<br>", unsafe_allow_html=True)
                csv_a = df_a.to_csv(index=False, sep=';').encode('utf-8-sig')
                st.download_button("📥 Exportar Asistencia", csv_a, "asistencia.csv", "text/csv")

# ==========================================
# PESTAÑA 2: BAÑO
# ==========================================
        with tab2:
            datos_b = cargar_bano()
            if datos_b.empty:
                st.error("No se pudo conectar a la base de Baño.")
            else:
                st.markdown("### 🔍 Filtros")
                cb1, cb2, cb3 = st.columns(3)
                with cb1: leg_b = st.number_input("Nº Legajo", min_value=0, value=0, step=1, key="leg_b")
                with cb2: nom_b = st.text_input("Buscar Nombre", key="nom_b")
                with cb3: rang_b = st.date_input("Rango de Fechas", value=(hoy, hoy), key="fec_b")

                df_b = datos_b.copy()
                if leg_b > 0: df_b = df_b[df_b['LEGAJO'] == leg_b]
                if nom_b: df_b = df_b[df_b['NOMBRE'].str.upper().str.contains(nom_b.upper(), na=False)]
                
                if len(rang_b) == 2:
                    df_b = df_b[(df_b['FECHA'] >= rang_b[0]) & (df_b['FECHA'] <= rang_b[1])]
                elif len(rang_b) == 1:
                    df_b = df_b[df_b['FECHA'] == rang_b[0]]

                col_g1, col_g2 = st.columns(2)
                with col_g1:
                    st.markdown("**Minutos por Día**")
                    if not df_b.empty: st.bar_chart(data=df_b.groupby('FECHA')['MIN_TOTALES'].sum().reset_index(), x='FECHA', y='MIN_TOTALES')
                with col_g2:
                    st.markdown("**Veces por Día**")
                    if not df_b.empty: st.bar_chart(data=df_b.groupby('FECHA')['CANT_VECES'].sum().reset_index(), x='FECHA', y='CANT_VECES')

                st.dataframe(df_b, use_container_width=True)
                csv_b = df_b.to_csv(index=False, sep=';').encode('utf-8-sig')
                st.download_button("📥 Exportar Baño", csv_b, "bano.csv", "text/csv")

# ==========================================
# PESTAÑA 3: DESCANSO / ALMUERZO
# ==========================================
        with tab3:
            if datos_maestros.empty:
                st.error("Esperando datos base...")
            else:
                st.markdown("### 🔍 Filtros de Descanso")
                cd1, cd2, cd3 = st.columns(3)
                with cd1: leg_d = st.number_input("Nº Legajo", min_value=0, value=0, step=1, key="leg_d")
                with cd2: nom_d = st.text_input("Buscar Nombre", key="nom_d")
                with cd3: rang_d = st.date_input("Rango de Fechas", value=(hoy, hoy), key="fec_d")

                df_d = datos_maestros[['LEGAJO', 'NOMBRE', 'FECHA', 'SALIDA_DESC', 'VUELTA_DESC', 'MIN_DESCANSO', 'DETALLE_DESCANSO']].copy()
                
                if leg_d > 0: df_d = df_d[df_d['LEGAJO'] == leg_d]
                if nom_d: df_d = df_d[df_d['NOMBRE'].str.upper().str.contains(nom_d.upper(), na=False)]
                
                if len(rang_d) == 2:
                    df_d = df_d[(df_d['FECHA'] >= rang_d[0]) & (df_d['FECHA'] <= rang_d[1])]
                elif len(rang_d) == 1:
                    df_d = df_d[df_d['FECHA'] == rang_d[0]]

                st.bar_chart(data=df_d.groupby('FECHA')['MIN_DESCANSO'].sum().reset_index(), x='FECHA', y='MIN_DESCANSO')
                st.dataframe(df_d, use_container_width=True)
                csv_d = df_d.to_csv(index=False, sep=';').encode('utf-8-sig')
                st.download_button("📥 Exportar Descanso", csv_d, "descanso.csv", "text/csv")

        with tab4:
            renderizar_modulo_laboratorio()
        with tab5:
            st.markdown("### 📦 Seguimiento de Pedidos (Administración)")
            df_pedidos = cargar_pedidos_completos()
            
            if df_pedidos.empty:
                st.warning("No se encontraron datos de pedidos o la ruta de red no es accesible.")
            else:
                st.markdown("#### 🔍 Filtros de Búsqueda")
                col_p1, col_p2, col_p3 = st.columns(3)
                with col_p1:
                    busq_np = st.text_input("Nota de Pedido / OC", key="busq_np")
                with col_p2:
                    busq_cli = st.text_input("Cliente", key="busq_cli_ped")
                with col_p3:
                    busq_cod = st.text_input("Código de Frasco", key="busq_cod_ped")
                
                # Aplicamos filtros dinámicos
                df_mostrar = df_pedidos.copy()
                if busq_np:
                    df_mostrar = df_mostrar[
                        df_mostrar['NOTA_PEDIDO'].astype(str).str.contains(busq_np, case=False) |
                        df_mostrar['ORDEN_COMPRA'].astype(str).str.contains(busq_np, case=False)
                    ]
                if busq_cli:
                    df_mostrar = df_mostrar[df_mostrar['CLIENTE'].astype(str).str.contains(busq_cli, case=False, na=False)]
                if busq_cod:
                    df_mostrar = df_mostrar[df_mostrar['COD_FRASCO'].astype(str).str.contains(busq_cod, case=False, na=False)]
                
                # Mostramos los primeros 1000 registros
                st.dataframe(df_mostrar.head(1000), use_container_width=True)
                
                st.markdown("<br>", unsafe_allow_html=True)
                csv_pedidos = df_mostrar.head(5000).to_csv(index=False, sep=';').encode('utf-8-sig')
                st.download_button("📥 Exportar Resultados a Excel", csv_pedidos, "pedidos_lumen.csv", "text/csv")
                st.markdown("---")

    elif clave != "":
        st.sidebar.error("Contraseña incorrecta")
    else:
        st.warning("🔒 Ingrese la contraseña en el menú lateral para acceder a la gestión de RRHH.")

elif perfil == "Laboratorio":
    # MODO PÚBLICO PARA LA TABLET (Solo ve Laboratorio)
    renderizar_modulo_laboratorio()

st.sidebar.markdown("---")
st.sidebar.markdown("### ⚙️ Sistema")
if st.sidebar.button("🔄 Sincronizar Todo"):
    st.cache_data.clear()
    st.rerun()