# -*- coding: utf-8 -*-
# ==========================================================================================
# App: Encuesta Comunidad → XLSForm para ArcGIS Survey123 (Páginas + Cantón→Distrito + Glosario)
# - Páginas reales (settings.style="pages")
# - Portada/Introducción (P1)
# - Consentimiento informado (P2)
# - Datos Demográficos (P3) + Cantón→Distrito (catálogo por lotes)
# - II. Percepción ciudadana (P4): preguntas 7 a 11 + matriz (select_one por fila)
# - III. Riesgos sociales/situacionales (P5): preguntas 12 a 18
# - Glosario AUTOMÁTICO:
#     * Lee el DOCX
#     * Detecta similitudes (términos del glosario presentes en la sección)
#     * Si hay coincidencias: agrega pregunta "¿Desea acceder al glosario de esta sección?"
#       y crea una PÁGINA de glosario con definiciones COMPLETAS (sin recortar).
# ==========================================================================================

import re
import unicodedata
from io import BytesIO
from datetime import datetime
from typing import Dict, List, Tuple

import streamlit as st
import pandas as pd

# --- Requiere python-docx para leer el glosario ---
from docx import Document

# ------------------------------------------------------------------------------------------
# Configuración de la app
# ------------------------------------------------------------------------------------------
st.set_page_config(page_title="Encuesta Comunidad → XLSForm (Survey123)", layout="wide")
st.title("Encuesta Comunidad → XLSForm para ArcGIS Survey123")

st.markdown("""
Esta app construye un **XLSForm** listo para **ArcGIS Survey123** con:
- **Páginas** (style = pages)
- **Catálogo Cantón → Distrito** (choice_filter)
- **Glosario por sección**, integrado al XLSForm **solo si hay coincidencias** con el Word.
""")

# ------------------------------------------------------------------------------------------
# Helpers base
# ------------------------------------------------------------------------------------------
def _rerun():
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()

def slugify_name(texto: str) -> str:
    if not texto:
        return "campo"
    t = texto.lower().strip()
    t = re.sub(r"[áàäâ]", "a", t)
    t = re.sub(r"[éèëê]", "e", t)
    t = re.sub(r"[íìïî]", "i", t)
    t = re.sub(r"[óòöô]", "o", t)
    t = re.sub(r"[úùüû]", "u", t)
    t = re.sub(r"ñ", "n", t)
    t = re.sub(r"[^a-z0-9]+", "_", t).strip("_")
    return t or "campo"

def asegurar_nombre_unico(base: str, usados: set) -> str:
    if base not in usados:
        return base
    i = 2
    while f"{base}_{i}" in usados:
        i += 1
    return f"{base}_{i}"

def norm_txt(s: str) -> str:
    """
    Normaliza para comparación:
    - minúsculas
    - sin tildes/diacríticos
    - espacios simples
    """
    if s is None:
        return ""
    s = str(s).strip().lower()
    s = "".join(
        ch for ch in unicodedata.normalize("NFD", s)
        if unicodedata.category(ch) != "Mn"
    )
    s = re.sub(r"\s+", " ", s)
    return s

def map_tipo_to_xlsform(tipo_ui: str, name: str):
    # UI mínimo (para seed fijo)
    if tipo_ui == "note":
        return ("note", None, None)
    if tipo_ui == "text":
        return ("text", None, None)
    if tipo_ui == "text_multiline":
        return ("text", "multiline", None)
    if tipo_ui == "select_one":
        return (f"select_one list_{name}", None, f"list_{name}")
    if tipo_ui == "select_multiple":
        return (f"select_multiple list_{name}", None, f"list_{name}")
    return ("text", None, None)

# ------------------------------------------------------------------------------------------
# Glosario (leer DOCX y construir dict término->definición SIN recortar)
# ------------------------------------------------------------------------------------------
GLOSARIO_DOCX_PATH = "/mnt/data/glosario proceso de encuestas ESS.docx"

@st.cache_data(show_spinner=False)
def cargar_glosario_desde_docx(path_docx: str) -> Dict[str, str]:
    """
    Extrae entradas tipo:
      "Término: definición..."
    Mantiene definiciones completas (incluye puntos, comillas, paréntesis, etc.).
    Une líneas cuando corresponda.
    """
    doc = Document(path_docx)
    paras = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]

    glos = {}
    # Patrón: "Termino: definicion"
    # Ojo: hay términos con paréntesis, comillas, guiones, etc.
    rx = re.compile(r"^\s*([^:]{2,120})\s*:\s*(.+)\s*$")

    current_term = None
    current_def = []

    def flush():
        nonlocal current_term, current_def
        if current_term and current_def:
            full_def = "\n".join([x.rstrip() for x in current_def]).strip()
            if full_def:
                # Si ya existe, no lo pisamos (primera ocurrencia manda)
                glos.setdefault(current_term.strip(), full_def)
        current_term = None
        current_def = []

    for line in paras:
        m = rx.match(line)
        if m:
            # nueva entrada
            flush()
            current_term = m.group(1).strip()
            current_def = [m.group(2).strip()]
        else:
            # continuación de definición (o texto suelto)
            if current_term:
                current_def.append(line)
            else:
                # Ignora encabezados u otros textos antes de la primera entrada
                continue

    flush()
    return glos

