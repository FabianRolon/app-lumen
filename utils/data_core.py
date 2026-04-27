import streamlit as st
import pandas as pd
import os
import sqlite3
import shutil
from dbfread import DBF
from config import RUTAS

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

def sincronizar_personal_dbf():
    if not os.path.exists(RUTAS["personal"]["red"]):
        return False, "⚠️ No se encuentra el archivo Empleado.Dbf en la red."

    try:
        # 1. Copiado de archivos (DBF + Memo)
        base_red = os.path.splitext(RUTAS["personal"]["red"])[0]
        base_loc = os.path.splitext(RUTAS["personal"]["loc"])[0]
        shutil.copy2(RUTAS["personal"]["red"], RUTAS["personal"]["loc"])
        for ext in ['.FPT', '.fpt', '.DBT', '.dbt']:
            if os.path.exists(base_red + ext):
                shutil.copy2(base_red + ext, base_loc + ext)

        # 2. Lectura RAW
        dbf_data = DBF(RUTAS["personal"]["loc"], encoding='latin1', ignore_missing_memofile=True)
        df = pd.DataFrame(iter(dbf_data))
        
        if df.empty:
            return False, "❌ El archivo DBF está vacío."

        # --- DIAGNÓSTICO DE COLUMNAS ---
        # Forzamos todo a mayúsculas para evitar errores de tipeo
        df.columns = [c.upper() for c in df.columns]
        columnas_reales = df.columns.tolist()
        
        # Verificamos si las columnas mínimas existen
        columnas_necesarias = ['CUIL', 'LEGAJO', 'NOMBREC']
        faltantes = [c for c in columnas_necesarias if c not in columnas_reales]
        if faltantes:
            return False, f"❌ Faltan columnas en el DBF: {faltantes}. Columnas encontradas: {columnas_reales[:10]}..."

        # --- FILTRO FLEXIBLE DE ACTIVOS ---
        # Intentamos filtrar por 'ACTIVO' o 'ESTADO'. Si no existen, traemos a todos.
        if 'ACTIVO' in df.columns:
            # Aceptamos 'T', True, 'S' (de Sí) o 1
            activos = df[df['ACTIVO'].astype(str).str.upper().str.startswith(('T', 'S', '1'))].copy()
        else:
            activos = df.copy()

        if activos.empty:
            return False, f"❌ Se leyeron {len(df)} empleados, pero ninguno pasó el filtro de 'ACTIVO'."

        # 3. Guardado en SQLite
        conn = sqlite3.connect(RUTAS["lab"])
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS credenciales_empleados 
                          (dni TEXT PRIMARY KEY, legajo TEXT, nombre TEXT, pin TEXT, rol TEXT, estado TEXT)''')
        
        nuevos = 0
        for _, emp in activos.iterrows():
            # Limpieza de CUIL para DNI
            cuil_raw = str(emp.get('CUIL', '')).replace('-', '').strip()
            dni = cuil_raw if cuil_raw else "0"
            legajo = str(emp.get('LEGAJO', '')).strip()
            nombre = str(emp.get('NOMBREC', 'S/N')).strip()
            pin_inicial = dni[-4:] if len(dni) >= 4 else "1234"
            
            if dni != "0":
                cursor.execute('''INSERT OR REPLACE INTO credenciales_empleados (dni, legajo, nombre, pin, rol, estado)
                                  VALUES (?, ?, ?, ?, 
                                  COALESCE((SELECT rol FROM credenciales_empleados WHERE dni=?), 'Planta'), 
                                  'ACTIVO')''', (dni, legajo, nombre, pin_inicial, dni))
                nuevos += 1
                
        conn.commit()
        conn.close()
        
        return True, f"✅ ¡Éxito! Se procesaron {nuevos} empleados correctamente."
        
    except Exception as e:
        return False, f"❌ Error crítico: {str(e)}"

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
        shutil.copy2(RUTAS["stock_movimientos"]["red"], RUTAS["stock_movimientos"]["loc"])
        df_ma = pd.DataFrame(iter(DBF(RUTAS["stock_movimientos"]["loc"], encoding='latin1')))
        
        col_ano = next((c for c in df_ma.columns if c.strip().upper().startswith('A') and c.strip().upper().endswith('O')), None)
        if col_ano:
            df_ma[col_ano] = pd.to_numeric(df_ma[col_ano], errors='coerce').fillna(0).astype(int)
            df_ma = df_ma[df_ma[col_ano] == 2026].copy()
            
        df_ma['CODIGO'] = df_ma['CODIGO'].astype(str).str.strip().str.upper()
        cols_ma = ['CODIGO', 'TKGSTOCK', 'TUBOSSTOCK', 'DESCRIP']
        if 'ORIGEN' in df_ma.columns: cols_ma.append('ORIGEN')
        df_ma = df_ma[[c for c in cols_ma if c in df_ma.columns]]

        shutil.copy2(RUTAS["stock_pallets"]["red"], RUTAS["stock_pallets"]["loc"])
        df_pa = pd.DataFrame(iter(DBF(RUTAS["stock_pallets"]["loc"], encoding='latin1')))
        df_pa['CODIGO'] = df_pa['CODIGO'].astype(str).str.strip().str.upper()
        
        if 'TUBOPALLET' in df_pa.columns: df_pa['TUBOPALLET'] = pd.to_numeric(df_pa['TUBOPALLET'], errors='coerce').fillna(0)
        if 'PESOPALLET' in df_pa.columns: df_pa['PESOPALLET'] = pd.to_numeric(df_pa['PESOPALLET'], errors='coerce').fillna(0)
            
        df_pa = df_pa.sort_values(by=['TUBOPALLET', 'PESOPALLET'])
        df_pa = df_pa.drop_duplicates(subset=['CODIGO'], keep='last')
        cols_pa = ['CODIGO', 'PESOTUBO', 'TUBOPALLET', 'PESOPALLET']
        df_pa = df_pa[[c for c in cols_pa if c in df_pa.columns]]

        df_fused = pd.merge(df_ma, df_pa, on='CODIGO', how='left')

        if 'ORIGEN' in df_fused.columns:
            df_fused['ORIGEN'] = df_fused['ORIGEN'].astype(str).str.strip().replace(r'\.0$', '', regex=True)
            mapa_origen = {'1': 'Brasil', '2': 'China', '3': 'EE.UU.'}
            df_fused['ORIGEN'] = df_fused['ORIGEN'].map(lambda x: mapa_origen.get(x, x))
        else:
            df_fused['ORIGEN'] = "-"

        df_fused['TKGSTOCK'] = pd.to_numeric(df_fused['TKGSTOCK'], errors='coerce').fillna(0)
        df_fused['TUBOSSTOCK'] = pd.to_numeric(df_fused['TUBOSSTOCK'], errors='coerce').fillna(0)
        df_fused['TUBOPALLET'] = pd.to_numeric(df_fused['TUBOPALLET'], errors='coerce').fillna(0)
        df_fused['PESOTUBO'] = pd.to_numeric(df_fused['PESOTUBO'], errors='coerce').fillna(0)
        
        df_fused['CANT_PALLETS'] = df_fused.apply(lambda row: round(row['TUBOSSTOCK'] / row['TUBOPALLET'], 2) if row['TUBOPALLET'] > 0 else 0.0, axis=1)
        return df_fused
    except Exception as e:
        st.error(f"Error en Fusión de Stock: {e}")
        return pd.DataFrame()