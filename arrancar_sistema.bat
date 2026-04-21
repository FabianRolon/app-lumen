@echo off
cd /d C:\proyecto_Asistencia
call entorno_dbf\Scripts\activate
streamlit run app.py --server.port 8501
--server.address 0.0.0.0 --server.headless
true