def detectar_terminos_en_texto(glosario: Dict[str, str], texto: str) -> List[str]:
    """
    Devuelve lista de términos del glosario encontrados en 'texto' (normalizado).
    Coincidencia por palabra/frase (con bordes) usando texto sin tildes.
    """
    t = norm_txt(texto)
    encontrados = []

    # Para evitar falsos positivos por subcadenas raras, usamos bordes "no-letra/no-numero".
    # Si el término tiene espacios, igual se busca como frase.
    for term in glosario.keys():
        nt = norm_txt(term)
        if not nt:
            continue

        # escapamos y buscamos como token/frase con bordes
        pattern = r"(?<![a-z0-9])" + re.escape(nt) + r"(?![a-z0-9])"
        if re.search(pattern, t):
            encontrados.append(term)

    # orden estable
    return sorted(set(encontrados), key=lambda x: norm_txt(x))

def compilar_texto_seccion(preguntas: List[Dict]) -> str:
    """
    Junta labels + opciones de una sección para detectar similitudes.
    """
    partes = []
    for q in preguntas:
        partes.append(str(q.get("label", "")))
        for opt in (q.get("opciones") or []):
            partes.append(str(opt))
    return "\n".join([p for p in partes if p and str(p).strip()])

# ------------------------------------------------------------------------------------------
# Catálogo Cantón → Distrito (por lotes)  **RESTABLECIDO**: varios distritos por Enter
# ------------------------------------------------------------------------------------------
if "choices_ext_rows" not in st.session_state:
    st.session_state.choices_ext_rows = []  # filas para hoja choices
if "choices_extra_cols" not in st.session_state:
    st.session_state.choices_extra_cols = set()

def _append_choice_unique(row: Dict):
    """Inserta fila en choices evitando duplicados por (list_name,name)."""
    key = (row.get("list_name"), row.get("name"))
    exists = any((r.get("list_name"), r.get("name")) == key for r in st.session_state.choices_ext_rows)
    if not exists:
        st.session_state.choices_ext_rows.append(row)

st.markdown("### Catálogo Cantón → Distrito (por lotes)")
with st.expander("Agrega un lote (un Cantón y varios Distritos)", expanded=True):
    col_c1, col_c2 = st.columns([1, 2])
    canton_txt = col_c1.text_input("Cantón (una vez)", value="")
    distritos_txt = col_c2.text_area("Distritos del cantón (uno por línea)", value="", height=110)

    col_b1, col_b2, col_b3 = st.columns([1, 1, 2])
    add_lote = col_b1.button("Agregar lote", type="primary", use_container_width=True)
    clear_all = col_b2.button("Limpiar catálogo", use_container_width=True)

    if clear_all:
        st.session_state.choices_ext_rows = []
        st.success("Catálogo limpiado.")

    if add_lote:
        c = canton_txt.strip()
        distritos = [d.strip() for d in distritos_txt.splitlines() if d.strip()]

        if not c or not distritos:
            st.error("Debes indicar el Cantón y al menos un Distrito (uno por línea).")
        else:
            slug_c = slugify_name(c)

            st.session_state.choices_extra_cols.update({"canton_key", "any"})

            # Placeholders (una sola vez por lista)
            _append_choice_unique({"list_name": "list_canton", "name": "__pick_canton__", "label": "— escoja un cantón —"})
            _append_choice_unique({"list_name": "list_distrito", "name": "__pick_distrito__", "label": "— escoja un cantón —", "any": "1"})

            # Cantón
            _append_choice_unique({"list_name": "list_canton", "name": slug_c, "label": c})

            # Distritos (muchos)
            usados_d = set()
            for d in distritos:
                slug_d = asegurar_nombre_unico(slugify_name(d), usados_d)
                usados_d.add(slug_d)
                _append_choice_unique({"list_name": "list_distrito", "name": slug_d, "label": d, "canton_key": slug_c})

            st.success(f"Lote agregado: {c} → {len(distritos)} distritos.")

if st.session_state.choices_ext_rows:
    st.dataframe(pd.DataFrame(st.session_state.choices_ext_rows), use_container_width=True, hide_index=True, height=220)

