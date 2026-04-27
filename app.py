import streamlit as st
import pandas as pd
import datetime
import os
import shutil
import sqlite3
import dbf
from streamlit_option_menu import option_menu

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
aplicar_estilos()
inicializar_db()

# --- MOTORES DE ADMINISTRACIÓN ---
def obtener_consumos_pendientes():
    if not os.path.exists(RUTAS["lab"]): return pd.DataFrame()
    conn = sqlite3.connect(RUTAS["lab"])
    df = pd.read_sql_query("SELECT * FROM consumos_planta WHERE estado_sync = 'PENDIENTE'", conn)
    conn.close()
    return df

def sincronizar_stock_dbf():
    df_pendientes = obtener_consumos_pendientes()
    if df_pendientes.empty: return 0, "No hay consumos pendientes."
    
    # 1. VOLVEMOS A TUS VARIABLES ORIGINALES (usamos fillna(0) por seguridad matemática)
    df_pendientes['kilos_totales'] = df_pendientes['kilos_usados'].fillna(0) + df_pendientes['descarte_kg'].fillna(0)
    df_agrupado = df_pendientes.groupby(['codigo_mp', 'origen'], as_index=False)[['kilos_totales', 'tubos_usados']].sum()
    
    consumos_dict = {}
    for index, row in df_agrupado.iterrows():
        # 2. MEJORA DE SEGURIDAD: Usamos una "tupla" en lugar de un texto con guiones bajos.
        # Así, si tu código es "Z_014", no se rompe la separación.
        llave = (str(row['codigo_mp']).strip().upper(), str(row['origen']).strip().upper())
        consumos_dict[llave] = {'k': float(row['kilos_totales']), 't': int(row['tubos_usados']), 'encontrado': False}
    
    mapa_origen_inverso = {'BRASIL': '1', 'CHINA': '2', 'EE.UU.': '3'}
    
    try:
        shutil.copy2(RUTAS["stock_movimientos"]["red"], RUTAS["stock_movimientos"]["loc"])
        backup_name = f"STOCKMA_BACKUP_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.dbf"
        backup_path = os.path.join(os.path.dirname(RUTAS["stock_movimientos"]["red"]), backup_name)
        shutil.copy2(RUTAS["stock_movimientos"]["red"], backup_path)
        
        items_actualizados = 0

        with dbf.Table(RUTAS["stock_movimientos"]["loc"]) as tabla_maestra:
            tabla_maestra.open(mode=dbf.READ_WRITE)
            
            for registro in tabla_maestra:
                # 3. VAMOS DIRECTO A LA COLUMNA "ANO"
                try: 
                    ano_registro = int(getattr(registro, 'ANO')) 
                except: 
                    ano_registro = 0
                    
                # Volvemos a tu filtro del 2026
                if ano_registro == 2026:
                    cod_registro = str(registro.CODIGO).strip().upper()
                    try: ori_registro = str(registro.ORIGEN).strip().replace('.0', '')
                    except: ori_registro = "-"
                    
                    # Leemos directamente la tupla
                    for (cod_pend, ori_pend), valores in consumos_dict.items():
                        ori_pend_traducido = mapa_origen_inverso.get(ori_pend, ori_pend)
                        
                        if cod_registro == cod_pend and ori_registro == ori_pend_traducido:
                            k_restar = valores['k']
                            t_restar = valores['t']
                            
                            if k_restar > 0 or t_restar > 0:
                                nuevo_kilos = float(registro.TKGSTOCK) - k_restar
                                nuevo_tubos = float(registro.TUBOSSTOCK) - t_restar
                                dbf.write(registro, TKGSTOCK=nuevo_kilos, TUBOSSTOCK=nuevo_tubos)
                                
                                valores['k'] = 0.0
                                valores['t'] = 0
                                valores['encontrado'] = True
                                items_actualizados += 1

        shutil.copy2(RUTAS["stock_movimientos"]["loc"], RUTAS["stock_movimientos"]["red"])
        
        if items_actualizados > 0:
            conn = sqlite3.connect(RUTAS["lab"])
            cursor = conn.cursor()
            cursor.execute("UPDATE consumos_planta SET estado_sync = 'PROCESADO' WHERE estado_sync = 'PENDIENTE'")
            conn.commit()
            conn.close()
            st.cache_data.clear()
            return len(df_pendientes), f"✅ Sincronización exitosa. Se actualizaron {items_actualizados} artículos."
        else:
            detalles_perdidos = [f"{k[0]} (Origen: {k[1]})" for k, v in consumos_dict.items() if not v['encontrado']]
            return 0, f"⚠️ Alerta: Ningún código del informe se encontró en el DBF. Revisar: {', '.join(detalles_perdidos)}"

    except Exception as e:
        return -1, f"Error crítico: {e}"

