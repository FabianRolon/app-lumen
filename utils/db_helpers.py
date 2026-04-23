import sqlite3
from config import RUTAS

def inicializar_db():
    conn = sqlite3.connect(RUTAS["lab"])
    cursor = conn.cursor()
    
    # 1. Tabla Laboratorio (Mantenemos igual)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS analisis_hidrolitica (
            nro_analisis INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT, hora TEXT, responsable TEXT, maquina TEXT, horno TEXT, temperatura TEXT,
            cliente TEXT, medida TEXT, capacidad TEXT, cod TEXT, boca TEXT, color TEXT,
            pared TEXT, impresion TEXT, tratado TEXT, lote_lumen TEXT,
            l_m_prima TEXT, batch TEXT, volumen TEXT, blanco REAL,
            titulacion REAL, resultado_final REAL, maximo REAL, observaciones TEXT,
            nro_certificado INTEGER
        )
    ''')

    # 2. Tabla Consumos y Producción (IDP 71 REV 4)
    # Agregamos campos de producción total y desglose de descarte
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS consumos_planta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT, hora TEXT, maquina TEXT,
            codigo_mp TEXT, origen TEXT, kilos_usados REAL, tubos_usados INTEGER,
            prod_total INTEGER, desc_destruido REAL, desc_recuperable REAL, 
            estado_sync TEXT
        )
    ''')
    # Migración silenciosa por si las columnas no existen
    columnas_idp = [
        ("prod_total", "INTEGER"), 
        ("desc_destruido", "REAL"), 
        ("desc_recuperable", "REAL")
    ]
    for col, tipo in columnas_idp:
        try: cursor.execute(f"ALTER TABLE consumos_planta ADD COLUMN {col} {tipo}")
        except: pass

    # 3. Tabla de Control Dimensional (CP 71 REV 3)
    # Actualizamos para los 5 campos específicos del papel
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS controles_proceso (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT, hora TEXT, maquina TEXT, codigo_mp TEXT,
            legajo_operario TEXT, largo REAL, diam_int_boca REAL, 
            diam_ext_boca REAL, altura_labio REAL, espesor_fondo REAL,
            defecto_visual TEXT, estado TEXT, accion_correctiva TEXT
        )
    ''')
    # Migración para CP 71
    columnas_cp = [
        ("largo", "REAL"), ("diam_int_boca", "REAL"), 
        ("diam_ext_boca", "REAL"), ("altura_labio", "REAL"), 
        ("espesor_fondo", "REAL")
    ]
    for col, tipo in columnas_cp:
        try: cursor.execute(f"ALTER TABLE controles_proceso ADD COLUMN {col} {tipo}")
        except: pass

    # 4. Tabla de Paradas de Máquina (Nuevo del IDP 71)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS paradas_maquina (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT, hora_inicio TEXT, hora_fin TEXT, 
            maquina TEXT, causa TEXT, intervencion TEXT, responsable TEXT
        )
    ''')

    # 5. Tabla de Liberación (Los 9 puntos)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS liberacion_linea (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT, hora TEXT, maquina TEXT,
            codigo_mp TEXT, legajo_firma TEXT, estado TEXT
        )
    ''')

    # --- PROCESO DE TUBOS (Maquinas Planas) ---
    
    # Etapa 1: Corte de Tubos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS proceso_corte_tubos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT, hora TEXT, maquina TEXT, lote_lumen TEXT,
            legajo_operario TEXT, kg_vidrio_bruto REAL, kg_cortados REAL, descarte REAL
        )
    ''')

    # Etapa 2: Formado (Máquina Plana)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS proceso_maquina_tubos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT, hora TEXT, maquina TEXT, lote_lumen TEXT,
            legajo_operario TEXT, kg_cortados_usados REAL, unidades_ok INTEGER, 
            desc_destruido REAL, desc_recuperable REAL
        )
    ''')

    # Nueva Tabla: Registro de Embalaje
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS registro_embalaje (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            hora TEXT,
            turno TEXT,
            maquina TEXT,
            op TEXT,
            producto TEXT,
            embalador TEXT,
            cajas INTEGER,
            unidades_caja INTEGER,
            total_unidades INTEGER,
            descarte_unidades INTEGER,
            motivo_descarte TEXT,
            control_tension TEXT,
            control_visual TEXT,
            observaciones TEXT
        )
    ''')

    conn.commit()
    conn.close()