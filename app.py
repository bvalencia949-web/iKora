import streamlit as st
import pandas as pd
import plotly.express as px
import requests

# ==========================================
# 🔒 CONFIGURACIÓN Y CREDENCIALES
# ==========================================
NOTION_TOKEN = st.secrets["NOTION_TOKEN"]
DATABASE_ID = st.secrets["DATABASE_ID"]

st.set_page_config(page_title="Control de Gastos Detallado", layout="wide")

# Inyección de estilos CSS (mismo look and feel del otro dashboard)
st.markdown("""
    <style>
    .block-container { padding-top: 2rem; padding-bottom: 2rem; }

    div[data-testid="stMetric"] {
        background-color: var(--background-secondary-color);
        padding: 20px 24px;
        border-radius: 12px;
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05), 0 2px 4px -1px rgba(0,0,0,0.03);
        border: 1px solid rgba(128, 128, 128, 0.15);
        transition: transform 0.2s ease;
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-2px);
    }
    div[data-testid="stMetricValue"] {
        font-size: 28px !important;
        font-weight: 700 !important;
    }

    hr {
        margin: 2rem 0;
        border: 0;
        height: 1px;
        background-image: linear-gradient(to right, rgba(0, 0, 0, 0), rgba(128, 128, 128, 0.4), rgba(0, 0, 0, 0));
    }

    button[data-baseweb="tab"] {
        font-size: 16px !important;
        font-weight: 600 !important;
        padding: 12px 20px !important;
    }

    .section-title {
        font-size: 1.25rem;
        font-weight: 600;
        margin-bottom: 12px;
        color: var(--text-color);
    }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 🔄 EXTRACCIÓN DE DATOS
# ==========================================
def cargar_datos():
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }

    try:
        all_results = []
        payload = {}
        while True:
            response = requests.post(url, headers=headers, json=payload)
            if response.status_code != 200:
                st.error(f"Error Notion API [{response.status_code}]: {response.text}")
                return pd.DataFrame()
            data = response.json()
            all_results.extend(data.get("results", []))
            if data.get("has_more"):
                payload = {"start_cursor": data.get("next_cursor")}
            else:
                break

        datos = []
        for row in all_results:
            props = row.get("properties", {})

            # Nombre -> propiedad de tipo Title
            nombre_title = props.get("Nombre", {}).get("title", [])
            nombre = nombre_title[0].get("text", {}).get("content", "") if nombre_title else "Sin nombre"

            cantidad = props.get("Cantidad", {}).get("number", 0) or 0
            valor = props.get("Valor", {}).get("number", 0) or 0

            # Importe: puede ser number o formula (number). Cubrimos ambos casos.
            importe_prop = props.get("Importe", {})
            if "formula" in importe_prop:
                importe = importe_prop.get("formula", {}).get("number", 0) or 0
            else:
                importe = importe_prop.get("number", 0) or 0

            # Si no hay Importe cargado, lo calculamos como respaldo
            if not importe:
                importe = cantidad * valor

            # Fecha del gasto: buscamos automáticamente la propiedad de fecha,
            # cubriendo distintos tipos posibles en Notion (date, formula con fecha,
            # created_time, last_edited_time), sin depender del nombre exacto.
            fecha_str = None

            # 1ra pasada: propiedad tipo 'date' explícita
            for prop_value in props.values():
                if isinstance(prop_value, dict) and prop_value.get("type") == "date":
                    date_obj = prop_value.get("date")
                    if date_obj and date_obj.get("start"):
                        fecha_str = date_obj.get("start")
                        break

            # 2da pasada: fórmula que devuelve una fecha
            if not fecha_str:
                for prop_value in props.values():
                    if isinstance(prop_value, dict) and prop_value.get("type") == "formula":
                        formula_obj = prop_value.get("formula", {})
                        if formula_obj.get("type") == "date" and formula_obj.get("date"):
                            fecha_str = formula_obj["date"].get("start")
                            break

            # 3ra pasada: propiedades automáticas de Notion (creación / última edición)
            if not fecha_str:
                for prop_value in props.values():
                    if isinstance(prop_value, dict) and prop_value.get("type") in ("created_time", "last_edited_time"):
                        fecha_str = prop_value.get(prop_value.get("type"))
                        break

            metodo_pago = props.get("Método de pago", {}).get("select", {}).get("name", "Sin especificar")
            categoria = props.get("Categoría", {}).get("select", {}).get("name", "Otros")
            cuenta = props.get("Cuenta", {}).get("select", {}).get("name", "Sin especificar")

            datos.append({
                "Nombre": nombre,
                "Cantidad": float(cantidad),
                "Valor": float(valor),
                "Importe": float(importe),
                "Fecha_Raw": fecha_str,
                "Metodo_Pago": metodo_pago,
                "Categoria": categoria,
                "Cuenta": cuenta
            })

        df = pd.DataFrame(datos)
        if not df.empty:
            df['Fecha_Raw'] = pd.to_datetime(df['Fecha_Raw'])
            df = df.sort_values(by='Fecha_Raw', ascending=True)
            df['Mes'] = df['Fecha_Raw'].dt.strftime('%m/%Y')
        return df
    except Exception as e:
        st.error(f"Error al procesar los datos: {e}")
        return pd.DataFrame()

df_raw = cargar_datos()

# ==========================================
# 📋 FILTROS INTELIGENTES (SIDEBAR)
# ==========================================
with st.sidebar:
    st.header("🎯 Filtros")
    st.markdown("---")

    if not df_raw.empty:
        meses_disp = df_raw['Mes'].unique()[::-1]
        mes_sel = st.multiselect("Mes", meses_disp, default=[])

        cat_disp = sorted(df_raw['Categoria'].unique())
        cat_sel = st.multiselect("Categoría", cat_disp, default=[])

        metodo_disp = sorted(df_raw['Metodo_Pago'].unique())
        metodo_sel = st.multiselect("Método de pago", metodo_disp, default=[])

        cuenta_disp = sorted(df_raw['Cuenta'].unique())
        cuenta_sel = st.multiselect("Cuenta", cuenta_disp, default=[])

        df_filtrado = df_raw.copy()

        if mes_sel:
            df_filtrado = df_filtrado[df_filtrado['Mes'].isin(mes_sel)]
        if cat_sel:
            df_filtrado = df_filtrado[df_filtrado['Categoria'].isin(cat_sel)]
        if metodo_sel:
            df_filtrado = df_filtrado[df_filtrado['Metodo_Pago'].isin(metodo_sel)]
        if cuenta_sel:
            df_filtrado = df_filtrado[df_filtrado['Cuenta'].isin(cuenta_sel)]
    else:
        df_filtrado = pd.DataFrame()

# ==========================================
# 📊 LÓGICA DE CÁLCULO
# ==========================================
st.title("🧾 Control de Gastos Detallado")

if df_raw.empty:
    st.error("No se pudo cargar la información. Revisa la conexión con Notion.")
else:
    ingreso = df_filtrado[df_filtrado['Cuenta'] == 'Ingreso']['Importe'].sum()
    gasto = df_filtrado[df_filtrado['Cuenta'] == 'Gasto']['Importe'].sum()
    inversion = df_filtrado[df_filtrado['Cuenta'] == 'Inversión']['Importe'].sum()
    ganancia = ingreso - gasto - inversion
    capital = df_filtrado[df_filtrado['Cuenta'] == 'Capital']['Importe'].sum()

    cant_inversion = df_filtrado[df_filtrado['Cuenta'] == 'Inversión']['Cantidad'].sum()
    cant_ingreso = df_filtrado[df_filtrado['Cuenta'] == 'Ingreso']['Cantidad'].sum()
    stock = cant_inversion - cant_ingreso

    m1, m2, m3 = st.columns(3)
    m1.metric("📈 Ingreso", f"S/. {ingreso:,.2f}")
    m2.metric("📉 Gasto", f"S/. {gasto:,.2f}")
    m3.metric("🧱 Inversión", f"S/. {inversion:,.2f}")

    m4, m5, m6 = st.columns(3)
    m4.metric("💰 Ganancia", f"S/. {ganancia:,.2f}")
    m5.metric("📦 Stock", f"{stock:,.0f} unidades")
    m6.metric("🏦 Capital", f"S/. {capital:,.2f}")

    st.markdown("<hr>", unsafe_allow_html=True)

    tab_general, tab_metodos, tab_detalle = st.tabs(
        ["📊 Análisis General", "💳 Métodos y Cuentas", "📋 Historial"]
    )

    # ==========================================
    # TAB 1: ANÁLISIS GENERAL
    # ==========================================
    with tab_general:
        col_cat, col_stock = st.columns(2)

        with col_cat:
            st.markdown('<p class="section-title">Distribución por Categoría (Ventas)</p>', unsafe_allow_html=True)
            df_ingreso = df_filtrado[df_filtrado['Cuenta'] == 'Ingreso']
            if not df_ingreso.empty:
                df_cat = df_ingreso.groupby('Categoria')['Importe'].sum().reset_index().sort_values('Importe', ascending=False)
                fig_cat = px.bar(
                    df_cat, x="Categoria", y="Importe", text_auto='.2f',
                    color="Categoria", color_discrete_sequence=px.colors.qualitative.Pastel
                )
                fig_cat.update_traces(hovertemplate="<b>%{x}</b><br>Importe: S/. %{y:,.2f}<extra></extra>")
                fig_cat.update_layout(xaxis_title="Categoría", yaxis_title="Importe vendido (S/.)", showlegend=False, margin=dict(t=10, b=10))
                st.plotly_chart(fig_cat, use_container_width=True)
            else:
                st.info("No hay registros de tipo 'Ingreso' para mostrar.")

        with col_stock:
            st.markdown('<p class="section-title">Stock por Categoría</p>', unsafe_allow_html=True)
            if not df_filtrado.empty:
                df_inv_cat = df_filtrado[df_filtrado['Cuenta'] == 'Inversión'].groupby('Categoria')['Cantidad'].sum()
                df_ing_cat = df_filtrado[df_filtrado['Cuenta'] == 'Ingreso'].groupby('Categoria')['Cantidad'].sum()
                df_stock_cat = (df_inv_cat.subtract(df_ing_cat, fill_value=0)).reset_index()
                df_stock_cat.columns = ['Categoria', 'Cantidad']
                df_stock_cat = df_stock_cat.sort_values('Cantidad', ascending=False)
                fig_stock = px.bar(
                    df_stock_cat, x="Categoria", y="Cantidad", text_auto='.0f',
                    color="Categoria", color_discrete_sequence=px.colors.qualitative.Set3
                )
                fig_stock.update_traces(hovertemplate="<b>%{x}</b><br>Stock: %{y:,.0f}<extra></extra>")
                fig_stock.update_layout(xaxis_title="Categoría", yaxis_title="Stock (unidades)", showlegend=False, margin=dict(t=10, b=10))
                st.plotly_chart(fig_stock, use_container_width=True)
            else:
                st.info("No hay registros para mostrar.")

    # ==========================================
    # TAB 2: MÉTODOS DE PAGO Y CUENTAS
    # ==========================================
    with tab_metodos:
        col_metodo, col_mes = st.columns(2)

        with col_metodo:
            st.markdown('<p class="section-title">💳 Gasto por Método de Pago</p>', unsafe_allow_html=True)
            if not df_filtrado.empty:
                df_metodo = df_filtrado.groupby('Metodo_Pago')['Importe'].sum().reset_index()
                fig_metodo = px.pie(
                    df_metodo, names="Metodo_Pago", values="Importe", hole=0.45,
                    color_discrete_sequence=px.colors.qualitative.Bold
                )
                fig_metodo.update_traces(hovertemplate="<b>%{label}</b><br>Importe: S/. %{value:,.2f}<extra></extra>")
                fig_metodo.update_layout(margin=dict(t=10, b=10))
                st.plotly_chart(fig_metodo, use_container_width=True)
            else:
                st.info("No hay registros para mostrar.")

        with col_mes:
            st.markdown('<p class="section-title">Gasto por Mes</p>', unsafe_allow_html=True)
            df_solo_gasto = df_filtrado[df_filtrado['Cuenta'] == 'Gasto']
            if not df_solo_gasto.empty:
                df_mes_gasto = df_solo_gasto.groupby('Mes')['Importe'].sum().reset_index()
                fig_mes = px.bar(
                    df_mes_gasto, x="Mes", y="Importe", text_auto='.2f',
                    color_discrete_sequence=['#2b5c8f']
                )
                fig_mes.update_traces(hovertemplate="<b>Importe:</b> S/. %{y:,.2f}<extra></extra>")
                fig_mes.update_layout(xaxis_title="Mes", yaxis_title="Importe (S/.)", margin=dict(t=10, b=10))
                st.plotly_chart(fig_mes, use_container_width=True)
            else:
                st.info("No hay registros de tipo 'Gasto' en este periodo.")

    # ==========================================
    # TAB 3: HISTORIAL
    # ==========================================
    with tab_detalle:
        st.markdown('<p class="section-title">📋 Historial de Gastos</p>', unsafe_allow_html=True)
        st.dataframe(
            df_filtrado[['Fecha_Raw', 'Nombre', 'Cantidad', 'Valor', 'Importe', 'Metodo_Pago', 'Categoria', 'Cuenta']]
            .rename(columns={
                'Fecha_Raw': 'Fecha del gasto',
                'Metodo_Pago': 'Método de pago',
                'Categoria': 'Categoría'
            })
            .sort_values('Fecha del gasto', ascending=False),
            use_container_width=True,
            hide_index=True
        )
