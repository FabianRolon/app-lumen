import streamlit as st
import pandas as pd
from dbfread import DBF
import datetime
import os
import shutil
import sqlite3

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Control Factory 4.0", layout="wide")
st.title("🏭 Panel de Control Central - DATOS EN VIVO")

RUTAS = {
    "asist": {"red": r'C:\Reloj\Bases\ASIGTURN.DBF', "loc": r'C:\proyecto_Asistencia\asistencia_temp.dbf'},
    "bano": {"red": r'\\CALIDAD\Bases\BANODBF.dbf', "loc": r'C:\proyecto_Asistencia\bano_temp.dbf'},
    "lab": r'C:\proyecto_Asistencia\laboratorio.db' # NUEVA RUTA SQLITE
}

# --- LISTAS DESPLEGABLES LABORATORIO ---
RESPONSABLES = ["Hernan Spataro", "Nahuel Ayala", "Fabian Rolon"]
BOCAS = ["10", "Rosca 9B", "Rosca 9A", "Rosca", "Monodisco", "20", "20 C/Anclaje", "13", "13 C/Anclaje"]
PAREDES = ["0.5", "0.75", "0.80", "0.90", "1.00", "1.10", "1.20"]
MAQUINAS = ["F1", "F2", "F3", "F4"]
HORNOS = ["H1", "H2", "H3", "H4", "H5"]

# --- INICIALIZADOR DE BASE DE DATOS ---
def inicializar_db():
    conn = sqlite3.connect(RUTAS["lab"])
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS analisis_hidrolitica (
            nro_analisis INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            hora TEXT,
            responsable TEXT,
            maquina TEXT,
            horno TEXT,
            cliente TEXT,
            medida TEXT,
            cod TEXT,
            boca TEXT,
            color TEXT,
            pared TEXT,
            impresion TEXT,
            tratado TEXT,
            lote_lumen TEXT,
            l_m_prima TEXT,
            batch TEXT,
            volumen TEXT,
            blanco REAL,
            titulacion REAL,
            resultado_final REAL,
            maximo REAL,
            observaciones TEXT
        )
    ''')
    conn.commit()
    conn.close()

# Ejecutamos esta función apenas arranca el sistema
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

# --- MOTORES LABORATORIO ---
def obtener_siguiente_nro_analisis():
    if not os.path.exists(RUTAS["lab"]): return 5000
    conn = sqlite3.connect(RUTAS["lab"])
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(nro_analisis) FROM analisis_hidrolitica")
    resultado = cursor.fetchone()[0]
    conn.close()
    return (resultado + 1) if resultado else 5000

def guardar_analisis_lab(datos):
    conn = sqlite3.connect(RUTAS["lab"])
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO analisis_hidrolitica (
            nro_analisis, fecha, hora, responsable, maquina, horno, cliente, medida, cod, boca, 
            color, pared, impresion, tratado, lote_lumen, l_m_prima, batch, volumen, blanco, 
            titulacion, resultado_final, maximo, observaciones
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    ''', datos)
    conn.commit()
    conn.close()

def cargar_historial_lab():
    if not os.path.exists(RUTAS["lab"]): return pd.DataFrame()
    conn = sqlite3.connect(RUTAS["lab"])
    df = pd.read_sql_query("SELECT * FROM analisis_hidrolitica ORDER BY nro_analisis DESC", conn)
    conn.close()
    return df

# --- 3. INTERFAZ Y SOLAPAS ---
tab1, tab2, tab3, tab4 = st.tabs(["🕒 ASISTENCIA", "🚻 BAÑO", "☕ DESCANSO", "🔬 LABORATORIO"])
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

