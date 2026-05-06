import streamlit as st
import pandas as pd
import fdb
import plotly.express as px  
import re
from datetime import date, timedelta
from fpdf import FPDF
import io

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="UGRPG - Dashboard Producción", layout="wide")



def generar_pdf_resumen(df_resumen, f_inicio, f_fin):
    pdf = FPDF()
    pdf.add_page()
    
    # Encabezado
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, "Reporte de Toneladas a Producir - UGRPG", ln=True, align='C')
    
    pdf.set_font("Arial", '', 12)
    pdf.cell(0, 10, f"Periodo: {f_inicio} al {f_fin}", ln=True, align='C')
    pdf.ln(10)
    
    # Tabla de totales
    pdf.set_font("Arial", 'B', 12)
    pdf.set_fill_color(200, 220, 255)
    pdf.cell(120, 10, "Producto", border=1, fill=True)
    pdf.cell(60, 10, "Total Toneladas", border=1, fill=True, align='C')
    pdf.ln()
    
    pdf.set_font("Arial", '', 11)
    total_general_ton = 0
    
    for _, fila in df_resumen.iterrows():
        pdf.cell(120, 8, str(fila['PRODUCTO']), border=1)
        pdf.cell(60, 8, f"{fila['TOTAL_TONELADAS']:,.2f}", border=1, align='C')
        pdf.ln()
        total_general_ton += fila['TOTAL_TONELADAS']
    
    # Total Final
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(120, 10, "TOTAL GENERAL", border=1)
    pdf.cell(60, 10, f"{total_general_ton:,.2f} Ton", border=1, align='C')
    
    # Retornar el PDF como bytes
    return pdf.output(dest='S').encode('latin-1')




def extraer_kilos(nombre_producto):
    """
    Busca números seguidos de 'kg' o 'k' en el nombre del producto.
    Si no encuentra nada, asume 1 (para no afectar la multiplicación o manejarlo como error).
    """
    match = re.search(r'(\d+)\s*(?:kg|k)', nombre_producto, re.IGNORECASE)
    if match:
        return float(match.group(1))
    return 0.0  # O un valor por defecto si el producto no es por saco

@st.cache_data
def obtener_datos_produccion(f_inicio, f_fin):
    # ... (Tu función de conexión original se mantiene igual)
    #
    conn = None
    try:
        fdb.load_api(st.secrets["firebird"]["dll_path"])
        conn = fdb.connect(
            host=st.secrets["firebird"]["host"],
            database=st.secrets["firebird"]["database"],
            user=st.secrets["firebird"]["user"],
            password=st.secrets["firebird"]["password"],
            charset=st.secrets["firebird"]["charset"]
        )
        cur = conn.cursor()
        query = """
            SELECT 
                D1.FECHA_VIGENCIA_ENTREGA,
                D1.FOLIO,
                A1.NOMBRE AS PRODUCTO, 
                SUM(DET1.UNIDADES) AS TOTAL_SACOS,
                A1.UNIDAD_VENTA AS UNIDAD
            FROM DOCTOS_VE_DET DET1
            INNER JOIN DOCTOS_VE D1 ON (D1.DOCTO_VE_ID = DET1.DOCTO_VE_ID)
            INNER JOIN ARTICULOS A1 ON (A1.ARTICULO_ID = DET1.ARTICULO_ID)
            INNER JOIN LIBRES_PED_VE L1 ON (L1.DOCTO_VE_ID = D1.DOCTO_VE_ID)
            WHERE (DET1.ROL <> 'C')
              AND (L1.PROGRAMADO = 'P')
              AND (D1.FECHA_VIGENCIA_ENTREGA BETWEEN ? AND ?)
            GROUP BY D1.FECHA_VIGENCIA_ENTREGA, D1.FOLIO, A1.NOMBRE, A1.UNIDAD_VENTA
            ORDER BY D1.FECHA_VIGENCIA_ENTREGA ASC, TOTAL_SACOS DESC
        """
        cur.execute(query, (f_inicio, f_fin))
        data = cur.fetchall()
        cols = [desc[0] for desc in cur.description]
        return pd.DataFrame(data, columns=cols)
    except Exception as e:
        return f"Error: {str(e)}"
    finally:
        if conn: conn.close()

