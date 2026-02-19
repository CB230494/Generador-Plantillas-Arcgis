# -*- coding: utf-8 -*-
# ==========================================================================================
# App: Encuesta POLICIAL (Fuerza Pública) → XLSForm para ArcGIS Survey123 (versión extendida)
# - Constructor completo (agregar/editar/ordenar/borrar)
# - Condicionales (relevant) + finalizar temprano
# - Exportar/Importar proyecto (JSON)
# - Exportar a XLSForm (survey/choices/settings)
# - PÁGINAS reales (style="pages"): Intro + Consentimiento + Datos generales + Interés policial + Interés interno
# - Portada con logo (media::image) y texto de introducción
# - Consentimiento:
#     - Texto en BLOQUES (notes separados) para que se vea ordenado en Survey123
#     - Si marca "No" ⇒ NO muestra el resto de páginas y cae a una página final para enviar
# - FIX: Al editar preguntas/opciones, los cambios SIEMPRE se reflejan (qid estable)
#
# ✅ ESTA VERSIÓN:
#   - NO incluye Cantón/Distrito (solo Delegación destino)
#   - Incluye:
#       P1 Introducción (Policial Percepción Institucional 2026)
#       P2 Consentimiento (igual)
#       P3 Datos generales (1–5.1)
#       P4 Información de interés policial (6–8 + 6.1–6.4 condicional)
#       P5 Información de interés interno (9–16 + condicionales 10.1, 11.1, 12.1, 13.1, 14.1)
# ==========================================================================================

import re
import json
import uuid
from io import BytesIO
from datetime import datetime
from typing import List, Dict

import streamlit as st
import pandas as pd

# ------------------------------------------------------------------------------------------
# Configuración de la app
# ------------------------------------------------------------------------------------------
st.set_page_config(page_title="Encuesta Policial → XLSForm (Survey123)", layout="wide")
st.title("👮‍♂️ Encuesta Policial (Fuerza Pública) → XLSForm para ArcGIS Survey123")

st.markdown("""
Crea tu cuestionario y **exporta un XLSForm** listo para **ArcGIS Survey123**.

Incluye:
- Tipos: **text**, **integer/decimal**, **date**, **time**, **geopoint**, **select_one**, **select_multiple**.
- **Constructor completo** (agregar, editar, ordenar, borrar) con condicionales.
- **Páginas** con navegación **Siguiente/Anterior** (`settings.style = pages`).
- **Portada** con **logo** (`media::image`) e **introducción**.
- **Consentimiento informado** (si NO acepta, la encuesta termina) con texto ordenado por bloques.
""")