# ==========================================
# PESTAÑA 4: LABORATORIO (¡NUEVO!)
# ==========================================
with tab4:
    st.header("🔬 Control de Calidad: Resistencia Hidrolítica")
    tab_lab1, tab_lab2 = st.tabs(["📝 Nuevo Análisis (Tablet)", "📚 Historial de Registros"])

    # --- SUB-PESTAÑA 1: CARGA DE DATOS ---
    with tab_lab1:
        nro_actual = obtener_siguiente_nro_analisis()
        st.markdown(f"### Análisis Nro: **{nro_actual}**")
        
        # Usamos columnas para simular el formulario de papel
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            resp = st.selectbox("Responsable", RESPONSABLES)
            cli = st.text_input("Cliente")
            lote_lum = st.text_input("Lote Lumen")
        with col2:
            maq = st.selectbox("Máquina", MAQUINAS)
            med = st.text_input("Medida")
            l_mp = st.text_input("L.M.Prima")
        with col3:
            hor = st.selectbox("Horno", HORNOS)
            cod = st.text_input("Cod.")
            batch = st.text_input("Batch")
        with col4:
            boc = st.selectbox("Boca", BOCAS)
            col_vid = st.selectbox("Color", ["Ambar", "Incoloro"])
            par = st.selectbox("Pared", PAREDES)
            
        col_c1, col_c2, col_c3 = st.columns(3)
        with col_c1:
            imp = st.text_input("Impresión")
        with col_c2:
            trat = st.radio("Tratado", ["Si", "No"], horizontal=True)
        with col_c3:
            vol = st.radio("Vol. Analizado", ["50%", "100%"], horizontal=True)

        st.markdown("---")
        st.markdown("#### 🧪 Resultados de Titulación")
        c_tit1, c_tit2, c_tit3, c_tit4 = st.columns(4)
        
        with c_tit1: blanco = st.number_input("Blanco (ml)", min_value=0.0, step=0.01, format="%.2f")
        with c_tit2: titulacion = st.number_input("Titulación (ml)", min_value=0.0, step=0.01, format="%.2f")
        with c_tit3: maximo = st.number_input("Máximo Permitido", min_value=0.0, step=0.01, format="%.2f")
        
        # CÁLCULO MATEMÁTICO EN VIVO
        resultado_calc = 0.0
        if vol == "50%":
            resultado_calc = (titulacion - blanco) * 2
        else:
            resultado_calc = titulacion - blanco
            
        with c_tit4:
            # Mostramos el resultado con colores dependiendo si aprueba o no
            if maximo > 0 and resultado_calc > maximo:
                st.error(f"RESULTADO FINAL: {resultado_calc:.2f} (RECHAZADO)")
            else:
                st.success(f"RESULTADO FINAL: {resultado_calc:.2f} (OK)")

        obs = st.text_area("Observaciones")

        # BOTÓN DE GUARDADO
        if st.button("💾 Guardar Análisis", use_container_width=True, type="primary"):
            ahora = datetime.datetime.now()
            datos_insertar = (
                nro_actual, ahora.strftime("%Y-%m-%d"), ahora.strftime("%H:%M:%S"),
                resp, maq, hor, cli, med, cod, boc, col_vid, par, imp, trat, 
                lote_lum, l_mp, batch, vol, blanco, titulacion, resultado_calc, maximo, obs
            )
            try:
                guardar_analisis_lab(datos_insertar)
                st.success(f"✅ Análisis {nro_actual} guardado exitosamente. La pantalla se actualizará para el próximo.")
                st.rerun() # Recarga la app para limpiar el formulario e incrementar el número
            except Exception as e:
                st.error(f"Error al guardar: {e}")

    # --- SUB-PESTAÑA 2: HISTORIAL ---
    with tab_lab2:
        df_lab = cargar_historial_lab()
        if not df_lab.empty:
            st.markdown("### 📚 Búsqueda de Historial")
            col_b1, col_b2 = st.columns(2)
            with col_b1: buscar_lote = st.text_input("🔍 Buscar por Lote Lumen")
            with col_b2: buscar_cli = st.text_input("🔍 Buscar por Cliente")
            
            # Filtros dinámicos
            df_mostrar = df_lab.copy()
            if buscar_lote: df_mostrar = df_mostrar[df_mostrar['lote_lumen'].str.contains(buscar_lote, case=False, na=False)]
            if buscar_cli: df_mostrar = df_mostrar[df_mostrar['cliente'].str.contains(buscar_cli, case=False, na=False)]
            
            st.dataframe(df_mostrar, use_container_width=True)
            csv_lab = df_mostrar.to_csv(index=False, sep=';').encode('utf-8-sig')
            st.download_button("📥 Exportar a Excel (CSV)", csv_lab, "historial_laboratorio.csv", "text/csv")
        else:
            st.info("Aún no hay registros en la base de datos de laboratorio.")

st.sidebar.markdown("### ⚙️ Sistema")
if st.sidebar.button("🔄 Sincronizar Todo"):
    st.cache_data.clear()
    st.rerun()