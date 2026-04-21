import sqlite3
import os

# Definimos dónde se va a guardar la base de datos
ruta_db = r'C:\proyecto_Asistencia\laboratorio.db'

# Nos conectamos (si el archivo no existe, SQLite lo crea mágicamente)
conexion = sqlite3.connect(ruta_db)
cursor = conexion.cursor()

# Creamos la estructura exacta de la tabla de Calidad
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

conexion.commit()
conexion.close()

print("¡Base de datos de Laboratorio creada con éxito en C:\proyecto_Asistencia!")