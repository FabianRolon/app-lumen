import pandas as pd
from dbfread import DBF
import sqlite3

def convertir_dbf_a_sqlite(ruta_dbf, nombre_tabla_nueva, ruta_sqlite):
    print(f"Abriendo archivo {ruta_dbf}...")
    
    try:
        # 1. Leemos el DBF viejo (usamos latin1 por las eñes y acentos)
        tabla_dbf = DBF(ruta_dbf, encoding='latin1')
        
        # 2. Lo convertimos a una tabla de Pandas (DataFrame)
        df = pd.DataFrame(iter(tabla_dbf))
        
        # Mostramos las primeras filas y columnas para chusmear qué tiene
        print("\nColumnas encontradas:", df.columns.tolist())
        print(f"Total de registros: {len(df)}")
        
        # 3. Lo inyectamos en nuestra base SQLite nueva
        conn = sqlite3.connect(ruta_sqlite)
        # if_exists='replace' borra la tabla si ya existe y la crea de cero
        df.to_sql(nombre_tabla_nueva, conn, if_exists='replace', index=False)
        conn.close()
        
        print(f"\n✅ ¡Éxito! La tabla '{nombre_tabla_nueva}' se guardó en SQLite.")
        
    except Exception as e:
        print(f"❌ Ocurrió un error: {e}")

# --- ZONA DE EJECUCIÓN ---
# Cambiá estos nombres por las rutas reales de tus archivos
ARCHIVO_VIEJO = "DESPLOTE.DBF" 
NUEVA_TABLA = "LOTESMP"
MI_BASE_SQLITE = "laboratorio.db" # O podemos crear una nueva como "erp.db"

convertir_dbf_a_sqlite(ARCHIVO_VIEJO, NUEVA_TABLA, MI_BASE_SQLITE)