from fpdf import FPDF

def crear_certificado_prueba():
    # 1. Crea el documento A4 en milímetros
    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.add_page()
    
    # 2. Pega la imagen de fondo (desde la esquina 0,0 ocupando todo el A4)

    pdf.image('plantilla_certificado.jpg', x=0, y=0, w=210, h=297)
    
    # 3. Configura la tipografía (Arial, Negrita, Tamaño 12)
    pdf.set_font("helvetica", style="B", size=12)
    
    # 4. Imprime datos de prueba en coordenadas específicas (X, Y)
    pdf.text(x=55, y=80, txt="LUMEN-9999") # Nota de Pedido
    pdf.text(x=20, y=56, txt="10/03/2026") # Fecha
    pdf.text(x=153, y=80, txt="26500")  # Lote Lumen
    pdf.text(x=111, y=56, txt="Elea Phoenix")  #Cliente
    pdf.text(x=62, y=69, txt="5511555")  #Cliente
    pdf.text(x=186, y=56, txt="F4")  #Maquina

        
    # 5. Guarda el PDF resultante
    pdf.output('certificado_calibracion.pdf')
    print("¡PDF generado con éxito! Abrí certificado_calibracion.pdf para verlo.")

# Ejecuta la función
crear_certificado_prueba()