# ------------------------------------------------------------------------------------------
# Cabecera: datos básicos + logo opcional
# ------------------------------------------------------------------------------------------
DEFAULT_LOGO_PATH = "001.png"

col_logo, col_txt = st.columns([1, 3], vertical_alignment="center")
with col_logo:
    up_logo = st.file_uploader("Logo (PNG/JPG)", type=["png", "jpg", "jpeg"])
    if up_logo:
        st.image(up_logo, caption="Logo cargado", use_container_width=True)
        st.session_state["_logo_bytes"] = up_logo.getvalue()
        st.session_state["_logo_name"] = up_logo.name
    else:
        try:
            st.image(DEFAULT_LOGO_PATH, caption="Logo (001.png)", use_container_width=True)
            st.session_state["_logo_bytes"] = None
            st.session_state["_logo_name"] = "001.png"
        except Exception:
            st.session_state["_logo_bytes"] = None
            st.session_state["_logo_name"] = "logo.png"

with col_txt:
    delegacion = st.text_input("Nombre del lugar / Delegación", value="San Carlos Oeste")
    logo_media_name = st.text_input(
        "Nombre de archivo para `media::image` (Survey123)",
        value=st.session_state.get("_logo_name", "001.png"),
        help="Debe coincidir con el archivo en la carpeta `media/` de Survey123 Connect."
    )

# ------------------------------------------------------------------------------------------
# Textos fijos (SIN recortar)
# ------------------------------------------------------------------------------------------
INTRO_P1 = (
    "Con el fin de hacer más segura nuestra comunidad, deseamos concentrarnos en los\n"
    "problemas de seguridad más importantes. Queremos trabajar en conjunto con el gobierno\n"
    "local, otras instituciones y la comunidad para reducir los delitos y riesgos que afectan a las\n"
    "personas.\n\n"
    "Es importante recordarle que la información que usted nos proporcione es confidencial y se\n"
    "utilizará únicamente para mejorar la seguridad en nuestra área."
)

CONSENTIMIENTO_P2 = (
    "Consentimiento Informado para la Participación en la Encuesta\n\n"
    "Usted está siendo invitado(a) a participar de forma libre y voluntaria en una encuesta sobre seguridad,\n"
    "convivencia y percepción ciudadana.\n\n"
    "El objetivo de esta encuesta es recopilar información de carácter preventivo y estadístico, con el fin de\n"
    "apoyar la planificación de acciones de prevención, mejora de la convivencia y fortalecimiento de la\n"
    "seguridad en comunidades y zonas comerciales.\n\n"
    "La participación es totalmente voluntaria. Usted puede negarse a responder cualquier pregunta, así\n"
    "como retirarse de la encuesta en cualquier momento, sin que ello genere consecuencia alguna.\n\n"
    "De conformidad con lo dispuesto en el artículo 5 de la Ley N.º 8968, Ley de Protección de la Persona\n"
    "frente al Tratamiento de sus Datos Personales, se le informa que:\n"
    "• Finalidad del tratamiento: La información recopilada será utilizada exclusivamente para fines\n"
    "  estadísticos, analíticos y preventivos.\n"
    "• Confidencialidad: La información se tratará de forma confidencial.\n"
    "• Carácter voluntario: La participación es libre y voluntaria.\n"
)

# ------------------------------------------------------------------------------------------
# Seed fijo de secciones (P1..P5) — sin constructor editable (para que NO tengas que tocar nada)
# ------------------------------------------------------------------------------------------
# Si querés que vuelva el constructor, se puede, pero aquí lo dejo fijo como pediste:
# "yo no voy agregar nada ni hacer cambios".

YESNO = ["Sí", "No"]

# P3 Datos demográficos (según tu imagen)
P3_DEMOG = [
    {"tipo_ui": "select_one", "name": "canton", "label": "1. Cantón:", "required": True, "opciones": [], "list_name_override": "list_canton"},
    {"tipo_ui": "select_one", "name": "distrito", "label": "2. Distrito:", "required": True, "opciones": [], "list_name_override": "list_distrito",
     "choice_filter": "canton_key=${canton} or any='1'"},
    {"tipo_ui": "select_one", "name": "edad_rango", "label": "3. Edad (en años cumplidos): marque con una X la categoría que incluya su edad.",
     "required": True, "opciones": ["18 a 29 años", "30 a 44 años", "45 a 59 años", "60 años o más"]},
    {"tipo_ui": "select_one", "name": "genero", "label": "4. ¿Con cuál de estas opciones se identifica?",
     "required": True, "opciones": ["Femenino", "Masculino", "Persona No Binaria", "Prefiero no decir"]},
    {"tipo_ui": "select_one", "name": "escolaridad", "label": "5. Escolaridad:",
     "required": True, "opciones": ["Ninguna", "Primaria incompleta", "Primaria completa", "Secundaria incompleta", "Secundaria completa",
                                    "Técnico", "Universitaria incompleta", "Universitaria completa"]},
    {"tipo_ui": "select_one", "name": "relacion_zona", "label": "6. ¿Cuál es su relación con la zona?",
     "required": True, "opciones": ["Vivo en la zona", "Trabajo en la zona", "Visito la zona", "Estudio en la zona"]},
]

