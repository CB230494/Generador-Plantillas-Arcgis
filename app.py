# -*- coding: utf-8 -*-
# ==========================================================================================
# App: Encuesta Comunidad → XLSForm para ArcGIS Survey123 (versión Comunidad)
# - PÁGINAS reales (style="pages")
# - P1: Introducción (texto fijo)
# - P2: Consentimiento informado (texto fijo)
# - P3: Datos demográficos (incluye Cantón→Distrito con catálogo por lotes)
# - P4: Percepción ciudadana de seguridad en el distrito (preguntas 7 a 11)
# - P5: Riesgos sociales y situacionales en el distrito (preguntas 12 a 18)
# - Catálogo Cantón → Distrito (por lotes) con múltiples distritos por cantón (multilínea)
# - Glosario POR PÁGINA: solo agrega definiciones si hay similitudes con el glosario DOCX
#   (si el usuario entra al glosario, NO podrá avanzar: solo “Atrás” para volver a la página)
# - Exporta XLSForm (survey/choices/settings)
# - NO genera Word ni PDF
# ==========================================================================================

import re
import os
import json
import unicodedata
from io import BytesIO
from datetime import datetime
from typing import List, Dict, Tuple

import streamlit as st
import pandas as pd

# ------------------------------------------------------------------------------------------
# Configuración de la app
# ------------------------------------------------------------------------------------------
st.set_page_config(page_title="Encuesta Comunidad → XLSForm (Survey123)", layout="wide")
st.title("🏘️ Encuesta Comunidad → XLSForm para ArcGIS Survey123")

st.markdown("""
Crea tu cuestionario y **exporta un XLSForm** listo para **ArcGIS Survey123**.

Incluye:
- Páginas reales con **style = pages**.
- **Catálogo Cantón → Distrito** (por lotes) y filtros en cascada (**choice_filter**).
- **Glosario por página**: solo se agregan definiciones si coinciden con el glosario (DOCX).
- Exporta **survey / choices / settings**.
""")

# ------------------------------------------------------------------------------------------
# Helpers generales
# ------------------------------------------------------------------------------------------
TIPOS = [
    "Texto (corto)",
    "Párrafo (texto largo)",
    "Número",
    "Selección única",
    "Selección múltiple",
    "Fecha",
    "Hora",
    "GPS (ubicación)"
]

def _rerun():
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()

def normalize_txt(s: str) -> str:
    if s is None:
        return ""
    s = str(s).strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return s

def slugify_name(texto: str) -> str:
    if not texto:
        return "campo"
    t = texto.lower()
    t = re.sub(r"[áàäâ]", "a", t); t = re.sub(r"[éèëê]", "e", t)
    t = re.sub(r"[íìïî]", "i", t); t = re.sub(r"[óòöô]", "o", t)
    t = re.sub(r"[úùüû]", "u", t); t = re.sub(r"ñ", "n", t)
    t = re.sub(r"[^a-z0-9]+", "_", t).strip("_")
    return t or "campo"

def asegurar_nombre_unico(base: str, usados: set) -> str:
    if base not in usados:
        return base
    i = 2
    while f"{base}_{i}" in usados:
        i += 1
    return f"{base}_{i}"

def map_tipo_to_xlsform(tipo_ui: str, name: str):
    if tipo_ui == "Texto (corto)":
        return ("text", None, None)
    if tipo_ui == "Párrafo (texto largo)":
        return ("text", "multiline", None)
    if tipo_ui == "Número":
        return ("integer", None, None)
    if tipo_ui == "Selección única":
        return (f"select_one list_{name}", None, f"list_{name}")
    if tipo_ui == "Selección múltiple":
        return (f"select_multiple list_{name}", None, f"list_{name}")
    if tipo_ui == "Fecha":
        return ("date", None, None)
    if tipo_ui == "Hora":
        return ("time", None, None)
    if tipo_ui == "GPS (ubicación)":
        return ("geopoint", None, None)
    return ("text", None, None)

def xlsform_or_expr(conds: List[str] | None):
    if not conds:
        return None
    if len(conds) == 1:
        return conds[0]
    return "(" + " or ".join(conds) + ")"

def xlsform_not(expr: str | None):
    if not expr:
        return None
    return f"not({expr})"

def build_relevant_expr(rules_for_target: List[Dict]):
    """
    rules_for_target: [{"src":..., "op":"="|"selected"|"!=", "values":[...]}]
    Devuelve una expresión OR de reglas.
    """
    or_parts = []
    for r in rules_for_target:
        src = r["src"]
        op = r.get("op", "=")
        vals = r.get("values", [])
        if not vals:
            continue

        if op == "=":
            segs = [f"${{{src}}}='{v}'" for v in vals]
        elif op == "selected":
            segs = [f"selected(${{{src}}}, '{v}')" for v in vals]
        elif op == "!=":
            segs = [f"${{{src}}}!='{v}'" for v in vals]
        else:
            segs = [f"${{{src}}}='{v}'" for v in vals]

        or_parts.append(xlsform_or_expr(segs))

    return xlsform_or_expr(or_parts)

# ------------------------------------------------------------------------------------------
# Glosario: cargar DOCX y detectar similitudes por página
# ------------------------------------------------------------------------------------------
GLOSSARY_DOCX_PATH = "glosario proceso de encuestas ESS.docx"

def cargar_glosario_desde_docx(docx_path: str) -> Dict[str, str]:
    """
    Lee el DOCX y construye dict {termino: definicion} usando patrón "Término: definición".
    NO recorta ni resume: usa el texto tal cual esté en el DOCX.
    """
    if not os.path.exists(docx_path):
        return {}

    try:
        from docx import Document
        doc = Document(docx_path)
    except Exception:
        return {}

    gloss = {}
    for p in doc.paragraphs:
        txt = (p.text or "").strip()
        if not txt:
            continue
        if ":" not in txt:
            continue
        term, defi = txt.split(":", 1)
        term = term.strip()
        defi = defi.strip()
        if term and defi and term not in gloss:
            gloss[term] = defi
    return gloss

def detectar_terminos_glosario_en_texto(gloss: Dict[str, str], texto: str) -> List[Tuple[str, str]]:
    """
    Retorna lista [(termino, definicion)] SOLO si el término aparece en el texto (búsqueda normalizada).
    - Busca por el término completo y además por la parte antes de "(" si existe.
    - No inventa definiciones.
    """
    if not gloss:
        return []

    tnorm = normalize_txt(texto)
    hallados = []

    for term, defi in gloss.items():
        term_norm = normalize_txt(term)
        # Variante 1: término completo
        variantes = [term_norm]

        # Variante 2: antes de paréntesis (si aplica)
        if "(" in term:
            base = term.split("(", 1)[0].strip()
            if base:
                variantes.append(normalize_txt(base))

        # Buscar por coincidencia simple (contención)
        found = any(v and (v in tnorm) for v in variantes)

        # Protección: evitar falsos positivos muy cortos
        # (si la variante base es demasiado corta, exigir palabra completa)
        if not found:
            continue

        hallados.append((term, defi))

    # Orden alfabético por término
    hallados.sort(key=lambda x: normalize_txt(x[0]))
    return hallados

