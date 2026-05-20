import streamlit as st
import pandas as pd
import datetime
import os
import shutil
import sqlite3
import dbf
import time
from streamlit_option_menu import option_menu
import modulos.trazabilidad as modulo_trazabilidad


# --- IMPORTACIONES DE LA NUEVA ARQUITECTURA ---
from config import RUTAS, aplicar_estilos
from utils.db_helpers import inicializar_db
from utils.data_core import (
    cargar_asistencia, cargar_pedidos_completos, cargar_produccion, 
    cargar_bano, cargar_stock_fusionado, sincronizar_personal_dbf
)
import modulos.planta as modulo_planta
import modulos.laboratorio as modulo_laboratorio

# --- 1. CONFIGURACIÓN INICIAL ---
st.set_page_config(page_title="LumenGlass 3.0 (ISO 9001)", layout="wide", initial_sidebar_state="expanded")
# --- INICIALIZAR MEMORIA DE SESIÓN ADMINISTRADOR ---
if "admin_auth" not in st.session_state:
    st.session_state.admin_auth = False
if "admin_last_activity" not in st.session_state:
    st.session_state.admin_last_activity = time.time()
aplicar_estilos()
inicializar_db()

# --- MOTORES DE ADMINISTRACIÓN ---
def obtener_consumos_pendientes():
    if not os.path.exists(RUTAS["lab"]): return pd.DataFrame()
    conn = sqlite3.connect(RUTAS["lab"])
    
    query = """
    /* SECTOR VIALES */
    SELECT 
        id, 
        fecha, 
        maquina, 
        codigo_mp,                         -- Nombre real en consumos_planta
        kilos_usados AS kilos_a_descontar, -- Mapeo de kilos
        tubos_usados AS tubos_a_descontar, -- Mapeo de tubos
        origen,
        'consumos_planta' AS tabla_origen,
        'Viales' AS SECTOR
    FROM consumos_planta 
    WHERE estado_sync = 'PENDIENTE'
    
    UNION ALL
    
    /* SECTOR CORTE */
    SELECT 
        id, 
        fecha, 
        maquina, 
        codigo_mp AS codigo_mp,           -- Usamos lote_lumen como el código del material
        kg_vidrio_bruto AS kilos_a_descontar, -- Mapeo de kilos (nombre distinto!)
        tubos_usados AS tubos_a_descontar,    -- Mapeo de tubos (columna nueva)
        origen,
        'proceso_corte_tubos' AS tabla_origen,
        'Corte' AS SECTOR
    FROM proceso_corte_tubos 
    WHERE estado_sync = 'PENDIENTE'
    """
    
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


