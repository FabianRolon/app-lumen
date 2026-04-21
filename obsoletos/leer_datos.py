from dbfread import DBF
import pandas as pd

# 1 y 2. Cargamos el archivo y limpiamos las columnas (lo que ya hicimos)
archivo_dbf = DBF('ASIGTURN.dbf', encoding='latin1') 
tabla_completa = pd.DataFrame(iter(archivo_dbf))

columnas_vip = ['LEGAJO', 'NOMBRE', 'FECHA', 'HORAI', 'HORAE', 'TOTALH']
tabla_limpia = tabla_completa[columnas_vip]

# ---------------- LO NUEVO EMPIEZA ACÁ ----------------

# 3. Nos aseguramos de que Python lea los legajos como números
tabla_limpia['LEGAJO'] = pd.to_numeric(tabla_limpia['LEGAJO'], errors='coerce')

# 4. Definimos a quién buscamos
legajo_buscado = 30

# 5. ¡Aplicamos el filtro mágico!
resultados = tabla_limpia[tabla_limpia['LEGAJO'] == legajo_buscado]

# 6. Mostramos los resultados
print(f"\nBuscando movimientos del Legajo {legajo_buscado}...")
print(f"¡Se encontraron {len(resultados)} registros en total!")
print("\nAquí están los primeros 5 movimientos de este empleado:")
print(resultados.head())