# Cache del glosario (en sesión)
if "glosario_dict" not in st.session_state:
    st.session_state.glosario_dict = cargar_glosario_desde_docx(GLOSSARY_DOCX_PATH)

# ------------------------------------------------------------------------------------------
# Catálogo Cantón → Distrito (por lotes)
# - Permite MULTI distritos por cantón (multilínea)
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

st.markdown("### 🗂️ Catálogo Cantón → Distrito (por lotes)")
with st.expander("Agrega un lote (un Cantón y varios Distritos)", expanded=True):
    col_c1, col_c2 = st.columns(2)
    canton_txt = col_c1.text_input("Cantón (una vez)", value="")
    distritos_txt = col_c2.text_area(
        "Distritos (uno por línea)",
        value="",
        height=120,
        help="Escribe VARIOS distritos, uno por línea, para el mismo cantón."
    )

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
            st.error("Debes indicar Cantón y al menos un Distrito (uno por línea).")
        else:
            slug_c = slugify_name(c)

            # columnas extra usadas por filtros/placeholder
            st.session_state.choices_extra_cols.update({"canton_key", "any"})

            # Placeholders (una sola vez por lista)
            _append_choice_unique({"list_name": "list_canton", "name": "__pick_canton__", "label": "— escoja un cantón —"})
            _append_choice_unique({"list_name": "list_distrito", "name": "__pick_distrito__", "label": "— escoja un cantón —", "any": "1"})

            # Cantón
            _append_choice_unique({"list_name": "list_canton", "name": slug_c, "label": c})

            # Distritos (muchos para el mismo cantón)
            usados_d = set()
            for d in distritos:
                # Evitar que dentro del mismo lote se repita el mismo slug
                slug_d_base = slugify_name(d)
                slug_d = asegurar_nombre_unico(slug_d_base, usados_d)
                usados_d.add(slug_d)

                # En choices la unicidad es global por (list_name, name)
                # Si ya existe ese slug_d, se respeta (no se duplica)
                _append_choice_unique({"list_name": "list_distrito", "name": slug_d, "label": d, "canton_key": slug_c})

            st.success(f"Lote agregado: {c} → {len(distritos)} distrito(s).")

# Vista previa de catálogo
if st.session_state.choices_ext_rows:
    st.dataframe(
        pd.DataFrame(st.session_state.choices_ext_rows),
        use_container_width=True,
        hide_index=True,
        height=240
    )

# ------------------------------------------------------------------------------------------
# Cabecera: Logo + Delegación
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
            st.warning("Sube un logo para incluirlo en el XLSForm.")
            st.session_state["_logo_bytes"] = None
            st.session_state["_logo_name"] = "logo.png"

with col_txt:
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    delegacion = st.text_input("Nombre del lugar / Delegación", value="San Carlos Oeste")
    logo_media_name = st.text_input(
        "Nombre de archivo para `media::image`",
        value=st.session_state.get("_logo_name", "001.png"),
        help="Debe coincidir con el archivo en `media/` de Survey123 Connect."
    )
    titulo_compuesto = (f"Encuesta comunidad – {delegacion.strip()}" if delegacion.strip() else "Encuesta comunidad")
    st.markdown(f"<h5 style='text-align:center;margin:4px 0'>📋 {titulo_compuesto}</h5>", unsafe_allow_html=True)

# ------------------------------------------------------------------------------------------
# Estado
# ------------------------------------------------------------------------------------------
if "preguntas" not in st.session_state:
    st.session_state.preguntas = []
if "reglas_visibilidad" not in st.session_state:
    st.session_state.reglas_visibilidad = []
if "reglas_finalizar" not in st.session_state:
    st.session_state.reglas_finalizar = []

# ------------------------------------------------------------------------------------------
# Textos fijos (P1 y P2)
# ------------------------------------------------------------------------------------------
INTRO_COMUNIDAD = (
    "Con el fin de hacer más segura nuestra comunidad, deseamos concentrarnos en los "
    "problemas de seguridad más importantes. Queremos trabajar en conjunto con el gobierno "
    "local, otras instituciones y la comunidad para reducir los delitos y riesgos que afectan a las "
    "personas.\n\n"
    "Es importante recordarle que la información que usted nos proporcione es confidencial y se "
    "utilizará únicamente para mejorar la seguridad en nuestra área."
)

CONSENTIMIENTO_INFORMADO = (
    "Usted está siendo invitado(a) a participar de forma libre y voluntaria en una encuesta sobre seguridad, "
    "convivencia y percepción ciudadana, dirigida a personas mayores de 18 años.\n\n"
    "El objetivo de esta encuesta es recopilar información de carácter preventivo y estadístico, con el fin "
    "de apoyar la planificación de acciones de prevención, mejora de la convivencia y fortalecimiento de "
    "la seguridad en comunidades y zonas comerciales.\n\n"
    "La participación es totalmente voluntaria. Usted puede negarse a responder cualquier pregunta, así "
    "como retirarse de la encuesta en cualquier momento, sin que ello genere consecuencia alguna.\n\n"
    "De conformidad con lo dispuesto en el artículo 5 de la Ley N.º 8968, Ley de Protección de la Persona "
    "frente al Tratamiento de sus Datos Personales, se le informa que:\n\n"
    "• Finalidad del tratamiento: La información recopilada será utilizada exclusivamente para fines "
    "estadísticos, analíticos y preventivos, y no para investigaciones penales, procesos judiciales, "
    "sanciones administrativas ni procedimientos disciplinarios.\n"
    "• Datos personales: La encuesta no requiere datos sensibles. Cualquier dato de contacto que usted "
    "brinde será voluntario.\n"
    "• Confidencialidad: La información será tratada de forma confidencial y se resguardará conforme a la "
    "normativa vigente.\n"
    "• Derechos: Usted puede solicitar información, rectificación o supresión de sus datos en los términos "
    "de la Ley N.º 8968.\n\n"
    "Al continuar, usted manifiesta haber leído y comprendido la información anterior."
)