def sincronizar_stock_dbf(anio_seleccionado):
    # 1. Obtenemos los pendientes
    df_pendientes = obtener_consumos_pendientes()
    if df_pendientes.empty: 
        return 0, ["No hay consumos pendientes."]
    
    ANIO_CORRIENTE = anio_seleccionado
    mapa_origenes = {"BRASIL": 1, "CHINA": 2, "EEUU": 3, "USA": 3}

    # 🛡️ BACKUP AUTOMÁTICO
    ruta_stock = RUTAS["stock_movimientos"]["red"]
    try:
        if os.path.exists(ruta_stock):
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            ruta_backup = ruta_stock.lower().replace(".dbf", f"_backup_{timestamp}.dbf")
            shutil.copy2(ruta_stock, ruta_backup)
    except Exception as e:
        return 0, [f"❌ Error al crear backup: {e}"]

    registros_aprobados = 0
    mensajes_log = []
    
    try:
        # Abrimos la tabla
        tabla_stock = dbf.Table(ruta_stock, codepage='cp1252')
        tabla_stock.open(mode=dbf.READ_WRITE)
        
        conn = sqlite3.connect(RUTAS["lab"])
        cursor = conn.cursor()

        for index, fila in df_pendientes.iterrows():
            try:
                codigo_tubo = str(fila['codigo_mp']).strip().upper()
                kilos_a_descontar = float(fila['kilos_a_descontar'])
                tubos_a_descontar = int(fila["tubos_a_descontar"])
                id_registro = fila['id']
                tabla_origen = fila['tabla_origen']
                origen_texto = str(fila['origen']).strip().upper()
                id_origen = mapa_origenes.get(origen_texto, 0)
                
                encontrado = False

                # 🚀 SOLUCIÓN AL ERROR: Búsqueda manual compatible
                # Recorremos la tabla buscando la coincidencia de los 3 campos
                for registro in tabla_stock:
                    # Extraemos y limpiamos los valores del DBF para comparar
                    cod_dbf = str(registro.CODIGO).strip().upper()
                    ori_dbf = int(registro.ORIGEN)
                    ani_dbf = int(registro.ANO)

                    if cod_dbf == codigo_tubo and ori_dbf == id_origen and ani_dbf == ANIO_CORRIENTE:
                        # Si coincide, procedemos al descuento
                        with registro:
                            # Importante: Usar el nombre exacto del campo (TKGSTOCK o STOCK)
                            registro.TKGSTOCK -= kilos_a_descontar
                            registro.TUBOSSTOCK -= tubos_a_descontar
                        encontrado = True
                        break # Salimos del loop una vez encontrado

                if encontrado:
                    query_update = f"UPDATE {tabla_origen} SET estado_sync = 'APROBADO' WHERE id = ?"
                    cursor.execute(query_update, (id_registro,))
                    registros_aprobados += 1
                    mensajes_log.append(f"✅ {codigo_tubo} ({origen_texto}): Descontado.")
                else:
                    mensajes_log.append(f"⚠️ {codigo_tubo}: No encontrado (Origen {origen_texto}, Año {ANIO_CORRIENTE}).")

            except Exception as e_fila:
                mensajes_log.append(f"❌ Error en {codigo_tubo}: {e_fila}")
            
        conn.commit()
        conn.close()
        tabla_stock.close()

        return registros_aprobados, mensajes_log

    except Exception as e:
        return 0, [f"Error crítico: {e}"]

# ==========================================
# GESTOR DE PERFILES Y RUTEO DE PANTALLAS
# ==========================================
with st.sidebar:
    st.markdown("## ⚙️ Lumen Glass")
    st.markdown("---")
    perfil = option_menu(
        "Panel de Control", 
        ["Planta", "Laboratorio", "Administrador", "Trazabilidad"], 
        icons=['gear-fill', 'eyedropper', 'briefcase-fill', 'search'], 
        menu_icon="cast", default_index=1, 
        styles={
            "container": {"padding": "0!important", "background-color": "transparent"},
            "icon": {"color": "#94a3b8", "font-size": "18px"}, 
            "nav-link": {"font-size": "16px", "text-align": "left", "margin":"0px", "--hover-color": "#334155"},
            "nav-link-selected": {"background-color": "#3b82f6", "color": "white", "font-weight": "normal"},
        }
    )
    st.markdown("---")
    st.caption("Sistema ISO 9001 v3.0")

# --- NAVEGACIÓN MODULAR ---
if perfil == "Planta":
    df_st = cargar_stock_fusionado()
    df_prod = cargar_produccion()
    modulo_planta.renderizar_planta(df_st, df_prod)

elif perfil == "Laboratorio":
    modulo_laboratorio.renderizar_modulo_laboratorio()

