# app.py - Versión optimizada para Streamlit Cloud
import streamlit as st
import mysql.connector
from mysql.connector import Error
import os
import folium
from streamlit_folium import st_folium
from folium.plugins import MarkerCluster
import pandas as pd
from datetime import datetime
import hashlib

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="MotoMetric - Concesionarios Bogotá", 
    page_icon="🏍️",
    layout="wide",
    initial_sidebar_state="auto"
)

# --- CSS RESPONSIVE PARA MÓVIL ---
st.markdown("""
<style>
    /* Estilos para móvil */
    @media (max-width: 768px) {
        .stButton > button {
            font-size: 14px !important;
            padding: 10px !important;
            margin: 5px 0 !important;
        }
        
        [data-testid="stMetricValue"] {
            font-size: 1.2rem !important;
        }
        
        [data-testid="stMetricLabel"] {
            font-size: 0.8rem !important;
        }
        
        .stMarkdown h1 {
            font-size: 1.5rem !important;
        }
        
        .stMarkdown h3 {
            font-size: 1.2rem !important;
        }
        
        /* Mejorar cards en móvil */
        [data-testid="column"] {
            padding: 5px !important;
        }
        
        /* Ajustar imágenes */
        [data-testid="stImage"] img {
            max-height: 150px !important;
        }
    }
    
    /* Estilos generales */
    .stAlert {
        border-radius: 10px;
    }
    
    .folium-map {
        border-radius: 10px;
        border: 1px solid #ddd;
    }
    
    /* Tooltips personalizados */
    [data-testid="stTooltipIcon"] {
        color: #1976D2;
    }
</style>
""", unsafe_allow_html=True)

# --- CONEXIÓN A BASE DE DATOS REMOTA ---
# Usar st.secrets para datos sensibles
# En Streamlit Cloud, añadir estos secrets en la configuración

def get_db_connection():
    """Obtiene conexión a base de datos usando secrets"""
    try:
        # Intentar conectar usando secrets de Streamlit Cloud
        config = {
            'host': st.secrets["DB_HOST"],
            'user': st.secrets["DB_USER"],
            'password': st.secrets["DB_PASSWORD"],
            'database': st.secrets["DB_NAME"],
            'port': st.secrets.get("DB_PORT", 3306),
            'connection_timeout': 30,
            'use_pure': True
        }
        return mysql.connector.connect(**config)
    except Exception as e:
        st.error(f"❌ Error de conexión: {e}")
        st.info("💡 Usando datos de demostración...")
        return None

@st.cache_data(ttl=300)  # Cache por 5 minutos
def ejecutar_consulta(query, params=None):
    """Ejecuta consultas con manejo de errores"""
    conn = get_db_connection()
    if not conn:
        return []
    
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, params or ())
        resultados = cursor.fetchall()
        cursor.close()
        conn.close()
        return resultados
    except Error as e:
        st.error(f"Error en consulta: {e}")
        return []
    except Exception as e:
        st.error(f"Error inesperado: {e}")
        return []

# --- DEMO DATA (si no hay conexión a BD) ---
def obtener_datos_demo():
    """Datos de demostración si no hay conexión"""
    return {
        'marcas': ['Yamaha', 'Honda', 'Suzuki', 'AKT', 'KTM', 'Hero'],
        'tipos': ['Naked', 'Deportiva', 'Scooter', 'Touring', 'Enduro', 'Cruiser'],
        'motos_demo': [
            {'id': 1, 'marca': 'Yamaha', 'modelo': 'MT-07', 'precio': 35000000, 
             'cc': 689, 'tipo': 'Naked', 'imagen': 'https://via.placeholder.com/400x250?text=MT-07'},
            {'id': 2, 'marca': 'Honda', 'modelo': 'CB190R', 'precio': 12000000,
             'cc': 184, 'tipo': 'Naked', 'imagen': 'https://via.placeholder.com/400x250?text=CB190R'},
            {'id': 3, 'marca': 'Suzuki', 'modelo': 'GSX-R150', 'precio': 15000000,
             'cc': 147, 'tipo': 'Deportiva', 'imagen': 'https://via.placeholder.com/400x250?text=GSX-R150'},
        ]
    }