# ------------------------------------------------------------------------------------------
# Precarga (seed) de preguntas: P3, P4, P5 (P1 y P2 se generan como páginas fijas)
# ------------------------------------------------------------------------------------------
if "seed_cargado" not in st.session_state:
    # Slugs útiles
    v_si = slugify_name("Sí")
    v_no = slugify_name("No")

    # Listas comunes (se definen como opciones “humanas”, el XLSForm hará slug interno)
    escala_seguridad_5 = ["Muy inseguro", "Inseguro", "Ni seguro ni inseguro", "Seguro", "Muy seguro"]
    escala_ordinal_1_5 = [
        "1 (Mucho Menos Seguro)",
        "2 (Menos Seguro)",
        "3 (Se mantiene igual)",
        "4 (Más Seguro)",
        "5 (Mucho Más Seguro)"
    ]
    escala_matriz_1_5_na = [
        "Muy Inseguro (1)",
        "Inseguro (2)",
        "Ni seguro ni inseguro (3)",
        "Seguro (4)",
        "Muy Seguro (5)",
        "No Aplica"
    ]

    # -----------------------
    # P3: Datos demográficos
    # -----------------------
    seed = [
        # Cantón / Distrito (catálogo)
        {"tipo_ui": "Selección única", "label": "1- Cantón:", "name": "canton", "required": True,
         "opciones": [], "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección única", "label": "2- Distrito:", "name": "distrito", "required": True,
         "opciones": [], "appearance": None,
         "choice_filter": "canton_key=${canton} or any='1'",
         "relevant": None},

        # Edad por rangos
        {"tipo_ui": "Selección única", "label": "3- Edad (en años cumplidos): marque con una X la categoría que incluya su edad.",
         "name": "edad_rango", "required": True,
         "opciones": ["18 a 29 años", "30 a 44 años", "45 a 59 años", "60 años o más"],
         "appearance": None, "choice_filter": None, "relevant": None},

        # Identidad
        {"tipo_ui": "Selección única", "label": "4- ¿Con cuál de estas opciones se identifica?",
         "name": "identidad_genero", "required": True,
         "opciones": ["Femenino", "Masculino", "Persona No Binaria", "Prefiero no decir"],
         "appearance": None, "choice_filter": None, "relevant": None},

        # Escolaridad
        {"tipo_ui": "Selección única", "label": "5- Escolaridad:", "name": "escolaridad", "required": True,
         "opciones": [
             "Ninguna", "Primaria", "Primaria incompleta", "Primaria completa",
             "Secundaria incompleta", "Secundaria completa", "Técnico",
             "Universitaria incompleta", "Universitaria completa"
         ],
         "appearance": None, "choice_filter": None, "relevant": None},

        # Relación con la zona (selección única)
        {"tipo_ui": "Selección única", "label": "6- ¿Cuál es su relación con la zona?",
         "name": "relacion_zona", "required": True,
         "opciones": ["Vivo en la zona", "Trabajo en la zona", "Visito la zona", "Estudio en la zona"],
         "appearance": None, "choice_filter": None, "relevant": None},

        # ------------------------------------------
        # P4: Percepción ciudadana (Preg. 7 a 11)
        # ------------------------------------------
        {"tipo_ui": "Selección única",
         "label": "7- ¿Qué tan seguro percibe usted el distrito donde reside o transita?",
         "name": "p7_seguridad_distrito", "required": True,
         "opciones": escala_seguridad_5,
         "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección múltiple",
         "label": "7.1- Indique por qué considera el distrito inseguro (Marque todas las situaciones que usted percibe que ocurren con mayor frecuencia en su comunidad):",
         "name": "p7_1_motivos_inseguridad", "required": True,
         "opciones": [
             "Venta o distribución de drogas",
             "Consumo de drogas en espacios públicos",
             "Consumo de alcohol en el espacios públicos",
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
         "appearance": None, "choice_filter": None,
         "relevant": xlsform_or_expr([
             f"${{p7_seguridad_distrito}}='{slugify_name('Muy inseguro')}'",
             f"${{p7_seguridad_distrito}}='{slugify_name('Inseguro')}'",
         ])},

        {"tipo_ui": "Párrafo (texto largo)",
         "label": "7.1.a- Si marcó “Otro problema que considere importante”, detállelo:",
         "name": "p7_1_otro_detalle", "required": False,
         "opciones": [],
         "appearance": None, "choice_filter": None,
         "relevant": f"selected(${{p7_1_motivos_inseguridad}}, '{slugify_name('Otro problema que considere importante')}')"},

        {"tipo_ui": "Selección única",
         "label": "8- ¿Cómo se percibe la seguridad en este distrito este año en comparación con el año anterior?",
         "name": "p8_comparacion_anual", "required": True,
         "opciones": escala_ordinal_1_5,
         "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Párrafo (texto largo)",
         "label": "8.1- Indique por qué (Espacio abierto para detallar):",
         "name": "p8_1_porque", "required": True,
         "opciones": [],
         "appearance": None, "choice_filter": None,
         "relevant": xlsform_or_expr([f"${{p8_comparacion_anual}}='{slugify_name(x)}'" for x in escala_ordinal_1_5])},

        # P9: matriz (una pregunta por fila)
        {"tipo_ui": "Selección única",
         "label": "9- Discotecas, bares, sitios de entretenimiento",
         "name": "p9_zona_discotecas", "required": True,
         "opciones": escala_matriz_1_5_na,
         "appearance": "minimal", "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección única",
         "label": "9- Espacios recreativos (parques, play, plaza de deportes)",
         "name": "p9_zona_recreativos", "required": True,
         "opciones": escala_matriz_1_5_na,
         "appearance": "minimal", "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección única",
         "label": "9- Lugar de residencia (casa de habitación)",
         "name": "p9_zona_residencia", "required": True,
         "opciones": escala_matriz_1_5_na,
         "appearance": "minimal", "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección única",
         "label": "9- Paradas y/o estaciones de buses, taxis, trenes",
         "name": "p9_zona_paradas", "required": True,
         "opciones": escala_matriz_1_5_na,
         "appearance": "minimal", "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección única",
         "label": "9- Puentes peatonales",
         "name": "p9_zona_puentes", "required": True,
         "opciones": escala_matriz_1_5_na,
         "appearance": "minimal", "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección única",
         "label": "9- Transporte público",
         "name": "p9_zona_transporte_publico", "required": True,
         "opciones": escala_matriz_1_5_na,
         "appearance": "minimal", "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección única",
         "label": "9- Zona bancaria",
         "name": "p9_zona_bancaria", "required": True,
         "opciones": escala_matriz_1_5_na,
         "appearance": "minimal", "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección única",
         "label": "9- Zona de comercio",
         "name": "p9_zona_comercio", "required": True,
         "opciones": escala_matriz_1_5_na,
         "appearance": "minimal", "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección única",
         "label": "9- Zonas residenciales (calles y barrios, distinto a su casa)",
         "name": "p9_zona_residenciales", "required": True,
         "opciones": escala_matriz_1_5_na,
         "appearance": "minimal", "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección única",
         "label": "9- Zonas francas",
         "name": "p9_zona_francas", "required": True,
         "opciones": escala_matriz_1_5_na,
         "appearance": "minimal", "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección única",
         "label": "9- Lugares de interés turístico",
         "name": "p9_zona_turistico", "required": True,
         "opciones": escala_matriz_1_5_na,
         "appearance": "minimal", "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección única",
         "label": "9- Centros educativos",
         "name": "p9_zona_educativos", "required": True,
         "opciones": escala_matriz_1_5_na,
         "appearance": "minimal", "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección única",
         "label": "9- Zonas con deficiencia de iluminación",
         "name": "p9_zona_iluminacion", "required": True,
         "opciones": escala_matriz_1_5_na,
         "appearance": "minimal", "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección única",
         "label": "10- Según su percepción ¿cuál de los siguientes tipos de espacios del distrito considera más inseguro?",
         "name": "p10_tipo_espacio_inseguro", "required": True,
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
         ],
         "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Texto (corto)",
         "label": "10.a- Si seleccionó “Otros”, indique cuál:",
         "name": "p10_otros_detalle", "required": False,
         "opciones": [],
         "appearance": None, "choice_filter": None,
         "relevant": f"${{p10_tipo_espacio_inseguro}}='{slugify_name('Otros')}'"},

        {"tipo_ui": "Párrafo (texto largo)",
         "label": "11- Según su percepción, describa brevemente por qué considera inseguro el tipo de espacio seleccionado en la pregunta anterior. (Espacio abierto para detallar):",
         "name": "p11_porque_espacio", "required": True,
         "opciones": [],
         "appearance": None, "choice_filter": None, "relevant": None},

        # ------------------------------------------
        # P5: Riesgos sociales y situacionales (12-18)
        # ------------------------------------------
        {"tipo_ui": "Selección múltiple",
         "label": "12- Según su percepción u observación, seleccione las problemáticas que afectan su distrito:",
         "name": "p12_problematicas", "required": True,
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
         ],
         "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Párrafo (texto largo)",
         "label": "12.a- Si marcó “Otro problema que considere importante”, detállelo:",
         "name": "p12_otro_detalle", "required": False,
         "opciones": [],
         "appearance": None, "choice_filter": None,
         "relevant": f"selected(${{p12_problematicas}}, '{slugify_name('Otro problema que considere importante')}')"},

        {"tipo_ui": "Selección múltiple",
         "label": "13- En relación con la inversión social en su distrito, indique cuáles de las siguientes carencias identifica:",
         "name": "p13_inversion_social", "required": True,
         "opciones": [
             "Falta de oferta educativa",
             "Falta de oferta deportiva",
             "Falta de oferta recreativa",
             "Falta de actividades culturales"
         ],
         "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección múltiple",
         "label": "14- Según su percepción u observación, indique dónde se presenta consumo de drogas en el distrito:",
         "name": "p14_consumo_drogas_donde", "required": True,
         "opciones": ["Área privada", "Área pública", "No se observa consumo"],
         "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección múltiple",
         "label": "15- Indique las principales deficiencias de infraestructura vial que afectan su distrito:",
         "name": "p15_infra_vial", "required": True,
         "opciones": ["Calles en mal estado", "Falta de señalización de tránsito", "Carencia o inexistencia de aceras"],
         "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección múltiple",
         "label": "16- Según su percepción u observación, indique en qué tipo de espacios se identifica la existencia de puntos de venta de drogas (búnkeres) en el distrito:",
         "name": "p16_bunkeres_espacio", "required": True,
         "opciones": ["Casa de habitación (Espacio cerrado)", "Edificación abandonada", "Lote baldío", "Otro"],
         "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Texto (corto)",
         "label": "16.a- Si seleccionó “Otro”, indique cuál:",
         "name": "p16_otro_detalle", "required": False,
         "opciones": [],
         "appearance": None, "choice_filter": None,
         "relevant": f"selected(${{p16_bunkeres_espacio}}, '{slugify_name('Otro')}')"},

        {"tipo_ui": "Selección múltiple",
         "label": "17- En relación con el transporte en su distrito, indique cuáles situaciones representan una afectación:",
         "name": "p17_transporte", "required": True,
         "opciones": ["Informal (taxis piratas)", "Plataformas (digitales)"],
         "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección múltiple",
         "label": "18- En relación con la presencia policial en su distrito, indique cuál de las siguientes situaciones identifica:",
         "name": "p18_presencia_policial", "required": True,
         "opciones": [
             "Falta de presencia policial",
             "Presencia policial insuficiente",
             "Presencia policial solo en ciertos horarios",
             "No observa presencia policial"
         ],
         "appearance": None, "choice_filter": None, "relevant": None},
    ]

    st.session_state.preguntas = seed
    st.session_state.seed_cargado = True