# P4 II. Percepción ciudadana de seguridad en el distrito (Q7..11 + matriz)
LIKERT_5_NA = ["Muy inseguro (1)", "Inseguro (2)", "Ni seguro ni inseguro (3)", "Seguro (4)", "Muy seguro (5)", "No aplica"]

P4_PERCEPCION = [
    {"tipo_ui": "select_one", "name": "p7_perc_seguro_distrito",
     "label": "7. ¿Qué tan seguro percibe usted el distrito donde reside o transita?",
     "required": True, "opciones": ["Muy inseguro", "Inseguro", "Ni seguro ni inseguro", "Seguro", "Muy seguro"]},

    {"tipo_ui": "select_multiple", "name": "p71_por_que_inseguro",
     "label": "7.1. Indique por qué considera el distrito inseguro (Marque todas las situaciones que usted percibe que ocurren con mayor frecuencia en su comunidad):",
     "required": True,
     "opciones": [
         "Venta o distribución de drogas",
         "Consumo de drogas en espacios públicos",
         "Consumo de alcohol en espacios públicos",
         "Riñas o peleas frecuentes",
         "Asaltos o robos a personas",
         "Robos a viviendas o comercios",
         "Amenazas o extorsiones",
         "Balaceras, detonaciones o ruidos similares",
         "Presencia de grupos que generan temor",
         "Vandalismo o daños intencionales",
         "Poca iluminación en calles o espacios públicos",
         "Lotes baldíos o abandonados",
         "Casas o edificios abandonados",
         "Calles en mal estado",
         "Falta de limpieza o acumulación de basura",
         "Paradas de bus inseguras",
         "Falta de cámaras de seguridad",
         "Comercios inseguros o sin control",
         "Daños frecuentes a la propiedad",
         "Presencia de personas en situación de calle",
         "Ventas ambulantes desordenadas",
         "Problemas con transporte informal",
         "Zonas donde se concentra consumo de alcohol o drogas",
         "Puntos conflictivos recurrentes",
         "Falta de patrullajes visibles",
         "Falta de presencia policial en la zona",
         "Situaciones de violencia intrafamiliar",
         "Situaciones de violencia de género",
         "Otro problema que considere importante"
     ],
     "relevant": None  # la seteo abajo según selección
    },

    {"tipo_ui": "note", "name": "nota_p71",
     "label": "Esta pregunta recoge percepción general y no constituye denuncia."},

    {"tipo_ui": "select_one", "name": "p8_comparacion_anno",
     "label": "8. ¿Cómo se percibe la seguridad en este distrito este año en comparación con el año anterior?",
     "required": True, "opciones": ["1 (Mucho menos seguro)", "2 (Menos seguro)", "3 (Se mantiene igual)", "4 (Más seguro)", "5 (Mucho más seguro)"]},

    {"tipo_ui": "text_multiline", "name": "p81_indique_por_que",
     "label": "8.1. Indique por qué: Espacio abierto para detallar:",
     "required": True,
     "relevant": "${p8_comparacion_anno}!=''"},

    # Matriz Q9 (select_one por fila con escala 1..5 + NA)
    {"tipo_ui": "select_one", "name": "p9_discotecas",
     "label": "9. Discotecas, bares, sitios de entretenimiento",
     "required": True, "opciones": LIKERT_5_NA},
    {"tipo_ui": "select_one", "name": "p9_espacios_recreativos",
     "label": "9. Espacios recreativos (parques, play, plaza de deportes)",
     "required": True, "opciones": LIKERT_5_NA},
    {"tipo_ui": "select_one", "name": "p9_residencia",
     "label": "9. Lugar de residencia (casa de habitación)",
     "required": True, "opciones": LIKERT_5_NA},
    {"tipo_ui": "select_one", "name": "p9_paradas",
     "label": "9. Paradas y/o estaciones de buses, taxis, trenes",
     "required": True, "opciones": LIKERT_5_NA},
    {"tipo_ui": "select_one", "name": "p9_puentes",
     "label": "9. Puentes peatonales",
     "required": True, "opciones": LIKERT_5_NA},
    {"tipo_ui": "select_one", "name": "p9_transporte",
     "label": "9. Transporte público",
     "required": True, "opciones": LIKERT_5_NA},
    {"tipo_ui": "select_one", "name": "p9_zona_bancaria",
     "label": "9. Zona bancaria",
     "required": True, "opciones": LIKERT_5_NA},
    {"tipo_ui": "select_one", "name": "p9_zona_comercio",
     "label": "9. Zona de comercio",
     "required": True, "opciones": LIKERT_5_NA},
    {"tipo_ui": "select_one", "name": "p9_zonas_residenciales",
     "label": "9. Zonas residenciales (calles y barrios, distinto a su casa)",
     "required": True, "opciones": LIKERT_5_NA},
    {"tipo_ui": "select_one", "name": "p9_zonas_francas",
     "label": "9. Zonas francas",
     "required": True, "opciones": LIKERT_5_NA},
    {"tipo_ui": "select_one", "name": "p9_turistico",
     "label": "9. Lugares de interés turístico",
     "required": True, "opciones": LIKERT_5_NA},
    {"tipo_ui": "select_one", "name": "p9_centros_educativos",
     "label": "9. Centros educativos",
     "required": True, "opciones": LIKERT_5_NA},
    {"tipo_ui": "select_one", "name": "p9_def_iluminacion",
     "label": "9. Zonas con deficiencia de iluminación",
     "required": True, "opciones": LIKERT_5_NA},

    {"tipo_ui": "select_one", "name": "p10_tipo_espacio_mas_inseguro",
     "label": "10. Según su percepción ¿cuál de los siguientes tipos de espacios del distrito considera más inseguro?",
     "required": True,
     "opciones": [
         "Discotecas, bares, sitios de entretenimiento",
         "Espacios recreativos (parques, play, plaza de deportes)",
         "Lugar de residencia (casa de habitación)",
         "Paradas y/o estaciones de buses, taxis, trenes",
         "Puentes peatonales",
         "Transporte público",
         "Zona bancaria",
         "Zona comercial",
         "Zonas francas",
         "Zonas residenciales (calles y barrios, distinto a su casa)",
         "Lugares de interés turístico",
         "Centros educativos",
         "Zonas con deficiencia de iluminación",
         "Otros"
     ]},

    {"tipo_ui": "text_multiline", "name": "p11_por_que_tipo_espacio",
     "label": "11. Según su percepción, describa brevemente por qué considera inseguro el tipo de espacio seleccionado en la pregunta anterior. Espacio abierto para detallar:",
     "required": True},
]