elif perfil == "Administrador":
        # 1. Configurar tiempo máximo de inactividad (Ej: 15 minutos = 900 segundos)
        TIEMPO_INACTIVIDAD = 900
        
        # 2. Control de Inactividad Silencioso
        if st.session_state.admin_auth:
            tiempo_pasado = time.time() - st.session_state.admin_last_activity
            if tiempo_pasado > TIEMPO_INACTIVIDAD:
                st.session_state.admin_auth = False # Forzar cierre de sesión
                st.sidebar.warning("⏱️ Sesión cerrada por inactividad.")
                st.rerun()
            else:
                # Si está activo dentro del administrador, renovamos el tiempo
                st.session_state.admin_last_activity = time.time()

        st.sidebar.markdown("---")
        
        # 3. Mostrar el Login (Si no está autorizado)
        if not st.session_state.admin_auth:
            st.sidebar.markdown("### Acceso Restringido")
            
            # Usamos un form para que pueda apretar "Enter" en el teclado
            with st.sidebar.form("login_admin"):
                clave = st.text_input("🔑 Contraseña:", type="password")
                submit_btn = st.form_submit_button("Ingresar")
                
                if submit_btn:
                    if clave == "admin123":
                        st.session_state.admin_auth = True
                        st.session_state.admin_last_activity = time.time()
                        st.rerun() # Recarga la pantalla y hace desaparecer el login
                    else:
                        st.error("Contraseña incorrecta")
            
            # Mensaje en la pantalla principal
            st.warning("🔒 Ingrese la contraseña en el menú lateral para acceder a la Administración.")

        # 4. Mostrar el Módulo Completo (Si ESTÁ autorizado)
        else:
            # Botón para cerrar la sesión manualmente
            if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True):
                st.session_state.admin_auth = False
                st.rerun()
                
            # ==========================================================
            # TU CÓDIGO ORIGINAL DEL ADMINISTRADOR (AHORA PROTEGIDO)
            # ==========================================================
            st.title("🏭 Nuevo Sistema Lumen Glass")
            tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8= st.tabs(["🕒 ASISTENCIA", "🚻 BAÑO", "☕ DESCANSO", "🔬 LABORATORIO", "📦 PEDIDOS", "🏭 PRODUCCIÓN", "📦 MATERIA PRIMA", "SEGURIDAD Y RRHH"])
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

            with tab4: modulo_laboratorio.renderizar_modulo_laboratorio()
            
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
                    st.warning("No se encontraron datos de producción.")
                else:
                    columnas_a_limpiar = ['LOTE_LUMEN', 'NOTA_PEDIDO', 'ORDEN_COMPRA', 'CANTIDAD', 'MAQUINA', 'BOCA']
                    for col in columnas_a_limpiar:
                        if col in df_prod.columns:
                            df_prod[col] = df_prod[col].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
                            df_prod[col] = df_prod[col].replace(['nan', 'None', ''], '-')

                    df_prod['lote_num'] = pd.to_numeric(df_prod['LOTE_LUMEN'], errors='coerce')
                    df_prod = df_prod.sort_values(by='lote_num', ascending=False).drop(columns=['lote_num'])

                    col_pr1, col_pr2, col_pr3, col_pr4 = st.columns(4)
                    with col_pr1: busq_lote_pr = st.text_input("Buscar por Lote Lumen", key="busq_lote_pr")
                    with col_pr2: busq_cli_pr = st.text_input("Buscar por Cliente", key="busq_cli_pr")
                    with col_pr3: busq_maq_pr = st.text_input("Filtrar por Máquina (Ej: F1)", key="busq_maq_pr")
                    with col_pr4: busq_np_pr = st.text_input("Buscar Nota de Pedido", key="busq_np_pr")

                    df_mostrar_pr = df_prod.copy()
                    if busq_lote_pr: df_mostrar_pr = df_mostrar_pr[df_mostrar_pr['LOTE_LUMEN'].astype(str).str.contains(busq_lote_pr, case=False, na=False)]
                    if busq_cli_pr: df_mostrar_pr = df_mostrar_pr[df_mostrar_pr['CLIENTE'].astype(str).str.contains(busq_cli_pr, case=False, na=False)]
                    if busq_maq_pr: df_mostrar_pr = df_mostrar_pr[df_mostrar_pr['MAQUINA'].astype(str).str.upper() == busq_maq_pr.upper()]
                    if busq_np_pr: df_mostrar_pr = df_mostrar_pr[df_mostrar_pr['NOTA_PEDIDO'].astype(str).str.contains(busq_np_pr, case=False, na=False)]

                    st.dataframe(df_mostrar_pr.head(1000), use_container_width=True)
                    st.download_button(label="📥 Exportar Producción a Excel", data=df_mostrar_pr.head(5000).to_csv(index=False, sep=';').encode('utf-8-sig'), file_name="ordenes_produccion.csv", mime="text/csv")

            with tab7:
                st.markdown("### 📦 Inventario de Materia Prima")
                anio_actual = 2026
                anio_seleccionado = anio_actual
                # 1. SECCIÓN DE PENDIENTES (SINCRONIZACIÓN)
                df_pendientes = obtener_consumos_pendientes()
                if not df_pendientes.empty:
                    st.write("### 📝 Consumos pendientes de aprobación")
                    
                    # Filtro rápido por sector para la tabla de arriba
                    sector_sel = st.selectbox("Filtrar por Sector:", ["Todos", "Corte", "Viales"])
                    df_mostrar_p = df_pendientes.copy()
                    if sector_sel != "Todos":
                        df_mostrar_p = df_mostrar_p[df_mostrar_p['SECTOR'] == sector_sel]

                    st.dataframe(df_mostrar_p, use_container_width=True)
                    
                    if st.button("Aprobar y Descontar Stock"):
                        aprobados, log = sincronizar_stock_dbf(anio_seleccionado)
                        st.success(f"Se aprobaron {aprobados} registros correctamente para el año {anio_seleccionado}.")
                        
                        with st.expander("Ver detalle de sincronización", expanded=True):
                            for linea in log:
                                if "✅" in linea: st.write(linea)
                                elif "⚠️" in linea: st.warning(linea)
                                else: st.error(linea)
                else:
                    st.success("✅ No hay consumos pendientes de aprobación.")
                
                st.markdown("---")

                # 2. SECCIÓN DE CONSULTA DE STOCK (INFORME CONTADURÍA)
                df_st = cargar_stock_fusionado()
                
                if df_st.empty:
                    st.warning("No hay datos de stock disponibles.")
                else:
                    # FILTROS
                    cs1, cs2, cs3, cs4 = st.columns(4)
                    with cs1: b_cod = st.text_input("🔍 Buscar Código", key="st_b_cod")
                    with cs2: b_desc = st.text_input("📝 Buscar por Descripción", key="st_b_desc")
                    with cs3: 
                        origenes_disp = ["Todos"] + sorted([o for o in df_st['ORIGEN'].unique() if o not in ["-", "nan", ""]])
                        b_ori = st.selectbox("🌍 Filtrar por Origen", origenes_disp, key="st_b_ori")
                    with cs4: 
                        anio_seleccionado = st.selectbox("📅 Seleccionar Año de Stock:", [2025, 2026], index=1)

                    # APLICACIÓN DE FILTROS EN EL DATAFRAME
                    df_st_f = df_st.copy()
                    
                    # FILTRO DE AÑO (CRÍTICO: Filtramos antes de calcular métricas)
                    columna_anio = 'ANO' 
            
                    if columna_anio in df_st_f.columns:
                        df_st_f[columna_anio] = df_st_f[columna_anio].astype(str).str.replace('.0', '', regex=False).str.strip()
                        df_st_f = df_st_f[df_st_f[columna_anio] == str(anio_seleccionado)]
                    else:
                        st.error(f"⚠️ Error: No existe la columna '{columna_anio}'. Las columnas que encontró son: {df_st_f.columns.tolist()}")
                    # ------------------------------
                    
                    if b_cod: 
                        df_st_f = df_st_f[df_st_f['CODIGO'].astype(str).str.contains(b_cod.upper(), case=False, na=False)]
                    if b_desc: 
                        df_st_f = df_st_f[df_st_f['DESCRIP'].astype(str).str.contains(b_desc.upper(), case=False, na=False)]
                    if b_ori != "Todos": 
                        df_st_f = df_st_f[df_st_f['ORIGEN'] == b_ori]

                    # REORDENAMIENTO DE COLUMNAS
                    columnas_deseadas = ['CODIGO', 'DESCRIP', 'ORIGEN', 'TKGSTOCK', 'TUBOSSTOCK', 'CANT_PALLETS', 'TUBOPALLET', 'PESOTUBO']
                    columnas_finales = [c for c in columnas_deseadas if c in df_st_f.columns]
                    columnas_resto = [c for c in df_st_f.columns if c not in columnas_finales]
                    df_st_f = df_st_f[columnas_finales + columnas_resto]

                    # MÉTRICAS DINÁMICAS
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric(f"Kilos Totales {anio_seleccionado}", f"{df_st_f['TKGSTOCK'].sum():,.2f} kg")
                    m2.metric(f"Unidades de Tubos", f"{int(df_st_f['TUBOSSTOCK'].sum()):,}")
                    m3.metric(f"Pallets Totales", f"{df_st_f['CANT_PALLETS'].sum():,.2f}")
                    m4.metric("Registros", len(df_st_f))

                    # VISTA DE TABLA
                    df_vista = df_st_f.rename(columns={
                        'CODIGO': 'CÓDIGO', 'DESCRIP': 'DESCRIPCIÓN', 'ORIGEN': 'ORIGEN',
                        'TKGSTOCK': 'STOCK (KG)', 'TUBOSSTOCK': 'STOCK (TUBOS)',
                        'CANT_PALLETS': 'PALLETS', 'TUBOPALLET': 'TUB/PALLET', 'PESOTUBO': 'PESO/TUBO'
                    })
                    
                    st.dataframe(df_vista, use_container_width=True, hide_index=True)
                    
                    st.markdown("---")
                    
                    # EXPORTACIÓN
                    csv_data = df_vista.to_csv(index=False, sep=';', encoding='utf-8-sig').encode('utf-8-sig')
                    
                    st.download_button(
                        label=f"📥 DESCARGAR INFORME STOCK {anio_seleccionado} (EXCEL)",
                        data=csv_data, 
                        file_name=f"Informe_Stock_MP_{anio_seleccionado}_{datetime.datetime.now().strftime('%d-%m')}.csv",
                        mime="text/csv", 
                        use_container_width=True
                    )

            with tab8:
                st.subheader("👥 Gestión de Accesos (ISO 9001)")
                
                col1, col2 = st.columns([1, 3])
                with col1:
                    st.info("Sincroniza la nómina desde el sistema central. Los nuevos empleados tendrán por defecto el rol 'Planta' y un PIN inicial (últimos 4 del CUIL).")
                    if st.button("🔄 Sincronizar Empleados (DBF)", use_container_width=True):
                        with st.spinner("Leyendo base Legada..."):
                            exito, mensaje = sincronizar_personal_dbf()
                            if exito:
                                st.success(mensaje)
                                st.rerun() # Recarga la tabla de abajo
                            else:
                                st.error(mensaje)
                
                with col2:
                    conn = sqlite3.connect(RUTAS["lab"])
                    try:
                        df_usuarios = pd.read_sql_query("SELECT dni as DNI, legajo as Legajo, nombre as Nombre, rol as Rol FROM credenciales_empleados WHERE estado='ACTIVO'", conn)
                    except sqlite3.OperationalError: 
                        df_usuarios = pd.DataFrame()
                    except Exception:
                        df_usuarios = pd.DataFrame()
                    
                    if not df_usuarios.empty:
                        st.write("**Personal Activo en el Sistema** (Editá la columna 'Rol' y presioná Guardar)")
                        
                        df_editado = st.data_editor(
                            df_usuarios,
                            column_config={
                                "Rol": st.column_config.SelectboxColumn(
                                    "Rol Asignado",
                                    help="Nivel de acceso en la app",
                                    options=["Planta", "Embalaje", "Laboratorio", "Administrador"],
                                    required=True
                                ),
                                "DNI": st.column_config.TextColumn(disabled=True),
                                "Legajo": st.column_config.TextColumn(disabled=True),
                                "Nombre": st.column_config.TextColumn(disabled=True)
                            },
                            hide_index=True,
                            use_container_width=True
                        )
                        
                        if st.button("💾 Guardar Cambios de Roles"):
                            cursor = conn.cursor()
                            for index, row in df_editado.iterrows():
                                cursor.execute("UPDATE credenciales_empleados SET rol=? WHERE dni=?", (row['Rol'], row['DNI']))
                            conn.commit()
                            st.success("✅ Roles actualizados correctamente.")
                    else:
                        st.warning("No hay empleados en la base de datos segura. Por favor, presioná 'Sincronizar' a la izquierda.")
                    
                    conn.close()