# ------------------------------------------------------------------------------------------
# Sidebar: Metadatos + Exportar/Importar proyecto
# ------------------------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Configuración")
    form_title = st.text_input(
        "Título del formulario",
        value=(f"Encuesta comunidad – {delegacion.strip()}" if delegacion.strip() else "Encuesta comunidad")
    )
    idioma = st.selectbox("Idioma por defecto (default_language)", options=["es", "en"], index=0)
    version_auto = datetime.now().strftime("%Y%m%d%H%M")
    version = st.text_input("Versión (settings.version)", value=version_auto)

    st.markdown("---")
    st.caption("📘 Glosario (DOCX)")
    st.write(f"Ruta esperada: **{GLOSSARY_DOCX_PATH}**")
    if st.session_state.glosario_dict:
        st.success(f"Glosario cargado: {len(st.session_state.glosario_dict)} término(s).")
    else:
        st.warning("No se pudo cargar el glosario. Coloca el DOCX con ese nombre en la carpeta del proyecto.")

    st.markdown("---")
    st.caption("💾 Exporta/Importa tu proyecto (JSON)")
    col_exp, col_imp = st.columns(2)

    if col_exp.button("Exportar proyecto (JSON)", use_container_width=True):
        proj = {
            "form_title": form_title, "idioma": idioma, "version": version,
            "preguntas": st.session_state.preguntas,
            "reglas_visibilidad": st.session_state.reglas_visibilidad,
            "reglas_finalizar": st.session_state.reglas_finalizar,
            "choices_ext_rows": st.session_state.choices_ext_rows
        }
        jbuf = BytesIO(json.dumps(proj, ensure_ascii=False, indent=2).encode("utf-8"))
        st.download_button(
            "Descargar JSON",
            data=jbuf,
            file_name="proyecto_encuesta_comunidad.json",
            mime="application/json",
            use_container_width=True
        )

    up = col_imp.file_uploader("Importar JSON", type=["json"], label_visibility="collapsed")
    if up is not None:
        try:
            raw = up.read().decode("utf-8")
            data = json.loads(raw)
            st.session_state.preguntas = list(data.get("preguntas", []))
            st.session_state.reglas_visibilidad = list(data.get("reglas_visibilidad", []))
            st.session_state.reglas_finalizar = list(data.get("reglas_finalizar", []))
            st.session_state.choices_ext_rows = list(data.get("choices_ext_rows", []))
            _rerun()
        except Exception as e:
            st.error(f"No se pudo importar el JSON: {e}")

# ------------------------------------------------------------------------------------------
# Constructor: Agregar nuevas preguntas (opcional)
# ------------------------------------------------------------------------------------------
st.subheader("📝 Diseña tus preguntas (opcional)")