# relevant de 7.1: solo si Q7 es "Muy inseguro" o "Inseguro"
# Usamos slug interno al exportar choices; aquí dejamos regla al construir (ver función).
# Para no depender de slug literal aquí, lo armamos en construir.

# P5 III. Riesgos sociales y situacionales (12..18)
P5_RIESGOS = [
    {"tipo_ui": "note", "name": "p5_intro",
     "label": "A continuación, se presentará una lista de problemáticas que se catalogan como factores situacionales, con la finalidad de que seleccione aquellos que considere que ocurren en su distrito."},

    {"tipo_ui": "select_multiple", "name": "p12_problematicas",
     "label": "12. Según su percepción u observación, seleccione las problemáticas que afectan su distrito:",
     "required": True,
     "opciones": [
         "Problemas vecinales o conflictos entre vecinos",
         "Personas en situación de ocio",
         "Presencia de personas en situación de calle",
         "Zona donde se ejerce prostitución",
         "Desvinculación escolar (deserción escolar)",
         "Falta de oportunidades laborales",
         "Acumulación de basura, aguas negras o mal alcantarillado",
         "Carencia o inexistencia de alumbrado público",
         "Lotes baldíos",
         "Cuarterías",
         "Asentamientos informales o precarios",
         "Pérdida de espacios públicos (parques, polideportivos u otros)",
         "Consumo de alcohol en vía pública",
         "Ventas informales desordenadas",
         "Escándalos musicales o ruidos excesivos",
         "Otro problema que considere importante"
     ]},

    {"tipo_ui": "select_multiple", "name": "p13_carencias_inversion_social",
     "label": "13. En relación con la inversión social en su distrito, indique cuáles de las siguientes carencias identifica:",
     "required": True,
     "opciones": [
         "Falta de oferta educativa",
         "Falta de oferta deportiva",
         "Falta de oferta recreativa",
         "Falta de actividades culturales"
     ]},

    {"tipo_ui": "select_multiple", "name": "p14_consumo_drogas_donde",
     "label": "14. Según su percepción u observación, indique dónde se presenta consumo de drogas en el distrito:",
     "required": True,
     "opciones": ["Área privada", "Área pública", "No se observa consumo"]},

    {"tipo_ui": "select_multiple", "name": "p15_def_infra_vial",
     "label": "15. Indique las principales deficiencias de infraestructura vial que afectan su distrito:",
     "required": True,
     "opciones": ["Calles en mal estado", "Falta de señalización de tránsito", "Carencia o inexistencia de aceras"]},

    {"tipo_ui": "select_multiple", "name": "p16_bunkeres",
     "label": "16. Según su percepción u observación, indique en qué tipo de espacios se identifica la existencia de puntos de venta de drogas (búnkeres) en el distrito:",
     "required": True,
     "opciones": ["Casa de habitación (Espacio cerrado)", "Edificación abandonada", "Lote baldío", "Otro"]},

    {"tipo_ui": "select_multiple", "name": "p17_transporte_afectacion",
     "label": "17. En relación con el transporte en su distrito, indique cuáles situaciones representan una afectación:",
     "required": True,
     "opciones": ["Informal (taxis piratas)", "Plataformas (digitales)"]},

    {"tipo_ui": "select_multiple", "name": "p18_presencia_policial",
     "label": "18. En relación con la presencia policial en su distrito, indique cuál de las siguientes situaciones identifica:",
     "required": True,
     "opciones": [
         "Falta de presencia policial",
         "Presencia policial insuficiente",
         "Presencia policial solo en ciertos horarios",
         "No observa presencia policial"
     ]},
]

