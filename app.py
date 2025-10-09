# -*- coding: utf-8 -*-
# App: Constructor de Encuestas → Exporta XLSForm para Survey123 (condicionales + cascadas + intro/logo)
import re, json
from io import BytesIO
from datetime import datetime

import streamlit as st
import pandas as pd

# ==========================
# Configuración de la app
# ==========================
st.set_page_config(page_title="Constructor de Encuestas → XLSForm (Survey123)", layout="wide")
st.title("🧩 Constructor de Encuestas → XLSForm para ArcGIS Survey123")

st.markdown("""
Crea tu cuestionario y **exporta un XLSForm** (Excel con hojas `survey`, `choices`, `settings`) listo para publicar en **ArcGIS Survey123**.
- Soporta **texto**, **párrafo**, **número**, **selección única**, **selección múltiple**, **fecha**, **hora**, **GPS (geopoint)**.
- **Ordena** preguntas, marca **requeridas**, define **opciones**.
- **Condicionales (relevant)** para mostrar/ocultar preguntas según respuestas.
- **Finalizar temprano** ocultando lo que sigue si se cumple una condición.
- **Listas en cascada** (ejemplo Cantón→Distrito CR) vía **choice_filter**.
""")

# ==========================
# Compat: rerun (1.36+ / previas)
# ==========================
def _rerun():
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()

# ==========================
# Helpers
# ==========================
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
        return ("integer", None, None)  # cambia a 'decimal' si lo prefieres
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