# ------------------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------------------
TIPOS = [
    "Texto (corto)",
    "Párrafo (texto largo)",
    "Número",
    "Selección única",
    "Selección múltiple",
    "Fecha",
    "Hora",
    "GPS (ubicación)",
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
# FIX REFLEJO DE EDICIÓN: ID estable por pregunta (qid) + editor por qid
# ------------------------------------------------------------------------------------------
def ensure_qid(q: Dict) -> Dict:
    if "qid" not in q or not q["qid"]:
        q["qid"] = str(uuid.uuid4())
    return q

def q_index_by_qid(qid: str) -> int:
    for i, q in enumerate(st.session_state.preguntas):
        if q.get("qid") == qid:
            return i
    return -1

# ------------------------------------------------------------------------------------------
# Estado base (session_state)
# ------------------------------------------------------------------------------------------
if "preguntas" not in st.session_state:
    st.session_state.preguntas = []
if "reglas_visibilidad" not in st.session_state:
    st.session_state.reglas_visibilidad = []
if "reglas_finalizar" not in st.session_state:
    st.session_state.reglas_finalizar = []
if "edit_qid" not in st.session_state:
    st.session_state.edit_qid = None

# ------------------------------------------------------------------------------------------
# Logo + Delegación
# ------------------------------------------------------------------------------------------
DEFAULT_LOGO_PATH = "001.png"

col_logo, col_txt = st.columns([1, 3], vertical_alignment="center")
with col_logo:
    up_logo = st.file_uploader("Logo (PNG/JPG)", type=["png", "jpg", "jpeg"], key="uploader_logo")
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
    delegacion = st.text_input("Delegación destino (texto)", value="Alajuela Norte", key="delegacion_txt")
    logo_media_name = st.text_input(
        "Nombre de archivo para `media::image`",
        value=st.session_state.get("_logo_name", "001.png"),
        help="Debe coincidir con el archivo en `media/` de Survey123 Connect.",
        key="logo_media_txt"
    )
    titulo_compuesto = (f"Encuesta policial – {delegacion.strip()}" if delegacion.strip() else "Encuesta policial")
    st.markdown(f"<h5 style='text-align:center;margin:4px 0'>📋 {titulo_compuesto}</h5>", unsafe_allow_html=True)

def _get_logo_media_name():
    """
    Devuelve el nombre del archivo que se usará en la columna media::image del XLSForm.
    Debe existir en la carpeta media/ del proyecto Survey123 (Survey123 Connect).
    """
    try:
        return st.session_state.get("logo_media_txt") or st.session_state.get("_logo_name") or "001.png"
    except Exception:
        return "001.png"

# ------------------------------------------------------------------------------------------
# Textos base (Intro / Consentimiento / Intros de páginas)
# ------------------------------------------------------------------------------------------
INTRO_POLICIAL_2026 = (
    "Esta encuesta busca recopilar información desde la experiencia del personal de la Fuerza Pública para apoyar la "
    "planificación preventiva y la mejora del servicio policial."
)

INTRO_DATOS_GENERALES = (
)

INTRO_INTERES_POLICIAL = (
    "En este apartado, el objetivo principal es comprender las estructuras criminales y las problemáticas de interés policial "
    "presentes en la jurisdicción de la delegación. A través de esto se busca obtener una visión clara de la naturaleza y dinámicas "
    "de las organizaciones criminales en la zona."
)

INTRO_INTERES_INTERNO = (
    "En este apartado se recopila información sobre recursos, condiciones institucionales, necesidades de capacitación y factores "
    "internos que inciden en la prestación del servicio policial. La información es para uso institucional y análisis preventivo."
)

CONSENTIMIENTO_TITULO = "Consentimiento Informado para la Participación en la Encuesta"
CONSENT_SI = slugify_name("Sí")
CONSENT_NO = slugify_name("No")

CONSENTIMIENTO_BLOQUES = [
    "Usted está siendo invitado(a) a participar de forma libre y voluntaria en una encuesta sobre seguridad, convivencia y percepción institucional, dirigida al personal de la Fuerza Pública.",
    "El objetivo de esta encuesta es recopilar información de carácter preventivo y estadístico, con el fin de apoyar el análisis institucional, la planificación preventiva y la mejora continua del servicio policial.",
    "La participación es totalmente voluntaria. Usted puede negarse a responder cualquier pregunta, así como retirarse de la encuesta en cualquier momento, sin que ello genere consecuencia alguna.",
    "De conformidad con lo dispuesto en el artículo 5 de la Ley N.º 8968 (Protección de la Persona frente al Tratamiento de sus Datos Personales), se le informa que:",
    "Finalidad del tratamiento: La información recopilada será utilizada exclusivamente para fines estadísticos, analíticos y preventivos, y no para investigaciones penales, procesos judiciales, sanciones administrativas ni procedimientos disciplinarios.",
    "Datos personales: Algunos apartados permiten, de forma voluntaria, el suministro de datos personales o información de contacto.",
    "Tratamiento de los datos: Los datos serán almacenados, analizados y resguardados bajo criterios de confidencialidad y seguridad, conforme a la normativa vigente.",
    "Destinatarios y acceso: La información será conocida únicamente por el personal autorizado del Ministerio de Seguridad Pública / Fuerza Pública, para los fines indicados. No será cedida a terceros ajenos a estos fines.",
    "Responsable de la base de datos: El Ministerio de Seguridad Pública, a través de las instancias competentes, será responsable del tratamiento y custodia de la información recolectada.",
    "Derechos de la persona participante: Usted conserva el derecho a la autodeterminación informativa y a decidir libremente sobre el suministro de sus datos.",
    "Las respuestas brindadas no constituyen denuncias formales, ni sustituyen los mecanismos legales correspondientes.",
    "Al continuar con la encuesta, usted manifiesta haber leído y comprendido la información anterior y otorga su consentimiento informado para participar."
]

# ------------------------------------------------------------------------------------------
# Sidebar: Exportar/Importar proyecto (JSON) + Config
# ------------------------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Configuración")
    _ = st.text_input(
        "Título del formulario (referencia)",
        value=(f"Encuesta policial – {delegacion.strip()}" if delegacion.strip() else "Encuesta policial"),
        key="sb_form_title_ref"
    )
    idioma = st.selectbox("Idioma por defecto (default_language)", options=["es", "en"], index=0, key="sb_idioma")
    version_auto = datetime.now().strftime("%Y%m%d%H%M")
    version = st.text_input("Versión (settings.version)", value=version_auto, key="sb_version")

    st.markdown("---")
    st.caption("💾 Exporta/Importa tu proyecto (JSON)")
    col_exp, col_imp = st.columns(2)

    if col_exp.button("Exportar proyecto (JSON)", use_container_width=True, key="btn_export_json"):
        proj = {
            "idioma": idioma,
            "version": version,
            "preguntas": st.session_state.preguntas,  # incluye qid
            "reglas_visibilidad": st.session_state.reglas_visibilidad,
            "reglas_finalizar": st.session_state.reglas_finalizar,
            "delegacion": delegacion,
        }
        jbuf = BytesIO(json.dumps(proj, ensure_ascii=False, indent=2).encode("utf-8"))
        st.download_button(
            "Descargar JSON",
            data=jbuf,
            file_name="proyecto_encuesta_policial.json",
            mime="application/json",
            use_container_width=True
        )

    up = col_imp.file_uploader("Importar JSON", type=["json"], label_visibility="collapsed", key="uploader_json")
    if up is not None:
        try:
            raw = up.read().decode("utf-8")
            data = json.loads(raw)

            preguntas = list(data.get("preguntas", []))
            st.session_state.preguntas = [ensure_qid(q) for q in preguntas]

            st.session_state.reglas_visibilidad = list(data.get("reglas_visibilidad", []))
            st.session_state.reglas_finalizar = list(data.get("reglas_finalizar", []))
            st.session_state.edit_qid = None
            _rerun()
        except Exception as e:
            st.error(f"No se pudo importar el JSON: {e}")

# ------------------------------------------------------------------------------------------
# Precarga (seed) — POLICIAL (Fuerza Pública)
# ------------------------------------------------------------------------------------------
def _add_if_missing(q: Dict):
    nm = q.get("name")
    if not nm:
        return
    exists = any(qq.get("name") == nm for qq in st.session_state.preguntas)
    if not exists:
        st.session_state.preguntas.append(ensure_qid(q))

if "seed_cargado_policial" not in st.session_state:
    SLUG_SI = slugify_name("Sí")
    SLUG_NO = slugify_name("No")

    # Consentimiento
    _add_if_missing({
        "tipo_ui": "Selección única",
        "label": "¿Acepta participar en esta encuesta?",
        "name": "consentimiento",
        "required": True,
        "opciones": ["Sí", "No"],
        "appearance": "horizontal",
        "choice_filter": None,
        "relevant": None
    })

    # ---------------- P3 DATOS GENERALES (1–5.1) ----------------
    _add_if_missing({
        "tipo_ui": "Número",
        "label": "1. Años de servicio:",
        "name": "anios_servicio",
        "required": True,
        "opciones": [],
        "appearance": None,
        "choice_filter": None,
        "relevant": None
    })

    _add_if_missing({
        "tipo_ui": "Selección única",
        "label": "2. Edad (en años cumplidos): marque la categoría que incluya su edad.",
        "name": "edad_rango",
        "required": True,
        "opciones": ["18 a 29 años", "30 a 44 años", "45 a 59 años", "60 años o más"],
        "appearance": None,
        "choice_filter": None,
        "relevant": None
    })

    _add_if_missing({
        "tipo_ui": "Selección única",
        "label": "3. ¿Con cuál de estas opciones se identifica?",
        "name": "genero",
        "required": True,
        "opciones": ["Femenino", "Masculino", "Persona No Binaria", "Prefiero no decir"],
        "appearance": None,
        "choice_filter": None,
        "relevant": None
    })

    _add_if_missing({
        "tipo_ui": "Selección única",
        "label": "4. Escolaridad:",
        "name": "escolaridad",
        "required": True,
        "opciones": [
            "Ninguna",
            "Primaria incompleta",
            "Primaria completa",
            "Secundaria incompleta",
            "Secundaria completa",
            "Técnico",
            "Universitaria incompleta",
            "Universitaria completa",
        ],
        "appearance": None,
        "choice_filter": None,
        "relevant": None
    })

    _add_if_missing({
        "tipo_ui": "Selección única",
        "label": "5. ¿Cuál es la clase policial que desempeña en su delegación?",
        "name": "clase_policial",
        "required": True,
        "opciones": [
            "Agente I",
            "Agente II",
            "Suboficial I",
            "Suboficial II",
            "Oficial I",
            "Jefe Sub delegación (distrito)",
            "Sub Jefe de delegación",
            "Jefe de delegación",
        ],
        "appearance": None,
        "choice_filter": None,
        "relevant": None
    })

    # 5.1 (en tu imagen aparece como selección única; la dejamos select_one)
    _add_if_missing({
        "tipo_ui": "Selección única",
        "label": "5.1. ¿Cuál es la función principal que desempeña actualmente en la delegación?",
        "name": "funcion_principal",
        "required": True,
        "opciones": [
            "Jefatura / supervisión",
            "Operaciones",
            "Programas preventivos",
            "Oficial de guardia",
            "Comunicaciones",
            "Armería",
            "Conducción operativa de vehículos oficiales",
            "Operativa / patrullaje",
            "Fronteras",
            "Seguridad turística",
            "Otra función",
        ],
        "appearance": None,
        "choice_filter": None,
        "relevant": None
    })
    _add_if_missing({
        "tipo_ui": "Texto (corto)",
        "label": "Indique cuál es esa otra función:",
        "name": "funcion_principal_otro",
        "required": True,
        "opciones": [],
        "appearance": None,
        "choice_filter": None,
        "relevant": f"${{funcion_principal}}='{slugify_name('Otra función')}'"
    })

    # ---------------- P4 INFORMACIÓN DE INTERÉS POLICIAL (6–8 + 6.1–6.4) ----------------
    _add_if_missing({
        "tipo_ui": "Selección única",
        "label": "6. ¿Tiene conocimiento sobre la presencia de personas, grupos u organizaciones que desarrollan actividades ilícitas en su jurisdicción?",
        "name": "presencia_ilicita",
        "required": True,
        "opciones": ["Sí", "No"],
        "appearance": "horizontal",
        "choice_filter": None,
        "relevant": None
    })

    rel6_si = f"${{presencia_ilicita}}='{SLUG_SI}'"

    _add_if_missing({
        "tipo_ui": "Párrafo (texto largo)",
        "label": "6.1 En caso afirmativo, indique si alguna de estas estructuras es conocida públicamente por un nombre o denominación general:",
        "name": "estructura_nombre_publico",
        "required": True,
        "opciones": [],
        "appearance": "multiline",
        "choice_filter": None,
        "relevant": rel6_si
    })

    _add_if_missing({
        "tipo_ui": "Selección múltiple",
        "label": "6.2 En caso afirmativo, ¿qué tipo de actividades delictivas identifica que desarrollan estas personas, grupos u organizaciones en su jurisdicción?",
        "name": "actividades_delictivas_identificadas",
        "required": True,
        "opciones": [
            "Punto de Venta y distribución de Drogas. Búnker (espacio cerrado para la venta y distribución de drogas).",
            "Delitos contra la vida (Homicidios, heridos, femicidios).",
            "Venta y consumo de drogas en vía pública.",
            "Delitos sexuales",
            "Asalto (a personas, comercio, vivienda, transporte público).",
            "Daños a la propiedad. (Destruir, inutilizar o desaparecer).",
            "Estafas (Billetes, documentos, oro, lotería falsos).",
            "Estafa Informática (computadora, tarjetas, teléfonos, etc.).",
            "Extorsión (intimidar o amenazar a otras personas con fines de lucro).",
            "Hurto.",
            "Receptación (persona que adquiere, recibe u oculta artículos provenientes de un delito en el que no participó).",
            "Robo a edificaciones.",
            "Robo a vivienda.",
            "Robo de ganado y agrícola.",
            "Robo a comercio",
            "Robo de vehículos.",
            "Tacha de vehículos.",
            "Contrabando (licor, cigarrillos, medicinas, ropa, calzado, etc.)",
            "Tráfico de personas (coyotaje)",
            "Otro",
        ],
        "appearance": "columns",
        "choice_filter": None,
        "relevant": rel6_si
    })
    _add_if_missing({
        "tipo_ui": "Texto (corto)",
        "label": "Indique cuál es ese otro tipo de actividad delictiva:",
        "name": "actividades_delictivas_otro",
        "required": True,
        "opciones": [],
        "appearance": None,
        "choice_filter": None,
        "relevant": f"{rel6_si} and selected(${{actividades_delictivas_identificadas}}, '{slugify_name('Otro')}')"
    })

    _add_if_missing({
        "tipo_ui": "Párrafo (texto largo)",
        "label": "6.3 Indique quién o quiénes se dedican a estos actos criminales. (nombres, apellidos, alias, lugar o domicilio)",
        "name": "quienes_actos_criminales",
        "required": True,
        "opciones": [],
        "appearance": "multiline",
        "choice_filter": None,
        "relevant": rel6_si
    })

    _add_if_missing({
        "tipo_ui": "Párrafo (texto largo)",
        "label": "6.4 Modo de operar de esta estructura criminal (por ejemplo: venta de droga exprés o en vía pública, asalto a mano armada, modo de desplazamiento, etc.)",
        "name": "modo_operar_estructura",
        "required": True,
        "opciones": [],
        "appearance": "multiline",
        "choice_filter": None,
        "relevant": rel6_si
    })

    _add_if_missing({
        "tipo_ui": "Párrafo (texto largo)",
        "label": "7. Indique el lugar, sector o zona que, según su experiencia policial, presenta mayores condiciones de inseguridad dentro de su área de responsabilidad.",
        "name": "zona_mayor_inseguridad",
        "required": True,
        "opciones": [],
        "appearance": "multiline",
        "choice_filter": None,
        "relevant": None
    })

    _add_if_missing({
        "tipo_ui": "Párrafo (texto largo)",
        "label": "8. Describa las principales situaciones o condiciones de riesgo que inciden en la inseguridad de esa zona.",
        "name": "condiciones_riesgo_zona",
        "required": True,
        "opciones": [],
        "appearance": "multiline",
        "choice_filter": None,
        "relevant": None
    })

    # ---------------- P5 INFORMACIÓN DE INTERÉS INTERNO (9–16) ----------------
    _add_if_missing({
        "tipo_ui": "Párrafo (texto largo)",
        "label": "9. Desde su experiencia operativa, indique qué recursos considera necesarios para fortalecer la labor policial en su delegación.",
        "name": "recursos_necesarios",
        "required": True,
        "opciones": [],
        "appearance": "multiline",
        "choice_filter": None,
        "relevant": None
    })

    _add_if_missing({
        "tipo_ui": "Selección única",
        "label": "10. ¿Considera que las condiciones actuales de su delegación permiten cubrir adecuadamente sus necesidades básicas para el servicio (descanso, alimentación, recurso móvil, entre otros)?",
        "name": "condiciones_basicas_ok",
        "required": True,
        "opciones": ["Sí", "No"],
        "appearance": "horizontal",
        "choice_filter": None,
        "relevant": None
    })
    _add_if_missing({
        "tipo_ui": "Párrafo (texto largo)",
        "label": "10.1 ¿Cuáles condiciones considera que se pueden mejorar?",
        "name": "condiciones_mejorar",
        "required": True,
        "opciones": [],
        "appearance": "multiline",
        "choice_filter": None,
        "relevant": f"${{condiciones_basicas_ok}}='{SLUG_NO}'"
    })

    _add_if_missing({
        "tipo_ui": "Selección única",
        "label": "11. ¿Considera usted que hace falta capacitación para el personal en su delegación policial?",
        "name": "falta_capacitacion",
        "required": True,
        "opciones": ["Sí", "No"],
        "appearance": "horizontal",
        "choice_filter": None,
        "relevant": None
    })
    _add_if_missing({
        "tipo_ui": "Párrafo (texto largo)",
        "label": "11.1 Especifique en qué áreas necesita capacitación.",
        "name": "areas_capacitacion",
        "required": True,
        "opciones": [],
        "appearance": "multiline",
        "choice_filter": None,
        "relevant": f"${{falta_capacitacion}}='{SLUG_SI}'"
    })

    _add_if_missing({
        "tipo_ui": "Selección única",
        "label": "12. ¿En qué medida considera que la institución genera un entorno que favorece su motivación para la atención a la ciudadanía?",
        "name": "entorno_motivacion",
        "required": True,
        "opciones": ["Mucho", "Algo", "Poco", "Nada"],
        "appearance": None,
        "choice_filter": None,
        "relevant": None
    })
    rel_12_poco_nada = xlsform_or_expr([
        f"${{entorno_motivacion}}='{slugify_name('Poco')}'",
        f"${{entorno_motivacion}}='{slugify_name('Nada')}'",
    ])
    _add_if_missing({
        "tipo_ui": "Párrafo (texto largo)",
        "label": "12.1 De manera general, indique por qué lo considera así.",
        "name": "motivo_motivacion",
        "required": True,
        "opciones": [],
        "appearance": "multiline",
        "choice_filter": None,
        "relevant": rel_12_poco_nada
    })

    _add_if_missing({
        "tipo_ui": "Selección única",
        "label": "13. ¿Tiene usted conocimiento de situaciones internas que, según su criterio, afectan el adecuado funcionamiento operativo o el servicio a la ciudadanía en su delegación?",
        "name": "situaciones_internas",
        "required": True,
        "opciones": ["Sí", "No"],
        "appearance": "horizontal",
        "choice_filter": None,
        "relevant": None
    })
    _add_if_missing({
        "tipo_ui": "Párrafo (texto largo)",
        "label": "13.1 Describa, de manera general, las situaciones a las que se refiere, relacionadas con aspectos operativos, administrativos o de servicio.",
        "name": "desc_situaciones_internas",
        "required": True,
        "opciones": [],
        "appearance": "multiline",
        "choice_filter": None,
        "relevant": f"${{situaciones_internas}}='{SLUG_SI}'"
    })

    _add_if_missing({
        "tipo_ui": "Selección única",
        "label": "14. ¿Conoce oficiales de Fuerza Pública que se relacionen con alguna estructura criminal o cometan algún delito?",
        "name": "oficiales_relacion_crimen",
        "required": True,
        "opciones": ["Sí", "No"],
        "appearance": "horizontal",
        "choice_filter": None,
        "relevant": None
    })
    _add_if_missing({
        "tipo_ui": "Párrafo (texto largo)",
        "label": "14.1 Describa la situación de la cual tiene conocimiento. (aporte nombre de la estructura, tipo de actividad, nombre de oficiales, función del oficial dentro de la organización, alias, etc.)",
        "name": "desc_oficiales_relacion",
        "required": True,
        "opciones": [],
        "appearance": "multiline",
        "choice_filter": None,
        "relevant": f"${{oficiales_relacion_crimen}}='{SLUG_SI}'"
    })

    _add_if_missing({
        "tipo_ui": "Párrafo (texto largo)",
        "label": "15. Desea, de manera voluntaria, dejar un medio de contacto para brindar más información (correo electrónico, número de teléfono, etc.)",
        "name": "contacto_voluntario",
        "required": False,
        "opciones": [],
        "appearance": "multiline",
        "choice_filter": None,
        "relevant": None
    })

    _add_if_missing({
        "tipo_ui": "Párrafo (texto largo)",
        "label": "16. En el siguiente espacio podrá registrar alguna otra información que estime pertinente.",
        "name": "info_adicional",
        "required": False,
        "opciones": [],
        "appearance": "multiline",
        "choice_filter": None,
        "relevant": None
    })

    st.session_state.seed_cargado_policial = True

# Asegurar qid en todo
st.session_state.preguntas = [ensure_qid(q) for q in st.session_state.preguntas]

# ------------------------------------------------------------------------------------------
# Constructor: Agregar nuevas preguntas
# ------------------------------------------------------------------------------------------
st.subheader("📝 Diseña tus preguntas")

with st.form("form_add_q", clear_on_submit=False):
    tipo_ui = st.selectbox("Tipo de pregunta", options=TIPOS, key="add_tipo")
    label = st.text_input("Etiqueta (texto exacto)", key="add_label")
    sugerido = slugify_name(label) if label else ""
    col_n1, col_n2, col_n3 = st.columns([2, 1, 1])
    name = col_n1.text_input("Nombre interno (XLSForm 'name')", value=sugerido, key="add_name")
    required = col_n2.checkbox("Requerida", value=False, key="add_required")
    appearance = col_n3.text_input("Appearance (opcional)", value="", key="add_appearance")

    opciones = []
    if tipo_ui in ("Selección única", "Selección múltiple"):
        st.markdown("**Opciones (una por línea)**")
        txt_opts = st.text_area("Opciones", height=120, key="add_opts")
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

        nueva = ensure_qid({
            "tipo_ui": tipo_ui,
            "label": label.strip(),
            "name": unico,
            "required": required,
            "opciones": opciones,
            "appearance": (appearance.strip() or None),
            "choice_filter": None,
            "relevant": None
        })
        st.session_state.preguntas.append(nueva)
        st.session_state.edit_qid = None
        st.success(f"Pregunta agregada: **{label}** (name: `{unico}`)")
        _rerun()

# ------------------------------------------------------------------------------------------
# Lista / Ordenado / Edición
# ------------------------------------------------------------------------------------------
st.subheader("📚 Preguntas (ordénalas y edítalas)")

if not st.session_state.preguntas:
    st.info("Aún no has agregado preguntas.")
else:
    for idx, q in enumerate(st.session_state.preguntas):
        q = ensure_qid(q)
        qid = q["qid"]

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

            up_btn = c2.button("⬆️ Subir", key=f"up_{qid}", use_container_width=True, disabled=(idx == 0))
            down_btn = c3.button("⬇️ Bajar", key=f"down_{qid}", use_container_width=True, disabled=(idx == len(st.session_state.preguntas) - 1))
            edit_btn = c4.button("✏️ Editar", key=f"edit_{qid}", use_container_width=True)
            del_btn = c5.button("🗑️ Eliminar", key=f"del_{qid}", use_container_width=True)

            if up_btn:
                st.session_state.preguntas[idx - 1], st.session_state.preguntas[idx] = st.session_state.preguntas[idx], st.session_state.preguntas[idx - 1]
                _rerun()

            if down_btn:
                st.session_state.preguntas[idx + 1], st.session_state.preguntas[idx] = st.session_state.preguntas[idx], st.session_state.preguntas[idx + 1]
                _rerun()

            if edit_btn:
                st.session_state.edit_qid = qid
                _rerun()

            if del_btn:
                if st.session_state.edit_qid == qid:
                    st.session_state.edit_qid = None
                del st.session_state.preguntas[idx]
                st.warning("Pregunta eliminada.")
                _rerun()

            if st.session_state.edit_qid == qid:
                st.markdown("**Editar esta pregunta**")

                ne_label = st.text_input("Etiqueta", value=q["label"], key=f"e_label_{qid}")
                ne_name = st.text_input("Nombre interno (name)", value=q["name"], key=f"e_name_{qid}")
                ne_required = st.checkbox("Requerida", value=q["required"], key=f"e_req_{qid}")
                ne_appearance = st.text_input("Appearance", value=q.get("appearance") or "", key=f"e_app_{qid}")
                ne_choice_filter = st.text_input("choice_filter (opcional)", value=q.get("choice_filter") or "", key=f"e_cf_{qid}")
                ne_relevant = st.text_input("relevant (opcional)", value=q.get("relevant") or "", key=f"e_rel_{qid}")

                ne_opciones = q.get("opciones") or []
                if q["tipo_ui"] in ("Selección única", "Selección múltiple"):
                    ne_opts_txt = st.text_area("Opciones (una por línea)", value="\n".join(ne_opciones), key=f"e_opts_{qid}")
                    ne_opciones = [o.strip() for o in ne_opts_txt.splitlines() if o.strip()]

                col_ok, col_cancel = st.columns(2)

                if col_ok.button("💾 Guardar cambios", key=f"e_save_{qid}", use_container_width=True):
                    cur_idx = q_index_by_qid(qid)
                    if cur_idx == -1:
                        st.error("No se encontró la pregunta (posible cambio de estado). Intenta de nuevo.")
                        st.session_state.edit_qid = None
                        _rerun()

                    new_base = slugify_name(ne_name or ne_label)
                    usados = {qq["name"] for j, qq in enumerate(st.session_state.preguntas) if j != cur_idx}
                    ne_name_final = new_base if new_base not in usados else asegurar_nombre_unico(new_base, usados)

                    st.session_state.preguntas[cur_idx]["label"] = ne_label.strip() or q["label"]
                    st.session_state.preguntas[cur_idx]["name"] = ne_name_final
                    st.session_state.preguntas[cur_idx]["required"] = ne_required
                    st.session_state.preguntas[cur_idx]["appearance"] = ne_appearance.strip() or None
                    st.session_state.preguntas[cur_idx]["choice_filter"] = ne_choice_filter.strip() or None
                    st.session_state.preguntas[cur_idx]["relevant"] = ne_relevant.strip() or None

                    if q["tipo_ui"] in ("Selección única", "Selección múltiple"):
                        st.session_state.preguntas[cur_idx]["opciones"] = ne_opciones

                    st.success("Cambios guardados.")
                    st.session_state.edit_qid = None
                    _rerun()

                if col_cancel.button("Cancelar", key=f"e_cancel_{qid}", use_container_width=True):
                    st.session_state.edit_qid = None
                    _rerun()

# ------------------------------------------------------------------------------------------
# Condicionales (panel) — opcional adicional (mantiene funcionalidad)
# ------------------------------------------------------------------------------------------
st.subheader("🔀 Condicionales (mostrar / finalizar)")
if not st.session_state.preguntas:
    st.info("Agrega preguntas para definir condicionales.")
else:
    # Mostrar
    with st.expander("👁️ Mostrar pregunta si se cumple condición", expanded=False):
        names = [q["name"] for q in st.session_state.preguntas]
        labels_by_name = {q["name"]: q["label"] for q in st.session_state.preguntas}

        target = st.selectbox("Pregunta a mostrar (target)", options=names,
                              format_func=lambda n: f"{n} — {labels_by_name[n]}",
                              key="vis_target")
        src = st.selectbox("Depende de (source)", options=names,
                           format_func=lambda n: f"{n} — {labels_by_name[n]}",
                           key="vis_src")
        op = st.selectbox("Operador", options=["=", "selected"], key="vis_op")
        src_q = next((qq for qq in st.session_state.preguntas if qq["name"] == src), None)

        vals = []
        if src_q and src_q.get("opciones"):
            vals = st.multiselect("Valores (usa texto, internamente se usará slug)", options=src_q["opciones"], key="vis_vals")
            vals = [slugify_name(v) for v in vals]
        else:
            manual = st.text_input("Valor (si la pregunta no tiene opciones)", key="vis_manual")
            vals = [slugify_name(manual)] if manual.strip() else []

        if st.button("➕ Agregar regla de visibilidad", key="btn_add_vis"):
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

    # Finalizar
    with st.expander("⏹️ Finalizar temprano si se cumple condición", expanded=False):
        names = [q["name"] for q in st.session_state.preguntas]
        labels_by_name = {q["name"]: q["label"] for q in st.session_state.preguntas}

        src2 = st.selectbox("Condición basada en", options=names,
                            format_func=lambda n: f"{n} — {labels_by_name[n]}",
                            key="final_src")
        op2 = st.selectbox("Operador", options=["=", "selected", "!="], key="final_op")
        src2_q = next((qq for qq in st.session_state.preguntas if qq["name"] == src2), None)

        vals2 = []
        if src2_q and src2_q.get("opciones"):
            vals2 = st.multiselect("Valores (slug interno)", options=src2_q["opciones"], key="final_vals")
            vals2 = [slugify_name(v) for v in vals2]
        else:
            manual2 = st.text_input("Valor (si no hay opciones)", key="final_manual")
            vals2 = [slugify_name(manual2)] if manual2.strip() else []

        if st.button("➕ Agregar regla de finalización", key="btn_add_fin"):
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
# Construcción XLSForm
# ------------------------------------------------------------------------------------------
def construir_xlsform(preguntas, form_title: str, idioma: str, version: str,
                      reglas_vis, reglas_fin):
    survey_rows = []
    choices_rows = []
    choices_keys = set()

    def _choices_add_unique(row: Dict):
        key = (row.get("list_name"), row.get("name"))
        if key not in choices_keys:
            choices_rows.append(row)
            choices_keys.add(key)

    idx_by_name = {q.get("name"): i for i, q in enumerate(preguntas)}

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

    def add_q(q, idx):
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

        # Restricción para años de servicio (0–50)
        if q.get("name") == "anios_servicio":
            row["constraint"] = ". >= 0 and . <= 50"
            row["constraint_message"] = "Ingrese un valor entre 0 y 50."

        survey_rows.append(row)

        # Choices
        if list_name:
            usados = set()
            for opt_label in (q.get("opciones") or []):
                base = slugify_name(opt_label)
                opt_name = asegurar_nombre_unico(base, usados)
                usados.add(opt_name)
                _choices_add_unique({"list_name": list_name, "name": opt_name, "label": str(opt_label)})

    # --------------------------------------------------------------------------------------
    # Página 1: Intro
    # --------------------------------------------------------------------------------------
    survey_rows += [
        {"type": "begin_group", "name": "p1_intro", "label": "Introducción", "appearance": "field-list"},
        {"type": "note", "name": "intro_logo", "label": form_title, "media::image": _get_logo_media_name()},
        {"type": "note", "name": "intro_texto", "label": INTRO_POLICIAL_2026},
        {"type": "end_group", "name": "p1_end"},
    ]

    # --------------------------------------------------------------------------------------
    # Página 2: Consentimiento
    # --------------------------------------------------------------------------------------
    idx_consent = idx_by_name.get("consentimiento", None)
    survey_rows.append({"type": "begin_group", "name": "p2_consentimiento", "label": "Consentimiento informado", "appearance": "field-list"})
    survey_rows.append({"type": "note", "name": "cons_title", "label": CONSENTIMIENTO_TITULO})
    for i, txt in enumerate(CONSENTIMIENTO_BLOQUES, start=1):
        survey_rows.append({"type": "note", "name": f"cons_b{i:02d}", "label": txt})
    if idx_consent is not None:
        add_q(preguntas[idx_consent], idx_consent)
    survey_rows.append({"type": "end_group", "name": "p2_consentimiento_end"})

    # Página final si NO acepta
    survey_rows.append({
        "type": "begin_group",
        "name": "p_fin_no",
        "label": "Finalización",
        "appearance": "field-list",
        "relevant": f"${{consentimiento}}='{CONSENT_NO}'"
    })
    survey_rows.append({
        "type": "note",
        "name": "fin_no_texto",
        "label": "Gracias. Al no aceptar participar, la encuesta finaliza en este punto."
    })
    survey_rows.append({"type": "end_group", "name": "p_fin_no_end"})

    # Desde aquí, todo SOLO si consentimiento = Sí
    rel_si = f"${{consentimiento}}='{CONSENT_SI}'"

    # --------------------------------------------------------------------------------------
    # Sets por página
    # --------------------------------------------------------------------------------------
    p_datos_generales = {
        "anios_servicio", "edad_rango", "genero", "escolaridad",
        "clase_policial", "funcion_principal", "funcion_principal_otro"
    }

    p_interes_policial = {
        "presencia_ilicita",
        "estructura_nombre_publico",
        "actividades_delictivas_identificadas", "actividades_delictivas_otro",
        "quienes_actos_criminales",
        "modo_operar_estructura",
        "zona_mayor_inseguridad",
        "condiciones_riesgo_zona",
    }

    p_interes_interno = {
        "recursos_necesarios",
        "condiciones_basicas_ok", "condiciones_mejorar",
        "falta_capacitacion", "areas_capacitacion",
        "entorno_motivacion", "motivo_motivacion",
        "situaciones_internas", "desc_situaciones_internas",
        "oficiales_relacion_crimen", "desc_oficiales_relacion",
        "contacto_voluntario",
        "info_adicional",
    }

    # --------------------------------------------------------------------------------------
    # Helper páginas
    # --------------------------------------------------------------------------------------
    def add_page(group_name, page_label, names_set, intro_note_text: str = None,
                 group_appearance: str = "field-list", group_relevant: str = None,
                 extra_notes: List[Dict] = None):
        row = {"type": "begin_group", "name": group_name, "label": page_label, "appearance": group_appearance}
        if group_relevant:
            row["relevant"] = group_relevant
        survey_rows.append(row)

        if intro_note_text:
            note = {"type": "note", "name": f"{group_name}_intro", "label": intro_note_text}
            if group_relevant:
                note["relevant"] = group_relevant
            survey_rows.append(note)

        if extra_notes:
            for nn in extra_notes:
                nrow = dict(nn)
                if group_relevant and "relevant" not in nrow:
                    nrow["relevant"] = group_relevant
                survey_rows.append(nrow)

        for i, qq in enumerate(preguntas):
            if qq["name"] in names_set:
                add_q(qq, i)

        survey_rows.append({"type": "end_group", "name": f"{group_name}_end"})

    # --------------------------------------------------------------------------------------
    # P3 Datos generales
    # --------------------------------------------------------------------------------------
    add_page(
        "p3_datos_generales",
        "Datos generales",
        p_datos_generales,
        intro_note_text=INTRO_DATOS_GENERALES,
        group_appearance="field-list",
        group_relevant=rel_si
    )

    # --------------------------------------------------------------------------------------
    # P4 Información de interés policial (con NOTA previa repetida en 6.1, 6.3, 6.4 como en tus imágenes)
    # --------------------------------------------------------------------------------------
    nota_previa_confidencial = {
        "type": "note",
        "name": "nota_previa_confidencial",
        "label": "Nota previa: La información solicitada en los siguientes apartados es de carácter confidencial, para uso institucional y análisis preventivo. No constituye denuncia formal.",
        "relevant": f"{rel_si} and ${{presencia_ilicita}}='{slugify_name('Sí')}'"
    }

    add_page(
        "p4_interes_policial",
        "Información de interés policial",
        p_interes_policial,
        intro_note_text=INTRO_INTERES_POLICIAL,
        group_appearance="field-list",
        group_relevant=rel_si,
        extra_notes=[nota_previa_confidencial]
    )

    # --------------------------------------------------------------------------------------
    # P5 Información de interés interno
    # --------------------------------------------------------------------------------------
    add_page(
        "p5_interes_interno",
        "Información de interés interno",
        p_interes_interno,
        intro_note_text=INTRO_INTERES_INTERNO,
        group_appearance="field-list",
        group_relevant=rel_si
    )

    # --------------------------------------------------------------------------------------
    # DataFrames
    # --------------------------------------------------------------------------------------
    survey_cols_all = set().union(*[r.keys() for r in survey_rows])
    survey_cols = [c for c in [
        "type", "name", "label", "required", "appearance", "choice_filter",
        "relevant", "constraint", "constraint_message", "media::image"
    ] if c in survey_cols_all]
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
        "style": "pages",
    }], columns=["form_title", "version", "default_language", "style"])

    return df_survey, df_choices, df_settings