# --- INTERFAZ Y LÓGICA ---
st.title("📊 Control de Carga y Producción - UGRPG")

with st.sidebar:
    st.header("Configuración de Reporte")
    today = date.today()
    rango_fechas = st.date_input(
        "Selecciona el rango de entregas",
        value=(today, today + timedelta(days=3)),
        min_value=today - timedelta(days=30),
        max_value=today + timedelta(days=90)
    )

if len(rango_fechas) == 2:
    f_inicio, f_fin = rango_fechas
    resultado = obtener_datos_produccion(f_inicio, f_fin)

    if isinstance(resultado, str):
        st.error(resultado)
    elif not resultado.empty:
        resultado['FECHA_VIGENCIA_ENTREGA'] = pd.to_datetime(resultado['FECHA_VIGENCIA_ENTREGA']).dt.date
        
            # --- NUEVA LÓGICA DE CÁLCULO ---
        # Convertimos los sacos (Decimal) a float para que sean compatibles
        resultado['TOTAL_SACOS'] = resultado['TOTAL_SACOS'].astype(float)

        # 1. Extraer los kilos del nombre
        resultado['KG_POR_SACO'] = resultado['PRODUCTO'].apply(extraer_kilos)

        # 2. Ahora la multiplicación funcionará sin errores
        resultado['TOTAL_TONELADAS'] = (resultado['TOTAL_SACOS'] * resultado['KG_POR_SACO']) / 1000
        
        # --- SECCIÓN DE MÉTRICAS ---
        col1, col2 = st.columns(2)
        total_sacos = resultado['TOTAL_SACOS'].sum()
        total_ton = resultado['TOTAL_TONELADAS'].sum()
        
        col1.metric("Volumen Total (Sacos)", f"{total_sacos:,.0f}")
        col2.metric("Toneladas Necesarias", f"{total_ton:,.2f} Ton")

        # --- GRÁFICO EN TONELADAS ---
        df_prod = resultado.groupby('PRODUCTO')['TOTAL_TONELADAS'].sum().reset_index().sort_values('TOTAL_TONELADAS', ascending=False)
        
        fig_agrupado = px.bar(
            df_prod.head(15), 
            x='TOTAL_TONELADAS',
            y='PRODUCTO',
            orientation='h',
            color='TOTAL_TONELADAS',
            color_continuous_scale='Cividis', # Cambiado para diferenciar
            text_auto='.2f',
            title=f"Toneladas Acumuladas del {f_inicio} al {f_fin}",
            labels={'TOTAL_TONELADAS': 'Toneladas'}
        )
        st.plotly_chart(fig_agrupado, use_container_width=True)

        if not resultado.empty:
            # Preparamos el resumen agrupado para el PDF
            df_resumen_pdf = resultado.groupby('PRODUCTO')['TOTAL_TONELADAS'].sum().reset_index()
            df_resumen_pdf = df_resumen_pdf.sort_values('TOTAL_TONELADAS', ascending=False)

            with st.expander("📄 Ver detalle por Folio y Fecha"):
                # Botón para descargar PDF
                pdf_bytes = generar_pdf_resumen(df_resumen_pdf, f_inicio, f_fin)
                
                st.download_button(
                    label="📥 Descargar Reporte de Toneladas (PDF)",
                    data=pdf_bytes,
                    file_name=f"Reporte_Produccion_{f_inicio}.pdf",
                    mime="application/pdf"
                )
                
                st.write("Esta tabla muestra la fecha específica asignada a cada pedido:")
                st.dataframe(
                    resultado,
                    use_container_width=True,
                    hide_index=True
                    # ... tus configuraciones de columna anteriores ...
                )
            