def build_relevant_expr(rules_for_target):
    """
    rules_for_target: lista de condiciones (cada una puede equivaler a 1..N opciones)
      Ej: [{"src":"canton","op":"=","values":["alajuela"]}, ...]
    Devuelve una expresión XLSForm para 'relevant'
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

# ==========================
# Intro resumida y cabecera visual
# ==========================
INTRO_RESUMIDA = (
    "Con el fin de fortalecer la seguridad en los territorios, esta encuesta recoge "
    "percepciones y datos operativos del personal de Fuerza Pública sobre riesgos, delitos "
    "y necesidades internas de la delegación. La información es confidencial y se usará "
    "exclusivamente para orientar acciones de mejora y coordinación institucional."
)

DEFAULT_LOGO_PATH = "001.png"  # tu archivo en el repo
col_logo, col_txt = st.columns([1, 3])
with col_logo:
    up_logo = st.file_uploader("Logo (PNG/JPG)", type=["png", "jpg", "jpeg"])
    if up_logo:
        st.image(up_logo, caption="Logo cargado", use_container_width=True)
        st.session_state["_logo_bytes"] = up_logo.getvalue()
        st.session_state["_logo_name"] = up_logo.name
    else:
        # Si no suben nada, usamos 001.png del repo
        try:
            st.image(DEFAULT_LOGO_PATH, caption="Logo (001.png)", use_container_width=True)
            st.session_state["_logo_bytes"] = None
            st.session_state["_logo_name"] = "001.png"
        except Exception:
            st.warning("Sube un logo (PNG/JPG) para mostrarlo e incluirlo en el XLSForm.")
            st.session_state["_logo_bytes"] = None
            st.session_state["_logo_name"] = "logo.png"

with col_txt:
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    dirigido_a = st.text_input("¿A quién va dirigido?", value="Fuerza Pública – Delegación …")
    logo_media_name = st.text_input(
        "Nombre del archivo (para `media::image` en Survey123)",
        value=st.session_state.get("_logo_name", "001.png"),
        help="Este nombre debe coincidir con el PNG que copies a la carpeta `media` del proyecto en Survey123 Connect."
    )
    st.markdown(
        f"<div style='font-size:20px; text-align:center; margin-top:6px;'><b>{dirigido_a}</b></div>",
        unsafe_allow_html=True
    )

# ==========================
# Estado
# ==========================
if "preguntas" not in st.session_state:
    st.session_state.preguntas = []

if "reglas_visibilidad" not in st.session_state:
    st.session_state.reglas_visibilidad = []

if "reglas_finalizar" not in st.session_state:
    st.session_state.reglas_finalizar = []

if "choices_extra_cols" not in st.session_state:
    st.session_state.choices_extra_cols = set()

# Seed precargado con tu estructura y condicionales
if "seed_cargado" not in st.session_state:
    seed = [
        # --- Página 2: Datos generales ---
        {"tipo_ui":"Número", "label":"Años de servicio", "name":"anos_servicio","required":True,"opciones":[], "appearance":None,"choice_filter":None,"relevant":None},
        {"tipo_ui":"Número", "label":"Edad", "name":"edad","required":True,"opciones":[], "appearance":None,"choice_filter":None,"relevant":None},
        {"tipo_ui":"Selección única", "label":"Género", "name":"genero","required":True,
         "opciones":["Masculino","Femenino","LGBTQ+"],"appearance":None,"choice_filter":None,"relevant":None},
        {"tipo_ui":"Selección única", "label":"Escolaridad", "name":"escolaridad","required":True,
         "opciones":["Ninguna","Primaria","Primaria Incompleta","Secundaria","Secundaria Incompleta","Universidad Completa","Universidad Incompleta","Técnico"],
         "appearance":None,"choice_filter":None,"relevant":None},

        # Manual de puesto (principal)
        {"tipo_ui":"Selección única","label":"¿Qué clase del manual de puestos desempeña en su delegación?",
         "name":"manual_puesto","required":True,
         "opciones":["Agente I","Agente II","Sub Oficial I","Sub Oficial II","Oficial I","Jefe de Delegación","Sub Jefe de Delegación"],
         "appearance":None,"choice_filter":None,"relevant":None},

        # Sub-listas según selección
        {"tipo_ui":"Selección única","label":"Funciones (Agente II)",
         "name":"agente_ii_funcion","required":False,
         "opciones":["Agente de Fronteras","Agente de Seguridad Turística","Agente de Programas Preventivos",
                     "Agente de Comunicaciones","Agente Armero","Agente Conductor de Vehículos Oficiales","Agente de Operaciones"],
         "appearance":None,"choice_filter":None,"relevant":"${manual_puesto}='Agente II'"},

        {"tipo_ui":"Selección única","label":"Funciones (Sub Oficial I)",
         "name":"subof1_funcion","required":False,
         "opciones":["Encargado Equipo Operativo Policial","Encargado Equipo de Seguridad Turística",
                     "Encargado Equipo de Fronteras","Encargado Programas Preventivos",
                     "Encargado Agentes Armeros","Encargado de Equipo de Comunicaciones"],
         "appearance":None,"choice_filter":None,"relevant":"${manual_puesto}='Sub Oficial I'"},

        {"tipo_ui":"Selección única","label":"Funciones (Sub Oficial II)",
         "name":"subof2_funcion","required":False,
         "opciones":["Encargado Subgrupo Operativo Policial","Encargado Subgrupo de Seguridad Turística",
                     "Encargado Subgrupo de Fronteras","Oficial de Guardia","Encargado de Operaciones"],
         "appearance":None,"choice_filter":None,"relevant":"${manual_puesto}='Sub Oficial II'"},

        {"tipo_ui":"Selección única","label":"Funciones (Oficial I)",
         "name":"oficial1_funcion","required":False,
         "opciones":["Jefe Delegación Distrital","Encargado Grupo Operativo Policial"],
         "appearance":None,"choice_filter":None,"relevant":"${manual_puesto}='Oficial I'"},

        # --- Página 3: Información de Interés Policial ---
        {"tipo_ui":"Selección única", "label":"¿Mantiene usted información de estructuras/personas de interés policial en su jurisdicción?",
         "name":"info_estructuras","required":True,"opciones":["Sí","No"],"appearance":None,"choice_filter":None,"relevant":None},

        {"tipo_ui":"Selección múltiple","label":"¿Qué tipo de actividad delictual realizan?",
         "name":"actividad_delictual","required":True,
         "opciones":[
            "Bunker (venta/distribución de drogas)","Delitos contra la vida (homicidios, heridos)",
            "Venta/consumo de drogas en vía pública","Delitos sexuales",
            "Asalto (personas, comercio, vivienda, TP)","Daños a la propiedad",
            "Estafas (billetes/documentos/oro/lotería falsos)","Estafa informática",
            "Extorsión","Hurto","Receptación","Robo a edificaciones","Robo a vivienda",
            "Robo de ganado/agrícola","Robo a comercio","Robo de vehículos","Tacha de vehículos",
            "Contrabando (licor/cigarrillos/medicinas/ropa/calzado)","Tráfico ilegal de personas (coyotaje)","Otro"
         ],
         "appearance":None,"choice_filter":None,"relevant":"${info_estructuras}='Sí'"},

        {"tipo_ui":"Texto (corto)","label":"¿Cuál es el nombre de la estructura criminal?","name":"nombre_estructura","required":True,
         "opciones":[],"appearance":None,"choice_filter":None,"relevant":"${info_estructuras}='Sí'"},
        {"tipo_ui":"Párrafo (texto largo)","label":"Indique quién(es) se dedican a estos actos (nombres, apellidos, alias, domicilio)",
         "name":"quienes","required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":"${info_estructuras}='Sí'"},
        {"tipo_ui":"Párrafo (texto largo)","label":"Modo de operar (venta exprés/vía pública, asalto, desplazamiento, etc.)",
         "name":"modus_operandi","required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":"${info_estructuras}='Sí'"},

        {"tipo_ui":"Texto (corto)","label":"¿Cuál es la zona más insegura en su área de responsabilidad?",
         "name":"zona_insegura","required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":None},
        {"tipo_ui":"Párrafo (texto largo)","label":"Describa por qué considera que esa zona es insegura",
         "name":"por_que_insegura","required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":None},

        # --- Página 4: Información de Interés Interno ---
        {"tipo_ui":"Párrafo (texto largo)","label":"¿Qué recurso hace falta en su delegación para mejorar el servicio?",
         "name":"recurso_falta","required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":None},

        {"tipo_ui":"Selección única","label":"¿Las condiciones de su delegación son aptas para sus necesidades básicas?",
         "name":"condiciones_aptas","required":True,"opciones":["Sí","No"],"appearance":None,"choice_filter":None,"relevant":None},
        {"tipo_ui":"Párrafo (texto largo)","label":"¿Cuáles condiciones se pueden mejorar?",
         "name":"condiciones_mejorar","required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":"${condiciones_aptas}='No'"},

        {"tipo_ui":"Selección única","label":"¿Hace falta capacitación para el personal en su delegación?",
         "name":"falta_capacitacion","required":True,"opciones":["Sí","No"],"appearance":None,"choice_filter":None,"relevant":None},
        {"tipo_ui":"Párrafo (texto largo)","label":"Especifique en qué áreas necesita capacitación",
         "name":"areas_capacitacion","required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":"${falta_capacitacion}='Sí'"},

        {"tipo_ui":"Selección única","label":"¿Se siente motivado por la institución para brindar un buen servicio?",
         "name":"motivado","required":True,"opciones":["Sí","No"],"appearance":None,"choice_filter":None,"relevant":None},
        {"tipo_ui":"Párrafo (texto largo)","label":"Explique por qué no se siente motivado",
         "name":"motivo_no","required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":"${motivado}='No'"},

        {"tipo_ui":"Selección única","label":"¿Mantiene conocimiento de situaciones anómalas en su delegación? (confidencial)",
         "name":"anomalias","required":True,"opciones":["Sí","No"],"appearance":None,"choice_filter":None,"relevant":None},
        {"tipo_ui":"Párrafo (texto largo)","label":"Especifique cuáles son las situaciones anómalas",
         "name":"detalle_anomalias","required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":"${anomalias}='Sí'"},

        {"tipo_ui":"Selección única","label":"¿Conoce oficiales relacionados con estructuras criminales o delitos?",
         "name":"oficiales_relacionados","required":True,"opciones":["Sí","No"],"appearance":None,"choice_filter":None,"relevant":None},
        {"tipo_ui":"Párrafo (texto largo)","label":"Describa la situación (estructura, tipo de actividad, oficiales, funciones, alias, etc.)",
         "name":"describe_situacion","required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":"${oficiales_relacionados}='Sí'"},

        {"tipo_ui":"Texto (corto)","label":"Medio de contacto para ampliar (opcional)",
         "name":"medio_contacto","required":False,"opciones":[],"appearance":None,"choice_filter":None,"relevant":None},
    ]
    st.session_state.preguntas = seed
    st.session_state.reglas_visibilidad = []  # usamos 'relevant' embebido
    st.session_state.reglas_finalizar = []    # sin finalización global
    st.session_state.seed_cargado = True

# ==========================
# Sidebar: Metadatos + Atajos
# ==========================
with st.sidebar:
    st.header("⚙️ Configuración")
    form_title = st.text_input("Título del formulario", value="Encuesta Fuerza Pública")
    idioma = st.selectbox("Idioma por defecto (default_language)", options=["es", "en"], index=0)
    version_auto = datetime.now().strftime("%Y%m%d%H%M")
    version = st.text_input("Versión (settings.version)", value=version_auto,
                            help="Survey123 usa este campo para gestionar actualizaciones.")

    st.markdown("---")
    st.caption("🚀 Insertar ejemplo de **listas en cascada** Cantón→Distrito (CR)")
    if st.button("Insertar Cantón→Distrito (ejemplo CR)", use_container_width=True):
        # Pregunta Cantón
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
            "relevant": None
        })

        # Pregunta Distrito (filtrada por canton_key)
        usados.add(name_canton)
        name_distrito = asegurar_nombre_unico("distrito", usados)
        st.session_state.preguntas.append({
            "tipo_ui": "Selección única",
            "label": "Seleccione el Distrito",
            "name": name_distrito,
            "required": True,
            "opciones": ["— se rellena con la lista extendida —"],
            "appearance": None,
            "choice_filter": "canton_key=${" + name_canton + "}",
            "relevant": None
        })

        # Registrar regla de visibilidad opcional (mostrar si hay cantón, aquí lo omitimos porque estamos filtrando por choice_filter)

        # Choices extendidos
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
            ["Alajuela","San José","Carrizal","San Antonio","Guácima",
             "San Isidro","Sabanilla","San Rafael","Río Segundo",
             "Desamparados","Turrúcares","Tambor","Garita","Sarapiquí"], "Alajuela (Central)")
        add_choices(list_distrito, ["Centro","Este","Oeste","Norte","Sur"], "Sabanilla")
        add_choices(list_distrito,
            ["Desamparados","San Miguel","San Juan de Dios","San Rafael Arriba",
             "San Antonio","Frailes","Patarrá","San Cristóbal","Rosario",
             "Damas","San Rafael Abajo","Gravilias","Los Guido"], "Desamparados")

        st.success("Ejemplo Cantón→Distrito insertado. Puedes ver/editar en la lista de preguntas.")
        _rerun()

    st.markdown("---")
    st.caption("💾 Exporta/Importa tu proyecto (JSON)")
    col_exp, col_imp = st.columns([1,1])
    with col_exp:
        if st.button("Exportar proyecto (JSON)", use_container_width=True):
            proj = {
                "form_title": form_title,
                "idioma": idioma,
                "version": version,
                "preguntas": st.session_state.preguntas,
                "reglas_visibilidad": st.session_state.reglas_visibilidad,
                "reglas_finalizar": st.session_state.reglas_finalizar,
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

# ==========================
# Constructor de preguntas
# ==========================
st.subheader("📝 Diseña tus preguntas")

with st.form("form_add_q", clear_on_submit=False):
    tipo_ui = st.selectbox("Tipo de pregunta", options=TIPOS)
    label = st.text_input("Etiqueta (lo que verá el encuestado)", placeholder="Ej.: ¿Cuál es su nombre?")
    sugerido = slugify_name(label) if label else ""
    col_n1, col_n2, col_n3 = st.columns([2,1,1])
    with col_n1:
        name = st.text_input("Nombre interno (XLSForm 'name')", value=sugerido,
                             help="Sin espacios; minúsculas; se usará para el campo en XLSForm.")
    with col_n2:
        required = st.checkbox("Requerida", value=False)
    with col_n3:
        appearance = st.text_input("Appearance (opcional)", value="")

    opciones = []
    if tipo_ui in ("Selección única", "Selección múltiple"):
        st.markdown("**Opciones (una por línea)**")
        txt_opts = st.text_area("Opciones", height=120, placeholder="Ej.:\nSí\nNo\nNo sabe / No responde")
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
            "relevant": None
        }
        st.session_state.preguntas.append(nueva)
        st.success(f"Pregunta agregada: **{label}** (name: `{unico}`)")

# ==========================
# Reglas condicionales (adicionales si las quieres encima de las ya embebidas)
# ==========================
st.subheader("🔀 Condicionales (mostrar / finalizar)")

if not st.session_state.preguntas:
    st.info("Agrega preguntas para definir condicionales.")
else:
    # UI reglas de visibilidad
    with st.expander("👁️ Mostrar pregunta si se cumple condición", expanded=False):
        names = [q["name"] for q in st.session_state.preguntas]
        labels_by_name = {q["name"]: q["label"] for q in st.session_state.preguntas}
        tipos_by_name  = {q["name"]: q["tipo_ui"] for q in st.session_state.preguntas}
        target = st.selectbox("Pregunta a mostrar (target)", options=names, format_func=lambda n: f"{n} — {labels_by_name[n]}")
        src = st.selectbox("Depende de (source)", options=names, format_func=lambda n: f"{n} — {labels_by_name[n]}")
        op = st.selectbox("Operador", options=["=", "selected"], help="= para select_one; selected para select_multiple")
        src_q = next((q for q in st.session_state.preguntas if q["name"] == src), None)
        vals = []
        if src_q and src_q["opciones"]:
            vals = st.multiselect("Valores que activan la visibilidad", options=src_q["opciones"])
        else:
            manual = st.text_input("Valor (si la pregunta no tiene opciones predeterminadas)")
            vals = [manual] if manual.strip() else []

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

    # UI reglas de finalizar
    with st.expander("⏹️ Finalizar temprano si se cumple condición", expanded=False):
        names = [q["name"] for q in st.session_state.preguntas]
        labels_by_name = {q["name"]: q["label"] for q in st.session_state.preguntas}
        src2 = st.selectbox("Condición basada en", options=names, format_func=lambda n: f"{n} — {labels_by_name[n]}", key="final_src")
        op2 = st.selectbox("Operador", options=["=", "selected", "!="], key="final_op")
        src2_q = next((q for q in st.session_state.preguntas if q["name"] == src2), None)
        vals2 = []
        if src2_q and src2_q["opciones"]:
            vals2 = st.multiselect("Valores que disparan el fin", options=src2_q["opciones"], key="final_vals")
        else:
            manual2 = st.text_input("Valor (si no hay opciones)", key="final_manual")
            vals2 = [manual2] if manual2.strip() else []
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

# ==========================
# Lista / Ordenado / Edición
# ==========================
st.subheader("📚 Preguntas (ordénalas y edítalas)")

if not st.session_state.preguntas:
    st.info("Aún no has agregado preguntas.")
else:
    for idx, q in enumerate(st.session_state.preguntas):
        with st.container(border=True):
            c1, c2, c3, c4, c5 = st.columns([4,2,2,2,2])
            c1.markdown(f"**{idx+1}. {q['label']}**")
            meta = f"type: {q['tipo_ui']}  •  name: `{q['name']}`  •  requerida: {'sí' if q.get('required') else 'no'}"
            if q.get("appearance"): meta += f"  •  appearance: `{q['appearance']}`"
            if q.get("choice_filter"): meta += f"  •  choice_filter: `{q['choice_filter']}`"
            if q.get("relevant"): meta += f"  •  relevant: `{q['relevant']}`"
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
                ne_required = st.checkbox("Requerida", value=q.get("required", False), key=f"e_req_{idx}")
                ne_appearance = st.text_input("Appearance", value=q.get("appearance") or "", key=f"e_app_{idx}")
                ne_choice_filter = st.text_input("choice_filter (opcional)", value=q.get("choice_filter") or "", key=f"e_cf_{idx}")
                ne_relevant = st.text_input("relevant (opcional – se autogenera por reglas)", value=q.get("relevant") or "", key=f"e_rel_{idx}")

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

            if borrar:
                del st.session_state.preguntas[idx]
                st.warning("Pregunta eliminada.")
                _rerun()

# ==========================
# Construcción XLSForm
# ==========================
def construir_xlsform(preguntas, form_title: str, idioma: str, version: str,
                      reglas_vis, reglas_fin):
    """
    Construye DataFrames: survey, choices, settings.
    - Inserta INTRO como primera fila (type=note) con media::image.
    - Aplica 'relevant' para reglas de visibilidad añadidas desde UI (además de los que ya traiga cada pregunta).
    - Aplica 'fin temprano' agregando NOT(condición) a todas las preguntas posteriores.
    - Propaga 'choice_filter' y 'appearance' si existen.
    - choices admite columnas extra (p.ej. canton_key).
    """
    survey_rows = []
    choices_rows = []

    # --- 0) Fila de introducción ---
    survey_rows.append({
        "type": "note",
        "name": "intro",
        "label": f"<b>{form_title}</b><br/>Dirigido a: <i>{dirigido_a}</i><br/><br/>{INTRO_RESUMIDA}",
        "media::image": logo_media_name
    })

    # Índices por name para calcular "posteriores"
    idx_by_name = {q["name"]: i for i, q in enumerate(preguntas)}

    # 1) Recolectar reglas de visibilidad por target (desde UI extra)
    vis_by_target = {}
    for r in reglas_vis:
        vis_by_target.setdefault(r["target"], []).append({"src": r["src"], "op": r.get("op","="), "values": r.get("values", [])})

    # 2) Precalcular condiciones de finalización (por índice)
    fin_conds = []  # [(index_src, cond_expr)]
    for r in reglas_fin:
        cond = build_relevant_expr([{"src": r["src"], "op": r.get("op","="), "values": r.get("values",[])}])
        if cond:
            fin_conds.append((r["index_src"], cond))

    # 3) Construir survey + choices
    for i, q in enumerate(preguntas):
        name = q["name"]
        label = q["label"]
        tipo_ui = q["tipo_ui"]
        required = "yes" if q.get("required") else None
        appearance = q.get("appearance") or None
        choice_filter = q.get("choice_filter") or None
        manual_relevant = q.get("relevant") or None  # embebido

        x_type, default_app, list_name = map_tipo_to_xlsform(tipo_ui, name)
        if default_app and not appearance:
            appearance = default_app

        # Relevant a partir de reglas adicionales (UI)
        rel_auto = build_relevant_expr(vis_by_target.get(name, []))

        # Fin temprano: NOT(cond) para todo lo posterior
        not_conds = []
        for idx_src, cond in fin_conds:
            if idx_src < i:
                not_conds.append(xlsform_not(cond))
        fin_expr = None
        if not_conds:
            fin_expr = "(" + " and ".join([c for c in not_conds if c]) + ")"

        relevant_parts = [p for p in [manual_relevant, rel_auto, fin_expr] if p]
        relevant_final = None
        if relevant_parts:
            if len(relevant_parts) == 1:
                relevant_final = relevant_parts[0]
            else:
                relevant_final = "(" + ") and (".join(relevant_parts) + ")"

        row = {
            "type": x_type,
            "name": name,
            "label": label
        }
        if required: row["required"] = required
        if appearance: row["appearance"] = appearance
        if choice_filter: row["choice_filter"] = choice_filter
        if relevant_final: row["relevant"] = relevant_final
        survey_rows.append(row)

        # Choices
        if list_name:
            opciones = q.get("opciones") or []
            usados = set()
            for opt_label in opciones:
                base = slugify_name(str(opt_label))
                opt_name = asegurar_nombre_unico(base, usados)
                usados.add(opt_name)
                choices_rows.append({
                    "list_name": list_name,
                    "name": opt_name,
                    "label": str(opt_label)
                })

    # 4) Agregar choices extendidos (ej. distritos con canton_key)
    if "choices_ext_rows" in st.session_state:
        for r in st.session_state.choices_ext_rows:
            choices_rows.append(dict(r))

    # 5) DataFrames
    # survey: columnas posibles (+ media::image)
    survey_cols_all = set()
    for r in survey_rows:
        survey_cols_all.update(r.keys())
    base_cols = ["type","name","label","required","appearance","choice_filter","relevant","media::image"]
    survey_cols = [c for c in base_cols if c in survey_cols_all]
    for k in sorted(survey_cols_all):
        if k not in survey_cols:
            survey_cols.append(k)
    df_survey  = pd.DataFrame(survey_rows,  columns=survey_cols)

    # choices: admite columnas extra
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
        "default_language": idioma
    }], columns=["form_title", "version", "default_language"])

    return df_survey, df_choices, df_settings

def descargar_excel_xlsform(df_survey, df_choices, df_settings, nombre_archivo: str = "encuesta_xlsform.xlsx"):
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
                ws.set_column(col_idx, col_idx, max(14, min(40, len(str(col_name)) + 10)))

    buffer.seek(0)
    st.download_button(
        label=f"📥 Descargar XLSForm ({nombre_archivo})",
        data=buffer,
        file_name=nombre_archivo,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

# ==========================
# Exportar / Vista previa
# ==========================
st.markdown("---")
st.subheader("📦 Generar XLSForm (Excel) para Survey123")

st.caption("""
El archivo incluirá:
- **survey** con tipos, `relevant`, `choice_filter`, `appearance`, y una primera fila **note** con introducción + `media::image`,
- **choices** con listas (y columnas extra como `canton_key` si usas cascadas),
- **settings** con título, versión e idioma.
""")

if st.button("🧮 Construir XLSForm", use_container_width=True, disabled=not st.session_state.preguntas):
    try:
        names = [q["name"] for q in st.session_state.preguntas]
        if len(names) != len(set(names)):
            st.error("Hay 'name' duplicados. Edita las preguntas para que cada 'name' sea único.")
        else:
            df_survey, df_choices, df_settings = construir_xlsform(
                st.session_state.preguntas,
                form_title=form_title.strip() or "Encuesta",
                idioma=idioma,
                version=version.strip() or datetime.now().strftime("%Y%m%d%H%M"),
                reglas_vis=st.session_state.reglas_visibilidad,
                reglas_fin=st.session_state.reglas_finalizar
            )

            st.success("XLSForm construido. Revisa una vista previa rápida:")
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

            nombre_archivo = slugify_name(form_title or "encuesta") + "_xlsform.xlsx"
            descargar_excel_xlsform(df_survey, df_choices, df_settings, nombre_archivo=nombre_archivo)

            # Botón para descargar el logo si fue subido (para carpeta media en Survey123)
            if st.session_state.get("_logo_bytes"):
                st.download_button(
                    "📥 Descargar logo para carpeta media",
                    data=st.session_state["_logo_bytes"],
                    file_name=logo_media_name,
                    mime="image/png",
                    use_container_width=True
                )
            else:
                st.caption(f"Usando logo por defecto: **{st.session_state.get('_logo_name','001.png')}**. "
                           "Cópialo a la carpeta **media** del proyecto en Survey123 Connect y respeta el mismo nombre.")

            st.info("""
**Publicar en Survey123**
1) Abre **ArcGIS Survey123 Connect**.
2) Crea una **encuesta desde archivo** y selecciona el XLSForm descargado.
3) Copia el PNG del logo a la carpeta **media** del proyecto (mismo nombre que `media::image`).
4) Publica. Las condiciones (`relevant`) y las cascadas (`choice_filter`) se aplican automáticamente.
""")
    except Exception as e:
        st.error(f"Ocurrió un error al generar el XLSForm: {e}")

# ==========================
# Nota final
# ==========================
st.markdown("""
---
✅ **Listo para Survey123:** admite `relevant`, `choice_filter`, `appearance`, tipos `text`, `integer`, `date`, `time`, `geopoint`,
`select_one` y `select_multiple`.  
🧪 Tip: Puedes seguir usando el panel **Condicionales** para reglas extra además de las ya embebidas en las preguntas.
""")
