import streamlit as st

# --- RUTAS DE BASES DE DATOS ---
RUTAS = {
    "asist": {"red": r'C:\Reloj\Bases\ASIGTURN.DBF', "loc": r'C:\proyecto_Asistencia\asistencia_temp.dbf'},
    "bano": {"red": r'\\CALIDAD\Bases\BANODBF.dbf', "loc": r'C:\proyecto_Asistencia\bano_temp.dbf'},
    "lab": r'C:\proyecto_Asistencia\laboratorio.db',
    "pedidos": {"red": r'\\LUMENGLASS\Sistemas\Bases\REMENCA.dbf', "loc": r'C:\proyecto_Asistencia\remenca_temp.dbf'},
    "remitos": {"red": r'\\LUMENGLASS\Sistemas\Bases\REMITOS.dbf', "loc": r'C:\proyecto_Asistencia\remitos_temp.dbf'},
    "produccion": {"red": r'\\LUMENGLASS\Sistemas\Bases\ORDPRODU.dbf', "loc": r'C:\proyecto_Asistencia\ordprodu_temp.dbf'},
    "maestro_clientes": {"red": r'\\LUMENGLASS\Sistemas\Bases\CLIENTES.dbf', "loc": r'C:\proyecto_Asistencia\clientes_temp.dbf'},
    "certificados": r'\\CALIDAD\certificados de calidad',
    "stock_movimientos": {"red": r'\\LUMENGLASS\Sistemas\Bases\STOCKMA.dbf', "loc": r'C:\proyecto_Asistencia\stockma_temp.dbf'},
    "stock_pallets": {"red": r'\\LUMENGLASS\Sistemas\Bases\PALLETS.dbf', "loc": r'C:\proyecto_Asistencia\pallets_temp.dbf'}
}

# --- CONSTANTES DE LA FÁBRICA ---
RESPONSABLES = ["Nahuel Ayala", "Hernan Spataro", "Fabian Rolon", "Lucio Menendez"]
BOCAS = ["Tapa Rosca","20 Normal","20 C/Anclaje","13 Normal","13 C/Anclaje","8 Normal","8 C/Anclaje","10 Normal","Tapa Rosca 9A","Tapa Rosca 9B","Tapa Rosca 10","Perfumero","Boca Spray","Tubo","Cuadrada","N/Aplica"]
MAQUINAS = ["F1", "F2", "F3", "F4", "P1", "P2", "P3"]
HORNOS = ["H1", "H2", "H3", "H4", "H5"]

# --- ESTILOS VISUALES (MODO OSCURO) ---
def aplicar_estilos():
    st.markdown("""
        <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        
        [data-testid="stVerticalBlock"] > [style*="flex-direction: column;"] > [data-testid="stVerticalBlock"] {
            background-color: #1e293b;
            border-radius: 12px;
            padding: 1.5rem;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.5);
            border: 1px solid #334155;
        }

        .stButton > button {
            border-radius: 8px;
            font-weight: 600;
            transition: all 0.3s ease;
            border: none;
        }
        .stButton > button:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.5);
        }
        
        [data-baseweb="tab-list"] { gap: 8px; }
        [data-baseweb="tab"] { border-radius: 8px 8px 0px 0px; padding: 10px; }
        </style>
    """, unsafe_allow_html=True)