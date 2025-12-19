# -*- coding: utf-8 -*-
# ==========================================================================================
# App: Constructor de Encuestas → XLSForm para ArcGIS Survey123 (versión extendida)
# ✅ FIX: HINT + GUIDANCE_HINT (ayuda por ícono)  [NO hover]
# - Survey123 NO soporta tooltip por hover estándar.
# - Para ver la definición "oculta", Survey123 requiere guidance_hint + (idealmente) hint.
# - En Web/Field App la ayuda se ve al tocar el ícono de ayuda / panel de ayuda.
#
# Incluye:
# - Constructor completo (agregar/editar/ordenar/borrar)
# - Condicionales (relevant) + Finalizar temprano
# - Listas en cascada (choice_filter)
# - Exportar/Importar proyecto (JSON)
# - Exportar a XLSForm (survey/choices/settings)
# - PÁGINAS reales (Next/Back) con settings.style = "pages"
# - Introducción con logo (media::image) y texto (NOTE)
# - Seed Fuerza Pública EXACTO + subopciones corregidas
# - Exportar Word + PDF editable (con opciones y ayudas impresas)
# ==========================================================================================

import re
import json
from io import BytesIO
from datetime import datetime

import streamlit as st
import pandas as pd

# ==========================================================================================
# Configuración de la app
# ==========================================================================================
st.set_page_config(page_title="Constructor de Encuestas → XLSForm (Survey123)", layout="wide")
st.title("🧩 Constructor de Encuestas → XLSForm para ArcGIS Survey123")

st.markdown("""
Crea tu cuestionario y **exporta un XLSForm** listo para **ArcGIS Survey123 (Connect/Web Designer)**.

Incluye:
- Tipos: **text**, **integer/decimal**, **date**, **time**, **geopoint**, **select_one**, **select_multiple**.
- **Constructor completo** (agregar, editar, ordenar, borrar).
- **Condicionales (relevant)** y **finalizar temprano**.
- **Listas en cascada** con **choice_filter** (ejemplo Cantón→Distrito).
- **Páginas** con navegación **Siguiente/Anterior** (`settings.style = pages`).
- **Introducción** con **logo** usando `media::image`.
- ✅ **Definiciones/ayuda ocultas** con `guidance_hint` (se ven al tocar el ícono de ayuda).
""")

# ==========================================================================================
# Utilidades / Helpers
# ==========================================================================================
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
    """Compatibilidad para versiones de Streamlit."""
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()

def slugify_name(texto: str) -> str:
    """Convierte a un slug (válido para XLSForm 'name' y 'choice name')."""
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
    """Evita duplicados en 'name'."""
    if base not in usados:
        return base
    i = 2
    while f"{base}_{i}" in usados:
        i += 1
    return f"{base}_{i}"

def map_tipo_to_xlsform(tipo_ui: str, name: str):
    """Mapeo UI → tipo XLSForm + list_name (si aplica) + appearance por defecto."""
    if tipo_ui == "Texto (corto)":
        return ("text", None, None)
    if tipo_ui == "Párrafo (texto largo)":
        return ("text", "multiline", None)
    if tipo_ui == "Número":
        return ("integer", None, None)  # cambia a 'decimal' si requieres decimales
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
    """Combina condiciones en formato XLSForm con OR ( )"""
    if not conds:
        return None
    if len(conds) == 1:
        return conds[0]
    return "(" + " or ".join(conds) + ")"

def xlsform_not(expr):
    """Negación de una expresión XLSForm."""
    if not expr:
        return None
    return f"not({expr})"