# ------------------------------------------------------------------------------------------
# Sidebar: Metadatos
# ------------------------------------------------------------------------------------------
with st.sidebar:
    st.header("Configuración")
    form_title = st.text_input("Título del formulario", value=(f"Encuesta comunidad – {delegacion.strip()}" if delegacion.strip() else "Encuesta comunidad"))
    idioma = st.selectbox("Idioma por defecto", options=["es", "en"], index=0)
    version_auto = datetime.now().strftime("%Y%m%d%H%M")
    version = st.text_input("Versión (settings.version)", value=version_auto)

# ------------------------------------------------------------------------------------------
# Construcción XLSForm con glosario por sección (como PÁGINA extra, integrada al survey)
# ------------------------------------------------------------------------------------------
def construir_choices_para_pregunta(q: Dict) -> Tuple[List[Dict], str]:
    """
    Devuelve:
      - rows de choices (list_name, name, label)
      - list_name
    """
    _, _, list_name = map_tipo_to_xlsform(q["tipo_ui"], q["name"])
    if q.get("list_name_override"):
        list_name = q["list_name_override"]

    if not list_name:
        return [], ""

    # Cantón/Distrito NO generan aquí sus opciones (vienen del catálogo)
    if q["name"] in {"canton", "distrito"}:
        return [], list_name

    rows = []
    usados = set()
    for opt_label in (q.get("opciones") or []):
        base = slugify_name(opt_label)
        opt_name = asegurar_nombre_unico(base, usados)
        usados.add(opt_name)
        rows.append({"list_name": list_name, "name": opt_name, "label": str(opt_label)})
    return rows, list_name

def agregar_pagina(survey_rows: List[Dict], group_name: str, group_label: str, preguntas: List[Dict]):
    survey_rows.append({"type": "begin_group", "name": group_name, "label": group_label, "appearance": "field-list"})
    for q in preguntas:
        x_type, default_app, list_name = map_tipo_to_xlsform(q["tipo_ui"], q["name"])

        # override list_name si aplica (cantón/distrito)
        if q.get("list_name_override"):
            if "select_one" in x_type:
                x_type = f"select_one {q['list_name_override']}"
            elif "select_multiple" in x_type:
                x_type = f"select_multiple {q['list_name_override']}"

        row = {"type": x_type, "name": q["name"], "label": q["label"]}

        if q.get("required"):
            row["required"] = "yes"

        # appearance
        app = q.get("appearance") or default_app
        if app:
            row["appearance"] = app

        # choice_filter
        if q.get("choice_filter"):
            row["choice_filter"] = q["choice_filter"]

        # relevant
        if q.get("relevant"):
            row["relevant"] = q["relevant"]

        # constraints placeholders para cantón/distrito
        if q["name"] == "canton":
            row["constraint"] = ". != '__pick_canton__'"
            row["constraint_message"] = "Seleccione un cantón válido."
        if q["name"] == "distrito":
            row["constraint"] = ". != '__pick_distrito__'"
            row["constraint_message"] = "Seleccione un distrito válido."

        survey_rows.append(row)

    survey_rows.append({"type": "end_group", "name": f"{group_name}_end"})

