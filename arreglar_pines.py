import streamlit as st
import sqlite3
from config import RUTAS

st.title("🔧 Actualizador de PINs (DNI a partir de CUIL)")

if st.button("🚀 Ejecutar corrección de PINs", type="primary"):
    try:
        conn = sqlite3.connect(RUTAS["lab"])
        cursor = conn.cursor()
        
        cursor.execute("SELECT legajo, cuil FROM credenciales_empleados")
        empleados = cursor.fetchall()
        
        actualizados = 0
        
        for legajo, cuil in empleados:
            if cuil and str(cuil).strip() != "":
                cuil_limpio = str(cuil).replace("-", "").strip()
                
                if len(cuil_limpio) >= 5:
                    # Toma los 4 dígitos antes del último
                    nuevo_pin = cuil_limpio[-5:-1]
                    
                    cursor.execute("UPDATE credenciales_empleados SET pin = ? WHERE legajo = ?", (nuevo_pin, legajo))
                    actualizados += 1
                    
                    st.success(f"✅ Legajo {legajo} | CUIL: {cuil_limpio} -> **Nuevo PIN: {nuevo_pin}**")
                else:
                    st.warning(f"⚠️ Legajo {legajo} ignorado (CUIL muy corto: {cuil_limpio})")
            else:
                st.info(f"ℹ️ Legajo {legajo} ignorado (No tiene CUIL cargado)")
                
        conn.commit()
        conn.close()
        
        st.balloons()
        st.success(f"🎉 ¡Proceso finalizado! Se actualizaron {actualizados} PINs en la base de datos.")
        
    except Exception as e:
        st.error(f"❌ Error al actualizar: {e}")