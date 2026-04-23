import streamlit as st
import pandas as pd
from dbfread import DBF
import datetime
import os
import shutil

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Control Factory 3.2", layout="wide")
st.title("🏭 Panel de Control Central - DATOS EN VIVO")

# Ajustar la ruta "red" de asistencia a donde hayas puesto tu DBF local
RUTAS = {
    "asist": {"red": r'C:\Reloj\Bases\ASIGTURN.DBF', "loc": r'C:\proyecto_Asistencia\asistencia_temp.dbf'},
    "bano": {"red": r'\\CALIDAD\Bases\BANODBF.dbf', "loc": r'C:\proyecto_Asistencia\bano_temp.dbf'}
}

# --- 2. MOTORES DE LECTURA ---
@st.cache_data(ttl=60)
def cargar_asistencia():
    if not os.path.exists(RUTAS["asist"]["red"]): return pd.DataFrame()
    shutil.copy2(RUTAS["asist"]["red"], RUTAS["asist"]["loc"])
    df = pd.DataFrame(iter(DBF(RUTAS["asist"]["loc"], encoding='latin1')))
    
    df['LEGAJO'] = pd.to_numeric(df['LEGAJO'], errors='coerce')
    df['FECHA'] = pd.to_datetime(df['FECHA'], errors='coerce').dt.date
    
    # 2.A - LÓGICA DE ASISTENCIA GENERAL
    e = pd.to_datetime(df['HORAI'], errors='coerce')
    s = pd.to_datetime(df['HORAE'], errors='coerce')
    dif = s - e
    dif = dif.where(dif >= pd.Timedelta(0), dif + pd.Timedelta(days=1))
    df['TOTAL_HS'] = (dif.dt.total_seconds() / 3600).fillna(0).round(2)
    
    # 2.B - LÓGICA DE DESCANSO / ALMUERZO
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
        df.loc[validos & (minutos_reales > 90), 'DETALLE_DESCANSO'] = "⚠️ Excede 90m (Tope)"
        
        df.loc[sin_vuelta, 'MIN_DESCANSO'] = 90
        df.loc[sin_vuelta, 'DETALLE_DESCANSO'] = "⚠️ Sin Vuelta (Tope 90m)"
        
        df['SALIDA_DESC'] = df['SALIDA_DESC'].fillna("-")
        df['VUELTA_DESC'] = df['VUELTA_DESC'].fillna("-")
    else:
        df['SALIDA_DESC'] = "-"
        df['VUELTA_DESC'] = "-"
        df['MIN_DESCANSO'] = 0
        df['DETALLE_DESCANSO'] = "Sin columnas"

    return df

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
    for i in range(1, 8):
        pares.append((f'HINICIO{i}', f'HFINAL{i}'))
        
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

# --- 3. INTERFAZ Y SOLAPAS ---
tab1, tab2, tab3 = st.tabs(["🕒 ASISTENCIA", "🚻 CONTROL DE BAÑO", "☕ DESCANSO / ALMUERZO"])

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

st.sidebar.markdown("### ⚙️ Sistema")
if st.sidebar.button("🔄 Sincronizar Todo"):
    st.cache_data.clear()
    st.rerun()