def construir_xlsform(form_title_: str, idioma_: str, version_: str, logo_media: str):
    survey_rows: List[Dict] = []
    choices_rows: List[Dict] = []

    # 1) P1 Intro
    survey_rows += [
        {"type": "begin_group", "name": "p1_intro", "label": "Introducción", "appearance": "field-list"},
        {"type": "note", "name": "p1_logo", "label": form_title_, "media::image": logo_media},
        {"type": "note", "name": "p1_texto", "label": INTRO_P1},
        {"type": "end_group", "name": "p1_intro_end"},
    ]

    # 2) P2 Consentimiento
    p2 = [
        {"tipo_ui": "note", "name": "p2_consent_text", "label": CONSENTIMIENTO_P2, "required": False},
        {"tipo_ui": "select_one", "name": "p2_acepta", "label": "¿Acepta participar en esta encuesta?", "required": True, "opciones": YESNO},
    ]
    agregar_pagina(survey_rows, "p2_consentimiento", "Consentimiento informado", p2)

    # 3) P3 Demográficos
    agregar_pagina(survey_rows, "p3_demograficos", "I. Datos demográficos", P3_DEMOG)

    # 4) P4 Percepción
    # relevant de 7.1: solo si Q7 = Muy inseguro o Inseguro (slug interno)
    # slugify_name("Muy inseguro") -> muy_inseguro, slugify_name("Inseguro") -> inseguro
    p4_local = []
    for q in P4_PERCEPCION:
        qq = dict(q)
        if qq["name"] == "p71_por_que_inseguro":
            qq["relevant"] = "(${p7_perc_seguro_distrito}='muy_inseguro' or ${p7_perc_seguro_distrito}='inseguro')"
        p4_local.append(qq)

    agregar_pagina(survey_rows, "p4_percepcion", "II. Percepción ciudadana de seguridad en el distrito", p4_local)

    # 5) P5 Riesgos
    agregar_pagina(survey_rows, "p5_riesgos", "III. Riesgos, delitos, victimización y evaluación policial", P5_RIESGOS)

    # ---------------------------
    # CHOICES (de preguntas)
    # ---------------------------
    # P2 (acepta)
    for q in p2:
        rows, _ = construir_choices_para_pregunta(q)
        choices_rows.extend(rows)

    # P3
    for q in P3_DEMOG:
        rows, _ = construir_choices_para_pregunta(q)
        choices_rows.extend(rows)

    # P4
    for q in p4_local:
        rows, _ = construir_choices_para_pregunta(q)
        choices_rows.extend(rows)

    # P5
    for q in P5_RIESGOS:
        rows, _ = construir_choices_para_pregunta(q)
        choices_rows.extend(rows)

    # ---------------------------
    # Catálogo Cantón→Distrito (choices_ext_rows)
    # ---------------------------
    for r in st.session_state.choices_ext_rows:
        choices_rows.append(dict(r))

    # ---------------------------
    # Glosario por sección (INTEGRADO COMO PÁGINAS EXTRA)
    # - Detecta coincidencias por sección
    # - Si hay: agrega pregunta "ver glosario" dentro de la página
    #   y agrega una PÁGINA glosario inmediatamente después (top-level group)
    # ---------------------------
    glosario = cargar_glosario_desde_docx(GLOSARIO_DOCX_PATH)

    def inyectar_glosario_por_seccion(nombre_grupo_pagina: str, label_grupo_glos: str, preguntas_seccion: List[Dict]):
        # Texto de sección
        texto = compilar_texto_seccion(preguntas_seccion)
        terms = detectar_terminos_en_texto(glosario, texto)

        if not terms:
            return  # NO se agrega nada si no hay coincidencias

        # 1) Dentro de la página: agregar pregunta (select_one Sí/No)
        #    OJO: debemos insertarla ANTES del end_group del grupo correspondiente.
        ver_name = f"ver_glosario_{nombre_grupo_pagina}"
        list_ver = f"list_{ver_name}"

        # choices para ver glosario
        usados = set()
        for opt in YESNO:
            nm = asegurar_nombre_unico(slugify_name(opt), usados); usados.add(nm)
            choices_rows.append({"list_name": list_ver, "name": nm, "label": opt})

        # Insertar justo antes de "end_group" de esa página
        # Buscamos el end_group name = f"{grupo}_end"
        end_key = f"{nombre_grupo_pagina}_end"
        insert_idx = next((i for i, r in enumerate(survey_rows) if r.get("type") == "end_group" and r.get("name") == end_key), None)
        if insert_idx is None:
            return

        survey_rows.insert(insert_idx, {
            "type": f"select_one {list_ver}",
            "name": ver_name,
            "label": "¿Desea acceder al glosario de esta sección?",
            "required": "no"
        })

        # 2) Página extra: Glosario (top-level group para que se pueda ir atrás/adelante)
        gname = f"glosario_{nombre_grupo_pagina}"
        survey_rows.append({"type": "begin_group", "name": gname, "label": label_grupo_glos, "appearance": "field-list",
                            "relevant": f"${{{ver_name}}}='si'"})

        # Definiciones como notes (SIN recortar)
        # Nota: Las definiciones se ponen tal cual (pueden tener saltos de línea).
        for i, term in enumerate(terms, start=1):
            defin = glosario.get(term, "")
            survey_rows.append({
                "type": "note",
                "name": f"{gname}_t{i}",
                "label": f"{term}: {defin}"
            })

        survey_rows.append({"type": "end_group", "name": f"{gname}_end"})

    # Inyecta glosario en secciones donde haya coincidencias
    inyectar_glosario_por_seccion("p3_demograficos", "Glosario (I. Datos demográficos)", P3_DEMOG)
    inyectar_glosario_por_seccion("p4_percepcion", "Glosario (II. Percepción ciudadana)", p4_local)
    inyectar_glosario_por_seccion("p5_riesgos", "Glosario (III. Riesgos y situacionales)", P5_RIESGOS)

    # ---------------------------
    # DataFrames finales
    # ---------------------------
    df_survey = pd.DataFrame(survey_rows)

    # Choices: columnas base + extras (canton_key, any)
    if choices_rows:
        cols_all = set()
        for r in choices_rows:
            cols_all.update(r.keys())
        base = ["list_name", "name", "label"]
        for c in sorted(cols_all):
            if c not in base:
                base.append(c)
        df_choices = pd.DataFrame(choices_rows, columns=base)
    else:
        df_choices = pd.DataFrame(columns=["list_name", "name", "label"])

    df_settings = pd.DataFrame([{
        "form_title": form_title_,
        "version": version_,
        "default_language": idioma_,
        "style": "pages",
    }], columns=["form_title", "version", "default_language", "style"])

    return df_survey, df_choices, df_settings

