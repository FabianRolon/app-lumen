import sqlite3
import pandas as pd
import streamlit as st
from config import RUTAS

def obtener_batch_record(lote_lumen):
    """
    Busca toda la historia de un lote específico en las diferentes tablas de la base de datos.
    """
    # Verificamos que el lote no esté vacío
    if not lote_lumen or lote_lumen.strip() == "":
        return None

    lote_limpio = lote_lumen.strip().upper()
    
    try:
        conn = sqlite3.connect(RUTAS["lab"])
        
        # 1. Buscar en Consumos de Planta (Materia Prima usada)
        df_consumos = pd.read_sql_query(
            "SELECT fecha, hora, maquina, legajo_operario, kilos_usados, tubos_usados, origen FROM consumos_planta WHERE UPPER(lote_lumen) = ?", 
            conn, params=(lote_limpio,)
        )
        
        # 2. Buscar en Producción de Viales (Máquinas Planas/Rotativas)
        df_viales = pd.read_sql_query(
            "SELECT fecha, hora, maquina, legajo_operario, kg_cortados_usados, unidades_ok, desc_destruido, desc_recuperable FROM proceso_maquina_tubos WHERE UPPER(lote_lumen) = ?", 
            conn, params=(lote_limpio,)
        )
        
        # 3. Buscar en Corte de Tubos
        df_corte = pd.read_sql_query(
            "SELECT fecha, hora, maquina, legajo_operario, kg_vidrio_bruto, kg_cortados, descarte FROM proceso_corte_tubos WHERE UPPER(lote_lumen) = ?", 
            conn, params=(lote_limpio,)
        )
        
        # 4. Buscar en Laboratorio (Análisis Hidrolítica)
        df_lab = pd.read_sql_query(
            "SELECT nro_analisis, fecha, hora, responsable, resultado_final, observaciones FROM analisis_hidrolitica WHERE UPPER(lote_lumen) = ?", 
            conn, params=(lote_limpio,)
        )
        
        # 5. Buscar en Embalaje Final
        # Nota: En tu tabla de embalaje se guarda como 'op', buscamos ahí o en 'producto' por las dudas.
        df_embalaje = pd.read_sql_query(
            "SELECT fecha, hora, maquina, embalador, cajas, unidades_caja, total, descarte, motivo FROM registro_embalaje WHERE UPPER(op) = ? OR UPPER(producto) LIKE ?", 
            conn, params=(lote_limpio, f"%{lote_limpio}%")
        )
        
        conn.close()
        
        # Retornamos un diccionario con todos los DataFrames
        return {
            "consumos": df_consumos,
            "viales": df_viales,
            "corte": df_corte,
            "laboratorio": df_lab,
            "embalaje": df_embalaje
        }
        
    except Exception as e:
        st.error(f"Error al buscar la trazabilidad: {e}")
        return None