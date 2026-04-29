import streamlit as st
import pandas as pd
import fdb
import plotly.express as px  
from datetime import date, timedelta

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="UGRPG - Dashboard Producción", layout="wide")

@st.cache_data
def obtener_datos_produccion(f_inicio, f_fin):
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

        # Usamos parámetros (?) para que el rango sea dinámico
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
        df = pd.DataFrame(data, columns=cols)
        return df

    except Exception as e:
        return f"Error: {str(e)}"
    finally:
        if conn:
            conn.close()

# --- INTERFAZ DE FILTROS ---
st.title("📊 Control de Carga y Producción - UGRPG")

with st.sidebar:
    st.header("Configuración de Reporte")
    # Selector de rango de fechas
    today = date.today()
    rango_fechas = st.date_input(
        "Selecciona el rango de entregas",
        value=(today, today + timedelta(days=3)),
        min_value=today - timedelta(days=30),
        max_value=today + timedelta(days=90)
    )

# Verificamos que se hayan seleccionado ambas fechas (inicio y fin)
if len(rango_fechas) == 2:
    f_inicio, f_fin = rango_fechas
    resultado = obtener_datos_produccion(f_inicio, f_fin)

    if isinstance(resultado, str):
        st.error(resultado)
    elif not resultado.empty:
        # Limpieza de fechas para visualización
        resultado['FECHA_VIGENCIA_ENTREGA'] = pd.to_datetime(resultado['FECHA_VIGENCIA_ENTREGA']).dt.date
        
        # --- SECCIÓN DE MÉTRICAS ---
        total_general = resultado['TOTAL_SACOS'].sum()
        st.metric("Volumen Total en Rango Seleccionado", f"{total_general:,.0f} Sacos")

        # --- GRÁFICO CONSOLIDADO ---
        # Agrupamos por producto para el gráfico general
        df_prod = resultado.groupby('PRODUCTO')['TOTAL_SACOS'].sum().reset_index().sort_values('TOTAL_SACOS', ascending=False)
        
        fig_agrupado = px.bar(
            df_prod.head(15), 
            x='TOTAL_SACOS',
            y='PRODUCTO',
            orientation='h',
            color='TOTAL_SACOS',
            color_continuous_scale='Viridis',
            text_auto='.2s',
            title=f"Acumulado del {f_inicio} al {f_fin}"
        )

        fig_agrupado.update_layout(
            font=dict(size=18),
            yaxis={'categoryorder':'total ascending'},
            height=600
        )
        fig_agrupado.update_traces(textfont_size=20, textposition="outside", cliponaxis=False)
        
        st.plotly_chart(fig_agrupado, use_container_width=True)

        # --- DESGLOSE DETALLADO ---
        with st.expander("📄 Ver detalle por Folio y Fecha"):
            st.write("Esta tabla muestra la fecha específica asignada a cada pedido:")
            st.dataframe(
                resultado,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "FECHA_VIGENCIA_ENTREGA": st.column_config.DateColumn("Entrega Programada"),
                    "TOTAL_SACOS": st.column_config.NumberColumn("Sacos", format="%d")
                }
            )
    else:
        st.warning(f"No hay pedidos programados entre el {f_inicio} y el {f_fin}.")
else:
    st.info("Por favor, selecciona la fecha de inicio y fin en el calendario de la izquierda.")