elif perfil == "Trazabilidad":
        st.title("🔍 Auditoría de Trazabilidad (Batch Record)")
        st.markdown("Ingrese el **Lote Lumen** para rastrear su historia de producción, calidad y materias primas.")

        # Buscador interactivo
        lote_buscar = st.text_input("Nº de Lote Lumen:", placeholder="Ej: 12345 o ELEA-123")

        if lote_buscar:
            with st.spinner("Buscando registros en todas las áreas..."):
                # Llamamos a nuestro nuevo motor
                datos_batch = modulo_trazabilidad.obtener_batch_record(lote_buscar)

            # Verificamos si encontró algo en alguna de las tablas
            if datos_batch and (not datos_batch["embalaje"].empty or not datos_batch["laboratorio"].empty or not datos_batch["viales"].empty):
                st.success(f"✅ Trazabilidad encontrada para el lote: **{lote_buscar.upper()}**")

                # --- MÉTRICAS RÁPIDAS ---
                st.markdown("### 📊 Resumen del Lote")
                col1, col2, col3, col4 = st.columns(4)
                
                # Cálculos seguros (por si alguna tabla está vacía)
                total_unidades = datos_batch["embalaje"]['total'].sum() if not datos_batch["embalaje"].empty else 0
                total_descarte = datos_batch["embalaje"]['descarte'].sum() if not datos_batch["embalaje"].empty else 0
                controles_lab = len(datos_batch["laboratorio"])
                kilos_mp = datos_batch["consumos"]['kilos_usados'].sum() if not datos_batch["consumos"].empty else 0
                
                col1.metric("📦 Unidades Embaladas", f"{total_unidades:,.0f}")
                col2.metric("🗑️ Descarte (Cajas)", f"{total_descarte:,.0f}")
                col3.metric("🧪 Análisis de Lab", controles_lab)
                col4.metric("⚖️ KG Materia Prima", f"{kilos_mp:,.2f}")
                
                st.markdown("---")

                # --- PESTAÑAS DE NAVEGACIÓN ---
                tab1, tab2, tab3, tab4 = st.tabs([
                    "📦 1. Embalaje Final", 
                    "🔬 2. Laboratorio", 
                    "⚙️ 3. Proceso de Máquina", 
                    "🗄️ 4. Materia Prima"
                ])
                
                with tab1:
                    st.markdown("**Registro de Fin de Línea**")
                    if not datos_batch["embalaje"].empty:
                        st.dataframe(datos_batch["embalaje"], use_container_width=True, hide_index=True)
                    else:
                        st.info("No hay registros de embalaje para este lote aún.")
                        
                with tab2:
                    st.markdown("**Análisis de Resistencia Hidrolítica**")
                    if not datos_batch["laboratorio"].empty:
                        st.dataframe(datos_batch["laboratorio"], use_container_width=True, hide_index=True)
                    else:
                        st.info("El laboratorio aún no cargó resultados para este lote.")
                        
                with tab3:
                    st.markdown("**Producción de Viales**")
                    if not datos_batch["viales"].empty:
                        st.dataframe(datos_batch["viales"], use_container_width=True, hide_index=True)
                    st.markdown("**Corte de Tubos**")
                    if not datos_batch["corte"].empty:
                        st.dataframe(datos_batch["corte"], use_container_width=True, hide_index=True)
                        
                with tab4:
                    st.markdown("**Consumo y Origen de Materia Prima**")
                    if not datos_batch["consumos"].empty:
                        st.dataframe(datos_batch["consumos"], use_container_width=True, hide_index=True)
                    else:
                        st.info("Aún no se descontó materia prima en el sistema para este lote.")
                        
                # Espacio para el futuro botón de PDF (Fase 3)
                st.markdown("---")
                st.button("📄 Generar Batch Record Oficial (PDF)", disabled=True, help="Próximamente")

            else:
                st.warning(f"No se encontraron registros para el lote '{lote_buscar}'. Verifique que esté bien escrito o que ya haya sido procesado en planta.")

st.sidebar.markdown("---")
st.sidebar.markdown("### ⚙️ Sistema")
if st.sidebar.button("🔄 Sincronizar Todo"):
    st.cache_data.clear()
    st.rerun()