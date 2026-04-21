from dbfread import DBF
import os

RUTA_BANO = r'\\CALIDAD\Bases\BANODBF.dbf'

if os.path.exists(RUTA_BANO):
    tabla = DBF(RUTA_BANO, encoding='latin1')
    print("✅ Conexión exitosa!")
    print("📋 Las columnas de esta base son:")
    print(tabla.field_names) # Esto nos dará el mapa de la base
else:
    print("❌ No se encuentra la ruta. Verificá si tenés acceso a \\CALIDAD")