with st.form("form_add_q", clear_on_submit=False):
    tipo_ui = st.selectbox("Tipo de pregunta", options=TIPOS)
    label = st.text_input("Etiqueta (texto exacto)")
    sugerido = slugify_name(label) if label else ""
    col_n1, col_n2, col_n3 = st.columns([2, 1, 1])
    name = col_n1.text_input("Nombre interno (XLSForm 'name')", value=sugerido)
    required = col_n2.checkbox("Requerida", value=False)
    appearance = col_n3.text_input("Appearance (opcional)", value="")
    opciones = []
    if tipo_ui in ("Selección única", "Selección múltiple"):
        st.markdown("**Opciones (una por línea)**")
        txt_opts = st.text_area("Opciones", height=120)
        if txt_opts.strip():
            opciones = [o.strip() for o in txt_opts.splitlines() if o.strip()]
    add = st.form_submit_button("➕ Agregar pregunta")

if add:
    if not label.strip():
        st.warning("Agrega una etiqueta.")
    else:
        base = slugify_name(name or label)
        usados = {q["name"] for q in st.session_state.preguntas}
        unico = asegurar_nombre_unico(base, usados)
        st.session_state.preguntas.append({
            "tipo_ui": tipo_ui,
            "label": label.strip(),
            "name": unico,
            "required": required,
            "opciones": opciones,
            "appearance": (appearance.strip() or None),
            "choice_filter": None,
            "relevant": None
        })
        st.success(f"Pregunta agregada: **{label}** (name: `{unico}`)")

# ------------------------------------------------------------------------------------------
# Lista / Ordenado / Edición (completa)
# ------------------------------------------------------------------------------------------
st.subheader("📚 Preguntas (ordénalas y edítalas)")
if not st.session_state.preguntas:
    st.info("Aún no hay preguntas.")
else:
    for idx, q in enumerate(st.session_state.preguntas):
        with st.container(border=True):
            c1, c2, c3, c4, c5 = st.columns([4, 2, 2, 2, 2])
            c1.markdown(f"**{idx+1}. {q['label']}**")
            meta = f"type: {q['tipo_ui']}  •  name: `{q['name']}`  •  requerida: {'sí' if q['required'] else 'no'}"
            if q.get("appearance"):
                meta += f"  •  appearance: `{q['appearance']}`"
            if q.get("choice_filter"):
                meta += f"  •  choice_filter: `{q['choice_filter']}`"
            if q.get("relevant"):
                meta += f"  •  relevant: `{q['relevant']}`"
            c1.caption(meta)

            if q["tipo_ui"] in ("Selección única", "Selección múltiple"):
                c1.caption("Opciones: " + ", ".join(q.get("opciones") or []))

            up_btn = c2.button("⬆️ Subir", key=f"up_{idx}", use_container_width=True, disabled=(idx == 0))
            dn_btn = c3.button("⬇️ Bajar", key=f"down_{idx}", use_container_width=True,
                               disabled=(idx == len(st.session_state.preguntas) - 1))
            ed_btn = c4.button("✏️ Editar", key=f"edit_{idx}", use_container_width=True)
            del_btn = c5.button("🗑️ Eliminar", key=f"del_{idx}", use_container_width=True)

            if up_btn:
                st.session_state.preguntas[idx - 1], st.session_state.preguntas[idx] = (
                    st.session_state.preguntas[idx],
                    st.session_state.preguntas[idx - 1],
                )
                _rerun()
            if dn_btn:
                st.session_state.preguntas[idx + 1], st.session_state.preguntas[idx] = (
                    st.session_state.preguntas[idx],
                    st.session_state.preguntas[idx + 1],
                )
                _rerun()

            if ed_btn:
                st.markdown("**Editar esta pregunta**")
                ne_label = st.text_input("Etiqueta", value=q["label"], key=f"e_label_{idx}")
                ne_name = st.text_input("Nombre interno (name)", value=q["name"], key=f"e_name_{idx}")
                ne_required = st.checkbox("Requerida", value=q["required"], key=f"e_req_{idx}")
                ne_appearance = st.text_input("Appearance", value=q.get("appearance") or "", key=f"e_app_{idx}")
                ne_choice_filter = st.text_input("choice_filter (opcional)", value=q.get("choice_filter") or "", key=f"e_cf_{idx}")
                ne_relevant = st.text_input("relevant (opcional)", value=q.get("relevant") or "", key=f"e_rel_{idx}")

                ne_opciones = q.get("opciones") or []
                if q["tipo_ui"] in ("Selección única", "Selección múltiple"):
                    ne_opts_txt = st.text_area("Opciones (una por línea)", value="\n".join(ne_opciones), key=f"e_opts_{idx}")
                    ne_opciones = [o.strip() for o in ne_opts_txt.splitlines() if o.strip()]

                col_ok, col_cancel = st.columns(2)
                if col_ok.button("💾 Guardar cambios", key=f"e_save_{idx}", use_container_width=True):
                    new_base = slugify_name(ne_name or ne_label)
                    usados = {qq["name"] for j, qq in enumerate(st.session_state.preguntas) if j != idx}
                    ne_name_final = new_base if new_base not in usados else asegurar_nombre_unico(new_base, usados)

                    st.session_state.preguntas[idx]["label"] = ne_label.strip() or q["label"]
                    st.session_state.preguntas[idx]["name"] = ne_name_final
                    st.session_state.preguntas[idx]["required"] = ne_required
                    st.session_state.preguntas[idx]["appearance"] = ne_appearance.strip() or None
                    st.session_state.preguntas[idx]["choice_filter"] = ne_choice_filter.strip() or None
                    st.session_state.preguntas[idx]["relevant"] = ne_relevant.strip() or None
                    if q["tipo_ui"] in ("Selección única", "Selección múltiple"):
                        st.session_state.preguntas[idx]["opciones"] = ne_opciones

                    st.success("Cambios guardados.")
                    _rerun()

                if col_cancel.button("Cancelar", key=f"e_cancel_{idx}", use_container_width=True):
                    _rerun()

            if del_btn:
                del st.session_state.preguntas[idx]
                st.warning("Pregunta eliminada.")
                _rerun()

# ------------------------------------------------------------------------------------------
# Condicionales (editor adicional)
# ------------------------------------------------------------------------------------------
st.subheader("🔀 Condicionales (editor adicional)")
if not st.session_state.preguntas:
    st.info("Agrega preguntas para definir condicionales.")
