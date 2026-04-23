import os
import shutil

def organizar_txts():
    # Configuración
    carpeta_destino = "copias_txt"
    carpetas_a_ignorar = [carpeta_destino, "entorno_dbf", "__pycache__", ".git"]
    
    # Crear la carpeta de salida
    if not os.path.exists(carpeta_destino):
        os.makedirs(carpeta_destino)
        print(f"Directorio de salida listo: '{carpeta_destino}'\n")

    for raiz, directorios, archivos in os.walk('.'):
        # Filtramos 'directorios' para que os.walk no entre en las carpetas ignoradas
        # Esto hace que el script sea mucho más rápido
        directorios[:] = [d for d in directorios if d not in carpetas_a_ignorar]
        
        for archivo in archivos:
            if archivo.endswith('.py'):
                ruta_origen = os.path.join(raiz, archivo)
                
                # Crear nombre descriptivo basado en la ruta para evitar duplicados
                # Ejemplo: ./modulo/db.py -> modulo_db.txt
                ruta_relativa = os.path.relpath(raiz, '.')
                if ruta_relativa == '.':
                    nuevo_nombre = archivo.replace('.py', '.txt')
                else:
                    prefijo = ruta_relativa.replace(os.sep, '_')
                    nuevo_nombre = f"{prefijo}_{archivo.replace('.py', '.txt')}"
                
                ruta_destino = os.path.join(carpeta_destino, nuevo_nombre)

                try:
                    # Usamos copy2 para preservar metadatos (fecha de creación, etc.)
                    shutil.copy2(ruta_origen, ruta_destino)
                    print(f"Copiado: {ruta_origen} -> {ruta_destino}")
                except Exception as e:
                    print(f"Error con {archivo}: {e}")

if __name__ == "__main__":
    organizar_txts()