# ------------------------------------------------------------------------------------------
# Exportar a XLSForm (Excel) + Vista previa
# ------------------------------------------------------------------------------------------
st.markdown("---")
st.subheader("📤 Exportar XLSForm (Survey123)")

df_survey, df_choices, df_settings = construir_xlsform(
    preguntas=st.session_state.preguntas,
    form_title=titulo_compuesto,
    idioma=idioma,
    version=version,
    reglas_vis=st.session_state.reglas_visibilidad,
    reglas_fin=st.session_state.reglas_finalizar
)

with st.expander("👀 Vista previa (survey / choices / settings)", expanded=False):
    st.caption("Estas son las hojas que se exportarán al XLSForm.")
    st.markdown("**survey**")
    st.dataframe(df_survey, use_container_width=True, hide_index=True, height=260)
    st.markdown("**choices**")
    st.dataframe(df_choices, use_container_width=True, hide_index=True, height=260)
    st.markdown("**settings**")
    st.dataframe(df_settings, use_container_width=True, hide_index=True, height=120)

def _to_excel_bytes(df_survey: pd.DataFrame, df_choices: pd.DataFrame, df_settings: pd.DataFrame) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_survey.to_excel(writer, sheet_name="survey", index=False)
        df_choices.to_excel(writer, sheet_name="choices", index=False)
        df_settings.to_excel(writer, sheet_name="settings", index=False)
    output.seek(0)
    return output.getvalue()

xls_bytes = _to_excel_bytes(df_survey, df_choices, df_settings)
safe_deleg = slugify_name(delegacion or "delegacion")
file_name = f"xlsform_encuesta_policial_{safe_deleg}.xlsx"

st.download_button(
    "⬇️ Descargar XLSForm (Excel)",
    data=xls_bytes,
    file_name=file_name,
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True
)

st.info(
    "📌 Recordatorio Survey123: coloca el archivo del logo (por ejemplo, "
    f"**{_get_logo_media_name()}**) dentro de la carpeta **media/** del proyecto en Survey123 Connect."
)