else:
    with st.expander("👁️ Mostrar pregunta si se cumple condición", expanded=False):
        names = [q["name"] for q in st.session_state.preguntas]
        labels_by_name = {q["name"]: q["label"] for q in st.session_state.preguntas}

        target = st.selectbox("Pregunta a mostrar (target)", options=names,
                              format_func=lambda n: f"{n} — {labels_by_name[n]}")
        src = st.selectbox("Depende de (source)", options=names,
                           format_func=lambda n: f"{n} — {labels_by_name[n]}")
        op = st.selectbox("Operador", options=["=", "selected"])
        src_q = next((q for q in st.session_state.preguntas if q["name"] == src), None)

        vals = []
        if src_q and src_q["opciones"]:
            vals = st.multiselect("Valores (usa texto, internamente se usará slug)", options=src_q["opciones"])
            vals = [slugify_name(v) for v in vals]
        else:
            manual = st.text_input("Valor (si la pregunta no tiene opciones)")
            vals = [slugify_name(manual)] if manual.strip() else []

        if st.button("➕ Agregar regla de visibilidad"):
            if target == src:
                st.error("Target y Source no pueden ser la misma pregunta.")
            elif not vals:
                st.error("Indica al menos un valor.")
            else:
                st.session_state.reglas_visibilidad.append({"target": target, "src": src, "op": op, "values": vals})
                st.success("Regla agregada.")
                _rerun()

        if st.session_state.reglas_visibilidad:
            st.markdown("**Reglas de visibilidad actuales:**")
            for i, r in enumerate(st.session_state.reglas_visibilidad):
                st.write(f"- Mostrar **{r['target']}** si **{r['src']}** {r['op']} {r['values']}")
                if st.button(f"Eliminar regla #{i+1}", key=f"del_vis_{i}"):
                    del st.session_state.reglas_visibilidad[i]
                    _rerun()

    with st.expander("⏹️ Finalizar temprano si se cumple condición", expanded=False):
        names = [q["name"] for q in st.session_state.preguntas]
        labels_by_name = {q["name"]: q["label"] for q in st.session_state.preguntas}
        src2 = st.selectbox("Condición basada en", options=names,
                            format_func=lambda n: f"{n} — {labels_by_name[n]}",
                            key="final_src")
        op2 = st.selectbox("Operador", options=["=", "selected", "!="], key="final_op")
        src2_q = next((q for q in st.session_state.preguntas if q["name"] == src2), None)
        vals2 = []
        if src2_q and src2_q["opciones"]:
            vals2 = st.multiselect("Valores (slug interno)", options=src2_q["opciones"], key="final_vals")
            vals2 = [slugify_name(v) for v in vals2]
        else:
            manual2 = st.text_input("Valor (si no hay opciones)", key="final_manual")
            vals2 = [slugify_name(manual2)] if manual2.strip() else []

        if st.button("➕ Agregar regla de finalización"):
            if not vals2:
                st.error("Indica al menos un valor.")
            else:
                idx_src = next((i for i, q in enumerate(st.session_state.preguntas) if q["name"] == src2), 0)
                st.session_state.reglas_finalizar.append({"src": src2, "op": op2, "values": vals2, "index_src": idx_src})
                st.success("Regla agregada.")
                _rerun()

        if st.session_state.reglas_finalizar:
            st.markdown("**Reglas de finalización actuales:**")
            for i, r in enumerate(st.session_state.reglas_finalizar):
                st.write(f"- Si **{r['src']}** {r['op']} {r['values']} ⇒ ocultar lo que sigue (efecto fin)")
                if st.button(f"Eliminar regla fin #{i+1}", key=f"del_fin_{i}"):
                    del st.session_state.reglas_finalizar[i]
                    _rerun()

# ------------------------------------------------------------------------------------------
# Construcción XLSForm
# - P1 y P2 fijas
# - P3, P4, P5 desde seed (y cualquier pregunta extra)
# - Glosario por página si hay similitudes
# - Si entra a glosario, NO puede avanzar (solo Atrás): siguiente página queda oculta
# ------------------------------------------------------------------------------------------
def _get_logo_media_name():
    return logo_media_name