# ==========================================
# GESTOR DE PERFILES Y RUTEO DE PANTALLAS
# ==========================================
with st.sidebar:
    st.markdown("## ⚙️ Lumen Glass")
    st.markdown("---")
    perfil = option_menu(
        "Panel de Control", 
        ["Planta", "Laboratorio", "Administrador"], 
        icons=['gear-fill', 'eyedropper', 'briefcase-fill'], 
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
    st.sidebar.markdown("---")
    clave = st.sidebar.text_input("🔑 Contraseña:", type="password")
    if clave == "admin123":
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
            st.markdown("### 📦 Inventario de Materia Prima (Año 2026)")
            df_pendientes = obtener_consumos_pendientes()
            if not df_pendientes.empty:
                st.warning(f"🔔 ¡Atención! Hay **{len(df_pendientes)}** reportes de consumo de Planta esperando ser descontados.")
                
                st.markdown("**🔍 Detalle de los movimientos a descontar:**")
                st.dataframe(
                    df_pendientes[['fecha', 'hora', 'maquina', 'codigo_mp', 'origen', 'kilos_usados', 'tubos_usados', 'desc_destruido']], 
                    use_container_width=True, 
                    hide_index=True
                )
                
                if st.button("⚙️ APROBAR Y DESCONTAR DEL STOCK", type="primary"):
                    with st.spinner("Modificando base central y creando backup de seguridad..."):
                        filas, msg = sincronizar_stock_dbf()
                        if filas > 0:
                            st.success(f"✅ Se aplicaron {filas} reportes. {msg}")
                            import time
                            time.sleep(2)
                            st.rerun()
                        else:
                            st.error(msg)
            else:
                st.success("✅ Sistema sincronizado. Todo el consumo ha sido descontado.")
            
            st.markdown("---")
            df_st = cargar_stock_fusionado()
            if df_st.empty:
                st.warning("No hay datos de stock disponibles.")
            else:
                cs1, cs2, cs3 = st.columns(3)
                with cs1: b_cod = st.text_input("🔍 Buscar Código", key="st_b_cod")
                with cs2: b_desc = st.text_input("📝 Buscar por Descripción", key="st_b_desc")
                with cs3: 
                    origenes_disp = ["Todos"] + sorted([o for o in df_st['ORIGEN'].unique() if o not in ["-", "nan", ""]])
                    b_ori = st.selectbox("🌍 Filtrar por Origen", origenes_disp, key="st_b_ori")
                
                df_st_f = df_st.copy()
                if b_cod: df_st_f = df_st_f[df_st_f['CODIGO'].str.contains(b_cod.upper(), case=False)]
                if b_desc: df_st_f = df_st_f[df_st_f['DESCRIP'].str.contains(b_desc.upper(), case=False)]
                if b_ori != "Todos": df_st_f = df_st_f[df_st_f['ORIGEN'] == b_ori]

                columnas_deseadas = ['CODIGO', 'DESCRIP', 'ORIGEN', 'TKGSTOCK', 'TUBOSSTOCK', 'CANT_PALLETS', 'TUBOPALLET', 'PESOTUBO']
                columnas_finales = [c for c in columnas_deseadas if c in df_st_f.columns]
                columnas_resto = [c for c in df_st_f.columns if c not in columnas_finales]
                df_st_f = df_st_f[columnas_finales + columnas_resto]

                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Kilos Totales", f"{df_st_f['TKGSTOCK'].sum():,.2f} kg")
                m2.metric("Unidades de Tubos", f"{int(df_st_f['TUBOSSTOCK'].sum()):,}")
                m3.metric("Pallets Totales", f"{df_st_f['CANT_PALLETS'].sum():,.2f}")
                m4.metric("Códigos", len(df_st_f))

                df_vista = df_st_f.rename(columns={
                    'CODIGO': 'CÓDIGO', 'DESCRIP': 'DESCRIPCIÓN', 'ORIGEN': 'ORIGEN',
                    'TKGSTOCK': 'STOCK (KG)', 'TUBOSSTOCK': 'STOCK (TUBOS)',
                    'CANT_PALLETS': 'PALLETS', 'TUBOPALLET': 'TUB/PALLET', 'PESOTUBO': 'PESO/TUBO'
                })
                
                st.dataframe(df_vista, use_container_width=True, hide_index=True)
                st.markdown("---")
                fecha_hoy = datetime.datetime.now().strftime("%Y-%m-%d")
                csv_data = df_vista.to_csv(index=False, sep=';', encoding='utf-8-sig').encode('utf-8-sig')
                
                st.download_button(
                    label="📥 DESCARGAR INFORME PARA DIRECCIÓN (EXCEL)",
                    data=csv_data, file_name=f"Informe_Stock_Materia_Prima_{fecha_hoy}.csv",
                    mime="text/csv", use_container_width=True
                )

        with tab8:
            # ... dentro de la pestaña de Seguridad y RRHH ...
            st.subheader("👥 Gestión de Accesos (ISO 9001)")
            
            col1, col2 = st.columns([1, 3])
            with col1:
                st.info("Sincroniza la nómina desde el sistema central. Los nuevos empleados tendrán por defecto el rol 'Planta' y un PIN inicial (últimos 4 del CUIL).")
                if st.button("🔄 Sincronizar Empleados (DBF)", use_container_width=True):
                    with st.spinner("Leyendo base Legada..."):
                        # Importa la función arriba en tu app.py si no lo hiciste
                        exito, mensaje = sincronizar_personal_dbf()
                        if exito:
                            st.success(mensaje)
                            st.rerun() # Recarga la tabla de abajo
                        else:
                            st.error(mensaje)
            
            with col2:
                # Cargar y mostrar la tabla editable
                conn = sqlite3.connect(RUTAS["lab"])
                
                # Escudo Anti-Crash: Intentamos leer, si la tabla no existe, devolvemos un DataFrame vacío
                try:
                    df_usuarios = pd.read_sql_query("SELECT dni as DNI, legajo as Legajo, nombre as Nombre, rol as Rol FROM credenciales_empleados WHERE estado='ACTIVO'", conn)
                except sqlite3.OperationalError: # Ocurre si la tabla "credenciales_empleados" no existe
                    df_usuarios = pd.DataFrame()
                except Exception:
                    df_usuarios = pd.DataFrame()
                
                if not df_usuarios.empty:
                    st.write("**Personal Activo en el Sistema** (Editá la columna 'Rol' y presioná Guardar)")
                    
                    # Tabla editable (RBAC)
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
                    # Este es el cartel que te mostrará ahora de forma elegante en vez de explotar
                    st.warning("No hay empleados en la base de datos segura. Por favor, presioná 'Sincronizar' a la izquierda.")
                
                conn.close()

    elif clave != "": st.sidebar.error("Contraseña incorrecta")
    else: st.warning("🔒 Ingrese la contraseña en el menú lateral para acceder a la Administración.")

st.sidebar.markdown("---")
st.sidebar.markdown("### ⚙️ Sistema")
if st.sidebar.button("🔄 Sincronizar Todo"):
    st.cache_data.clear()
    st.rerun()