def build_relevant_expr(rules_for_target):
    """
    rules_for_target: lista de condiciones (cada una puede equivaler a 1..N opciones)
      Ej: [{"src":"canton","op":"=","values":["alajuela"]}, ...]
    Devuelve una expresión XLSForm para 'relevant'
    (usa OR cuando hay varios valores).
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
            or_parts.append(xlsform_or_expr(segs))
        elif op == "selected":
            segs = [f"selected(${{{src}}}, '{v}')" for v in vals]
            or_parts.append(xlsform_or_expr(segs))
        elif op == "!=":
            segs = [f"${{{src}}}!='{v}'" for v in vals]
            or_parts.append(xlsform_or_expr(segs))
        else:
            segs = [f"${{{src}}}='{v}'" for v in vals]
            or_parts.append(xlsform_or_expr(segs))
    return xlsform_or_expr(or_parts)

# ==========================================================================================
# Cabecera: Logo + “Nombre de la Delegación” → form_title compuesto
# ==========================================================================================
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
    delegacion = st.text_input("Nombre de la Delegación", value="San Carlos Oeste")
    logo_media_name = st.text_input(
        "Nombre de archivo para `media::image`",
        value=st.session_state.get("_logo_name", "001.png"),
        help="Debe coincidir con el archivo que copiarás en la carpeta `media/` de Survey123 Connect."
    )
    titulo_compuesto = f"Encuesta Fuerza Pública – Delegación {delegacion.strip()}" if delegacion.strip() else "Encuesta Fuerza Pública"
    st.markdown(f"<h5 style='text-align:center;margin:4px 0'>📋 {titulo_compuesto}</h5>", unsafe_allow_html=True)

# ==========================================================================================
# Estado (session_state)
# ==========================================================================================
if "preguntas" not in st.session_state:
    st.session_state.preguntas = []

if "reglas_visibilidad" not in st.session_state:
    st.session_state.reglas_visibilidad = []

if "reglas_finalizar" not in st.session_state:
    st.session_state.reglas_finalizar = []

if "choices_extra_cols" not in st.session_state:
    st.session_state.choices_extra_cols = set()

# ==========================================================================================
# SEED: Precarga de preguntas EXACTAS (Fuerza Pública) + condicionales corregidas
# ✅ Incluye ejemplo real de ayuda oculta (hint + guidance_hint) en 3 preguntas:
# - zona_insegura, por_que_insegura, condiciones_aptas
# ==========================================================================================
if "seed_cargado" not in st.session_state:

    v_si = slugify_name("Si")
    v_no = slugify_name("No")
    v_agente_ii = slugify_name("Agente II")
    v_sub_of_i  = slugify_name("Sub Oficial I")
    v_sub_of_ii = slugify_name("Sub Oficial II")
    v_oficial_i = slugify_name("Oficial I")

    seed = [
        # ================== Página 2: Datos ==================
        {"tipo_ui":"Número","label":"Años de servicio ","name":"anos_servicio","required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":None,"hint":None,"guidance_hint":None},
        {"tipo_ui":"Número","label":"Edad","name":"edad","required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":None,"hint":None,"guidance_hint":None},
        {"tipo_ui":"Selección única","label":"Genero","name":"genero","required":True,"opciones":["Masculino","Femenino","LGBTQ+"],"appearance":None,"choice_filter":None,"relevant":None,"hint":None,"guidance_hint":None},
        {"tipo_ui":"Selección única","label":"Escolaridad","name":"escolaridad","required":True,
         "opciones":["Ninguna","Primaria","Primaria Incompleta","Secundaria","Secundaria Incompleta","Universidad Completa","Universidad Incompleta","Técnico"],
         "appearance":None,"choice_filter":None,"relevant":None,"hint":None,"guidance_hint":None},
        {"tipo_ui":"Selección única","label":"¿Qué clase del manual de puestos desempeña en su delegación?","name":"manual_puesto","required":True,
         "opciones":["Agente I","Agente II","Sub Oficial I","Sub Oficial II","Oficial I","Jefe de Delegación","Sub Jefe de Delegación"],
         "appearance":None,"choice_filter":None,"relevant":None,
         "hint":"Toque el ícono de ayuda",
         "guidance_hint":"Seleccione la clase del Manual de Puestos que corresponde a su función actual en la delegación."},

        {"tipo_ui":"Selección única","label":"Agente II","name":"agente_ii","required":False,
         "opciones":["Agente de Fronteras","Agente de Seguridad Turistica","Agente de Programas Preventivos","Agente de comunicaciones","Agente Armero","Agente Conductor de Vehículos Oficiales","Agente de Operaciones"],
         "appearance":None,"choice_filter":None,"relevant":f"${{manual_puesto}}='{v_agente_ii}'","hint":None,"guidance_hint":None},

        {"tipo_ui":"Selección única","label":"Sub Oficial I","name":"sub_oficial_i","required":False,
         "opciones":["Encargado Equipo Operativo Policial","Encargado Equipo de Seguridad Turística","Encargado Equipo de Fronteras","Encargado Programas Preventivos","Encargado Agentes Armeros","Encargado de Equipo de Comunicaciones"],
         "appearance":None,"choice_filter":None,"relevant":f"${{manual_puesto}}='{v_sub_of_i}'","hint":None,"guidance_hint":None},

        {"tipo_ui":"Selección única","label":"Sub Oficial II","name":"sub_oficial_ii","required":False,
         "opciones":["Encargado Subgrupo Operativo Policial","Encargado Subgrupo de Seguridad Turística","Encargado Subgrupo de Fronteras","Oficial de Guardia","Encargado de Operaciones"],
         "appearance":None,"choice_filter":None,"relevant":f"${{manual_puesto}}='{v_sub_of_ii}'","hint":None,"guidance_hint":None},

        {"tipo_ui":"Selección única","label":"Oficial I","name":"oficial_i","required":False,
         "opciones":["Jefe Delegación Distrital","Encargado Grupo Operativo Policial"],
         "appearance":None,"choice_filter":None,"relevant":f"${{manual_puesto}}='{v_oficial_i}'","hint":None,"guidance_hint":None},

        # ================== Página 3: Información de Interés Policial ==================
        {"tipo_ui":"Selección única","label":"¿Mantiene usted información relacionada a personas, grupos de personas, objetivos reincidentes, objetivos de interés policial o estructuras criminales que se dediquen a realizar actos ilícitos en su jurisdicción?","name":"mantiene_info","required":True,"opciones":["Si","No"],"appearance":None,"choice_filter":None,"relevant":None,"hint":None,"guidance_hint":None},

        {"tipo_ui":"Selección múltiple","label":"¿Qué tipo de actividad delictual es la que se realiza por parte de estas personas?","name":"tipo_actividad","required":True,
         "opciones":["Bunker(espacio cerrado para la venta y distribucion de drogas)","Delitos contra la vida (Homicidios, heridos)","Venta y consumo de drogas en vía pública","Delitos sexuales","Asalto (a personas, comercio, vivienda, transporte público)","Daños a la propiedad. (Destruir, inutilizar o desaparecer)","Estafas (Billetes, documentos, oro, lotería falsos)","Estafa Informática (computadora, tarjetas, teléfonos, etc.)","Extorsión (intimidar o amenazar a otras personas con fines de lucro)","Hurto","Receptación (persona que adquiere, recibe u oculta artículos provenientes de un delito en el que no participó)","Robo a edificaciones","Robo a vivienda","Robo de ganado y agrícola","Robo a comercio","Robo de vehículos","Tacha de vehículos","Contrabando (licor, cigarrillos, medicinas, ropa, calzado, etc.)","Tráfico ilegal de personas (coyotaje)","Otro"],
         "appearance":None,"choice_filter":None,"relevant":f"${{mantiene_info}}='{v_si}'","hint":None,"guidance_hint":None},

        {"tipo_ui":"Texto (corto)","label":"¿Cuál es el nombre de la estructura criminal?","name":"nombre_estructura","required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":f"${{mantiene_info}}='{v_si}'","hint":None,"guidance_hint":None},

        {"tipo_ui":"Párrafo (texto largo)","label":"Indique quién o quienes se dedican a estos actos criminales.(nombres, apellidos, alias, dominicilio)","name":"quienes","required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":f"${{mantiene_info}}='{v_si}'","hint":None,"guidance_hint":None},

        {"tipo_ui":"Párrafo (texto largo)","label":"Modo de operar de esta estructura criminal (por ejemplo: venta de droga expres o en via publica, asalto a mano armada, modo de desplazamiento, etc.)","name":"modus_operandi","required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":f"${{mantiene_info}}='{v_si}'","hint":None,"guidance_hint":None},

        # ✅ Aquí la ayuda oculta que querías (sin mostrarse como texto largo fijo)
        {"tipo_ui":"Texto (corto)","label":"¿Cuál es el lugar o zona que usted considera más inseguro dentro de su area de responsabilidad?","name":"zona_insegura","required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":None,
         "hint":"Toque el ícono de ayuda",
         "guidance_hint":"Zona = área amplia (barrio/sector). Lugar = punto específico (parada, parque, comercio, esquina)."},

        {"tipo_ui":"Párrafo (texto largo)","label":"Describa por qué considera que esa zona es insegura","name":"por_que_insegura","required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":None,
         "hint":"Toque el ícono de ayuda",
         "guidance_hint":"Explique qué pasa ahí: tipo de delito o problema, horarios, frecuencia, actores, condiciones (iluminación, lotes baldíos, paradas, comercios, etc.)."},

        # ================== Página 4: Información de Interés Interno ==================
        {"tipo_ui":"Párrafo (texto largo)","label":"¿Qué recurso cree usted que hacen falta en su delegación para brindar una mejor labor al servicio a la ciudadanía?","name":"recurso_falta","required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":None,"hint":None,"guidance_hint":None},

        {"tipo_ui":"Selección única","label":"¿Considera usted que las condiciones de su delegación son aptas para satisfacer sus necesidades básicas? (buen dormir, alimentación, recurso móvil, etc.)","name":"condiciones_aptas","required":True,"opciones":["Si","No"],"appearance":None,"choice_filter":None,"relevant":None,
         "hint":"Toque el ícono de ayuda",
         "guidance_hint":"Considere: descanso, alimentación, higiene, espacio, equipo mínimo y movilidad (recurso móvil). Responda según su realidad actual."},

        {"tipo_ui":"Párrafo (texto largo)","label":"Cúales condiciones considera que se pueden mejorar.","name":"condiciones_mejorar","required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":f"${{condiciones_aptas}}='{v_no}'","hint":None,"guidance_hint":None},

        {"tipo_ui":"Selección única","label":"¿Considera usted que hace falta capacitación para el personal en su delegacion policial?","name":"falta_capacitacion","required":True,"opciones":["Si","No"],"appearance":None,"choice_filter":None,"relevant":None,"hint":None,"guidance_hint":None},

        {"tipo_ui":"Párrafo (texto largo)","label":"Especifique en que áreas necesita capacitación","name":"areas_capacitacion","required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":f"${{falta_capacitacion}}='{v_si}'","hint":None,"guidance_hint":None},

        {"tipo_ui":"Selección única","label":"¿Se siente usted motivado por la institución para brindar un buen servicio a la ciudadanía?","name":"motivado","required":True,"opciones":["Si","No"],"appearance":None,"choice_filter":None,"relevant":None,"hint":None,"guidance_hint":None},

        {"tipo_ui":"Párrafo (texto largo)","label":"Especifique por qué lo considera así.","name":"motivo_no","required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":f"${{motivado}}='{v_no}'","hint":None,"guidance_hint":None},

        {"tipo_ui":"Selección única","label":"¿Mantiene usted conocimiento de situaciones anómalas que sucedan en su delegación? (Recuerde la información suministrada es de carácter confidencial)*","name":"anomalias","required":True,"opciones":["Si","No"],"appearance":None,"choice_filter":None,"relevant":None,"hint":None,"guidance_hint":None},

        {"tipo_ui":"Párrafo (texto largo)","label":"Especifique cuáles son las situaciones anómalas que se refiere","name":"detalle_anomalias","required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":f"${{anomalias}}='{v_si}'","hint":None,"guidance_hint":None},

        {"tipo_ui":"Selección única","label":"¿Conoce oficiales de Fuerza Pública que se relacionen con alguna estructura criminal o cometan algún delito?","name":"oficiales_relacionados","required":True,"opciones":["Si","No"],"appearance":None,"choice_filter":None,"relevant":None,"hint":None,"guidance_hint":None},

        {"tipo_ui":"Párrafo (texto largo)","label":"Describa la situación de la cual tiene conocimiento. (aporte nombre de la estructura, tipo de actividad, nombre de oficiales, función del oficial dentro de la organización, alias, etc.)","name":"describe_situacion","required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":f"${{oficiales_relacionados}}='{v_si}'","hint":None,"guidance_hint":None},

        {"tipo_ui":"Texto (corto)","label":"Desea, de manera voluntaria, dejar un medio de contacto para brindar más información (correo electrónico, número de teléfono, etc.)","name":"medio_contacto","required":False,"opciones":[],"appearance":None,"choice_filter":None,"relevant":None,"hint":None,"guidance_hint":None}
    ]

    st.session_state.preguntas = seed
    st.session_state.seed_cargado = True

# ==========================================================================================
# Sidebar: Metadatos + Acciones rápidas
# ==========================================================================================
with st.sidebar:
    st.header("⚙️ Configuración")

    form_title = st.text_input(
        "Título del formulario",
        value=(f"Encuesta Fuerza Pública – Delegación {delegacion.strip()}"
               if delegacion.strip() else "Encuesta Fuerza Pública")
    )
    idioma = st.selectbox("Idioma por defecto (default_language)", options=["es", "en"], index=0)
    version_auto = datetime.now().strftime("%Y%m%d%H%M")
    version = st.text_input("Versión (settings.version)", value=version_auto)

    st.markdown("---")
    st.caption("🚀 Insertar ejemplo de **listas en cascada** Cantón→Distrito (CR)")

    if st.button("Insertar Cantón→Distrito (ejemplo CR)", use_container_width=True):
        usados = {q["name"] for q in st.session_state.preguntas}
        name_canton = asegurar_nombre_unico("canton", usados)

        st.session_state.preguntas.append({
            "tipo_ui": "Selección única",
            "label": "Seleccione el Cantón",
            "name": name_canton,
            "required": True,
            "opciones": ["Alajuela (Central)", "Sabanilla", "Desamparados"],
            "appearance": None,
            "choice_filter": None,
            "relevant": None,
            "hint": "Toque el ícono de ayuda",
            "guidance_hint": "Primero elija el cantón para filtrar los distritos."
        })

        usados.add(name_canton)
        name_distrito = asegurar_nombre_unico("distrito", usados)

        st.session_state.preguntas.append({
            "tipo_ui": "Selección única",
            "label": "Seleccione el Distrito",
            "name": name_distrito,
            "required": True,
            "opciones": ["— se rellena con la lista extendida —"],
            "appearance": None,
            "choice_filter": f"canton_key=${{{name_canton}}}",
            "relevant": None,
            "hint": "Toque el ícono de ayuda",
            "guidance_hint": "Los distritos se filtran según el cantón seleccionado."
        })

        if "choices_ext_rows" not in st.session_state:
            st.session_state.choices_ext_rows = []
        st.session_state.choices_extra_cols.update({"canton_key"})

        def add_choices(list_name, items, key):
            for lbl in items:
                st.session_state.choices_ext_rows.append({
                    "list_name": list_name,
                    "name": slugify_name(lbl),
                    "label": lbl,
                    "canton_key": key
                })

        list_distrito = f"list_{name_distrito}"
        add_choices(list_distrito,
            ["Alajuela","San José","Carrizal","San Antonio","Guácima","San Isidro","Sabanilla","San Rafael","Río Segundo",
             "Desamparados","Turrúcares","Tambor","Garita","Sarapiquí"], "Alajuela (Central)")
        add_choices(list_distrito, ["Centro","Este","Oeste","Norte","Sur"], "Sabanilla")
        add_choices(list_distrito,
            ["Desamparados","San Miguel","San Juan de Dios","San Rafael Arriba","San Antonio","Frailes","Patarrá",
             "San Cristóbal","Rosario","Damas","San Rafael Abajo","Gravilias","Los Guido"], "Desamparados")

        st.success("Ejemplo Cantón→Distrito insertado.")
        _rerun()

    st.markdown("---")
    st.caption("💾 Exporta/Importa tu proyecto (JSON)")
    col_exp, col_imp = st.columns(2)

    with col_exp:
        if st.button("Exportar proyecto (JSON)", use_container_width=True):
            proj = {
                "form_title": form_title,
                "idioma": idioma,
                "version": version,
                "preguntas": st.session_state.preguntas,
                "reglas_visibilidad": st.session_state.reglas_visibilidad,
                "reglas_finalizar": st.session_state.reglas_finalizar
            }
            jbuf = BytesIO(json.dumps(proj, ensure_ascii=False, indent=2).encode("utf-8"))
            st.download_button("Descargar JSON", data=jbuf, file_name="proyecto_encuesta.json",
                               mime="application/json", use_container_width=True)

    with col_imp:
        up = st.file_uploader("Importar JSON", type=["json"], label_visibility="collapsed")
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

# ==========================================================================================
# Constructor: Agregar nuevas preguntas
# ==========================================================================================
st.subheader("📝 Diseña tus preguntas")

with st.form("form_add_q", clear_on_submit=False):
    tipo_ui = st.selectbox("Tipo de pregunta", options=TIPOS)
    label = st.text_input("Etiqueta (texto exacto)")
    sugerido = slugify_name(label) if label else ""

    col_n1, col_n2, col_n3 = st.columns([2,1,1])
    with col_n1:
        name = st.text_input("Nombre interno (XLSForm 'name')", value=sugerido)
    with col_n2:
        required = st.checkbox("Requerida", value=False)
    with col_n3:
        appearance = st.text_input("Appearance (opcional)", value="")

    # ✅ Nuevos campos para ayuda (XLSForm: hint / guidance_hint)
    hint = st.text_input("Hint (texto corto)", value="")
    guidance_hint = st.text_area("Guidance hint (texto oculto por ícono de ayuda)", height=80)

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
        nueva = {
            "tipo_ui": tipo_ui,
            "label": label.strip(),
            "name": unico,
            "required": required,
            "opciones": opciones,
            "appearance": (appearance.strip() or None),
            "choice_filter": None,
            "relevant": None,
            "hint": (hint.strip() or None),
            "guidance_hint": (guidance_hint.strip() or None)
        }
        st.session_state.preguntas.append(nueva)
        st.success(f"Pregunta agregada: **{label}** (name: `{unico}`)")

# ==========================================================================================
# Panel de Condicionales (mostrar / finalizar)
# ==========================================================================================
st.subheader("🔀 Condicionales (mostrar / finalizar)")

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
        op = st.selectbox("Operador", options=["=", "selected"], help="= para select_one; selected para select_multiple")

        src_q = next((q for q in st.session_state.preguntas if q["name"] == src), None)
        vals = []
        if src_q and src_q["opciones"]:
            vals = st.multiselect("Valores que activan la visibilidad (elige texto; internamente se usa el 'name' slug)", options=src_q["opciones"])
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
                            format_func=lambda n: f"{n} — {labels_by_name[n]}", key="final_src")
        op2 = st.selectbox("Operador", options=["=", "selected", "!="], key="final_op")

        src2_q = next((q for q in st.session_state.preguntas if q["name"] == src2), None)
        vals2 = []
        if src2_q and src2_q["opciones"]:
            vals2 = st.multiselect("Valores que disparan el fin (se usan como 'name' slug)", options=src2_q["opciones"], key="final_vals")
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

# ==========================================================================================
# Lista / Ordenado / Edición (completa)
# ==========================================================================================
st.subheader("📚 Preguntas (ordénalas y edítalas)")

if not st.session_state.preguntas:
    st.info("Aún no has agregado preguntas.")
else:
    for idx, q in enumerate(st.session_state.preguntas):
        with st.container(border=True):
            c1, c2, c3, c4, c5 = st.columns([4, 2, 2, 2, 2])
            c1.markdown(f"**{idx+1}. {q['label']}**")
            meta = f"type: {q['tipo_ui']}  •  name: `{q['name']}`  •  requerida: {'sí' if q['required'] else 'no'}"
            if q.get("appearance"): meta += f"  •  appearance: `{q['appearance']}`"
            if q.get("choice_filter"): meta += f"  •  choice_filter: `{q['choice_filter']}`"
            if q.get("relevant"): meta += f"  •  relevant: `{q['relevant']}`"
            if q.get("hint"): meta += f"  •  hint: `{q['hint']}`"
            if q.get("guidance_hint"): meta += "  •  guidance_hint: ✅"
            c1.caption(meta)

            if q["tipo_ui"] in ("Selección única", "Selección múltiple"):
                c1.caption("Opciones: " + ", ".join(q.get("opciones") or []))

            up = c2.button("⬆️ Subir", key=f"up_{idx}", use_container_width=True, disabled=(idx == 0))
            down = c3.button("⬇️ Bajar", key=f"down_{idx}", use_container_width=True, disabled=(idx == len(st.session_state.preguntas)-1))
            edit = c4.button("✏️ Editar", key=f"edit_{idx}", use_container_width=True)
            borrar = c5.button("🗑️ Eliminar", key=f"del_{idx}", use_container_width=True)

            if up:
                st.session_state.preguntas[idx-1], st.session_state.preguntas[idx] = (
                    st.session_state.preguntas[idx], st.session_state.preguntas[idx-1]
                )
                _rerun()
            if down:
                st.session_state.preguntas[idx+1], st.session_state.preguntas[idx] = (
                    st.session_state.preguntas[idx], st.session_state.preguntas[idx+1]
                )
                _rerun()

            if edit:
                st.markdown("**Editar esta pregunta**")
                ne_label = st.text_input("Etiqueta", value=q["label"], key=f"e_label_{idx}")
                ne_name = st.text_input("Nombre interno (name)", value=q["name"], key=f"e_name_{idx}")
                ne_required = st.checkbox("Requerida", value=q["required"], key=f"e_req_{idx}")
                ne_appearance = st.text_input("Appearance", value=q.get("appearance") or "", key=f"e_app_{idx}")
                ne_choice_filter = st.text_input("choice_filter (opcional)", value=q.get("choice_filter") or "", key=f"e_cf_{idx}")
                ne_relevant = st.text_input("relevant (opcional – se autogenera por reglas)", value=q.get("relevant") or "", key=f"e_rel_{idx}")

                # ✅ Hint / Guidance hint
                ne_hint = st.text_input("hint (texto corto)", value=q.get("hint") or "", key=f"e_hint_{idx}")
                ne_guidance = st.text_area("guidance_hint (texto oculto por ícono)", value=q.get("guidance_hint") or "", height=80, key=f"e_gh_{idx}")

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
                    st.session_state.preguntas[idx]["hint"] = ne_hint.strip() or None
                    st.session_state.preguntas[idx]["guidance_hint"] = ne_guidance.strip() or None
                    if q["tipo_ui"] in ("Selección única", "Selección múltiple"):
                        st.session_state.preguntas[idx]["opciones"] = ne_opciones
                    st.success("Cambios guardados.")
                    _rerun()
                if col_cancel.button("Cancelar", key=f"e_cancel_{idx}", use_container_width=True):
                    _rerun()

            if borrar:
                del st.session_state.preguntas[idx]
                st.warning("Pregunta eliminada.")
                _rerun()

# ==========================================================================================
# Construcción XLSForm (páginas, condicionales y logo)
# ==========================================================================================
INTRO_AMPLIADA = (
    "Con el objetivo de fortalecer la seguridad en nuestros distintos territorios, esta encuesta "
    "recopila percepciones y datos operativos del personal de Fuerza Pública. La información será "
    "analizada para identificar patrones delictivos, necesidades de recursos y oportunidades de mejora. "
    "La participación es confidencial y los datos se utilizarán exclusivamente para orientar acciones "
    "institucionales y apoyar la toma de decisiones, en coordinación con las autoridades locales, "
    "otras instituciones y la comunidad."
)

def construir_xlsform(preguntas, form_title: str, idioma: str, version: str,
                      reglas_vis, reglas_fin):
    """
    Construye DataFrames: survey, choices, settings.
    - Páginas con grupos begin_group/end_group y appearance=field-list
    - Introducción con NOTE + media::image
    - relevant (manual + del panel) y finalizar-temprano (NOT de previas)
    - choices con columnas extra (cascadas)
    - ✅ hint + guidance_hint
    """
    survey_rows = []
    choices_rows = []

    # Reglas de visibilidad (panel)
    vis_by_target = {}
    for r in reglas_vis:
        vis_by_target.setdefault(r["target"], []).append({
            "src": r["src"], "op": r.get("op", "="), "values": r.get("values", [])
        })

    # Reglas de finalizar temprano (panel)
    fin_conds = []   # [(index_src, cond_expr)]
    for r in reglas_fin:
        cond = build_relevant_expr([{"src": r["src"], "op": r.get("op","="), "values": r.get("values",[])}])
        if cond:
            fin_conds.append((r["index_src"], cond))

    # ------------------- Página 1: INTRODUCCIÓN -------------------
    survey_rows.append({"type":"begin_group","name":"p1_intro","label":"Introducción","appearance":"field-list"})
    survey_rows.append({"type":"note","name":"intro_logo","label":form_title, "media::image": logo_media_name})
    survey_rows.append({"type":"note","name":"intro_texto","label":INTRO_AMPLIADA})
    survey_rows.append({"type":"end_group","name":"p1_end"})

    pagina2 = {"anos_servicio","edad","genero","escolaridad","manual_puesto","agente_ii","sub_oficial_i","sub_oficial_ii","oficial_i"}
    pagina3 = {"mantiene_info","tipo_actividad","nombre_estructura","quienes","modus_operandi","zona_insegura","por_que_insegura"}
    pagina4 = {"recurso_falta","condiciones_aptas","condiciones_mejorar","falta_capacitacion","areas_capacitacion","motivado","motivo_no","anomalias","detalle_anomalias","oficiales_relacionados","describe_situacion","medio_contacto"}

    def add_q(q, idx):
        x_type, default_app, list_name = map_tipo_to_xlsform(q["tipo_ui"], q["name"])

        rel_manual = q.get("relevant") or None
        rel_panel  = build_relevant_expr(vis_by_target.get(q["name"], []))

        nots = []
        for idx_src, cond in fin_conds:
            if idx_src < idx:
                nots.append(xlsform_not(cond))
        rel_fin = "(" + " and ".join(nots) + ")" if nots else None

        parts = [p for p in [rel_manual, rel_panel, rel_fin] if p]
        rel_final = None
        if parts:
            rel_final = parts[0] if len(parts) == 1 else "(" + ") and (".join(parts) + ")"

        row = {"type": x_type, "name": q["name"], "label": q["label"]}
        if q.get("required"): row["required"] = "yes"
        app = q.get("appearance") or default_app
        if app: row["appearance"] = app
        if q.get("choice_filter"): row["choice_filter"] = q["choice_filter"]
        if rel_final: row["relevant"] = rel_final

        # ✅ hint / guidance_hint
        if q.get("hint"): row["hint"] = q["hint"]
        if q.get("guidance_hint"): row["guidance_hint"] = q["guidance_hint"]

        survey_rows.append(row)

        if list_name:
            usados = set()
            for opt_label in (q.get("opciones") or []):
                base = slugify_name(opt_label)
                opt_name = asegurar_nombre_unico(base, usados)
                usados.add(opt_name)
                choices_rows.append({"list_name": list_name, "name": opt_name, "label": str(opt_label)})

    # Página 2
    survey_rows.append({"type":"begin_group","name":"p2_datos","label":"Datos","appearance":"field-list"})
    for i, q in enumerate(preguntas):
        if q["name"] in pagina2:
            add_q(q, i)
    survey_rows.append({"type":"end_group","name":"p2_end"})

    # Página 3
    survey_rows.append({"type":"begin_group","name":"p3_policial","label":"Información de Interés Policial","appearance":"field-list"})
    for i, q in enumerate(preguntas):
        if q["name"] in pagina3:
            add_q(q, i)
    survey_rows.append({"type":"end_group","name":"p3_end"})

    # Página 4
    survey_rows.append({"type":"begin_group","name":"p4_interno","label":"Información de Interés Interno","appearance":"field-list"})
    for i, q in enumerate(preguntas):
        if q["name"] in pagina4:
            add_q(q, i)
    survey_rows.append({"type":"end_group","name":"p4_end"})

    # Choices extendidos (cascadas)
    if "choices_ext_rows" in st.session_state:
        for r in st.session_state.choices_ext_rows:
            choices_rows.append(dict(r))

    # DataFrames
    survey_cols_all = set()
    for r in survey_rows:
        survey_cols_all.update(r.keys())

    survey_cols = [c for c in [
        "type","name","label",
        "hint","guidance_hint",
        "required","appearance","choice_filter","relevant",
        "media::image"
    ] if c in survey_cols_all]

    for k in sorted(survey_cols_all):
        if k not in survey_cols:
            survey_cols.append(k)

    df_survey = pd.DataFrame(survey_rows, columns=survey_cols)

    choices_cols_all = set()
    for r in choices_rows:
        choices_cols_all.update(r.keys())
    base_choice_cols = ["list_name","name","label"]
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
        df_survey.to_excel(writer,  sheet_name="survey",   index=False)
        df_choices.to_excel(writer, sheet_name="choices",  index=False)
        df_settings.to_excel(writer, sheet_name="settings", index=False)

        wb = writer.book
        fmt_hdr = wb.add_format({"bold": True, "align": "left"})
        for sheet, df in (("survey", df_survey), ("choices", df_choices), ("settings", df_settings)):
            ws = writer.sheets[sheet]
            ws.freeze_panes(1, 0)
            ws.set_row(0, None, fmt_hdr)
            cols = list(df.columns)
            for col_idx, col_name in enumerate(cols):
                ws.set_column(col_idx, col_idx, max(14, min(60, len(str(col_name)) + 12)))

    buffer.seek(0)
    st.download_button(
        label=f"📥 Descargar XLSForm ({nombre_archivo})",
        data=buffer,
        file_name=nombre_archivo,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

# ==========================================================================================
# Exportar / Vista previa
# ==========================================================================================
st.markdown("---")
st.subheader("📦 Generar XLSForm (Excel) para Survey123")

st.caption("""
El archivo incluirá:
- **survey** con `hint` + `guidance_hint` (ayuda oculta por ícono),
- **choices** con listas,
- **settings** con `style = pages`.
""")

if st.button("🧮 Construir XLSForm", use_container_width=True, disabled=not st.session_state.preguntas):
    try:
        names = [q["name"] for q in st.session_state.preguntas]
        if len(names) != len(set(names)):
            st.error("Hay 'name' duplicados. Edita las preguntas para que cada 'name' sea único.")
        else:
            df_survey, df_choices, df_settings = construir_xlsform(
                st.session_state.preguntas,
                form_title=(f"Encuesta Fuerza Pública – Delegación {delegacion.strip()}"
                            if delegacion.strip() else "Encuesta Fuerza Pública"),
                idioma=idioma,
                version=version.strip() or datetime.now().strftime("%Y%m%d%H%M"),
                reglas_vis=st.session_state.reglas_visibilidad,
                reglas_fin=st.session_state.reglas_finalizar
            )

            st.success("XLSForm construido. Vista previa:")
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown("**Hoja: survey**")
                st.dataframe(df_survey, use_container_width=True, hide_index=True)
            with c2:
                st.markdown("**Hoja: choices**")
                st.dataframe(df_choices, use_container_width=True, hide_index=True)
            with c3:
                st.markdown("**Hoja: settings**")
                st.dataframe(df_settings, use_container_width=True, hide_index=True)

            nombre_archivo = slugify_name(
                f"Encuesta Fuerza Pública – Delegación {delegacion}" if delegacion.strip() else "encuesta"
            ) + "_xlsform.xlsx"
            descargar_excel_xlsform(df_survey, df_choices, df_settings, nombre_archivo=nombre_archivo)

            if st.session_state.get("_logo_bytes"):
                st.download_button(
                    "📥 Descargar logo para carpeta media",
                    data=st.session_state["_logo_bytes"],
                    file_name=logo_media_name,
                    mime="image/png",
                    use_container_width=True
                )

            st.info("""