def construir_xlsform(preguntas: List[Dict], form_title: str, idioma: str, version: str,
                      reglas_vis: List[Dict], reglas_fin: List[Dict],
                      glosario_dict: Dict[str, str]):
    survey_rows: List[Dict] = []
    choices_rows: List[Dict] = []

    # Reglas panel
    vis_by_target = {}
    for r in reglas_vis:
        vis_by_target.setdefault(r["target"], []).append(
            {"src": r["src"], "op": r.get("op", "="), "values": r.get("values", [])}
        )

    # Reglas de fin
    fin_conds = []
    for r in reglas_fin:
        cond = build_relevant_expr([{"src": r["src"], "op": r.get("op", "="), "values": r.get("values", [])}])
        if cond:
            fin_conds.append((r["index_src"], cond))

    def add_q(q: Dict, idx: int):
        x_type, default_app, list_name = map_tipo_to_xlsform(q["tipo_ui"], q["name"])

        rel_manual = q.get("relevant") or None
        rel_panel = build_relevant_expr(vis_by_target.get(q["name"], []))
        nots = [xlsform_not(cond) for idx_src, cond in fin_conds if idx_src < idx]
        rel_fin = "(" + " and ".join(nots) + ")" if nots else None
        parts = [p for p in [rel_manual, rel_panel, rel_fin] if p]
        rel_final = parts[0] if parts and len(parts) == 1 else ("(" + ") and (".join(parts) + ")" if parts else None)

        row = {"type": x_type, "name": q["name"], "label": q["label"]}

        if q.get("required"):
            row["required"] = "yes"

        app = q.get("appearance") or default_app
        if app:
            row["appearance"] = app

        if q.get("choice_filter"):
            row["choice_filter"] = q["choice_filter"]

        if rel_final:
            row["relevant"] = rel_final

        # Constraints para placeholders de catálogo
        if q["name"] == "canton":
            row["constraint"] = ". != '__pick_canton__'"
            row["constraint_message"] = "Seleccione un cantón válido."
        if q["name"] == "distrito":
            row["constraint"] = ". != '__pick_distrito__'"
            row["constraint_message"] = "Seleccione un distrito válido."

        survey_rows.append(row)

        # No generar opciones para canton/distrito: se usan del catálogo
        if list_name and q["name"] not in {"canton", "distrito"}:
            usados = set()
            for opt_label in (q.get("opciones") or []):
                base = slugify_name(opt_label)
                opt_name = asegurar_nombre_unico(base, usados)
                usados.add(opt_name)
                choices_rows.append({"list_name": list_name, "name": opt_name, "label": str(opt_label)})

    # ---------------- Página 1: Intro ----------------
    survey_rows += [
        {"type": "begin_group", "name": "p1_intro", "label": "Introducción", "appearance": "field-list"},
        {"type": "note", "name": "p1_logo", "label": form_title, "media::image": _get_logo_media_name()},
        {"type": "note", "name": "p1_texto", "label": INTRO_COMUNIDAD},
        {"type": "end_group", "name": "p1_end"},
    ]

    # Glosario P1 (si coincide)
    p1_text = INTRO_COMUNIDAD
    p1_terms = detectar_terminos_glosario_en_texto(glosario_dict, p1_text)
    # Pregunta “acceso” + página glosario solo si hay términos
    if p1_terms:
        survey_rows += [
            {"type": "select_one yesno", "name": "p1_acceso_glosario", "label": "¿Desea acceder al glosario de esta sección?"},
        ]
        survey_rows += [
            {"type": "begin_group", "name": "p1_glosario", "label": "Glosario (Introducción)", "appearance": "field-list",
             "relevant": "${p1_acceso_glosario}='si'"},
            {"type": "note", "name": "p1_glosario_aviso", "label": "Está en el glosario. Use únicamente el botón “Atrás” para regresar a la página anterior."},
        ]
        # Notas (término + definición) sin recortar
        for i, (term, defi) in enumerate(p1_terms, start=1):
            survey_rows.append({"type": "note", "name": f"p1_glos_{i}", "label": f"{term}: {defi}"})
        survey_rows.append({"type": "end_group", "name": "p1_glosario_end"})

    # ---------------- Página 2: Consentimiento ----------------
    # Si P1 tiene glosario y el usuario lo abrió, P2 NO se muestra (para evitar “Siguiente” desde glosario)
    p2_relevant = None
    if p1_terms:
        p2_relevant = "(${p1_acceso_glosario}!='si' or ${p1_acceso_glosario}='')"

    survey_rows += [
        {"type": "begin_group", "name": "p2_consentimiento", "label": "Consentimiento Informado",
         "appearance": "field-list", **({"relevant": p2_relevant} if p2_relevant else {})},
        {"type": "note", "name": "p2_texto", "label": CONSENTIMIENTO_INFORMADO},
        {"type": "select_one yesno", "name": "p2_acepta", "label": "¿Acepta participar en esta encuesta?", "required": "yes"},
        {"type": "end_group", "name": "p2_end"},
    ]

    # Glosario P2
    p2_text = CONSENTIMIENTO_INFORMADO + " " + "¿Acepta participar en esta encuesta?"
    p2_terms = detectar_terminos_glosario_en_texto(glosario_dict, p2_text)
    if p2_terms:
        survey_rows += [
            {"type": "select_one yesno", "name": "p2_acceso_glosario", "label": "¿Desea acceder al glosario de esta sección?",
             **({"relevant": p2_relevant} if p2_relevant else {})},
            {"type": "begin_group", "name": "p2_glosario", "label": "Glosario (Consentimiento)", "appearance": "field-list",
             "relevant": f"({p2_relevant}) and ${p2_acceso_glosario}='si'" if p2_relevant else "${p2_acceso_glosario}='si'"},
            {"type": "note", "name": "p2_glosario_aviso", "label": "Está en el glosario. Use únicamente el botón “Atrás” para regresar a la página anterior."},
        ]
        for i, (term, defi) in enumerate(p2_terms, start=1):
            survey_rows.append({"type": "note", "name": f"p2_glos_{i}", "label": f"{term}: {defi}"})
        survey_rows.append({"type": "end_group", "name": "p2_glosario_end"})

    # ---------------- P3 / P4 / P5: construir por sets ----------------
    # Sets por página (comunidad)
    P3 = {"canton", "distrito", "edad_rango", "identidad_genero", "escolaridad", "relacion_zona"}
    P4 = {
        "p7_seguridad_distrito", "p7_1_motivos_inseguridad", "p7_1_otro_detalle",
        "p8_comparacion_anual", "p8_1_porque",
        "p9_zona_discotecas", "p9_zona_recreativos", "p9_zona_residencia", "p9_zona_paradas", "p9_zona_puentes",
        "p9_zona_transporte_publico", "p9_zona_bancaria", "p9_zona_comercio", "p9_zona_residenciales",
        "p9_zona_francas", "p9_zona_turistico", "p9_zona_educativos", "p9_zona_iluminacion",
        "p10_tipo_espacio_inseguro", "p10_otros_detalle",
        "p11_porque_espacio"
    }
    P5 = {
        "p12_problematicas", "p12_otro_detalle",
        "p13_inversion_social",
        "p14_consumo_drogas_donde",
        "p15_infra_vial",
        "p16_bunkeres_espacio", "p16_otro_detalle",
        "p17_transporte",
        "p18_presencia_policial"
    }

    # Relevants por bloqueo de glosario
    # Si P2 tiene glosario y se abre, bloquear P3
    block_after_p2 = None
    if p2_terms:
        # P3 solo se muestra si NO está en glosario P2
        base_p3_rel = "${p2_acceso_glosario}!='si' or ${p2_acceso_glosario}=''"
        # además, si p2_relevant existe (cuando P1 glosario) se agrega
        if p2_relevant:
            block_after_p2 = f"({p2_relevant}) and ({base_p3_rel})"
        else:
            block_after_p2 = base_p3_rel
    else:
        block_after_p2 = p2_relevant  # podría ser None o la regla de P1

    def page_relevant(prev_block_expr: str | None):
        return prev_block_expr if prev_block_expr else None

    def add_page(group_name: str, page_label: str, names_set: set, rel_expr: str | None):
        begin_row = {"type": "begin_group", "name": group_name, "label": page_label, "appearance": "field-list"}
        if rel_expr:
            begin_row["relevant"] = rel_expr
        survey_rows.append(begin_row)

        for i, q in enumerate(preguntas):
            if q["name"] in names_set:
                add_q(q, i)

        survey_rows.append({"type": "end_group", "name": f"{group_name}_end"})

    # P3
    rel_p3 = page_relevant(block_after_p2)
    add_page("p3_datos_demograficos", "I. DATOS DEMOGRÁFICOS", P3, rel_p3)

    # Glosario P3 (solo si hay similitudes)
    p3_text_blob = ""
    for q in preguntas:
        if q["name"] in P3:
            p3_text_blob += " " + str(q.get("label", ""))
            for opt in (q.get("opciones") or []):
                p3_text_blob += " " + str(opt)
    p3_terms = detectar_terminos_glosario_en_texto(glosario_dict, p3_text_blob)
    if p3_terms:
        # Pregunta acceso (dentro del mismo “bloque” de relevancia)
        row_access = {"type": "select_one yesno", "name": "p3_acceso_glosario", "label": "¿Desea acceder al glosario de esta sección?"}
        if rel_p3:
            row_access["relevant"] = rel_p3
        survey_rows.append(row_access)

        # Página glosario
        rel_glos_p3 = f"({rel_p3}) and ${p3_acceso_glosario}='si'" if rel_p3 else "${p3_acceso_glosario}='si'"
        survey_rows.append({"type": "begin_group", "name": "p3_glosario", "label": "Glosario (Datos demográficos)",
                            "appearance": "field-list", "relevant": rel_glos_p3})
        survey_rows.append({"type": "note", "name": "p3_glosario_aviso",
                            "label": "Está en el glosario. Use únicamente el botón “Atrás” para regresar a la página anterior."})
        for i, (term, defi) in enumerate(p3_terms, start=1):
            survey_rows.append({"type": "note", "name": f"p3_glos_{i}", "label": f"{term}: {defi}"})
        survey_rows.append({"type": "end_group", "name": "p3_glosario_end"})

    # P4: debe bloquear si se abrió glosario P3
    rel_p4 = rel_p3
    if p3_terms:
        block_p3 = "${p3_acceso_glosario}!='si' or ${p3_acceso_glosario}=''"
        rel_p4 = f"({rel_p3}) and ({block_p3})" if rel_p3 else block_p3

    add_page("p4_percepcion_seguridad", "II. PERCEPCIÓN CIUDADANA DE SEGURIDAD EN EL DISTRITO", P4, rel_p4)

    # Glosario P4
    p4_text_blob = ""
    for q in preguntas:
        if q["name"] in P4:
            p4_text_blob += " " + str(q.get("label", ""))
            for opt in (q.get("opciones") or []):
                p4_text_blob += " " + str(opt)
    p4_terms = detectar_terminos_glosario_en_texto(glosario_dict, p4_text_blob)
    if p4_terms:
        row_access = {"type": "select_one yesno", "name": "p4_acceso_glosario", "label": "¿Desea acceder al glosario de esta sección?"}
        if rel_p4:
            row_access["relevant"] = rel_p4
        survey_rows.append(row_access)

        rel_glos_p4 = f"({rel_p4}) and ${p4_acceso_glosario}='si'" if rel_p4 else "${p4_acceso_glosario}='si'"
        survey_rows.append({"type": "begin_group", "name": "p4_glosario", "label": "Glosario (Percepción de seguridad)",
                            "appearance": "field-list", "relevant": rel_glos_p4})
        survey_rows.append({"type": "note", "name": "p4_glosario_aviso",
                            "label": "Está en el glosario. Use únicamente el botón “Atrás” para regresar a la página anterior."})
        for i, (term, defi) in enumerate(p4_terms, start=1):
            survey_rows.append({"type": "note", "name": f"p4_glos_{i}", "label": f"{term}: {defi}"})
        survey_rows.append({"type": "end_group", "name": "p4_glosario_end"})

    # P5: debe bloquear si se abrió glosario P4
    rel_p5 = rel_p4
    if p4_terms:
        block_p4 = "${p4_acceso_glosario}!='si' or ${p4_acceso_glosario}=''"
        rel_p5 = f"({rel_p4}) and ({block_p4})" if rel_p4 else block_p4

    add_page("p5_riesgos_delitos", "III. RIESGOS, DELITOS, VICTIMIZACIÓN Y EVALUACIÓN POLICIAL", P5, rel_p5)

    # Glosario P5
    p5_text_blob = ""
    for q in preguntas:
        if q["name"] in P5:
            p5_text_blob += " " + str(q.get("label", ""))
            for opt in (q.get("opciones") or []):
                p5_text_blob += " " + str(opt)
    p5_terms = detectar_terminos_glosario_en_texto(glosario_dict, p5_text_blob)
    if p5_terms:
        row_access = {"type": "select_one yesno", "name": "p5_acceso_glosario", "label": "¿Desea acceder al glosario de esta sección?"}
        if rel_p5:
            row_access["relevant"] = rel_p5
        survey_rows.append(row_access)

        rel_glos_p5 = f"({rel_p5}) and ${p5_acceso_glosario}='si'" if rel_p5 else "${p5_acceso_glosario}='si'"
        survey_rows.append({"type": "begin_group", "name": "p5_glosario", "label": "Glosario (Riesgos y situacionales)",
                            "appearance": "field-list", "relevant": rel_glos_p5})
        survey_rows.append({"type": "note", "name": "p5_glosario_aviso",
                            "label": "Está en el glosario. Use únicamente el botón “Atrás” para regresar a la página anterior."})
        for i, (term, defi) in enumerate(p5_terms, start=1):
            survey_rows.append({"type": "note", "name": f"p5_glos_{i}", "label": f"{term}: {defi}"})
        survey_rows.append({"type": "end_group", "name": "p5_glosario_end"})

    # ---------------- choices: catálogo manual ----------------
    for r in st.session_state.choices_ext_rows:
        choices_rows.append(dict(r))

    # ---------------- DataFrames ----------------
    survey_cols_all = set().union(*[r.keys() for r in survey_rows])
    survey_cols = [
        c for c in [
            "type", "name", "label", "required", "appearance",
            "choice_filter", "relevant", "constraint", "constraint_message",
            "media::image"
        ] if c in survey_cols_all
    ]
    for k in sorted(survey_cols_all):
        if k not in survey_cols:
            survey_cols.append(k)
    df_survey = pd.DataFrame(survey_rows, columns=survey_cols)

    choices_cols_all = set()
    for r in choices_rows:
        choices_cols_all.update(r.keys())
    base_choice_cols = ["list_name", "name", "label"]
    for extra in sorted(choices_cols_all):
        if extra not in base_choice_cols:
            base_choice_cols.append(extra)
    df_choices = pd.DataFrame(choices_rows, columns=base_choice_cols) if choices_rows else pd.DataFrame(columns=base_choice_cols)

    df_settings = pd.DataFrame([{
        "form_title": form_title,
        "version": version,
        "default_language": idioma,
        "style": "pages"
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
        label=f"📥 Descargar XLSForm ({nombre_archivo})",
        data=buffer,
        file_name=nombre_archivo,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

# ------------------------------------------------------------------------------------------
# Exportar / Vista previa XLSForm
# ------------------------------------------------------------------------------------------
st.markdown("---")
st.subheader("📦 Generar XLSForm (Excel) para Survey123")

st.caption("""
Incluye:
- **survey** con páginas (begin_group/end_group) + condicionales (relevant) + filtros (choice_filter)
- **choices** con catálogo Cantón/Distrito y placeholders
- **settings** con **style = pages**
""")

if st.button("🧮 Construir XLSForm", use_container_width=True, disabled=not st.session_state.preguntas):
    try:
        names = [q["name"] for q in st.session_state.preguntas]
        if len(names) != len(set(names)):
            st.error("Hay 'name' duplicados. Edita las preguntas para que cada 'name' sea único.")
        else:
            df_survey, df_choices, df_settings = construir_xlsform(
                st.session_state.preguntas,
                form_title=(f"Encuesta comunidad – {delegacion.strip()}" if delegacion.strip() else "Encuesta comunidad"),
                idioma=idioma,
                version=(version.strip() or datetime.now().strftime("%Y%m%d%H%M")),
                reglas_vis=st.session_state.reglas_visibilidad,
                reglas_fin=st.session_state.reglas_finalizar,
                glosario_dict=st.session_state.glosario_dict
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
                    "📥 Descargar logo para carpeta media",
                    data=st.session_state["_logo_bytes"],
                    file_name=logo_media_name,
                    mime="image/png",
                    use_container_width=True
                )

            st.info("En Survey123 Connect: crea encuesta desde archivo XLSForm, copia el logo a `media/` y publica.")
    except Exception as e:
        st.error(f"Ocurrió un error al generar el XLSForm: {e}")