def descargar_excel_xlsform(df_survey, df_choices, df_settings, nombre_archivo: str):
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df_survey.to_excel(writer, sheet_name="survey", index=False)
        df_choices.to_excel(writer, sheet_name="choices", index=False)
        df_settings.to_excel(writer, sheet_name="settings", index=False)
        wb = writer.book
        fmt_hdr = wb.add_format({"bold": True, "align": "left"})
        for sheet, df in (("survey", df_survey), ("choices", df_choices), ("settings", df_settings)):
            ws = writer.sheets[sheet]
            ws.freeze_panes(1, 0)
            ws.set_row(0, None, fmt_hdr)
            for col_idx, col_name in enumerate(list(df.columns)):
                ws.set_column(col_idx, col_idx, max(14, min(60, len(str(col_name)) + 10)))
    buffer.seek(0)
    st.download_button(
        label=f"Descargar XLSForm ({nombre_archivo})",
        data=buffer,
        file_name=nombre_archivo,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

# ------------------------------------------------------------------------------------------
# Generar XLSForm
# ------------------------------------------------------------------------------------------
st.markdown("---")
st.subheader("Generar XLSForm (Excel) para Survey123")

if st.button("Construir XLSForm", use_container_width=True):
    if not st.session_state.choices_ext_rows:
        st.warning("Aún no has cargado el catálogo Cantón→Distrito. Puedes construir igual, pero cantón/distrito quedarán sin opciones.")
    try:
        df_survey, df_choices, df_settings = construir_xlsform(
            form_title_=form_title.strip() if form_title.strip() else "Encuesta comunidad",
            idioma_=idioma,
            version_=version.strip() if version.strip() else datetime.now().strftime("%Y%m%d%H%M"),
            logo_media=logo_media_name.strip() if logo_media_name.strip() else "001.png"
        )

        st.success("XLSForm construido. Vista previa:")
        c1, c2, c3 = st.columns(3)
        c1.markdown("**Hoja: survey**")
        c1.dataframe(df_survey, use_container_width=True, hide_index=True)
        c2.markdown("**Hoja: choices**")
        c2.dataframe(df_choices, use_container_width=True, hide_index=True)
        c3.markdown("**Hoja: settings**")
        c3.dataframe(df_settings, use_container_width=True, hide_index=True)

        nombre_archivo = slugify_name(form_title) + "_xlsform.xlsx"
        descargar_excel_xlsform(df_survey, df_choices, df_settings, nombre_archivo)

        if st.session_state.get("_logo_bytes"):
            st.download_button(
                "Descargar logo para carpeta media",
                data=st.session_state["_logo_bytes"],
                file_name=logo_media_name,
                mime="image/png",
                use_container_width=True
            )

        st.info("En Survey123 Connect: crear encuesta desde archivo XLSForm, copiar el logo a `media/` y publicar.")

    except Exception as e:
        st.error(f"Ocurrió un error al generar el XLSForm: {e}")
