from fpdf import FPDF

pdf = FPDF(orientation='P', unit='mm', format='A4')
pdf.add_page()
# Tu imagen de fondo
pdf.image('plantilla_certificado.jpg', x=0, y=0, w=210, h=297)

pdf.set_font("helvetica", style="B", size=12)

# --- MÉTODO VIEJO
# pdf.text(x=50, y=80, txt="LUMEN-9999")

# --- MÉTODO NUEVO (Centrado perfecto)
# 1. Le dice a dónde mover el cursor (Esquina superior izquierda del recuadro)
pdf.set_xy(x=12.1, y=50.5) 

# 2. Crea la celda: Ancho(w), Alto(h), Texto, Borde visible(1 o 0), y Alineación(C = Center)
pdf.cell(w=39.5, h=7.2, txt="10/03/2026", border=0, align='C')

#Nro analisis
pdf.set_xy(x=149.4, y=14.6)
pdf.cell(w=23.3, h=10.1, txt="8077", border=0, align='C')
#Cliente
pdf.set_xy(x=72.8, y=50.5)
pdf.cell(w=76.5, h=7.2, txt="ELEA PHOENIX", border=0, align='C')
#Maquina
pdf.set_xy(x=172.6, y=50.5)
pdf.cell(w=27, h=7.2, txt="F4", border=0, align='C')
#Orden de compra
pdf.set_xy(x=53.65, y=65.15)
pdf.cell(w=36.88, h=7.2, txt="1234246254", border=0, align='C')
#Nota de pedido
pdf.set_xy(x=53.65, y=74.49)
pdf.cell(w=36.88, h=7.2, txt="19888", border=0, align='C')
#Orden de compra
pdf.set_xy(x=53.65, y=83.71)
pdf.cell(w=36.88, h=7.2, txt="F2237", border=0, align='C')
#Lote Lumen
pdf.set_xy(x=146.6, y=74.48)
pdf.cell(w=25.9, h=7.2, txt="26555", border=0, align='C')
#Fecha de Entrega
pdf.set_xy(x=172.65, y=65.2)
pdf.cell(w=27, h=7.2, txt="30/04/2026", border=0, align='C')
#Cantidad
pdf.set_xy(x=12.3, y=95.65)
pdf.cell(w=39.3, h=7.2, txt="300000", border=0, align='C')
#Medida
pdf.set_xy(x=53.65, y=95.65)
pdf.cell(w=58.13, h=7.2, txt="22,50x34,5±0,5", border=0, align='C')
#Tipo Boca
pdf.set_xy(x=114.5, y=95.65)
pdf.cell(w=32.04, h=7.2, txt="ROSCA", border=0, align='C')
#Color vidrio
pdf.set_xy(x=149.42, y=95.65)
pdf.cell(w=50.23, h=7.2, txt="AMBAR", border=0, align='C')
#Capacidad
pdf.set_xy(x=12.3, y=110.51)
pdf.cell(w=39.3, h=7.2, txt="5 ml", border=0, align='C')
#Impresion
pdf.set_xy(x=53.7, y=110.51)
pdf.cell(w=58.11, h=7.2, txt="N/A", border=0, align='C')
#Codigo Plano
pdf.set_xy(x=114.5, y=110.51)
pdf.cell(w=35, h=7.2, txt="2234AMR", border=0, align='C')
#Lote Materia Prima
pdf.set_xy(x=53.7, y=131.5)
pdf.cell(w=36.87, h=5, txt="2578966", border=0, align='C')}
#Batch Materia Prima
pdf.set_xy(x=53.7, y=138.25)
pdf.cell(w=36.87, h=5, txt="2578966", border=0, align='C')
#Diametro
pdf.set_xy(x=53.7, y=145.5)
pdf.cell(w=36.87, h=5, txt="22,50", border=0, align='C')
#Pared
pdf.set_xy(x=53.7, y=152.4)
pdf.cell(w=36.87, h=5, txt="1,00", border=0, align='C')
#Impresiones control
pdf.set_xy(x=172.61, y=159.31)
pdf.cell(w=24.9, h=5, txt="N/A", border=0, align='C')
#Numero Analisis
pdf.set_xy(x=30.7, y=196.1)
pdf.cell(w=24.9, h=5, txt="8077", border=0, align='C')
#Resultado
pdf.set_xy(x=95, y=196.1)
pdf.cell(w=20.3, h=5, txt="0,76", border=0, align='C')
#Maximo
pdf.set_xy(x=172.2, y=196.1)
pdf.cell(w=20.3, h=5, txt="1,00", border=0, align='C')
#Fecha Fin1
pdf.set_xy(x=90.8, y=260.4)
pdf.cell(w=20, h=5, txt="10/03/2026", border=0, align='C')
#Fecha Fin2
pdf.set_xy(x=183.5, y=260.4)
pdf.cell(w=18, h=5, txt="10/03/2026", border=0, align='C')





pdf.output('certificado_CENTRADO.pdf')
print("¡PDF generado! Abrí certificado_CENTRADO.pdf")
