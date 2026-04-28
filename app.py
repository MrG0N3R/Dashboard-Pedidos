
import streamlit as st
import pandas as pd
import fdb
import plotly.express as px  # Para gráficos interactivos
from datetime import date

@st.cache_data
def obtener_datos_produccion():
    conn = None
    try:
        fdb.load_api(st.secrets["firebird"]["dll_path"])

        # Conexión remota al servidor de producción
        conn = fdb.connect(
            host=st.secrets["firebird"]["host"],
            database=st.secrets["firebird"]["database"],
            user=st.secrets["firebird"]["user"],
            password=st.secrets["firebird"]["password"],
            charset=st.secrets["firebird"]["charset"]
        )
        
        cur = conn.cursor()

        # Corregido: Se agrega D1.FOLIO al GROUP BY para evitar error de ejecución
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
              AND (D1.FECHA_VIGENCIA_ENTREGA = '2026-05-02')
            GROUP BY D1.FECHA_VIGENCIA_ENTREGA, D1.FOLIO, A1.NOMBRE, A1.UNIDAD_VENTA
            ORDER BY D1.FECHA_VIGENCIA_ENTREGA ASC, D1.FOLIO ASC, TOTAL_SACOS DESC
        """

        cur.execute(query)
        data = cur.fetchall()
        
        cols = [desc[0] for desc in cur.description]
        df = pd.DataFrame(data, columns=cols)
        return df

    except Exception as e:
        return f"Error: {str(e)}"
    finally:
        if conn:
            conn.close()

# --- INTERFAZ ---
st.set_page_config(page_title="UGRPG - Dashboard Producción", layout="wide")
st.title("📊 Resumen Visual de Carga - UGRPG")

resultado = obtener_datos_produccion()

if isinstance(resultado, str):
    st.error(resultado)
else:
    if not resultado.empty:
        # 1. LIMPIEZA DE DATOS
        resultado['FECHA_VIGENCIA_ENTREGA'] = pd.to_datetime(resultado['FECHA_VIGENCIA_ENTREGA']).dt.date
        
        # 2. SECCIÓN DE MÉTRICAS (KPIs)
        st.subheader("📌 Indicadores Clave")
        c1, c2, c3 = st.columns(3)
        
        total_sacos = resultado['TOTAL_SACOS'].sum()
        productos_unicos = resultado['PRODUCTO'].nunique()
        dia_pico = resultado.groupby('FECHA_VIGENCIA_ENTREGA')['TOTAL_SACOS'].sum().idxmax()
        
        c1.metric("Total Sacos a Producir", f"{total_sacos:,.0f}")
        c2.metric("Variedad de Productos", productos_unicos)
        c3.metric("Día de Mayor Carga", dia_pico.strftime('%d/%m'))

        st.divider()

        # 3. VISUALIZACIONES
        col_izq, col_der = st.columns([1, 1])

        with col_izq:
            st.write("### 🔥 Top 10 Productos con más Demanda")
            # Agrupamos para el gráfico de barras
            df_prod = resultado.groupby('PRODUCTO')['TOTAL_SACOS'].sum().reset_index().sort_values('TOTAL_SACOS', ascending=False).head(10)
            
            fig_bar = px.bar(
                df_prod, 
                x='TOTAL_SACOS', 
                y='PRODUCTO', 
                orientation='h',
                color='TOTAL_SACOS',
                color_continuous_scale='Blues',
                text_auto='.2s'
            )
            fig_bar.update_layout(yaxis={'categoryorder':'total ascending'}, showlegend=False)
            st.plotly_chart(fig_bar, use_container_width=True)

        with col_der:
            st.write("### 📅 Carga de Trabajo por Día")
            df_fecha = resultado.groupby('FECHA_VIGENCIA_ENTREGA')['TOTAL_SACOS'].sum().reset_index()
            
            fig_line = px.line(
                df_fecha, 
                x='FECHA_VIGENCIA_ENTREGA', 
                y='TOTAL_SACOS',
                markers=True,
                line_shape='spline',
                text='TOTAL_SACOS'
            )
            fig_line.update_traces(textposition="top center")
            st.plotly_chart(fig_line, use_container_width=True)

        # 4. TABLA DETALLADA AL FINAL
        with st.expander("🔎 Ver detalle de folios y pedidos"):
            st.dataframe(resultado, use_container_width=True, hide_index=True)

    else:
        st.warning("No hay datos para mostrar.")