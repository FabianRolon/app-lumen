import sqlite3
import pandas as pd
from datetime import datetime

def generar_stock_inicial():
    print("Iniciando la creación del inventario Día Cero...")
    # Conectamos a tu base de datos actual
    conn = sqlite3.connect("laboratorio.db")
    
    # Buscamos la tabla vieja y traemos solo lo que tiene stock real hoy
    # (Ajustá el nombre 'stockma' si en tu SQLite quedó guardada con otro nombre)
    query = """
    SELECT 
        CODIGO as CODIGOMP,
        ORIGEN,
        TKGSTOCK as KILOS_ACTUALES,
        TUBOSSTOCK as TUBOS_ACTUALES
    FROM stock_materiaprima
    WHERE TKGSTOCK > 0 AND CAST(ANO AS TEXT) = '2026'
    """
    
    try:
        # Leemos los datos
        df_stock = pd.read_sql_query(query, conn)
        
        # Agregamos las columnas fijas para cumplir con la trazabilidad ISO
        df_stock['LOTE'] = 'STK_INICIAL'
        df_stock['BATCH'] = 'MIGRACION'
        df_stock['FECHA_INGRESO'] = datetime.now().strftime("%Y-%m-%d")
        
        # Acomodamos el orden de las columnas para que quede prolijo
        columnas_finales = ['CODIGOMP', 'ORIGEN', 'LOTE', 'BATCH', 'KILOS_ACTUALES', 'TUBOS_ACTUALES', 'FECHA_INGRESO']
        df_stock = df_stock[columnas_finales]
        
        # Volcamos todo en la tabla definitiva del ERP
        df_stock.to_sql("mp_stock", conn, if_exists="replace", index=False)
        
        print(f"✅ ¡Éxito! Se migraron {len(df_stock)} artículos con stock positivo.")
        print("\nAsí quedó la foto de tu nuevo almacén (Primeros 5 registros):")
        print(df_stock.head())
        
    except Exception as e:
        print(f"❌ Ocurrió un error: {e}")
        print("💡 Consejo: Revisá si el nombre de la tabla vieja en SQLite es exactamente 'stockma'.")
    finally:
        conn.close()

# Ejecutamos el script
generar_stock_inicial()