# -*- coding: utf-8 -*-
# ==========================================================================================
# App: Encuesta FUERZA PÚBLICA → XLSForm para ArcGIS Survey123 (versión extendida)
# - MISMA UI y funcionalidades de tu app anterior (constructor, qid estable, JSON, XLSForm)
# - POR AHORA SOLO 3 páginas:
#     P1 Intro (texto FP 2026 EXACTO)
#     P2 Consentimiento (MISMO texto por bloques + finaliza si NO)
#     P3 Datos generales (título + intro EXACTO + preguntas base editables)
#
# ✅ CORRECCIÓN SOLICITADA:
# - NO lleva Cantón/Distrito
# - NO lleva catálogo por lotes ni choice_filter ni placeholders
# - Solo se usa el campo "Nombre del lugar / Delegación" del encabezado
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
st.set_page_config(page_title="Encuesta Fuerza Pública → XLSForm (Survey123)", layout="wide")
st.title("🚔 Encuesta Fuerza Pública → XLSForm para ArcGIS Survey123")

st.markdown("""
Crea tu cuestionario y **exporta un XLSForm** listo para **ArcGIS Survey123**.

Incluye:
- Tipos: **text**, **integer**, **date**, **time**, **geopoint**, **select_one**, **select_multiple**.
- **Constructor completo** (agregar, editar, ordenar, borrar) con condicionales.
- **Páginas** con navegación **Siguiente/Anterior** (`settings.style = pages`).
- **Portada** con **logo** (`media::image`) e **introducción**.
- **Consentimiento informado** (si NO acepta, la encuesta termina) con texto ordenado por bloques.
- **Exportar/Importar proyecto (JSON)**.
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
# FIX REFLEJO DE EDICIÓN: ID estable por pregunta (qid)
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
if "textos_fijos" not in st.session_state:
    st.session_state.textos_fijos = {}
if "edit_qid" not in st.session_state:
    st.session_state.edit_qid = None

# ------------------------------------------------------------------------------------------
# Cabecera: Logo + Delegación
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
    delegacion = st.text_input("Nombre del lugar / Delegación", value="Alajuela Norte", key="delegacion_txt")
    logo_media_name = st.text_input(
        "Nombre de archivo para `media::image`",
        value=st.session_state.get("_logo_name", "001.png"),
        help="Debe coincidir con el archivo en `media/` de Survey123 Connect.",
        key="logo_media_txt"
    )
    titulo_compuesto = (f"Encuesta Fuerza Pública – {delegacion.strip()}" if delegacion.strip() else "Encuesta Fuerza Pública")
    st.markdown(f"<h5 style='text-align:center;margin:4px 0'>📋 {titulo_compuesto}</h5>", unsafe_allow_html=True)

# ------------------------------------------------------------------------------------------
# Textos base (Intro FP + Datos Generales) + Consentimiento
# ------------------------------------------------------------------------------------------
INTRO_FP = (
    "El presente formato corresponde a la Encuesta Policial de Percepción Institucional 2026, dirigida al personal de la Fuerza Pública, "
    "y orientada a recopilar información relevante desde la experiencia operativa y territorial del funcionariado policial, en relación con "
    "la seguridad, la convivencia y los factores de riesgo presentes en las distintas jurisdicciones del país. "
    "El instrumento incorpora la percepción del personal sobre condiciones institucionales que inciden en la prestación del servicio policial, "
    "tales como el entorno operativo de la delegación, la disponibilidad de recursos, las necesidades de capacitación y el entorno institucional "
    "que favorece la motivación para la atención a la ciudadanía. "
    "La información recopilada servirá como insumo para el análisis institucional, la planificación preventiva y la mejora continua del servicio policial. "
    "El documento se remite para su revisión y validación técnica, con el fin de asegurar su coherencia metodológica, normativa y operativa, previo a su aplicación en territorio."
)

DATOS_GENERALES_INTRO = (
    "Datos generales\n\n"
    "“Esta encuesta busca recopilar información desde la experiencia del personal de la Fuerza Pública para apoyar la planificación preventiva y la mejora del servicio policial.”"
)

CONSENTIMIENTO_TITULO = "Consentimiento Informado para la Participación en la Encuesta"
CONSENT_SI = slugify_name("Sí")
CONSENT_NO = slugify_name("No")

CONSENTIMIENTO_BLOQUES = [
    "Usted está siendo invitado(a) a participar de forma libre y voluntaria en una encuesta sobre seguridad, convivencia y percepción ciudadana, dirigida a personas mayores de 18 años.",
    "El objetivo de esta encuesta es recopilar información de carácter preventivo y estadístico, con el fin de apoyar la planificación de acciones de prevención, mejora de la convivencia y fortalecimiento de la seguridad en comunidades y zonas comerciales.",
    "La participación es totalmente voluntaria. Usted puede negarse a responder cualquier pregunta, así como retirarse de la encuesta en cualquier momento, sin que ello genere consecuencia alguna.",
    "De conformidad con lo dispuesto en el artículo 5 de la Ley N.º 8968 (Protección de la Persona frente al Tratamiento de sus Datos Personales), se le informa que:",
    "Finalidad del tratamiento: La información recopilada será utilizada exclusivamente para fines estadísticos, analíticos y preventivos, y no para investigaciones penales, procesos judiciales, sanciones administrativas ni procedimientos disciplinarios.",
    "Datos personales: Algunos apartados permiten, de forma voluntaria, el suministro de datos personales o información de contacto.",
    "Tratamiento de los datos: Los datos serán almacenados, analizados y resguardados bajo criterios de confidencialidad y seguridad, conforme a la normativa vigente.",
    "Destinatarios y acceso: La información será conocida únicamente por el personal autorizado de la Fuerza Pública / Ministerio de Seguridad Pública, para los fines indicados. No será cedida a terceros ajenos a estos fines.",
    "Responsable de la base de datos: El Ministerio de Seguridad Pública, a través de la Dirección de Programas Policiales Preventivos, Oficina Estrategia Integral de Prevención para la Seguridad Pública (EIPESP / Estrategia Sembremos Seguridad), será responsable del tratamiento y custodia de la información recolectada.",
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
        value=(f"Encuesta Fuerza Pública – {delegacion.strip()}" if delegacion.strip() else "Encuesta Fuerza Pública"),
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
            "textos_fijos": st.session_state.textos_fijos,
        }
        jbuf = BytesIO(json.dumps(proj, ensure_ascii=False, indent=2).encode("utf-8"))
        st.download_button(
            "Descargar JSON",
            data=jbuf,
            file_name="proyecto_encuesta_fp_2026.json",
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
            st.session_state.textos_fijos = dict(data.get("textos_fijos", st.session_state.textos_fijos))

            st.session_state.edit_qid = None
            _rerun()
        except Exception as e:
            st.error(f"No se pudo importar el JSON: {e}")

# ------------------------------------------------------------------------------------------
# SEED base (sin Cantón/Distrito)
# ------------------------------------------------------------------------------------------
if "seed_cargado" not in st.session_state:
    seed = [
        # ---------------- Consentimiento ----------------
        {"tipo_ui": "Selección única",
         "label": "¿Acepta participar en esta encuesta?",
         "name": "consentimiento",
         "required": True,
         "opciones": ["Sí", "No"],
         "appearance": "horizontal",
         "choice_filter": None,
         "relevant": None},

        # ---------------- Datos generales ----------------
        {"tipo_ui": "Número",
         "label": "1. Años de servicio (años completos):",
         "name": "anos_servicio",
         "required": True,
         "opciones": [],
         "appearance": None,
         "choice_filter": None,
         "relevant": None},

        {"tipo_ui": "Selección única",
         "label": "2. Edad (en años cumplidos): marque una categoría que incluya su edad.",
         "name": "edad_rango",
         "required": True,
         "opciones": ["18 a 29 años", "30 a 44 años", "45 a 59 años", "60 años o más"],
         "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección única",
         "label": "3. ¿Con cuál de estas opciones se identifica?",
         "name": "identidad_genero",
         "required": True,
         "opciones": ["Femenino", "Masculino", "Persona no Binaria", "Prefiero no decir"],
         "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección única",
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
         "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección única",
         "label": "5. ¿Cuál es su clase policial que desempeña en su delegación?",
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
             "Otro",
         ],
         "appearance": "columns", "choice_filter": None, "relevant": None},

        {"tipo_ui": "Texto (corto)",
         "label": "Indique cuál es esa otra clase policial:",
         "name": "clase_policial_otro",
         "required": True,
         "opciones": [],
         "appearance": None,
         "choice_filter": None,
         "relevant": f"${{clase_policial}}='{slugify_name('Otro')}'"},

        {"tipo_ui": "Selección única",
         "label": "6. ¿Cuál es la función principal que desempeña actualmente en la delegación?",
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
         "appearance": "columns", "choice_filter": None, "relevant": None},

        {"tipo_ui": "Texto (corto)",
         "label": "Indique cuál es esa otra función:",
         "name": "funcion_principal_otro",
         "required": True,
         "opciones": [],
         "appearance": None,
         "choice_filter": None,
         "relevant": f"${{funcion_principal}}='{slugify_name('Otra función')}'"},
    ]

    st.session_state.preguntas = [ensure_qid(q) for q in seed]
    st.session_state.seed_cargado = True

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
# Lista / Ordenado / Edición (qid estable)
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
# Condicionales (panel)
# ------------------------------------------------------------------------------------------
st.subheader("🔀 Condicionales (mostrar / finalizar)")
if not st.session_state.preguntas:
    st.info("Agrega preguntas para definir condicionales.")
else:
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
# Helper logo
# ------------------------------------------------------------------------------------------
def _get_logo_media_name():
    try:
        return st.session_state.get("_logo_name") or st.session_state.get("logo_media_txt") or "001.png"
    except Exception:
        return "001.png"

# ------------------------------------------------------------------------------------------
# Construir XLSForm (3 páginas)
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

    def _aplicar_exclusividad_no_observa(row: Dict, q: Dict):
        if q.get("tipo_ui") != "Selección múltiple":
            return
        opts = q.get("opciones") or []
        if not opts:
            return

        exclusivas = [o for o in opts if str(o).strip().lower().startswith("no se observa")]
        if not exclusivas:
            exclusivas = [o for o in opts if str(o).strip().lower().startswith("no se observan")]
        if not exclusivas:
            return

        ex_label = exclusivas[0]
        ex_slug = slugify_name(ex_label)
        nm = q["name"]

        row["constraint"] = f"not(selected(${{{nm}}}, '{ex_slug}') and count-selected(${{{nm}}})>1)"
        row["constraint_message"] = f"Si selecciona “{ex_label}”, no puede marcar otras opciones."

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

        _aplicar_exclusividad_no_observa(row, q)
        survey_rows.append(row)

        if list_name:
            usados = set()
            for opt_label in (q.get("opciones") or []):
                base = slugify_name(opt_label)
                opt_name = asegurar_nombre_unico(base, usados)
                usados.add(opt_name)
                _choices_add_unique({"list_name": list_name, "name": opt_name, "label": str(opt_label)})

    # P1 Intro
    survey_rows += [
        {"type": "begin_group", "name": "p1_intro", "label": "Introducción", "appearance": "field-list"},
        {"type": "note", "name": "intro_logo", "label": form_title, "media::image": _get_logo_media_name()},
        {"type": "note", "name": "intro_texto", "label": INTRO_FP},
        {"type": "end_group", "name": "p1_end"},
    ]

    # P2 Consentimiento
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

    rel_si = f"${{consentimiento}}='{CONSENT_SI}'"

    # P3 Datos generales
    survey_rows.append({
        "type": "begin_group",
        "name": "p3_datos_generales",
        "label": "Datos generales",
        "appearance": "field-list",
        "relevant": rel_si
    })
    survey_rows.append({
        "type": "note",
        "name": "p3_intro",
        "label": DATOS_GENERALES_INTRO,
        "relevant": rel_si
    })

    for i, qq in enumerate(preguntas):
        if qq.get("name") == "consentimiento":
            continue
        if not qq.get("relevant"):
            qq["relevant"] = rel_si
        else:
            qq["relevant"] = f"({rel_si}) and ({qq['relevant']})"
        add_q(qq, i)

    survey_rows.append({"type": "end_group", "name": "p3_datos_generales_end"})

    # DataFrames
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
# Exportar XLSForm + Vista previa
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

safe_deleg = slugify_name(delegacion or "fp")
file_name = f"xlsform_encuesta_fp_{safe_deleg}.xlsx"

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
