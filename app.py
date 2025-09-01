import streamlit as st
import requests
import json
from urllib.parse import urlparse, parse_qs
from openai import OpenAI
import re
from datetime import datetime
import time

# Configuración de la página
st.set_page_config(
    page_title="Extractor de Filtros Ecommerce",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded"
)

class EcommerceFilterExtractor:
    def __init__(self, zenrows_api_key: str, openai_api_key: str):
        self.zenrows_api_key = zenrows_api_key
        self.openai_client = OpenAI(api_key=openai_api_key)
        self.zenrows_url = "https://api.zenrows.com/v1/"
    
    def extract_url_parameters(self, url: str):
        """Extrae parámetros directamente de la URL"""
        parsed_url = urlparse(url)
        url_params = parse_qs(parsed_url.query)
        
        clean_params = {}
        for key, values in url_params.items():
            if len(values) == 1:
                clean_params[key] = values[0]
            else:
                clean_params[key] = values
        
        return {
            'domain': parsed_url.netloc,
            'path': parsed_url.path,
            'parameters': clean_params
        }
    
    def scrape_page_content(self, url: str):
        """Obtiene el contenido HTML usando Zenrows"""
        params = {
            'url': url,
            'apikey': self.zenrows_api_key,
            'js_render': 'true',
            'wait': 3000,
        }
        
        try:
            response = requests.get(self.zenrows_url, params=params, timeout=30)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            st.error(f"Error al hacer scraping: {e}")
            return None
    
    def extract_filter_elements(self, html_content: str):
        """Extrae elementos relevantes del HTML"""
        if not html_content:
            return ""
        
        filter_patterns = [
            r'<div[^>]*class="[^"]*filter[^"]*"[^>]*>.*?</div>',
            r'<aside[^>]*class="[^"]*sidebar[^"]*"[^>]*>.*?</aside>',
            r'<form[^>]*class="[^"]*filter[^"]*"[^>]*>.*?</form>',
            r'<div[^>]*class="[^"]*facet[^"]*"[^>]*>.*?</div>',
            r'<select[^>]*name="[^"]*"[^>]*>.*?</select>',
            r'<input[^>]*type="checkbox"[^>]*>.*?(?=<input|</div>|</form>)',
            r'<ul[^>]*class="[^"]*category[^"]*"[^>]*>.*?</ul>',
        ]
        
        extracted_elements = []
        for pattern in filter_patterns:
            matches = re.findall(pattern, html_content, re.DOTALL | re.IGNORECASE)
            extracted_elements.extend(matches)
        
        content = ' '.join(extracted_elements)
        return content[:8000]
    
    def analyze_with_openai(self, url: str, html_content: str, url_params: dict):
        """Usa OpenAI para analizar el contenido"""
        filter_elements = self.extract_filter_elements(html_content)
        
        prompt = f"""
Analiza esta página de ecommerce y extrae todos los filtros disponibles de forma estructurada.

URL: {url}
Parámetros de URL detectados: {json.dumps(url_params, indent=2)}

Elementos HTML relevantes:
{filter_elements[:6000]}

Extrae y estructura los filtros en el siguiente formato JSON:
{{
    "filters": {{
        "price": {{
            "type": "range",
            "min": null,
            "max": null,
            "current_min": null,
            "current_max": null
        }},
        "categories": {{
            "type": "select",
            "options": [],
            "selected": []
        }},
        "brands": {{
            "type": "multiselect",
            "options": [],
            "selected": []
        }},
        "colors": {{
            "type": "multiselect",
            "options": [],
            "selected": []
        }},
        "sizes": {{
            "type": "multiselect", 
            "options": [],
            "selected": []
        }},
        "rating": {{
            "type": "range",
            "min": 1,
            "max": 5,
            "current": null
        }},
        "availability": {{
            "type": "boolean",
            "options": ["in_stock", "out_of_stock"],
            "selected": null
        }}
    }},
    "active_filters": {{}},
    "filter_count": 0,
    "sort_options": [],
    "current_sort": null
}}

Instrucciones:
1. Identifica TODOS los filtros disponibles en la página
2. Determina el tipo de cada filtro (range, select, multiselect, boolean)
3. Extrae las opciones disponibles para cada filtro
4. Identifica qué filtros están actualmente aplicados
5. Incluye opciones de ordenamiento si las encuentras
6. Si un filtro no existe en la página, no lo incluyas en la respuesta

Responde SOLO con el JSON válido, sin explicaciones adicionales.
"""

        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Eres un experto en análisis de páginas de ecommerce. Extraes filtros y los estructuras en formato JSON válido."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=2000
            )
            
            content = response.choices[0].message.content.strip()
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            else:
                return json.loads(content)
                
        except Exception as e:
            st.error(f"Error al analizar con OpenAI: {e}")
            return {"error": str(e)}
    
    def extract_filters(self, url: str, include_html_analysis: bool = True):
        """Función principal para extraer filtros"""
        result = {
            "url": url,
            "timestamp": datetime.now().isoformat(),
            "url_analysis": {},
            "filters": {},
            "success": False
        }
        
        try:
            # Extraer parámetros de la URL
            url_analysis = self.extract_url_parameters(url)
            result["url_analysis"] = url_analysis
            
            if include_html_analysis:
                # Hacer scraping de la página
                html_content = self.scrape_page_content(url)
                
                if html_content:
                    # Analizar con OpenAI
                    ai_analysis = self.analyze_with_openai(url, html_content, url_analysis)
                    result["filters"] = ai_analysis
                    result["success"] = True
                else:
                    result["error"] = "No se pudo obtener el contenido de la página"
            else:
                result["filters"] = {"url_parameters": url_analysis["parameters"]}
                result["success"] = True
                
        except Exception as e:
            result["error"] = str(e)
        
        return result