✅ **Para ver la ayuda en Survey123**
- En **Web App**: abre el panel/ícono de ayuda (según plantilla).
- En **Field App**: toca el **ícono de ayuda** (bombillo / i) de la pregunta.
Si tu plantilla Web no muestra el ícono, probá en Field App para confirmar.
""")
    except Exception as e:
        st.error(f"Ocurrió un error al generar el XLSForm: {e}")

st.markdown("""
---
🧠 **Importante**: Survey123 **no tiene hover tooltip** como en páginas web.
La alternativa funcional es `hint` + `guidance_hint` (ayuda por ícono/panel).
""")

# ==========================================================================================
# PARTE 10/10 — Exportar Word y PDF editable (mantiene tu lógica)
# ==========================================================================================
from typing import List, Dict
import os

try:
    from docx import Document
    from docx.shared import Pt, Inches, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ROW_HEIGHT_RULE
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
except Exception:
    Document = None

try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.lib.colors import HexColor, black
except Exception:
    canvas = None

def _build_cond_text(qname: str, reglas_vis: List[Dict]) -> str:
    rels = [r for r in reglas_vis if r.get("target") == qname]
    if not rels:
        return ""
    parts = []
    for r in rels:
        op = r.get("op", "=")
        vals = r.get("values", [])
        vtxt = ", ".join(vals) if vals else ""
        parts.append(f"{r['src']} {op} [{vtxt}]")
    return "Condición: se muestra si " + " OR ".join(parts)

def _get_logo_bytes_fallback() -> bytes | None:
    if st.session_state.get("_logo_bytes"):
        return st.session_state["_logo_bytes"]
    try:
        with open("001.png", "rb") as f:
            return f.read()
    except Exception:
        return None

def _wrap_text_lines(text: str, font_name: str, font_size: float, max_width: float) -> List[str]:
    if not text:
        return []
    words = text.split()
    lines, current = [], ""
    for w in words:
        test = (current + " " + w).strip()
        if stringWidth(test, font_name, font_size) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            if stringWidth(w, font_name, font_size) > max_width:
                chunk = ""
                for ch in w:
                    if stringWidth(chunk + ch, font_name, font_size) <= max_width:
                        chunk += ch
                    else:
                        if chunk:
                            lines.append(chunk)
                        chunk = ch
                current = chunk
            else:
                current = w
    if current:
        lines.append(current)
    return lines

def _is_yes_no_options(opts: List[str]) -> bool:
    if not opts:
        return False
    norm = {slugify_name(x) for x in opts if x and str(x).strip()}
    yes_variants = {"si", "sí", "yes"}
    no_variants = {"no"}
    return norm.issubset(yes_variants | no_variants) and \
           any(y in norm for y in yes_variants) and \
           any(n in norm for n in no_variants)

def _should_show_options(q: Dict) -> bool:
    if q.get("tipo_ui") not in ("Selección única", "Selección múltiple"):
        return False
    opts = q.get("opciones") or []
    return bool(opts) and not _is_yes_no_options(opts)

P3_NAMES = {
    "mantiene_info","tipo_actividad","nombre_estructura","quienes",
    "modus_operandi","zona_insegura","por_que_insegura"
}
P4_NAMES = {
    "recurso_falta","condiciones_aptas","condiciones_mejorar",
    "falta_capacitacion","areas_capacitacion","motivado","motivo_no",
    "anomalias","detalle_anomalias","oficiales_relacionados",
    "describe_situacion","medio_contacto"
}
ALLOWED_P3_P4 = P3_NAMES | P4_NAMES

def _only_pages_3_4(preguntas: List[Dict]) -> List[Dict]:
    return [q for q in preguntas if q.get("name") in ALLOWED_P3_P4]

def _set_cell_shading(cell, fill_hex: str):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = tcPr.find(qn('w:shd'))
    if shd is None:
        shd = OxmlElement('w:shd')
        tcPr.append(shd)
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), fill_hex.replace('#','').upper())

def _set_cell_borders(cell, color_hex: str):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    borders = tcPr.find(qn('w:tcBorders'))
    if borders is None:
        borders = OxmlElement('w:tcBorders')
        tcPr.append(borders)
    for edge in ('top','left','bottom','right'):
        tag = OxmlElement(f'w:{edge}')
        tag.set(qn('w:val'), 'single')
        tag.set(qn('w:sz'), '8')
        tag.set(qn('w:color'), color_hex.replace('#','').upper())
        borders.append(tag)

def _add_observation_box(doc: Document, fill_hex: str, border_hex: str):
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.LEFT
    tbl.autofit = True
    cell = tbl.cell(0, 0)
    _set_cell_shading(cell, fill_hex)
    _set_cell_borders(cell, border_hex)
    row = tbl.rows[0]
    row.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST
    row.height = Inches(1.1)
    p = cell.paragraphs[0]
    p.add_run("")

def export_docx_form(preguntas: List[Dict], form_title: str, intro: str, reglas_vis: List[Dict]):
    if Document is None:
        st.error("Falta dependencia: instala `python-docx` para generar Word.")
        return

    preguntas_use = _only_pages_3_4(preguntas)

    fills = ["#E6F4EA", "#E7F0FE", "#FDECEA"]
    borders = ["#1E8E3E", "#1A73E8", "#D93025"]
    BLACK = RGBColor(0, 0, 0)

    doc = Document()

    p = doc.add_paragraph()
    run = p.add_run(form_title)
    run.bold = True
    run.font.size = Pt(24)
    run.font.color.rgb = BLACK
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    logo_b = _get_logo_bytes_fallback()
    if logo_b:
        try:
            img_buf = BytesIO(logo_b)
            doc.add_paragraph().alignment = WD_ALIGN_PARAGRAPH.CENTER
            doc.add_picture(img_buf, width=Inches(2.8))
        except Exception:
            pass

    intro_p = doc.add_paragraph(intro)
    if intro_p.runs:
        intro_p.runs[0].font.size = Pt(12)
        intro_p.runs[0].font.color.rgb = BLACK

    sec3 = doc.add_paragraph("Información de Interés Policial")
    r = sec3.runs[0]; r.bold = True; r.font.size = Pt(14); r.font.color.rgb = BLACK

    i = 1
    color_idx = 0
    for q in preguntas_use:
        if q.get("name") not in P3_NAMES:
            continue

        doc.add_paragraph("")
        h = doc.add_paragraph(f"{i}. {q['label']}")
        h.runs[0].font.size = Pt(11)

        cond_txt = _build_cond_text(q["name"], reglas_vis)
        if cond_txt:
            cpara = doc.add_paragraph(cond_txt)
            cpara.runs[0].italic = True
            cpara.runs[0].font.size = Pt(9)

        # Mostrar ayuda en Word (aunque en Survey123 sea por ícono)
        if q.get("guidance_hint"):
            gpara = doc.add_paragraph(f"Ayuda: {q['guidance_hint']}")
            gpara.runs[0].italic = True
            gpara.runs[0].font.size = Pt(9)

        if _should_show_options(q):
            opts_str = ", ".join([str(x) for x in q.get("opciones") if str(x).strip()])
            opara = doc.add_paragraph(f"Opciones: {opts_str}")
            opara.runs[0].font.size = Pt(10)

        fill = fills[color_idx % len(fills)]
        border = borders[color_idx % len(borders)]
        color_idx += 1
        _add_observation_box(doc, fill, border)

        help_p = doc.add_paragraph("Agregue sus observaciones sobre la pregunta.")
        help_p.runs[0].italic = True
        help_p.runs[0].font.size = Pt(9)

        i += 1

    sec4 = doc.add_paragraph("Información de Interés Interno")
    r = sec4.runs[0]; r.bold = True; r.font.size = Pt(14); r.font.color.rgb = BLACK

    for q in preguntas_use:
        if q.get("name") not in P4_NAMES:
            continue

        doc.add_paragraph("")
        h = doc.add_paragraph(f"{i}. {q['label']}")
        h.runs[0].font.size = Pt(11)

        cond_txt = _build_cond_text(q["name"], reglas_vis)
        if cond_txt:
            cpara = doc.add_paragraph(cond_txt)
            cpara.runs[0].italic = True
            cpara.runs[0].font.size = Pt(9)

        if q.get("guidance_hint"):
            gpara = doc.add_paragraph(f"Ayuda: {q['guidance_hint']}")
            gpara.runs[0].italic = True
            gpara.runs[0].font.size = Pt(9)

        if _should_show_options(q):
            opts_str = ", ".join([str(x) for x in q.get("opciones") if str(x).strip()])
            opara = doc.add_paragraph(f"Opciones: {opts_str}")
            opara.runs[0].font.size = Pt(10)

        fill = fills[(i-1) % len(fills)]
        border = borders[(i-1) % len(borders)]
        _add_observation_box(doc, fill, border)

        help_p = doc.add_paragraph("Agregue sus observaciones sobre la pregunta.")
        help_p.runs[0].italic = True
        help_p.runs[0].font.size = Pt(9)

        i += 1

    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    st.download_button(
        "📄 Descargar Word del formulario",
        data=buf,
        file_name=slugify_name(form_title) + "_formulario.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        use_container_width=True
    )

def export_pdf_editable_form(preguntas: List[Dict], form_title: str, intro: str, reglas_vis: List[Dict]):
    if canvas is None:
        st.error("Falta dependencia: instala `reportlab` para generar PDF.")
        return

    preguntas_use = _only_pages_3_4(preguntas)

    PAGE_W, PAGE_H = A4
    margin = 2 * cm
    max_text_w = PAGE_W - 2 * margin

    title_font, title_size = "Helvetica-Bold", 24
    intro_font, intro_size = "Helvetica", 12
    intro_line_h = 18
    sec_font, sec_size = "Helvetica-Bold", 14
    label_font, label_size = "Helvetica", 11
    cond_font, cond_size = "Helvetica-Oblique", 9
    helper_font, helper_size = "Helvetica-Oblique", 9
    opts_font, opts_size = "Helvetica", 10
    gh_font, gh_size = "Helvetica-Oblique", 9

    fills = [HexColor("#E6F4EA"), HexColor("#E7F0FE"), HexColor("#FDECEA")]
    borders = [HexColor("#1E8E3E"), HexColor("#1A73E8"), HexColor("#D93025")]

    field_h = 80
    line_h = 14
    y = PAGE_H - margin

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(form_title)

    logo_b = _get_logo_bytes_fallback()
    if logo_b:
        try:
            img = ImageReader(BytesIO(logo_b))
            logo_w, logo_h = 160, 115
            c.drawImage(img, (PAGE_W - logo_w) / 2, y - logo_h, width=logo_w, height=logo_h,
                        preserveAspectRatio=True, mask='auto')
            y -= (logo_h + 24)
        except Exception:
            pass

    c.setFillColor(black)
    title_lines = _wrap_text_lines(form_title, title_font, title_size, max_text_w) or [form_title]
    c.setFont(title_font, title_size)
    for tl in title_lines:
        c.drawCentredString(PAGE_W / 2, y, tl)
        y -= 26

    c.setFont(intro_font, intro_size)
    intro_lines = _wrap_text_lines(intro, intro_font, intro_size, max_text_w)
    for line in intro_lines:
        if y < margin + 80:
            c.showPage(); y = PAGE_H - margin
            c.setFillColor(black); c.setFont(intro_font, intro_size)
        c.drawString(margin, y, line)
        y -= intro_line_h

    c.showPage()
    y = PAGE_H - margin
    c.setFillColor(black)

    c.setFont(sec_font, sec_size)
    c.drawString(margin, y, "Información de Interés Policial")
    y -= (line_h + 6)
    c.setFont(label_font, label_size)

    color_idx = 0
    i = 1
    for q in preguntas_use:
        if q.get("name") not in P3_NAMES:
            continue

        label_lines = _wrap_text_lines(f"{i}. {q['label']}", label_font, label_size, max_text_w)
        needed = line_h * len(label_lines) + field_h + 26

        cond_txt = _build_cond_text(q["name"], reglas_vis)
        cond_lines = []
        if cond_txt:
            cond_lines = _wrap_text_lines(cond_txt, cond_font, cond_size, max_text_w)
            needed += line_h * len(cond_lines)

        gh_txt = q.get("guidance_hint") or ""
        gh_lines = []
        if gh_txt:
            gh_lines = _wrap_text_lines(f"Ayuda: {gh_txt}", gh_font, gh_size, max_text_w)
            needed += line_h * len(gh_lines)

        opts_lines = []
        if _should_show_options(q):
            opts_str = ", ".join([str(x) for x in q.get("opciones") if str(x).strip()])
            opts_lines = _wrap_text_lines(f"Opciones: {opts_str}", opts_font, opts_size, max_text_w)
            needed += line_h * len(opts_lines)

        if y - needed < margin:
            c.showPage(); y = PAGE_H - margin
            c.setFillColor(black)
            c.setFont(sec_font, sec_size); c.drawString(margin, y, "Información de Interés Policial")
            y -= (line_h + 6); c.setFont(label_font, label_size)

        for line in label_lines:
            c.drawString(margin, y, line)
            y -= line_h

        if cond_txt:
            c.setFont(cond_font, cond_size)
            for cl in cond_lines:
                c.drawString(margin, y, cl)
                y -= line_h
            c.setFont(label_font, label_size)

        if gh_txt:
            c.setFont(gh_font, gh_size)
            for gl in gh_lines:
                c.drawString(margin, y, gl)
                y -= line_h
            c.setFont(label_font, label_size)

        if opts_lines:
            c.setFont(opts_font, opts_size)
            for ol in opts_lines:
                c.drawString(margin, y, ol)
                y -= line_h
            c.setFont(label_font, label_size)

        fill_color = fills[color_idx % len(fills)]
        border_color = borders[color_idx % len(borders)]
        color_idx += 1

        c.setFillColor(fill_color); c.setStrokeColor(border_color)
        c.rect(margin, y - field_h, max_text_w, field_h, fill=1, stroke=1)
        c.setFillColor(black)

        c.acroForm.textfield(
            name=f"campo_obs_{i}",
            tooltip=f"Observaciones para: {q['name']}",
            x=margin, y=y - field_h,
            width=max_text_w, height=field_h,
            borderWidth=1, borderStyle='solid',
            forceBorder=True, fieldFlags=4096, value=""
        )
        c.setFont(helper_font, helper_size)
        c.drawString(margin, y - field_h - 10, "Agregue sus observaciones sobre la pregunta.")
        c.setFont(label_font, label_size)

        y -= (field_h + 26)
        i += 1

    if y < margin + 120:
        c.showPage(); y = PAGE_H - margin; c.setFillColor(black)
    c.setFont(sec_font, sec_size)
    c.drawString(margin, y, "Información de Interés Interno")
    y -= (line_h + 6)
    c.setFont(label_font, label_size)

    for q in preguntas_use:
        if q.get("name") not in P4_NAMES:
            continue

        label_lines = _wrap_text_lines(f"{i}. {q['label']}", label_font, label_size, max_text_w)
        needed = line_h * len(label_lines) + field_h + 26

        cond_txt = _build_cond_text(q["name"], reglas_vis)
        cond_lines = []
        if cond_txt:
            cond_lines = _wrap_text_lines(cond_txt, cond_font, cond_size, max_text_w)
            needed += line_h * len(cond_lines)

        gh_txt = q.get("guidance_hint") or ""
        gh_lines = []
        if gh_txt:
            gh_lines = _wrap_text_lines(f"Ayuda: {gh_txt}", gh_font, gh_size, max_text_w)
            needed += line_h * len(gh_lines)

        opts_lines = []
        if _should_show_options(q):
            opts_str = ", ".join([str(x) for x in q.get("opciones") if str(x).strip()])
            opts_lines = _wrap_text_lines(f"Opciones: {opts_str}", opts_font, opts_size, max_text_w)
            needed += line_h * len(opts_lines)

        if y - needed < margin:
            c.showPage(); y = PAGE_H - margin
            c.setFillColor(black)
            c.setFont(sec_font, sec_size); c.drawString(margin, y, "Información de Interés Interno")
            y -= (line_h + 6); c.setFont(label_font, label_size)

        for line in label_lines:
            c.drawString(margin, y, line)
            y -= line_h

        if cond_txt:
            c.setFont(cond_font, cond_size)
            for cl in cond_lines:
                c.drawString(margin, y, cl)
                y -= line_h
            c.setFont(label_font, label_size)

        if gh_txt:
            c.setFont(gh_font, gh_size)
            for gl in gh_lines:
                c.drawString(margin, y, gl)
                y -= line_h
            c.setFont(label_font, label_size)

        if opts_lines:
            c.setFont(opts_font, opts_size)
            for ol in opts_lines:
                c.drawString(margin, y, ol)
                y -= line_h
            c.setFont(label_font, label_size)

        fill_color = fills[(i-1) % len(fills)]
        border_color = borders[(i-1) % len(borders)]
        c.setFillColor(fill_color); c.setStrokeColor(border_color)
        c.rect(margin, y - field_h, max_text_w, field_h, fill=1, stroke=1)
        c.setFillColor(black)

        c.acroForm.textfield(
            name=f"campo_obs_{i}",
            tooltip=f"Observaciones para: {q['name']}",
            x=margin, y=y - field_h,
            width=max_text_w, height=field_h,
            borderWidth=1, borderStyle='solid',
            forceBorder=True, fieldFlags=4096, value=""
        )
        c.setFont(helper_font, helper_size)
        c.drawString(margin, y - field_h - 10, "Agregue sus observaciones sobre la pregunta.")
        c.setFont(label_font, label_size)

        y -= (field_h + 26)
        i += 1

    c.showPage()
    c.save()
    buf.seek(0)
    st.download_button(
        "🧾 Descargar PDF editable del formulario",
        data=buf,
        file_name=slugify_name(form_title) + "_formulario_editable.pdf",
        mime="application/pdf",
        use_container_width=True
    )

st.markdown("### 📝 Exportar formulario en **Word** y **PDF editable**")
col_w, col_p = st.columns(2)

with col_w:
    if st.button("Generar Word (DOCX)"):
        export_docx_form(
            preguntas=st.session_state.preguntas,
            form_title=(f"Encuesta Fuerza Pública – Delegación {delegacion.strip()}"
                        if delegacion.strip() else "Encuesta Fuerza Pública"),
            intro=INTRO_AMPLIADA,
            reglas_vis=st.session_state.reglas_visibilidad
        )

with col_p:
    if st.button("Generar PDF editable"):
        export_pdf_editable_form(
            preguntas=st.session_state.preguntas,
            form_title=(f"Encuesta Fuerza Pública – Delegación {delegacion.strip()}"
                        if delegacion.strip() else "Encuesta Fuerza Pública"),
            intro=INTRO_AMPLIADA,
            reglas_vis=st.session_state.reglas_visibilidad
        )