def obtener_marcas():
    """Obtiene marcas disponibles"""
    query = "SELECT nombre FROM marcas ORDER BY nombre ASC"
    resultados = ejecutar_consulta(query)
    if resultados:
        return [r['nombre'] for r in resultados]
    # Datos demo
    return obtener_datos_demo()['marcas']

def obtener_tipos_moto():
    """Obtiene tipos de moto"""
    query = """
        SELECT DISTINCT tipo_moto 
        FROM motos_ficha_tecnica 
        WHERE tipo_moto IS NOT NULL AND tipo_moto != 'Otro'
        ORDER BY tipo_moto
    """
    resultados = ejecutar_consulta(query)
    if resultados:
        return ["Seleccionar..."] + [r['tipo_moto'] for r in resultados]
    # Datos demo
    return ["Seleccionar..."] + obtener_datos_demo()['tipos']

# --- FUNCIONES PRINCIPALES (mantén las que ya tienes) ---
# [Mantén todas tus funciones existentes: obtener_concesionarios_por_marca, 
#  obtener_localidades_bogota, mostrar_matriz, etc.]

# --- INTERFAZ PRINCIPAL ---
def main():
    """Función principal de la app"""
    
    # Logo en sidebar
    if os.path.exists("logo.png"):
        st.sidebar.image("logo.png", use_container_width=True)
    else:
        st.sidebar.title("🏍️ MotoMetric")
    
    st.sidebar.title("📋 Menú de Consultas")
    
    # Filtros
    marcas = obtener_marcas()
    marca_sel = st.sidebar.selectbox(
        "🔍 Marca", 
        ["Seleccionar..."] + marcas,
        key="marca_filter"
    )
    
    tipos = obtener_tipos_moto()
    tipo_sel = st.sidebar.selectbox(
        "🏍️ Tipo de Moto",
        tipos,
        key="tipo_filter"
    )
    
    # Botones de concesionarios
    st.sidebar.divider()
    st.sidebar.subheader("📍 Concesionarios Bogotá")
    
    if st.sidebar.button("🗺️ Ver Todos los Concesionarios", use_container_width=True):
        st.session_state.show_concesionarios = True
    
    if st.sidebar.button("📍 Concesionario más cercano", use_container_width=True):
        st.session_state.show_cercano = True
    
    # Mostrar contenido principal
    if marca_sel != "Seleccionar...":
        st.subheader(f"🏭 Catálogo {marca_sel}")
        # Aquí va tu lógica de mostrar motos por marca
        st.info(f"Mostrando motos de {marca_sel} - Conectado a base de datos remota")
        
    elif tipo_sel != "Seleccionar...":
        st.subheader(f"🏍️ Motos tipo {tipo_sel}")
        st.info(f"Mostrando motos tipo {tipo_sel}")
        
    else:
        # Página de inicio
        st.title("🏍️ MotoMetric Bogotá")
        st.markdown("""
        ### Tu guía de motos y concesionarios en Bogotá
        
        **¿Qué puedes hacer?**
        - 🔍 Explorar catálogo de motos por marca, precio o cilindraje
        - 📍 Encontrar concesionarios oficiales en Bogotá
        - 💰 Simular créditos para tu moto ideal
        - 📊 Comparar diferentes modelos
        
        **Selecciona un filtro en el panel lateral para comenzar**
        """)
        
        # Mostrar estadísticas rápidas
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("🏍️ Marcas", len(marcas))
        with col2:
            st.metric("📍 Concesionarios", "100+")
        with col3:
            st.metric("📱 Disponible", "Web y Móvil")
    
    # Modales para concesionarios (si están activados)
    if st.session_state.get('show_concesionarios', False):
        # Aquí llamas a tu función mostrar_concesionarios()
        st.session_state.show_concesionarios = False
        
    if st.session_state.get('show_cercano', False):
        # Aquí llamas a tu función mostrar_concesionario_cercano()
        st.session_state.show_cercano = False

if __name__ == "__main__":
    # Inicializar session state
    if 'show_concesionarios' not in st.session_state:
        st.session_state.show_concesionarios = False
    if 'show_cercano' not in st.session_state:
        st.session_state.show_cercano = False
    
    main()