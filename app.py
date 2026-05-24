import streamlit as st
import mysql.connector
from mysql.connector import Error
import os
import folium
from streamlit_folium import st_folium
from folium.plugins import MarkerCluster
import pandas as pd
from datetime import datetime

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
        .stButton > button { font-size: 14px !important; padding: 10px !important; }
        [data-testid="stMetricValue"] { font-size: 1.2rem !important; }
        [data-testid="stImage"] img { max-height: 150px !important; }
    }
    
    [data-testid="stMetricValue"] { font-size: 1.3rem; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; margin-bottom: 5px; }
    .stAlert { border-radius: 10px; }
    
    [data-testid="stImage"] img {
        height: 200px;
        object-fit: contain;
        background-color: #f0f2f6;
        border-radius: 10px 10px 0 0;
    }
    
    .folium-map {
        border-radius: 10px;
        border: 1px solid #ddd;
    }
</style>
""", unsafe_allow_html=True)

# --- CONEXIÓN A BASE DE DATOS REMOTA ---
def get_db_connection():
    """Conexión a MySQL en Clever Cloud usando secrets"""
    try:
        # Intentar conectar usando secrets de Streamlit Cloud
        config = {
            'host': st.secrets.get("DB_HOST", "localhost"),
            'user': st.secrets.get("DB_USER", "root"),
            'password': st.secrets.get("DB_PASSWORD", ""),
            'database': st.secrets.get("DB_NAME", "ejmotos"),
            'port': int(st.secrets.get("DB_PORT", 3306)),
            'connection_timeout': 30,
            'use_pure': True
        }
        return mysql.connector.connect(**config)
    except Exception as e:
        st.error(f"❌ Error de conexión: {e}")
        st.info("💡 Usando modo demostración...")
        return None

@st.cache_data(ttl=300)  # Cache por 5 minutos
def ejecutar_consulta(query, params=None):
    """Ejecuta consultas con manejo de errores y caché"""
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
        st.error(f"⚠️ Error en consulta: {e}")
        return []
    except Exception as e:
        st.error(f"⚠️ Error inesperado: {e}")
        return []

def obtener_marcas():
    """Obtiene marcas con caché"""
    query = "SELECT nombre FROM marcas ORDER BY nombre ASC"
    resultados = ejecutar_consulta(query)
    if resultados:
        return [r['nombre'] for r in resultados]
    return ["Yamaha", "Honda", "Suzuki", "AKT", "KTM"]  # Datos demo

def obtener_tipos_moto():
    """Obtiene lista de tipos de moto únicos"""
    query = """
        SELECT DISTINCT tipo_moto 
        FROM motos_ficha_tecnica 
        WHERE tipo_moto IS NOT NULL AND tipo_moto != 'Otro'
        ORDER BY tipo_moto
    """
    resultados = ejecutar_consulta(query)
    if resultados:
        return ["Seleccionar..."] + [r['tipo_moto'] for r in resultados]
    return ["Seleccionar...", "Naked", "Deportiva", "Scooter", "Touring"]

# --- FUNCIONES PARA CONCESIONARIOS ---
def obtener_concesionarios_por_marca(marca_nombre=None, localidad=None):
    """Obtiene concesionarios filtrados por marca y localidad"""
    query = """
        SELECT 
            c.id_pk_concesionario,
            c.nombre,
            c.direccion,
            c.localidad_bogota,
            c.telefono,
            c.latitud,
            c.longitud
        FROM concesionarios c
        WHERE 1=1
    """
    params = []
    
    if localidad and localidad != "Todas":
        query += " AND c.localidad_bogota = %s"
        params.append(localidad)
    
    if marca_nombre and marca_nombre != "Todos" and marca_nombre != "Seleccionar...":
        query += " AND c.nombre LIKE %s"
        params.append(f"%{marca_nombre}%")
    
    query += " ORDER BY c.localidad_bogota, c.nombre"
    
    resultados = ejecutar_consulta(query, params)
    
    for r in resultados:
        nombre = r['nombre'].lower()
        if 'yamaha' in nombre or 'auteco' in nombre:
            r['marca_concesionario'] = 'Yamaha'
        elif 'honda' in nombre:
            r['marca_concesionario'] = 'Honda'
        elif 'suzuki' in nombre:
            r['marca_concesionario'] = 'Suzuki'
        elif 'akt' in nombre:
            r['marca_concesionario'] = 'AKT'
        elif 'hero' in nombre:
            r['marca_concesionario'] = 'Hero'
        elif 'tvs' in nombre:
            r['marca_concesionario'] = 'TVS'
        elif 'ktm' in nombre:
            r['marca_concesionario'] = 'KTM'
        elif 'bajaj' in nombre:
            r['marca_concesionario'] = 'Bajaj'
        else:
            r['marca_concesionario'] = 'Multi-marca'
    
    return resultados

def obtener_localidades_bogota():
    """Obtiene lista de localidades de Bogotá con concesionarios"""
    query = """
        SELECT DISTINCT localidad_bogota 
        FROM concesionarios 
        WHERE localidad_bogota IS NOT NULL AND localidad_bogota != ''
        ORDER BY localidad_bogota
    """
    resultados = ejecutar_consulta(query)
    if resultados:
        return ["Todas"] + [r['localidad_bogota'] for r in resultados]
    return ["Todas", "Usaquén", "Chapinero", "Santa Fe", "San Cristóbal"]

def obtener_resumen_concesionarios():
    """Obtiene estadísticas de concesionarios"""
    query = """
        SELECT 
            COUNT(*) as total,
            COUNT(DISTINCT localidad_bogota) as localidades
        FROM concesionarios
    """
    resultados = ejecutar_consulta(query)
    if resultados:
        return resultados[0]['total'], resultados[0]['localidades']
    return 0, 0

def crear_mapa_concesionarios(concesionarios, centro_lat=4.7110, centro_lon=-74.0721, zoom_start=11):
    """Crea un mapa de Folium con los concesionarios de Bogotá"""
    if not concesionarios:
        return None
    
    m = folium.Map(location=[centro_lat, centro_lon], zoom_start=zoom_start)
    marker_cluster = MarkerCluster().add_to(m)
    
    colores_marca = {
        'Yamaha': 'red',
        'Honda': 'blue',
        'Suzuki': 'green',
        'AKT': 'orange',
        'KTM': 'purple',
        'Hero': 'cadetblue',
        'TVS': 'darkgreen',
        'Bajaj': 'darkred',
        'Multi-marca': 'gray'
    }
    
    for concesionario in concesionarios:
        marca = concesionario.get('marca_concesionario', 'Multi-marca')
        color = colores_marca.get(marca, 'darkblue')
        
        popup_html = f"""
        <div style="font-family: Arial, sans-serif; min-width: 250px;">
            <h4 style="color: #333; margin-bottom: 5px;">🏍️ {concesionario['nombre']}</h4>
            <hr style="margin: 5px 0;">
            <p style="margin: 5px 0;">
                <strong>🏢 Marca:</strong> {marca}<br>
                <strong>📍 Dirección:</strong> {concesionario['direccion']}<br>
                <strong>🏙️ Localidad:</strong> {concesionario['localidad_bogota']}<br>
                <strong>📞 Teléfono:</strong> {concesionario.get('telefono', 'No disponible')}<br>
            </p>
            <hr style="margin: 5px 0;">
            <small>📍 Haz clic para más detalles</small>
        </div>
        """
        
        folium.Marker(
            location=[concesionario['latitud'], concesionario['longitud']],
            popup=folium.Popup(popup_html, max_width=350),
            tooltip=concesionario['nombre'],
            icon=folium.Icon(color=color, icon='motorcycle', prefix='fa')
        ).add_to(marker_cluster)
    
    return m

# --- MODALES (DIALOGS) ---
@st.dialog("🏍️ Concesionarios en Bogotá")
def mostrar_concesionarios(marca_moto=None, modelo_moto=None):
    """Modal que muestra el mapa de concesionarios de Bogotá"""
    if marca_moto and marca_moto != "Seleccionar...":
        titulo = f"Concesionarios {marca_moto} en Bogotá"
    else:
        titulo = "Todos los Concesionarios de Motos en Bogotá"
    
    st.subheader(titulo)
    
    col_filtro1, col_filtro2 = st.columns(2)
    
    with col_filtro1:
        localidades = obtener_localidades_bogota()
        localidad_sel = st.selectbox("Filtrar por localidad:", localidades, key="localidad_filtro_mapa")
        localidad_filtro = None if localidad_sel == "Todas" else localidad_sel
    
    with col_filtro2:
        tipo_sel = st.radio(
            "Tipo de concesionario:",
            ["Oficial de la marca", "Todos los concesionarios"],
            horizontal=True
        )
    
    if tipo_sel == "Oficial de la marca" and marca_moto and marca_moto != "Seleccionar...":
        concesionarios = obtener_concesionarios_por_marca(marca_moto, localidad_filtro)
    else:
        concesionarios = obtener_concesionarios_por_marca(None, localidad_filtro)
    
    if not concesionarios:
        st.warning(f"No se encontraron concesionarios para los filtros seleccionados.")
        return
    
    total_concesionarios = len(concesionarios)
    localidades_unicas = len(set(c['localidad_bogota'] for c in concesionarios))
    marcas_unicas = len(set(c.get('marca_concesionario', 'Multi-marca') for c in concesionarios))
    
    col_est1, col_est2, col_est3, col_est4 = st.columns(4)
    with col_est1:
        st.metric("Total concesionarios", total_concesionarios)
    with col_est2:
        st.metric("📍 Localidades", localidades_unicas)
    with col_est3:
        st.metric("🏢 Marcas disponibles", marcas_unicas)
    with col_est4:
        if localidad_filtro:
            st.metric("Localidad seleccionada", localidad_filtro)
    
    st.divider()
    
    tab1, tab2 = st.tabs(["🗺️ Vista de Mapa", "📋 Lista de Concesionarios"])
    
    with tab1:
        if concesionarios:
            centro_lat = sum(float(c['latitud']) for c in concesionarios) / len(concesionarios)
            centro_lon = sum(float(c['longitud']) for c in concesionarios) / len(concesionarios)
            
            mapa = crear_mapa_concesionarios(concesionarios, centro_lat, centro_lon, zoom_start=12)
            
            if mapa:
                st_folium(mapa, width="100%", height=550)
                st.info("**Consejos:** Haz clic en cualquier marcador para ver detalles | Los colores indican la marca")
                st.caption("📍 **Leyenda de colores:** 🔴 Yamaha | 🔵 Honda | 🟢 Suzuki | 🟠 AKT | 🟣 KTM | ⚫ Otras marcas")
    
    with tab2:
        datos_tabla = []
        for c in concesionarios:
            datos_tabla.append({
                "Concesionario": c['nombre'],
                "Marca": c.get('marca_concesionario', 'Multi-marca'),
                "Localidad": c['localidad_bogota'],
                "Dirección": c['direccion'],
                "Teléfono": c.get('telefono', 'N/A')
            })
        
        df = pd.DataFrame(datos_tabla)
        st.dataframe(df, use_container_width=True, hide_index=True)

@st.dialog("📍 Concesionario más cercano")
def mostrar_concesionario_cercano():
    """Función para encontrar el concesionario más cercano (simulado)"""
    st.subheader("🔍 Encuentra el concesionario más cercano")
    
    st.info("Próximamente: Podrás usar tu ubicación para encontrar el concesionario más cercano")
    
    localidades = obtener_localidades_bogota()
    localidades_filtradas = [l for l in localidades if l != "Todas"]
    
    if localidades_filtradas:
        localidad_sel = st.selectbox("Selecciona tu localidad:", localidades_filtradas)
        
        if localidad_sel:
            concesionarios = obtener_concesionarios_por_marca(None, localidad_sel)
            if concesionarios:
                st.success(f"📍 Encontramos {len(concesionarios)} concesionario(s) en {localidad_sel}:")
                for c in concesionarios:
                    with st.container(border=True):
                        st.markdown(f"**{c['nombre']}**")
                        st.markdown(f"📍 {c['direccion']}")
                        st.markdown(f"📞 {c.get('telefono', 'N/A')}")

# --- FUNCIONES DE LIMPIEZA DE FILTROS ---
def limpiar_filtros(procedencia):
    if procedencia == "precio":
        st.session_state.v_marca = "Seleccionar..."
        st.session_state.v_cc = "Seleccionar..."
        st.session_state.v_tipo = "Seleccionar..."
    elif procedencia == "marca":
        st.session_state.v_precio = "Seleccionar..."
        st.session_state.v_cc = "Seleccionar..."
        st.session_state.v_tipo = "Seleccionar..."
    elif procedencia == "cc":
        st.session_state.v_marca = "Seleccionar..."
        st.session_state.v_precio = "Seleccionar..."
        st.session_state.v_tipo = "Seleccionar..."
    elif procedencia == "tipo":
        st.session_state.v_marca = "Seleccionar..."
        st.session_state.v_precio = "Seleccionar..."
        st.session_state.v_cc = "Seleccionar..."

# --- RENDERIZAR MATRIZ DE MOTOS ---
def mostrar_matriz(lista_datos, prefijo):
    if not lista_datos:
        st.info("No se encontraron resultados.")
        return

    COLUMNAS = 3
    
    for i in range(0, len(lista_datos), COLUMNAS):
        cols = st.columns(COLUMNAS)
        for j in range(COLUMNAS):
            if i + j < len(lista_datos):
                item = lista_datos[i + j]
                with cols[j]:
                    with st.container(border=True):
                        st.image(item['imagen'] or "https://via.placeholder.com/400x250?text=Sin+Imagen", use_container_width=True)
                        st.markdown(f"### {item['modelo']}")
                        st.markdown(f"**Precio:** :green[{item['precio']}]")
                        st.markdown(f"**Motor:** {item['cc']}")
                        st.caption("📌 *No incluye seguros ni trámites de matrícula*")
        
                        c1, c2 = st.columns(2)
                        with c1:
                            st.button("📊 Ficha Técnica", key=f"det_{prefijo}_{item['id']}", use_container_width=True)
                            st.button("💰 Crédito", key=f"cre_{prefijo}_{item['id']}", use_container_width=True)
                        
                        with c2:
                            st.button("📍 Concesionarios", key=f"con_{prefijo}_{item['id']}", use_container_width=True)
                            st.button("📈 Tabla", key=f"tab_{prefijo}_{item['id']}", use_container_width=True)

# --- INTERFAZ PRINCIPAL ---
def main():
    # Logo en sidebar
    if os.path.exists("logo.png"):
        st.sidebar.image("logo.png", use_container_width=True)
    else:
        st.sidebar.title("🏍️ MotoMetric")

    st.sidebar.title("📋 Menú de Consultas")

    # Filtro por Precio
    rangos = [f"{i}'000.000 - {i+3}'000.000" for i in range(4, 34, 3)]
    rango_sel = st.sidebar.selectbox(
        "💰 Filtrar por Precio:", 
        ["Seleccionar..."] + rangos, 
        key="v_precio", 
        on_change=limpiar_filtros, 
        args=("precio",)
    )

    # Filtro por Marca
    marcas_db = obtener_marcas()
    marca_sel = st.sidebar.selectbox(
        "🏭 Consultar Marca:", 
        ["Seleccionar..."] + marcas_db, 
        key="v_marca", 
        on_change=limpiar_filtros, 
        args=("marca",)
    )

    # Filtro por Cilindraje
    cc_opciones = ["100", "110", "125", "150", "160", "190", "200", "250", "300", "400", "450", "690", "1000", "1301"]
    cc_sel = st.sidebar.selectbox(
        "🔧 Filtrar por Cilindraje:", 
        ["Seleccionar..."] + [c+"cc" for c in cc_opciones], 
        key="v_cc", 
        on_change=limpiar_filtros, 
        args=("cc",)
    )

    # Filtro por Tipo de Moto
    tipos_db = obtener_tipos_moto()
    tipo_sel = st.sidebar.selectbox(
        "🏍️ Filtrar por Tipo:", 
        tipos_db, 
        key="v_tipo", 
        on_change=limpiar_filtros, 
        args=("tipo",)
    )

    # Botones de concesionarios en sidebar
    st.sidebar.divider()
    st.sidebar.subheader("📍 Concesionarios Bogotá")

    if st.sidebar.button("🗺️ Ver Todos los Concesionarios", use_container_width=True):
        mostrar_concesionarios()

    if st.sidebar.button("🔍 Concesionario más cercano", use_container_width=True):
        mostrar_concesionario_cercano()

    # --- CONTENIDO PRINCIPAL ---
    st.markdown("---")
    
    # Mensaje de bienvenida
    if all(v == "Seleccionar..." for v in [marca_sel, cc_sel, tipo_sel, rango_sel]):
        st.info("🏍️ **¡Bienvenido a MotoMetric Bogotá!** Selecciona un criterio en el panel lateral para explorar el catálogo de motos.")
        
        # Mostrar estadísticas rápidas
        col1, col2, col3 = st.columns(3)
        
        total_motos = ejecutar_consulta("SELECT COUNT(*) as total FROM motos_ficha_tecnica")
        if total_motos:
            col1.metric("🏍️ Total Motos", total_motos[0]['total'])
        
        total_marcas = ejecutar_consulta("SELECT COUNT(*) as total FROM marcas")
        if total_marcas:
            col2.metric("🏭 Marcas", total_marcas[0]['total'])
        
        total_cons, localidades = obtener_resumen_concesionarios()
        col3.metric("📍 Concesionarios", total_cons)
    
    # FILTRO POR MARCA
    if marca_sel != "Seleccionar...":
        query = """
            SELECT m.id_pk_moto, m.referencia AS modelo, p.precio_venta AS precio, 
            m.cilindraje_cc AS cc, m.url_imagen, m.tipo_moto
            FROM motos_ficha_tecnica m
            JOIN precios_trimestrales p ON m.id_pk_moto = p.id_fk_moto
            JOIN marcas ma ON m.id_fk_marca = ma.id_marca
            WHERE ma.nombre = %s
            ORDER BY p.precio_venta ASC
        """
        datos_db = ejecutar_consulta(query, (marca_sel,))
        if datos_db:
            motos = [{
                "id": d['id_pk_moto'], 
                "modelo": d['modelo'], 
                "precio": f"${int(d['precio']):,.0f}".replace(",", "."), 
                "cc": f"{d['cc']}cc", 
                "imagen": d['url_imagen'],
                "tipo": d['tipo_moto']
            } for d in datos_db]
            st.subheader(f"🏭 Catálogo {marca_sel} ({len(motos)} modelos)")
            mostrar_matriz(motos, "mrc")
        else:
            st.warning(f"No se encontraron motos de la marca {marca_sel}")
    
    # FILTRO POR CILINDRAJE
    elif cc_sel != "Seleccionar...":
        valor_cc = int(cc_sel.replace("cc", ""))
        query = """
            SELECT m.id_pk_moto, ma.nombre AS marca, m.referencia AS modelo, 
            p.precio_venta AS precio, m.cilindraje_cc AS cc, m.url_imagen, m.tipo_moto
            FROM motos_ficha_tecnica m 
            JOIN precios_trimestrales p ON m.id_pk_moto = p.id_fk_moto 
            JOIN marcas ma ON m.id_fk_marca = ma.id_marca 
            WHERE m.cilindraje_cc = %s
            ORDER BY p.precio_venta ASC
        """
        datos_db = ejecutar_consulta(query, (valor_cc,))
        if datos_db:
            motos = [{
                "id": d['id_pk_moto'], 
                "modelo": f"{d['marca']} {d['modelo']}", 
                "precio": f"${int(d['precio']):,.0f}".replace(",", "."), 
                "cc": f"{d['cc']}cc", 
                "imagen": d['url_imagen'],
                "tipo": d['tipo_moto']
            } for d in datos_db]
            st.subheader(f"🔧 Motos de {cc_sel} ({len(motos)} modelos)")
            mostrar_matriz(motos, "cc")
        else:
            st.warning(f"No se encontraron motos de {cc_sel}")
    
    # FILTRO POR TIPO DE MOTO
    elif tipo_sel != "Seleccionar...":
        query = """
            SELECT m.id_pk_moto, ma.nombre AS marca, m.referencia AS modelo, 
            p.precio_venta AS precio, m.cilindraje_cc AS cc, m.url_imagen, m.tipo_moto
            FROM motos_ficha_tecnica m 
            JOIN precios_trimestrales p ON m.id_pk_moto = p.id_fk_moto 
            JOIN marcas ma ON m.id_fk_marca = ma.id_marca 
            WHERE m.tipo_moto = %s
            ORDER BY p.precio_venta ASC
        """
        datos_db = ejecutar_consulta(query, (tipo_sel,))
        
        if datos_db:
            col_est1, col_est2, col_est3 = st.columns(3)
            with col_est1:
                st.metric("📊 Total modelos", len(datos_db))
            with col_est2:
                marcas_unicas = len(set(d['marca'] for d in datos_db))
                st.metric("🏭 Marcas disponibles", marcas_unicas)
            with col_est3:
                precio_min = min(d['precio'] for d in datos_db)
                precio_max = max(d['precio'] for d in datos_db)
                st.metric("💰 Rango de precios", f"${int(precio_min):,.0f} - ${int(precio_max):,.0f}".replace(",", "."))
            
            st.divider()
            motos = [{
                "id": d['id_pk_moto'], 
                "modelo": f"{d['marca']} {d['modelo']}", 
                "precio": f"${int(d['precio']):,.0f}".replace(",", "."), 
                "cc": f"{d['cc']}cc", 
                "imagen": d['url_imagen'],
                "tipo": d['tipo_moto']
            } for d in datos_db]
            
            mostrar_matriz(motos, "tipo")
        else:
            st.warning(f"No se encontraron motos del tipo **{tipo_sel}**")
    
    # FILTRO POR PRECIO
    elif rango_sel != "Seleccionar...":
        partes = rango_sel.replace("'000.000", "000000").split(" - ")
        query = """
            SELECT m.id_pk_moto, ma.nombre AS marca, m.referencia AS modelo, 
            p.precio_venta AS precio, m.cilindraje_cc AS cc, m.url_imagen, m.tipo_moto
            FROM motos_ficha_tecnica m 
            JOIN precios_trimestrales p ON m.id_pk_moto = p.id_fk_moto 
            JOIN marcas ma ON m.id_fk_marca = ma.id_marca 
            WHERE p.precio_venta BETWEEN %s AND %s
            ORDER BY p.precio_venta ASC
        """
        datos_db = ejecutar_consulta(query, (int(partes[0]), int(partes[1])))
        if datos_db:
            motos = [{
                "id": d['id_pk_moto'], 
                "modelo": f"{d['marca']} {d['modelo']}", 
                "precio": f"${int(d['precio']):,.0f}".replace(",", "."), 
                "cc": f"{d['cc']}cc", 
                "imagen": d['url_imagen'],
                "tipo": d['tipo_moto']
            } for d in datos_db]
            st.subheader(f"💰 Motos en rango de precio: {rango_sel} ({len(motos)} modelos)")
            mostrar_matriz(motos, "prc")
        else:
            st.warning(f"No se encontraron motos en el rango de precio {rango_sel}")

if __name__ == "__main__":
    # Inicializar session state
    if 'v_precio' not in st.session_state:
        st.session_state.v_precio = "Seleccionar..."
    if 'v_marca' not in st.session_state:
        st.session_state.v_marca = "Seleccionar..."
    if 'v_cc' not in st.session_state:
        st.session_state.v_cc = "Seleccionar..."
    if 'v_tipo' not in st.session_state:
        st.session_state.v_tipo = "Seleccionar..."
    
    main()
