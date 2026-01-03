# -*- coding: utf-8 -*-
# ==========================================================================================
# App: Encuesta Comunidad → XLSForm para ArcGIS Survey123 (PÁGINAS) + Catálogo Cantón→Distrito
# + Consentimiento (igual a app anterior) + Glosario automático por página (desde DOCX)
#
# - Página 1: Introducción con logo + texto (exacto)
# - Página 2: Consentimiento informado + ¿Acepta participar? (Sí/No)
#            + Si "No" => end
# - Página 3+: Páginas de la encuesta (como venís trabajando)
# - Catálogo manual por lotes: Cantón (una vez) + varios Distritos (uno por línea)
# - Glosario automático:
#      * Lee /mnt/data/glosario proceso de encuestas ESS.docx (o ruta local si está en el mismo folder)
#      * Detecta coincidencias por página (términos del glosario presentes en labels/opciones)
#      * Si hay coincidencias: al final de la página agrega pregunta opcional
#        "¿Desea consultar el glosario de esta página?"
#        Si responde Sí => aparece "Glosario" con definiciones y un aviso de volver con ATRÁS
#      * Si NO hay coincidencias => NO agrega glosario en esa página
#
# - Exporta XLSForm (Excel) con hojas: survey / choices / settings
# ==========================================================================================

import re
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
Crea tu encuesta y **exporta un XLSForm** listo para **ArcGIS Survey123**.

Incluye:
- **Páginas reales** con navegación **Siguiente/Anterior** (`settings.style = pages`).
- **Portada/Introducción** con logo (`media::image`) y texto.
- **Consentimiento informado** + aceptación **Sí/No** y finaliza si **No**.
- **Catálogo Cantón → Distrito** (manual por lotes).
- **Glosario automático por página** (si hay coincidencias con el Word de glosario).
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

def xlsform_or_expr(conds):
    if not conds:
        return None
    if len(conds) == 1:
        return conds[0]
    return "(" + " or ".join(conds) + ")"

def xlsform_not(expr):
    if not expr:
        return None
    return f"not({expr})"

def build_relevant_expr(rules_for_target: List[Dict]):
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
# Glosario (DOCX) - lectura + matching por página
# ------------------------------------------------------------------------------------------
def _norm_txt(s: str) -> str:
    s = (s or "").lower()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return s

def _load_glosario_docx() -> Dict[str, str]:
    """
    Carga glosario desde DOCX.
    Soporta:
      - párrafos tipo "Término: Definición"
      - o "Término\tDefinición"
    """
    rutas_posibles = [
        "/mnt/data/glosario proceso de encuestas ESS.docx",
        "glosario proceso de encuestas ESS.docx",
    ]
    doc = None
    last_err = None
    for rp in rutas_posibles:
        try:
            from docx import Document
            doc = Document(rp)
            break
        except Exception as e:
            last_err = e
            doc = None

    if doc is None:
        st.warning(
            "No se pudo leer el DOCX del glosario automáticamente. "
            "Verifica que exista como archivo local o en /mnt/data."
        )
        return {}

    paras = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
    glos = {}
    for p in paras:
        s = p.replace("\t", ": ")
        if ":" in s:
            term, defin = s.split(":", 1)
            term = term.strip()
            defin = defin.strip()
            if term and defin and len(term) < 120:
                glos[term] = defin

    return glos

if "glosario_dict" not in st.session_state:
    st.session_state.glosario_dict = _load_glosario_docx()

def glosario_matches_for_text(glosario: Dict[str, str], texto: str) -> List[str]:
    """
    Retorna términos (keys del glosario) que aparecen en el texto, de forma robusta:
    - Normaliza acentos y minúsculas.
    - Match por "frontera" alfanumérica.
    """
    if not glosario:
        return []
    t = _norm_txt(texto)
    hits = []
    for term in glosario.keys():
        tt = _norm_txt(term)
        if not tt:
            continue
        # frontera alfanumérica aproximada
        if re.search(rf"(?<![a-z0-9]){re.escape(tt)}(?![a-z0-9])", t):
            hits.append(term)
    # sin duplicados y orden estable
    seen = set()
    out = []
    for h in hits:
        if h not in seen:
            out.append(h)
            seen.add(h)
    return out

# ------------------------------------------------------------------------------------------
# Catálogo manual por lotes: Cantón → Distritos (VARIOS por cantón, uno por línea)
# ------------------------------------------------------------------------------------------
if "choices_ext_rows" not in st.session_state:
    st.session_state.choices_ext_rows = []  # filas para hoja choices