def main():
    st.title("🛒 Extractor de Filtros de Ecommerce")
    st.markdown("Extrae y analiza filtros de páginas de categorías de tiendas online usando IA")
    
    # Sidebar para configuración
    with st.sidebar:
        st.header("⚙️ Configuración")
        
        # Claves API
        zenrows_key = st.text_input(
            "Clave API de Zenrows", 
            type="password",
            help="Obtén tu clave en zenrows.com"
        )
        
        openai_key = st.text_input(
            "Clave API de OpenAI", 
            type="password",
            help="Obtén tu clave en platform.openai.com"
        )
        
        st.markdown("---")
        
        # Opciones de análisis
        st.header("🔧 Opciones")
        include_html = st.checkbox("Análisis completo (HTML)", value=True)
        
        if not include_html:
            st.info("Solo se analizarán los parámetros de la URL")
        
        st.markdown("---")
        
        # Enlaces útiles
        st.header("🔗 Enlaces útiles")
        st.markdown("- [Zenrows](https://zenrows.com)")
        st.markdown("- [OpenAI API](https://platform.openai.com)")
        st.markdown("- [Código fuente](https://github.com/tu-usuario/tu-repo)")
    
    # Área principal
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.header("📝 URL a Analizar")
        
        url = st.text_input(
            "Introduce la URL de la página de categoría:",
            placeholder="https://ejemplo.com/categoria/zapatos?filtros=activos",
            help="Debe ser una URL completa de una página de categoría de ecommerce"
        )
        
        # URLs de ejemplo
        with st.expander("🔍 URLs de ejemplo"):
            example_urls = [
                "https://www.amazon.com/s?k=laptops",
                "https://www.ebay.com/sch/i.html?_nkw=smartphone",
                "https://www.mercadolibre.com/categoria/zapatos",
                "https://www.aliexpress.com/category/electronics"
            ]
            
            for example_url in example_urls:
                if st.button(f"Usar: {example_url}", key=example_url):
                    st.experimental_rerun()
    
    with col2:
        st.header("🚀 Acción")
        
        analyze_button = st.button(
            "🔍 Analizar Filtros",
            type="primary",
            disabled=not (url and zenrows_key and openai_key),
            use_container_width=True
        )
        
        if not zenrows_key or not openai_key:
            st.warning("⚠️ Introduce las claves API para continuar")
        elif not url:
            st.warning("⚠️ Introduce una URL para analizar")
    
    # Procesar análisis
    if analyze_button and url and zenrows_key and openai_key:
        try:
            # Validar URL
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                st.error("❌ URL no válida")
                return
            
            # Crear extractor
            with st.spinner("🔄 Inicializando extractor..."):
                extractor = EcommerceFilterExtractor(zenrows_key, openai_key)
            
            # Mostrar progreso
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # Análisis
            status_text.text("📊 Analizando URL...")
            progress_bar.progress(25)
            
            if include_html:
                status_text.text("🕷️ Haciendo scraping de la página...")
                progress_bar.progress(50)
                
                status_text.text("🤖 Analizando contenido con IA...")
                progress_bar.progress(75)
            
            # Extraer filtros
            result = extractor.extract_filters(url, include_html)
            
            progress_bar.progress(100)
            status_text.text("✅ Análisis completado!")
            
            time.sleep(0.5)  # Pausa para mostrar completado
            progress_bar.empty()
            status_text.empty()
            
            # Mostrar resultados
            st.success(f"✅ Análisis completado para: {result['url']}")
            
            if result["success"]:
                # Tabs para organizar resultados
                tab1, tab2, tab3 = st.tabs(["🎯 Filtros Encontrados", "📋 Análisis URL", "📄 JSON Completo"])
                
                with tab1:
                    if "filters" in result["filters"]:
                        filters = result["filters"]["filters"]
                        
                        st.subheader(f"🎯 {len(filters)} Filtros Detectados")
                        
                        for filter_name, filter_data in filters.items():
                            with st.expander(f"🔍 {filter_name.title()} ({filter_data.get('type', 'unknown')})"):
                                st.json(filter_data)
                        
                        # Resumen
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Total Filtros", len(filters))
                        with col2:
                            active_count = len(result["filters"].get("active_filters", {}))
                            st.metric("Filtros Activos", active_count)
                        with col3:
                            sort_count = len(result["filters"].get("sort_options", []))
                            st.metric("Opciones Orden", sort_count)
                    else:
                        st.info("No se encontraron filtros estructurados en esta página")
                
                with tab2:
                    st.subheader("📋 Análisis de URL")
                    
                    url_info = result["url_analysis"]
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write("**Dominio:**", url_info["domain"])
                        st.write("**Ruta:**", url_info["path"])
                    
                    with col2:
                        params = url_info["parameters"]
                        st.write("**Parámetros URL:**", len(params))
                        if params:
                            st.json(params)
                
                with tab3:
                    st.subheader("📄 Respuesta JSON Completa")
                    st.json(result)
                    
                    # Botón para descargar
                    json_str = json.dumps(result, indent=2, ensure_ascii=False)
                    st.download_button(
                        label="📥 Descargar JSON",
                        data=json_str,
                        file_name=f"filtros_{parsed.netloc}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                        mime="application/json"
                    )
            
            else:
                st.error("❌ Error en el análisis:")
                st.error(result.get("error", "Error desconocido"))
                
        except Exception as e:
            st.error(f"❌ Error inesperado: {str(e)}")
    
    # Footer
    st.markdown("---")
    st.markdown(
        """
        <div style='text-align: center; color: #666;'>
            Desarrollado con ❤️ usando Streamlit | 
            <a href='https://zenrows.com' target='_blank'>Zenrows</a> + 
            <a href='https://openai.com' target='_blank'>OpenAI</a>
        </div>
        """, 
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()
