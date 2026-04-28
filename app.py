import streamlit as st
import pandas as pd
import fdb
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
st.set_page_config(page_title="UGRPG - Plan de Entrega", layout="wide")
st.title("📦 Detalle de Pedidos por Fecha de Entrega")

resultado = obtener_datos_produccion()

if isinstance(resultado, str):
    st.error(resultado)
else:
    if not resultado.empty:
        # Formateo de fecha para la tabla
        resultado['FECHA_VIGENCIA_ENTREGA'] = pd.to_datetime(resultado['FECHA_VIGENCIA_ENTREGA']).dt.date
        
        st.write("### Desglose de Carga para el día 02 de Mayo")
        
        st.dataframe(
            resultado, 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "FECHA_VIGENCIA_ENTREGA": st.column_config.DateColumn("Día Entrega"),
                "FOLIO": st.column_config.TextColumn("Folio Pedido"),
                "TOTAL_SACOS": st.column_config.NumberColumn("Sacos", format="%d"),
            }
        )
        
        # Métrica resumen
        st.metric("Total Sacos Programados", f"{resultado['TOTAL_SACOS'].sum():,.0f}")
    else:
        st.warning("No hay pedidos programados para la fecha seleccionada.")