if "choices_extra_cols" not in st.session_state:
    st.session_state.choices_extra_cols = set()

def _append_choice_unique(row: Dict):
    key = (row.get("list_name"), row.get("name"), row.get("label"), row.get("canton_key"))
    exists = any(
        (r.get("list_name"), r.get("name"), r.get("label"), r.get("canton_key")) == key
        for r in st.session_state.choices_ext_rows
    )
    if not exists:
        st.session_state.choices_ext_rows.append(row)

st.markdown("### 📚 Catálogo Cantón → Distritos (por lotes)")
with st.expander("Agrega un lote: Cantón (una vez) + varios Distritos (uno por línea)", expanded=True):
    col_c1, col_c2 = st.columns([1, 2])
    canton_txt = col_c1.text_input("Cantón (una vez)", value="")
    distritos_txt = col_c2.text_area(
        "Distritos del cantón (uno por línea)",
        value="",
        height=140,
        help="Pegá o escribí varios distritos, uno por línea, para el mismo cantón."
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
            st.error("Debes indicar el Cantón y al menos un Distrito (uno por línea).")
        else:
            slug_c = slugify_name(c)

            # columnas extra usadas por filtros/placeholder
            st.session_state.choices_extra_cols.update({"canton_key", "any"})

            # Placeholders (una sola vez por lista)
            _append_choice_unique({"list_name": "list_canton", "name": "__pick_canton__", "label": "— escoja un cantón —"})
            _append_choice_unique({"list_name": "list_distrito", "name": "__pick_distrito__", "label": "— escoja un cantón —", "any": "1"})

            # Cantón
            _append_choice_unique({"list_name": "list_canton", "name": slug_c, "label": c})

            # Distritos (VARIOS)
            usados_d = set()
            for d in distritos:
                slug_d = asegurar_nombre_unico(slugify_name(d), usados_d)
                usados_d.add(slug_d)
                _append_choice_unique({"list_name": "list_distrito", "name": slug_d, "label": d, "canton_key": slug_c})

            st.success(f"Lote agregado: {c} → {len(distritos)} distritos.")

# Vista previa de catálogo
if st.session_state.choices_ext_rows:
    st.dataframe(pd.DataFrame(st.session_state.choices_ext_rows).fillna(""),
                 use_container_width=True, hide_index=True, height=260)

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
# Textos EXACTOS para P1 + Consentimiento (igual a app anterior)
# ------------------------------------------------------------------------------------------
INTRO_COMUNIDAD = (
    "Con el fin de hacer más segura nuestra comunidad, deseamos concentrarnos en los \n"
    "problemas de seguridad más importantes. Queremos trabajar en conjunto con el gobierno \n"
    "local, otras instituciones y la comunidad para reducir los delitos y riesgos que afectan a las \n"
    "personas. \n"
    "Es importante recordarle que la información que usted nos proporcione es confidencial y se \n"
    "utilizará únicamente para mejorar la seguridad en nuestra área."
)

CONSENT_TITLE = "Consentimiento Informado para la Participación en la Encuesta"

CONSENT_PARRAFOS = [
    "Usted está siendo invitado(a) a participar de forma libre y voluntaria en una encuesta sobre seguridad, convivencia y percepción ciudadana, dirigida a personas mayores de 18 años.",
    "El objetivo de esta encuesta es recopilar información de carácter preventivo y estadístico, con el fin de apoyar la planificación de acciones de prevención, mejora de la convivencia y fortalecimiento de la seguridad en comunidades y zonas comerciales.",
    "La participación es totalmente voluntaria. Usted puede negarse a responder cualquier pregunta, así como retirarse de la encuesta en cualquier momento, sin que ello genere consecuencia alguna.",
    "De conformidad con lo dispuesto en el artículo 5 de la Ley N.º 8968, Ley de Protección de la Persona frente al Tratamiento de sus Datos Personales, se le informa que:"
]

CONSENT_BULLETS = [
    "Finalidad del tratamiento: La información recopilada será utilizada exclusivamente para fines estadísticos, analíticos y preventivos, y no para investigaciones penales, procesos judiciales, sanciones administrativas ni procedimientos disciplinarios.",
    "Datos personales: Algunos apartados permiten, de forma voluntaria, el suministro de datos personales o información de contacto.",
    "Tratamiento de los datos: Los datos serán almacenados, analizados y resguardados bajo criterios de confidencialidad y seguridad, conforme a la normativa vigente.",
    "Destinatarios y acceso: La información será conocida únicamente por el personal autorizado, para los fines indicados. No será cedida a terceros ajenos a estos fines.",
    "Responsable de la base de datos: El Ministerio de Seguridad Pública, a través de las dependencias competentes, será responsable del tratamiento y custodia de la información recolectada.",
    "Derechos de la persona participante: Usted conserva el derecho a la autodeterminación informativa y a decidir libremente sobre el suministro de sus datos."
]

CONSENT_CIERRE = [
    "Las respuestas brindadas no constituyen denuncias formales, ni sustituyen los mecanismos legales correspondientes.",
    "Al continuar con la encuesta, usted manifiesta haber leído y comprendido la información anterior y otorga su consentimiento informado para participar."
]

# ------------------------------------------------------------------------------------------
# Estado de constructor (se mantiene como tu versión)
# ------------------------------------------------------------------------------------------
if "preguntas" not in st.session_state:
    st.session_state.preguntas = []
if "reglas_visibilidad" not in st.session_state:
    st.session_state.reglas_visibilidad = []
if "reglas_finalizar" not in st.session_state:
    st.session_state.reglas_finalizar = []

# ------------------------------------------------------------------------------------------
# Precarga de preguntas (sin barrio; SOLO cantón y distrito)
# ------------------------------------------------------------------------------------------
if "seed_cargado" not in st.session_state:
    v_si = slugify_name("Si")
    v_no = slugify_name("No")
    v_mas_seguro = slugify_name("Más seguro")
    v_igual = slugify_name("Igual")
    v_menos_seg = slugify_name("Menos seguro")

    seed = [
        # ---------------- Página 3: Datos demográficos ----------------
        {"tipo_ui": "Selección única", "label": "Cantón", "name": "canton", "required": True,
         "opciones": [], "appearance": None, "choice_filter": None, "relevant": None},
        {"tipo_ui": "Selección única", "label": "Distrito", "name": "distrito", "required": True,
         "opciones": [], "appearance": None, "choice_filter": "canton_key=${canton} or any='1'", "relevant": None},

        {"tipo_ui": "Número", "label": "Edad", "name": "edad", "required": True,
         "opciones": [], "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección única", "label": "Género", "name": "genero", "required": True,
         "opciones": ["Masculino", "Femenino", "LGTBQ+"], "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección única", "label": "Escolaridad", "name": "escolaridad", "required": True,
         "opciones": ["Ninguna", "Primaria", "Primaria incompleta", "Secundaria completa", "Secundaria incompleta",
                      "Universitaria", "Universitaria incompleta", "Técnico"],
         "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección múltiple", "label": "¿Cuál es su relación con la zona?", "name": "relacion_zona", "required": True,
         "opciones": ["Vivo en la zona", "Trabajo en la zona", "Visito la zona"], "appearance": None, "choice_filter": None, "relevant": None},

        # ---------------- Página 4: Sentimiento de inseguridad ----------------
        {"tipo_ui": "Selección única", "label": "¿Se siente seguro en su barrio?", "name": "se_siente_seguro", "required": True,
         "opciones": ["Si", "No"], "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Párrafo (texto largo)", "label": "Indique por qué considera el barrio inseguro", "name": "motivo_inseguridad", "required": True,
         "opciones": [], "appearance": None, "choice_filter": None, "relevant": f"${{se_siente_seguro}}='{slugify_name('No')}'"},

        {"tipo_ui": "Selección única", "label": "¿Cómo se siente respecto a la seguridad en su barrio este año comparado con el anterior?", "name": "comparacion_anual", "required": True,
         "opciones": ["Más seguro", "Igual", "Menos seguro"], "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Párrafo (texto largo)", "label": "Indique por qué.", "name": "motivo_comparacion", "required": True,
         "opciones": [], "appearance": None, "choice_filter": None, "relevant": xlsform_or_expr([
             f"${{comparacion_anual}}='{v_mas_seguro}'",
             f"${{comparacion_anual}}='{v_igual}'",
             f"${{comparacion_anual}}='{v_menos_seg}'"
         ])},

        # ---------------- Página 5: Lugares del barrio ----------------
        {"tipo_ui": "Selección única", "label": "Discotecas, bares, sitios de entretenimiento", "name": "lugar_entretenimiento", "required": True,
         "opciones": ["Seguro", "Inseguro", "No existe en el Barrio"], "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección única", "label": "Espacios recreativos", "name": "espacios_recreativos", "required": True,
         "opciones": ["Seguro", "Inseguro", "No existe en el Barrio"], "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección única", "label": "Lugar de residencia", "name": "lugar_residencia", "required": True,
         "opciones": ["Seguro", "Inseguro", "No existe en el Barrio"], "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección única", "label": "Paradas/estaciones (buses, taxis, trenes)", "name": "paradas_estaciones", "required": True,
         "opciones": ["Seguro", "Inseguro", "No existe en el Barrio"], "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección única", "label": "Puentes peatonales", "name": "puentes_peatonales", "required": True,
         "opciones": ["Seguro", "Inseguro", "No existe en el Barrio"], "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección única", "label": "Transporte público", "name": "transporte_publico", "required": True,
         "opciones": ["Seguro", "Inseguro", "No existe en el Barrio"], "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección única", "label": "Zona bancaria", "name": "zona_bancaria", "required": True,
         "opciones": ["Seguro", "Inseguro", "No existe en el Barrio"], "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección única", "label": "Zona de comercio", "name": "zona_comercio", "required": True,
         "opciones": ["Seguro", "Inseguro", "No existe en el Barrio"], "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección única", "label": "Zonas residenciales", "name": "zonas_residenciales", "required": True,
         "opciones": ["Seguro", "Inseguro", "No existe en el Barrio"], "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección única", "label": "Lugares de interés turístico", "name": "lugares_turisticos", "required": True,
         "opciones": ["Seguro", "Inseguro", "No existe en el Barrio"], "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Texto (corto)", "label": "¿Cuál es el lugar o zona más inseguro en su barrio? (opcional)", "name": "zona_mas_insegura", "required": False,
         "opciones": [], "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Párrafo (texto largo)", "label": "Describa por qué considera que esa zona es insegura (opcional)", "name": "porque_insegura", "required": False,
         "opciones": [], "appearance": None, "choice_filter": None, "relevant": None},

        # ---------------- Página 6: Incidencia de delitos ----------------
        {"tipo_ui": "Selección múltiple", "label": "Incidencia relacionada a delitos", "name": "incidencia_delitos", "required": False,
         "opciones": [
             "Disturbios en vía pública.(Riñas o Agresión)",
             "Daños a la propiedad. (Destruir, inutilizar o desaparecer).",
             "Extorsión (intimidar o amenazar a otras personas con fines de lucro).",
             "Hurto. (sustracción de artículos mediante el descuido).",
             "Receptación (persona que adquiere, recibe u oculta artículos provenientes de un delito en el que no participó).",
             "Contrabando (licor, cigarrillos, medicinas, ropa, calzado, etc.)",
             "Maltrato animal",
             "Tráfico ilegal de personas (coyotaje)"
         ], "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección múltiple", "label": "Venta de drogas", "name": "venta_drogas", "required": False,
         "opciones": ["bunker espacio cerrado", "vía pública", "exprés"], "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección múltiple", "label": "Delitos contra la vida", "name": "delitos_vida", "required": False,
         "opciones": ["Homicidios", "Heridos"], "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección múltiple", "label": "Delitos sexuales", "name": "delitos_sexuales", "required": False,
         "opciones": ["Abuso sexual", "Acoso sexual", "Violación"], "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección múltiple", "label": "Asaltos", "name": "asaltos", "required": False,
         "opciones": ["Asalto a personas", "Asalto a comercio", "Asalto a vivienda", "Asalto a transporte público"],
         "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección múltiple", "label": "Estafas", "name": "estafas", "required": False,
         "opciones": ["Billetes falso", "Documentos falsos", "Estafa (Oro)", "Lotería falsos", "Estafas informáticas",
                      "Estafa telefónica", "Estafa con tarjetas"],
         "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección múltiple", "label": "Robo (sustracción con fuerza)", "name": "robo_fuerza", "required": False,
         "opciones": ["Tacha a comercio", "Tacha a edificaciones", "Tacha a vivienda", "Tacha de vehículos",
                      "Robo de Ganado Abigeato (Destace de ganado)",
                      "Robo de bienes agrícola", "Robo de vehículos", "Robo de cable", "Robo de combustible"],
         "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección múltiple", "label": "Abandono de personas", "name": "abandono_personas", "required": False,
         "opciones": ["Abandono de adulto mayor", "Abandono de menor de edad", "Abandono de incapaz"],
         "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección múltiple", "label": "Explotación infantil", "name": "explotacion_infantil", "required": False,
         "opciones": ["Sexual", "Laboral"], "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección múltiple", "label": "Delitos ambientales", "name": "delitos_ambientales", "required": False,
         "opciones": ["Caza ilegal", "Pesca ilegal", "Tala ilegal"], "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección múltiple", "label": "Trata de personas", "name": "trata_personas", "required": False,
         "opciones": ["Con fines laborales", "Con fines sexuales"], "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección única", "label": "Violencia Intrafamiliar", "name": "vi", "required": False,
         "opciones": ["Si", "No"], "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección única", "label": "¿Ha sido víctima o conoce a alguien que haya sido víctima de VI en el último año?", "name": "vi_victima_ultimo_anno", "required": True,
         "opciones": ["Si", "No"], "appearance": None, "choice_filter": None, "relevant": f"${{vi}}='{slugify_name('Si')}'"},

        {"tipo_ui": "Selección múltiple", "label": "Tipos de Violencia Intrafamiliar (marque todos los que correspondan)", "name": "vi_tipos", "required": True,
         "opciones": ["Violencia psicológica (gritos, amenazas, burlas, maltratos, etc)",
                      "Violencia física (golpes, empujones, etc)",
                      "Violencia patrimonial (destrucción o retención de artículos, documentos, dinero, etc)",
                      "Violencia sexual (actos sexuales no consentido)"],
         "appearance": None, "choice_filter": None, "relevant": f"${{vi}}='{slugify_name('Si')}'"},

        {"tipo_ui": "Selección única", "label": "¿Fue abordado por Fuerza Pública?", "name": "vi_fp_abordaje", "required": True,
         "opciones": ["Si", "No"], "appearance": None, "choice_filter": None, "relevant": f"${{vi}}='{slugify_name('Si')}'"},

        {"tipo_ui": "Selección única", "label": "¿Cómo fue el abordaje de la Fuerza Pública?", "name": "vi_fp_eval", "required": True,
         "opciones": ["Excelente", "Bueno", "Regular", "Malo"], "appearance": None, "choice_filter": None,
         "relevant": f"${{vi_fp_abordaje}}='{slugify_name('Si')}'"},

        # ---------------- Página 7: Riesgos Sociales ----------------
        {"tipo_ui": "Selección múltiple", "label": "Riesgos Sociales", "name": "riesgos_sociales", "required": False,
         "opciones": [
             "Escándalos musicales.",
             "Falta de oportunidades laborales.",
             "Problemas Vecinales.",
             "Asentamientos ilegales (conocido como precarios).",
             "Personas en situación de calle.",
             "Desvinculación escolar (deserción escolar)",
             "Zona de prostitución",
             "Consumo de alcohol en vía pública",
             "Personas con exceso de tiempo de ocio",
             "Acumulación de basuras, aguas negras, mal alcantarillado.",
             "Carencia o inexistencia de alumbrado público.",
             "Cuarterías",
             "Lotes baldíos.",
             "Ventas informales",
             "Pérdida de espacios públicos (parques, polideportivos, etc.).",
             "Otro"
         ], "appearance": None, "choice_filter": None, "relevant": None},
    ]

    st.session_state.preguntas = seed
    st.session_state.seed_cargado = True

# ------------------------------------------------------------------------------------------
# Sidebar: Metadatos + Exportar/Importar proyecto (se mantiene)
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
    st.caption("💾 Exporta/Importa tu proyecto (JSON)")
    col_exp, col_imp = st.columns(2)

    if col_exp.button("Exportar proyecto (JSON)", use_container_width=True):
        proj = {
            "form_title": form_title,
            "idioma": idioma,
            "version": version,
            "preguntas": st.session_state.preguntas,
            "reglas_visibilidad": st.session_state.reglas_visibilidad,
            "reglas_finalizar": st.session_state.reglas_finalizar
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
            _rerun()
        except Exception as e:
            st.error(f"No se pudo importar el JSON: {e}")

# ------------------------------------------------------------------------------------------
# Constructor: Agregar nuevas preguntas (se mantiene)
# ------------------------------------------------------------------------------------------
st.subheader("📝 Diseña tus preguntas")

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
# Lista / Ordenado / Edición (se mantiene)
# ------------------------------------------------------------------------------------------
st.subheader("📚 Preguntas (ordénalas y edítalas)")
if not st.session_state.preguntas:
    st.info("Aún no has agregado preguntas.")
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

            upb = c2.button("⬆️ Subir", key=f"up_{idx}", use_container_width=True, disabled=(idx == 0))
            downb = c3.button("⬇️ Bajar", key=f"down_{idx}", use_container_width=True, disabled=(idx == len(st.session_state.preguntas) - 1))
            editb = c4.button("✏️ Editar", key=f"edit_{idx}", use_container_width=True)
            delb = c5.button("🗑️ Eliminar", key=f"del_{idx}", use_container_width=True)

            if upb:
                st.session_state.preguntas[idx - 1], st.session_state.preguntas[idx] = st.session_state.preguntas[idx], st.session_state.preguntas[idx - 1]
                _rerun()
            if downb:
                st.session_state.preguntas[idx + 1], st.session_state.preguntas[idx] = st.session_state.preguntas[idx], st.session_state.preguntas[idx + 1]
                _rerun()

            if editb:
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

            if delb:
                del st.session_state.preguntas[idx]
                st.warning("Pregunta eliminada.")
                _rerun()

# ------------------------------------------------------------------------------------------
# Condicionales (se mantiene)
# ------------------------------------------------------------------------------------------
st.subheader("🔀 Condicionales (mostrar / finalizar)")
if not st.session_state.preguntas:
    st.info("Agrega preguntas para definir condicionales.")
else:
    with st.expander("👁️ Mostrar pregunta si se cumple condición", expanded=False):
        names = [q["name"] for q in st.session_state.preguntas]
        labels_by_name = {q["name"]: q["label"] for q in st.session_state.preguntas}

        target = st.selectbox(
            "Pregunta a mostrar (target)",
            options=names,
            format_func=lambda n: f"{n} — {labels_by_name[n]}"
        )
        src = st.selectbox(
            "Depende de (source)",
            options=names,
            format_func=lambda n: f"{n} — {labels_by_name[n]}"
        )
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

        src2 = st.selectbox(
            "Condición basada en",
            options=names,
            format_func=lambda n: f"{n} — {labels_by_name[n]}",
            key="final_src"
        )
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
                idx_src = next((i for i, qq in enumerate(st.session_state.preguntas) if qq["name"] == src2), 0)
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
# Construcción XLSForm (Páginas) + Consentimiento + Glosario por página
# ------------------------------------------------------------------------------------------
def construir_xlsform(preguntas, form_title: str, idioma: str, version: str,
                      reglas_vis, reglas_fin,
                      glosario_dict: Dict[str, str]):

    survey_rows = []
    choices_rows = []

    # ---------------- choices base
    list_yesno = "yesno"
    v_si = slugify_name("Sí")
    v_no = slugify_name("No")
    choices_rows += [
        {"list_name": list_yesno, "name": v_si, "label": "Sí"},
        {"list_name": list_yesno, "name": v_no, "label": "No"},
    ]

    # ---------------- visibilidad / fin (se mantiene)
    vis_by_target = {}
    for r in reglas_vis:
        vis_by_target.setdefault(r["target"], []).append(
            {"src": r["src"], "op": r.get("op", "="), "values": r.get("values", [])}
        )

    fin_conds = []
    for r in reglas_fin:
        cond = build_relevant_expr([{"src": r["src"], "op": r.get("op", "="), "values": r.get("values", [])}])
        if cond:
            fin_conds.append((r["index_src"], cond))

    def add_q(q, idx, page_text_accum: List[str]):
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

        # Constraints para placeholders del catálogo Cantón/Distrito
        if q["name"] == "canton":
            row["constraint"] = ". != '__pick_canton__'"
            row["constraint_message"] = "Seleccione un cantón válido."
        if q["name"] == "distrito":
            row["constraint"] = ". != '__pick_distrito__'"
            row["constraint_message"] = "Seleccione un distrito válido."

        survey_rows.append(row)

        # acumulador para glosario (label + opciones)
        page_text_accum.append(str(q.get("label") or ""))
        if q.get("opciones"):
            for opt in q["opciones"]:
                page_text_accum.append(str(opt))

        # choices (no generar opciones para canton/distrito, se usan las del catálogo)
        if list_name and q["name"] not in {"canton", "distrito"}:
            usados = set()
            for opt_label in (q.get("opciones") or []):
                base = slugify_name(opt_label)
                opt_name = asegurar_nombre_unico(base, usados)
                usados.add(opt_name)
                choices_rows.append({"list_name": list_name, "name": opt_name, "label": str(opt_label)})

    def add_glosario_for_page(page_key: str, page_label: str, page_text: str):
        """
        Agrega:
          - select_one yesno (opcional) al final de la página
          - si Sí: grupo Glosario con definiciones encontradas SOLO para esa página
        """
        hits = glosario_matches_for_text(glosario_dict, page_text)
        if not hits:
            return

        qname = f"glosario_{page_key}"
        survey_rows.append({
            "type": f"select_one {list_yesno}",
            "name": qname,
            "label": "¿Desea consultar el glosario de esta página?",
            "required": "",
            "appearance": "minimal"
        })

        rel_glos = f"${{{qname}}}='{v_si}'"
        survey_rows.append({
            "type": "begin_group",
            "name": f"{qname}_grp",
            "label": "Glosario",
            "appearance": "field-list",
            "relevant": rel_glos
        })

        survey_rows.append({
            "type": "note",
            "name": f"{qname}_nota",
            "label": "Para volver a la encuesta, use el botón **Atrás** (Anterior) y continúe donde estaba."
        })

        # definiciones completas (sin recortar)
        for i, term in enumerate(hits, start=1):
            defin = glosario_dict.get(term, "")
            survey_rows.append({
                "type": "note",
                "name": f"{qname}_t_{i}",
                "label": f"{term}: {defin}"
            })

        survey_rows.append({"type": "end_group", "name": f"{qname}_grp_end"})

    # =========================
    # Página 1: Introducción
    # =========================
    survey_rows.append({"type": "begin_group", "name": "p1_intro", "label": "Introducción", "appearance": "field-list"})
    survey_rows.append({"type": "note", "name": "p1_logo", "label": form_title, "media::image": logo_media_name})
    survey_rows.append({"type": "note", "name": "p1_texto", "label": INTRO_COMUNIDAD})
    survey_rows.append({"type": "end_group", "name": "p1_end"})

    # (glosario solo si encontrara coincidencias en intro; normalmente no)
    add_glosario_for_page("p1", "Introducción", INTRO_COMUNIDAD)

    # =========================
    # Página 2: Consentimiento
    # =========================
    survey_rows.append({"type": "begin_group", "name": "p2_consent", "label": "Consentimiento Informado", "appearance": "field-list"})
    survey_rows.append({"type": "note", "name": "p2_titulo", "label": CONSENT_TITLE})

    for i, p in enumerate(CONSENT_PARRAFOS, start=1):
        survey_rows.append({"type": "note", "name": f"p2_p_{i}", "label": p})

    for j, b in enumerate(CONSENT_BULLETS, start=1):
        survey_rows.append({"type": "note", "name": f"p2_b_{j}", "label": f"• {b}"})

    for k, c in enumerate(CONSENT_CIERRE, start=1):
        survey_rows.append({"type": "note", "name": f"p2_c_{k}", "label": c})

    survey_rows.append({
        "type": f"select_one {list_yesno}",
        "name": "acepta_participar",
        "label": "¿Acepta participar en esta encuesta?",
        "required": "yes",
        "appearance": "minimal"
    })
    survey_rows.append({"type": "end_group", "name": "p2_end"})

    # Finaliza si NO acepta
    survey_rows.append({
        "type": "end",
        "name": "fin_por_no",
        "label": "Gracias. Usted indicó que no acepta participar en esta encuesta.",
        "relevant": f"${{acepta_participar}}='{v_no}'"
    })

    # Relevante base: solo si acepta SÍ
    rel_si = f"${{acepta_participar}}='{v_si}'"

    # =========================
    # Distribución por páginas (en esta versión: demográficos, sentimiento, lugares, delitos, riesgos)
    # =========================
    # SETs por página (mismos names de seed)
    p3_demog = {"canton", "distrito", "edad", "genero", "escolaridad", "relacion_zona"}
    p4_sent = {"se_siente_seguro", "motivo_inseguridad", "comparacion_anual", "motivo_comparacion"}
    p5_lug = {"lugar_entretenimiento", "espacios_recreativos", "lugar_residencia", "paradas_estaciones",
              "puentes_peatonales", "transporte_publico", "zona_bancaria", "zona_comercio",
              "zonas_residenciales", "lugares_turisticos", "zona_mas_insegura", "porque_insegura"}
    p6_del = {"incidencia_delitos", "venta_drogas", "delitos_vida", "delitos_sexuales", "asaltos", "estafas",
              "robo_fuerza", "abandono_personas", "explotacion_infantil", "delitos_ambientales", "trata_personas",
              "vi", "vi_victima_ultimo_anno", "vi_tipos", "vi_fp_abordaje", "vi_fp_eval"}
    p7_ries = {"riesgos_sociales"}

    def add_page(group_name: str, page_label: str, names_set: set, page_key: str):
        survey_rows.append({
            "type": "begin_group",
            "name": group_name,
            "label": page_label,
            "appearance": "field-list",
            "relevant": rel_si
        })

        page_text_accum = [page_label]
        # agrega preguntas en el orden actual de "preguntas"
        for i, q in enumerate(preguntas):
            if q["name"] in names_set:
                add_q(q, i, page_text_accum)

        survey_rows.append({"type": "end_group", "name": f"{group_name}_end"})

        # Glosario automático SOLO si hay coincidencias en esta página
        add_glosario_for_page(page_key, page_label, "\n".join(page_text_accum))

    add_page("p3_demograficos", "Datos demográficos", p3_demog, "p3")
    add_page("p4_sentimiento", "Sentimiento de inseguridad en el barrio", p4_sent, "p4")
    add_page("p5_lugares", "Indique cómo se siente en los siguientes lugares de su barrio", p5_lug, "p5")
    add_page("p6_incidencia", "Incidencia relacionada a delitos", p6_del, "p6")
    add_page("p7_riesgos", "Riesgos Sociales", p7_ries, "p7")

    # =========================
    # Choices del catálogo manual Cantón/Distrito
    # =========================
    for r in st.session_state.choices_ext_rows:
        choices_rows.append(dict(r))

    # =========================
    # DataFrames
    # =========================
    survey_cols_all = set().union(*[r.keys() for r in survey_rows])
    survey_cols = [
        c for c in [
            "type", "name", "label", "required", "appearance",
            "choice_filter", "relevant", "constraint", "constraint_message", "media::image"
        ] if c in survey_cols_all
    ]
    for k in sorted(survey_cols_all):
        if k not in survey_cols:
            survey_cols.append(k)

    df_survey = pd.DataFrame(survey_rows, columns=survey_cols).fillna("")

    choices_cols_all = set()
    for r in choices_rows:
        choices_cols_all.update(r.keys())

    base_choice_cols = ["list_name", "name", "label"]
    for extra in sorted(choices_cols_all):
        if extra not in base_choice_cols:
            base_choice_cols.append(extra)

    df_choices = pd.DataFrame(choices_rows, columns=base_choice_cols).fillna("")

    df_settings = pd.DataFrame([{
        "form_title": form_title,
        "version": version,
        "default_language": idioma,
        "style": "pages"
    }], columns=["form_title", "version", "default_language", "style"]).fillna("")

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
- **survey** con páginas (`style = pages`), consentimiento y glosarios por página (si hay coincidencias),
- **choices** con catálogo Cantón/Distrito y listas de cada pregunta,
- **settings** con título, versión, idioma.
""")

if st.button("🧮 Construir XLSForm", use_container_width=True, disabled=not st.session_state.preguntas):
    try:
        names = [q["name"] for q in st.session_state.preguntas]
        if len(names) != len(set(names)):
            st.error("Hay 'name' duplicados. Edita las preguntas para que cada 'name' sea único.")
        else:
            df_survey, df_choices, df_settings = construir_xlsform(
                st.session_state.preguntas,
                form_title=form_title,
                idioma=idioma,
                version=(version.strip() or datetime.now().strftime("%Y%m%d%H%M")),
                reglas_vis=st.session_state.reglas_visibilidad,
                reglas_fin=st.session_state.reglas_finalizar,
                glosario_dict=st.session_state.glosario_dict
            )

            st.success("XLSForm construido. Vista previa:")
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown("**Hoja: survey**")
                st.dataframe(df_survey.fillna(""), use_container_width=True, hide_index=True)
            with c2:
                st.markdown("**Hoja: choices**")
                st.dataframe(df_choices.fillna(""), use_container_width=True, hide_index=True)
            with c3:
                st.markdown("**Hoja: settings**")
                st.dataframe(df_settings.fillna(""), use_container_width=True, hide_index=True)

            nombre_archivo = slugify_name(form_title) + "_xlsform.xlsx"
            descargar_excel_xlsform(df_survey, df_choices, df_settings, nombre_archivo)

            if st.session_state.get("_logo_bytes"):
                st.download_button(
                    "📥 Descargar logo para carpeta media/",
                    data=st.session_state["_logo_bytes"],
                    file_name=logo_media_name,
                    mime="image/png",
                    use_container_width=True
                )

            st.info("""
**Cómo usar en Survey123 Connect**
1) Crear encuesta **desde archivo** y seleccionar el XLSForm descargado.  
2) Copiar el logo dentro de la carpeta **media/** del proyecto, con el **mismo nombre** que pusiste en `media::image`.  
3) Verás páginas con **Siguiente/Anterior** (porque `settings.style = pages`).  
4) Si aparece glosario, es opcional: la persona entra y luego se devuelve con **Atrás** para seguir contestando.  
""")

    except Exception as e:
        st.error(f"Ocurrió un error al generar el XLSForm: {e}")
