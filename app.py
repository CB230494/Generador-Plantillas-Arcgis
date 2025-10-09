# -*- coding: utf-8 -*-
# App: Constructor de Encuestas → Exporta XLSForm para Survey123
# - Intro con logo (media::image)
# - Paginación por grupos (appearance=field-list)
# - Condicionales embebidas (relevant)
import re, json
from io import BytesIO
from datetime import datetime

import streamlit as st
import pandas as pd

# ========= Config app =========
st.set_page_config(page_title="Constructor de Encuestas → XLSForm (Survey123)", layout="wide")
st.title("🧩 Constructor de Encuestas → XLSForm para ArcGIS Survey123")

st.markdown("""
Crea tu cuestionario y **exporta un XLSForm** (Excel con `survey`, `choices`, `settings`) para **ArcGIS Survey123**.
- Tipos: texto, párrafo, número, select_one, select_multiple, fecha, hora, geopoint.
- **Condicionales** (`relevant`) embebidas y panel adicional para reglas.
- **Páginas** con `begin_group/end_group` (`appearance=field-list`).
- **Cascadas** vía `choice_filter` (Cantón→Distrito ejemplo).
""")

# ========= Utilidades =========
def _rerun():
    if hasattr(st, "rerun"): st.rerun()
    else: st.experimental_rerun()

TIPOS = [
    "Texto (corto)","Párrafo (texto largo)","Número",
    "Selección única","Selección múltiple","Fecha","Hora","GPS (ubicación)"
]

def slugify_name(texto: str) -> str:
    if not texto: return "campo"
    t = texto.lower()
    t = re.sub(r"[áàäâ]", "a", t); t = re.sub(r"[éèëê]", "e", t)
    t = re.sub(r"[íìïî]", "i", t); t = re.sub(r"[óòöô]", "o", t)
    t = re.sub(r"[úùüû]", "u", t); t = re.sub(r"ñ", "n", t)
    t = re.sub(r"[^a-z0-9]+", "_", t).strip("_")
    return t or "campo"

def asegurar_nombre_unico(base: str, usados: set) -> str:
    if base not in usados: return base
    i = 2
    while f"{base}_{i}" in usados: i += 1
    return f"{base}_{i}"

def map_tipo_to_xlsform(tipo_ui: str, name: str):
    if tipo_ui == "Texto (corto)": return ("text", None, None)
    if tipo_ui == "Párrafo (texto largo)": return ("text", "multiline", None)
    if tipo_ui == "Número": return ("integer", None, None)
    if tipo_ui == "Selección única": return (f"select_one list_{name}", None, f"list_{name}")
    if tipo_ui == "Selección múltiple": return (f"select_multiple list_{name}", None, f"list_{name}")
    if tipo_ui == "Fecha": return ("date", None, None)
    if tipo_ui == "Hora": return ("time", None, None)
    if tipo_ui == "GPS (ubicación)": return ("geopoint", None, None)
    return ("text", None, None)

def xlsform_or_expr(conds):
    if not conds: return None
    return conds[0] if len(conds)==1 else "(" + " or ".join(conds) + ")"

def xlsform_not(expr):
    return None if not expr else f"not({expr})"

def build_relevant_expr(rules_for_target):
    or_parts = []
    for r in rules_for_target:
        src, op, vals = r["src"], r.get("op","="), r.get("values",[])
        if not vals: continue
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

# ========= Intro y cabecera =========
INTRO_RESUMIDA = (
    "Con el fin de fortalecer la seguridad en los territorios, esta encuesta recoge "
    "percepciones y datos operativos del personal de Fuerza Pública sobre riesgos, delitos "
    "y necesidades internas de la delegación. La información es confidencial y se usará "
    "exclusivamente para orientar acciones de mejora y coordinación institucional."
)

DEFAULT_LOGO_PATH = "001.png"  # tu archivo en el repo
col_logo, col_txt = st.columns([1, 3])
with col_logo:
    up_logo = st.file_uploader("Logo (PNG/JPG)", type=["png","jpg","jpeg"])
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
            st.warning("Sube un logo (PNG/JPG) para incluirlo en el XLSForm.")
            st.session_state["_logo_bytes"] = None
            st.session_state["_logo_name"] = "logo.png"

with col_txt:
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    dirigido_a = st.text_input("¿A quién va dirigido?", value="Fuerza Pública – Delegación …")
    logo_media_name = st.text_input(
        "Nombre del archivo para `media::image`",
        value=st.session_state.get("_logo_name","001.png"),
        help="Este nombre DEBE coincidir con el PNG colocado en la carpeta `media` en Survey123 Connect."
    )
    st.markdown(
        f"<div style='font-size:20px; text-align:center; margin-top:6px;'><b>{dirigido_a}</b></div>",
        unsafe_allow_html=True
    )

# ========= Estado =========
for k, v in [("preguntas", []), ("reglas_visibilidad", []), ("reglas_finalizar", []), ("choices_extra_cols", set())]:
    if k not in st.session_state: st.session_state[k] = v

# Seed precargado con condicionales embebidas
if "seed_cargado" not in st.session_state:
    seed = [
        # ——— Página 2: Datos generales
        {"tipo_ui":"Número","label":"Años de servicio","name":"anos_servicio","required":True,
         "opciones":[],"appearance":None,"choice_filter":None,"relevant":None},
        {"tipo_ui":"Número","label":"Edad","name":"edad","required":True,
         "opciones":[],"appearance":None,"choice_filter":None,"relevant":None},
        {"tipo_ui":"Selección única","label":"Género","name":"genero","required":True,
         "opciones":["Masculino","Femenino","LGBTQ+"],"appearance":None,"choice_filter":None,"relevant":None},
        {"tipo_ui":"Selección única","label":"Escolaridad","name":"escolaridad","required":True,
         "opciones":["Ninguna","Primaria","Primaria Incompleta","Secundaria",
                     "Secundaria Incompleta","Universidad Completa","Universidad Incompleta","Técnico"],
         "appearance":None,"choice_filter":None,"relevant":None},

        {"tipo_ui":"Selección única","label":"¿Qué clase del manual de puestos desempeña en su delegación?",
         "name":"manual_puesto","required":True,
         "opciones":["Agente I","Agente II","Sub Oficial I","Sub Oficial II","Oficial I","Jefe de Delegación","Sub Jefe de Delegación"],
         "appearance":None,"choice_filter":None,"relevant":None},

        {"tipo_ui":"Selección única","label":"Funciones (Agente II)","name":"agente_ii_funcion","required":False,
         "opciones":["Agente de Fronteras","Agente de Seguridad Turística","Agente de Programas Preventivos",
                     "Agente de Comunicaciones","Agente Armero","Agente Conductor de Vehículos Oficiales","Agente de Operaciones"],
         "appearance":None,"choice_filter":None,"relevant":"${manual_puesto}='Agente II'"},
        {"tipo_ui":"Selección única","label":"Funciones (Sub Oficial I)","name":"subof1_funcion","required":False,
         "opciones":["Encargado Equipo Operativo Policial","Encargado Equipo de Seguridad Turística",
                     "Encargado Equipo de Fronteras","Encargado Programas Preventivos",
                     "Encargado Agentes Armeros","Encargado de Equipo de Comunicaciones"],
         "appearance":None,"choice_filter":None,"relevant":"${manual_puesto}='Sub Oficial I'"},
        {"tipo_ui":"Selección única","label":"Funciones (Sub Oficial II)","name":"subof2_funcion","required":False,
         "opciones":["Encargado Subgrupo Operativo Policial","Encargado Subgrupo de Seguridad Turística",
                     "Encargado Subgrupo de Fronteras","Oficial de Guardia","Encargado de Operaciones"],
         "appearance":None,"choice_filter":None,"relevant":"${manual_puesto}='Sub Oficial II'"},
        {"tipo_ui":"Selección única","label":"Funciones (Oficial I)","name":"oficial1_funcion","required":False,
         "opciones":["Jefe Delegación Distrital","Encargado Grupo Operativo Policial"],
         "appearance":None,"choice_filter":None,"relevant":"${manual_puesto}='Oficial I'"},

        # ——— Página 3: Información de Interés Policial
        {"tipo_ui":"Selección única","label":"¿Mantiene usted información de estructuras/personas de interés policial en su jurisdicción?",
         "name":"info_estructuras","required":True,"opciones":["Sí","No"],"appearance":None,"choice_filter":None,"relevant":None},
        {"tipo_ui":"Selección múltiple","label":"¿Qué tipo de actividad delictual realizan?","name":"actividad_delictual","required":True,
         "opciones":["Bunker (venta/distribución de drogas)","Delitos contra la vida (homicidios, heridos)",
                     "Venta/consumo de drogas en vía pública","Delitos sexuales","Asalto (personas, comercio, vivienda, TP)",
                     "Daños a la propiedad","Estafas (billetes/documentos/oro/lotería falsos)","Estafa informática","Extorsión",
                     "Hurto","Receptación","Robo a edificaciones","Robo a vivienda","Robo de ganado/agrícola","Robo a comercio",
                     "Robo de vehículos","Tacha de vehículos","Contrabando (licor/cigarrillos/medicinas/ropa/calzado)",
                     "Tráfico ilegal de personas (coyotaje)","Otro"],
         "appearance":None,"choice_filter":None,"relevant":"${info_estructuras}='Sí'"},
        {"tipo_ui":"Texto (corto)","label":"¿Cuál es el nombre de la estructura criminal?","name":"nombre_estructura","required":True,
         "opciones":[],"appearance":None,"choice_filter":None,"relevant":"${info_estructuras}='Sí'"},
        {"tipo_ui":"Párrafo (texto largo)","label":"Indique quién(es) se dedican a estos actos (nombres, apellidos, alias, domicilio)",
         "name":"quienes","required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":"${info_estructuras}='Sí'"},
        {"tipo_ui":"Párrafo (texto largo)","label":"Modo de operar (venta exprés/vía pública, asalto, desplazamiento, etc.)",
         "name":"modus_operandi","required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":"${info_estructuras}='Sí'"},
        {"tipo_ui":"Texto (corto)","label":"¿Cuál es la zona más insegura en su área de responsabilidad?","name":"zona_insegura",
         "required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":None},
        {"tipo_ui":"Párrafo (texto largo)","label":"Describa por qué considera que esa zona es insegura","name":"por_que_insegura",
         "required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":None},

        # ——— Página 4: Información de Interés Interno
        {"tipo_ui":"Párrafo (texto largo)","label":"¿Qué recurso hace falta en su delegación para mejorar el servicio?",
         "name":"recurso_falta","required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":None},
        {"tipo_ui":"Selección única","label":"¿Las condiciones de su delegación son aptas para sus necesidades básicas?",
         "name":"condiciones_aptas","required":True,"opciones":["Sí","No"],"appearance":None,"choice_filter":None,"relevant":None},
        {"tipo_ui":"Párrafo (texto largo)","label":"¿Cuáles condiciones se pueden mejorar?","name":"condiciones_mejorar","required":True,
         "opciones":[],"appearance":None,"choice_filter":None,"relevant":"${condiciones_aptas}='No'"},
        {"tipo_ui":"Selección única","label":"¿Hace falta capacitación para el personal en su delegación?",
         "name":"falta_capacitacion","required":True,"opciones":["Sí","No"],"appearance":None,"choice_filter":None,"relevant":None},
        {"tipo_ui":"Párrafo (texto largo)","label":"Especifique en qué áreas necesita capacitación","name":"areas_capacitacion",
         "required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":"${falta_capacitacion}='Sí'"},
        {"tipo_ui":"Selección única","label":"¿Se siente motivado por la institución para brindar un buen servicio?",
         "name":"motivado","required":True,"opciones":["Sí","No"],"appearance":None,"choice_filter":None,"relevant":None},
        {"tipo_ui":"Párrafo (texto largo)","label":"Explique por qué no se siente motivado","name":"motivo_no","required":True,
         "opciones":[],"appearance":None,"choice_filter":None,"relevant":"${motivado}='No'"},
        {"tipo_ui":"Selección única","label":"¿Mantiene conocimiento de situaciones anómalas en su delegación? (confidencial)",
         "name":"anomalias","required":True,"opciones":["Sí","No"],"appearance":None,"choice_filter":None,"relevant":None},
        {"tipo_ui":"Párrafo (texto largo)","label":"Especifique cuáles son las situaciones anómalas","name":"detalle_anomalias",
         "required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":"${anomalias}='Sí'"},
        {"tipo_ui":"Selección única","label":"¿Conoce oficiales relacionados con estructuras criminales o delitos?",
         "name":"oficiales_relacionados","required":True,"opciones":["Sí","No"],"appearance":None,"choice_filter":None,"relevant":None},
        {"tipo_ui":"Párrafo (texto largo)","label":"Describa la situación (estructura, tipo de actividad, oficiales, funciones, alias, etc.)",
         "name":"describe_situacion","required":True,"opciones":[],"appearance":None,"choice_filter":None,
         "relevant":"${oficiales_relacionados}='Sí'"},
        {"tipo_ui":"Texto (corto)","label":"Medio de contacto para ampliar (opcional)","name":"medio_contacto",
         "required":False,"opciones":[],"appearance":None,"choice_filter":None,"relevant":None},
    ]
    st.session_state.preguntas = seed
    st.session_state.reglas_visibilidad = []
    st.session_state.reglas_finalizar = []
    st.session_state.seed_cargado = True

# ========= Sidebar: metadatos + cascadas =========
with st.sidebar:
    st.header("⚙️ Configuración")
    form_title = st.text_input("Título del formulario", value="Encuesta Fuerza Pública")
    idioma = st.selectbox("Idioma por defecto", options=["es","en"], index=0)
    version_auto = datetime.now().strftime("%Y%m%d%H%M")
    version = st.text_input("Versión", value=version_auto)

    st.markdown("---")
    st.caption("🚀 Agregar ejemplo Cantón→Distrito (CR)")
    if st.button("Insertar cascada", use_container_width=True):
        usados = {q["name"] for q in st.session_state.preguntas}
        name_canton = asegurar_nombre_unico("canton", usados)
        st.session_state.preguntas.append({
            "tipo_ui":"Selección única","label":"Seleccione el Cantón","name":name_canton,"required":True,
            "opciones":["Alajuela (Central)","Sabanilla","Desamparados"],"appearance":None,"choice_filter":None,"relevant":None
        })
        usados.add(name_canton)
        name_distrito = asegurar_nombre_unico("distrito", usados)
        st.session_state.preguntas.append({
            "tipo_ui":"Selección única","label":"Seleccione el Distrito","name":name_distrito,"required":True,
            "opciones":["— se rellena con la lista extendida —"],"appearance":None,
            "choice_filter":f"canton_key=${{{name_canton}}}","relevant":None
        })
        if "choices_ext_rows" not in st.session_state: st.session_state.choices_ext_rows = []
        st.session_state.choices_extra_cols.update({"canton_key"})
        def add_choices(list_name, items, key):
            for lbl in items:
                st.session_state.choices_ext_rows.append({
                    "list_name": list_name,"name": slugify_name(lbl),"label": lbl,"canton_key": key
                })
        list_distrito = f"list_{name_distrito}"
        add_choices(list_distrito,
            ["Alajuela","San José","Carrizal","San Antonio","Guácima","San Isidro","Sabanilla","San Rafael","Río Segundo",
             "Desamparados","Turrúcares","Tambor","Garita","Sarapiquí"], "Alajuela (Central)")
        add_choices(list_distrito, ["Centro","Este","Oeste","Norte","Sur"], "Sabanilla")
        add_choices(list_distrito,
            ["Desamparados","San Miguel","San Juan de Dios","San Rafael Arriba","San Antonio","Frailes","Patarrá",
             "San Cristóbal","Rosario","Damas","San Rafael Abajo","Gravilias","Los Guido"], "Desamparados")
        st.success("Cascada agregada.")
        _rerun()

# ========= Constructor UI (agregar/editar/ordenar) =========
st.subheader("📝 Diseña tus preguntas")
with st.form("form_add_q", clear_on_submit=False):
    tipo_ui = st.selectbox("Tipo de pregunta", options=TIPOS)
    label = st.text_input("Etiqueta (lo que verá el encuestado)")
    sugerido = slugify_name(label) if label else ""
    col_n1, col_n2, col_n3 = st.columns([2,1,1])
    with col_n1:
        name = st.text_input("Nombre interno (name)", value=sugerido)
    with col_n2:
        required = st.checkbox("Requerida", value=False)
    with col_n3:
        appearance = st.text_input("Appearance (opcional)", value="")
    opciones = []
    if tipo_ui in ("Selección única","Selección múltiple"):
        st.markdown("**Opciones (una por línea)**")
        txt_opts = st.text_area("Opciones", height=120, placeholder="Sí\nNo")
        if txt_opts.strip(): opciones = [o.strip() for o in txt_opts.splitlines() if o.strip()]
    add = st.form_submit_button("➕ Agregar pregunta")
if add:
    if not label.strip():
        st.warning("Agrega una etiqueta.")
    else:
        base = slugify_name(name or label); usados = {q["name"] for q in st.session_state.preguntas}
        unico = asegurar_nombre_unico(base, usados)
        st.session_state.preguntas.append({
            "tipo_ui": tipo_ui,"label": label.strip(),"name": unico,"required": required,
            "opciones": opciones,"appearance": (appearance.strip() or None),
            "choice_filter": None,"relevant": None
        })
        st.success(f"Pregunta agregada: **{label}** (name: `{unico}`)")

st.subheader("📚 Preguntas (ordénalas y edítalas)")
if not st.session_state.preguntas:
    st.info("Aún no has agregado preguntas.")
else:
    for idx, q in enumerate(st.session_state.preguntas):
        with st.container(border=True):
            c1, c2, c3, c4, c5 = st.columns([4,2,2,2,2])
            c1.markdown(f"**{idx+1}. {q['label']}**")
            meta = f"type: {q['tipo_ui']} • name: `{q['name']}` • requerida: {'sí' if q.get('required') else 'no'}"
            if q.get("appearance"): meta += f" • appearance: `{q['appearance']}`"
            if q.get("choice_filter"): meta += f" • choice_filter: `{q['choice_filter']}`"
            if q.get("relevant"): meta += f" • relevant: `{q['relevant']}`"
            c1.caption(meta)
            if q["tipo_ui"] in ("Selección única","Selección múltiple"):
                c1.caption("Opciones: " + ", ".join(q.get("opciones") or []))
            up   = c2.button("⬆️ Subir", key=f"up_{idx}", use_container_width=True, disabled=(idx==0))
            down = c3.button("⬇️ Bajar", key=f"down_{idx}", use_container_width=True, disabled=(idx==len(st.session_state.preguntas)-1))
            edit = c4.button("✏️ Editar", key=f"edit_{idx}", use_container_width=True)
            borrar = c5.button("🗑️ Eliminar", key=f"del_{idx}", use_container_width=True)
            if up:
                st.session_state.preguntas[idx-1], st.session_state.preguntas[idx] = st.session_state.preguntas[idx], st.session_state.preguntas[idx-1]; _rerun()
            if down:
                st.session_state.preguntas[idx+1], st.session_state.preguntas[idx] = st.session_state.preguntas[idx], st.session_state.preguntas[idx+1]; _rerun()
            if edit:
                st.markdown("**Editar esta pregunta**")
                ne_label = st.text_input("Etiqueta", value=q["label"], key=f"e_label_{idx}")
                ne_name  = st.text_input("Name", value=q["name"], key=f"e_name_{idx}")
                ne_req   = st.checkbox("Requerida", value=q.get("required", False), key=f"e_req_{idx}")
                ne_app   = st.text_input("Appearance", value=q.get("appearance") or "", key=f"e_app_{idx}")
                ne_cf    = st.text_input("choice_filter", value=q.get("choice_filter") or "", key=f"e_cf_{idx}")
                ne_rel   = st.text_input("relevant", value=q.get("relevant") or "", key=f"e_rel_{idx}")
                ne_opciones = q.get("opciones") or []
                if q["tipo_ui"] in ("Selección única","Selección múltiple"):
                    ne_opts_txt = st.text_area("Opciones (una por línea)", value="\n".join(ne_opciones), key=f"e_opts_{idx}")
                    ne_opciones = [o.strip() for o in ne_opts_txt.splitlines() if o.strip()]
                col_ok, col_cancel = st.columns(2)
                if col_ok.button("💾 Guardar cambios", key=f"e_save_{idx}", use_container_width=True):
                    new_base = slugify_name(ne_name or ne_label)
                    usados = {qq["name"] for j, qq in enumerate(st.session_state.preguntas) if j != idx}
                    ne_name_final = new_base if new_base not in usados else asegurar_nombre_unico(new_base, usados)
                    q.update({"label": ne_label.strip() or q["label"], "name": ne_name_final, "required": ne_req,
                              "appearance": ne_app.strip() or None, "choice_filter": ne_cf.strip() or None,
                              "relevant": ne_rel.strip() or None})
                    if q["tipo_ui"] in ("Selección única","Selección múltiple"): q["opciones"] = ne_opciones
                    st.success("Cambios guardados."); _rerun()
                if col_cancel.button("Cancelar", key=f"e_cancel_{idx}", use_container_width=True): _rerun()
            if borrar:
                del st.session_state.preguntas[idx]; st.warning("Pregunta eliminada."); _rerun()

# ========= XLSForm (con páginas/grupos) =========
def construir_xlsform(pregs, form_title, idioma, version, reglas_vis, reglas_fin):
    survey_rows, choices_rows = [], []

    # 0) Intro (página 1) dentro de un group
    survey_rows.append({"type":"begin_group","name":"p1_intro","label":"Introducción","appearance":"field-list"})
    survey_rows.append({
        "type":"note","name":"intro",
        "label": f"<b>{form_title}</b><br/>Dirigido a: <i>{dirigido_a}</i><br/><br/>{INTRO_RESUMIDA}",
        "media::image": logo_media_name
    })
    survey_rows.append({"type":"end_group","name":"p1_intro_end"})

    # Preparación de reglas UI extra y “finalizar temprano”
    vis_by_target = {}
    for r in reglas_vis:
        vis_by_target.setdefault(r["target"], []).append({"src": r["src"], "op": r.get("op","="), "values": r.get("values", [])})
    fin_conds = []
    for r in reglas_fin:
        cond = build_relevant_expr([{"src": r["src"], "op": r.get("op","="), "values": r.get("values",[])}])
        if cond: fin_conds.append((r["index_src"], cond))

    # 1) Página 2: Datos generales
    survey_rows.append({"type":"begin_group","name":"p2_datos","label":"Datos generales","appearance":"field-list"})
    bloques_p2 = {"anos_servicio", "edad", "genero", "escolaridad", "manual_puesto",
                  "agente_ii_funcion", "subof1_funcion", "subof2_funcion", "oficial1_funcion"}

    # 2) Página 3: Interés Policial
    bloques_p3 = {"info_estructuras", "actividad_delictual", "nombre_estructura",
                  "quienes", "modus_operandi", "zona_insegura", "por_que_insegura"}

    # 3) Página 4: Interés Interno
    bloques_p4 = {"recurso_falta","condiciones_aptas","condiciones_mejorar","falta_capacitacion",
                  "areas_capacitacion","motivado","motivo_no","anomalias","detalle_anomalias",
                  "oficiales_relacionados","describe_situacion","medio_contacto"}

    def add_question_row(q, i_base):
        name, label, tipo_ui = q["name"], q["label"], q["tipo_ui"]
        required = "yes" if q.get("required") else None
        appearance = q.get("appearance") or None
        choice_filter = q.get("choice_filter") or None
        manual_relevant = q.get("relevant") or None
        x_type, default_app, list_name = map_tipo_to_xlsform(tipo_ui, name)
        if default_app and not appearance: appearance = default_app

        rel_auto = build_relevant_expr(vis_by_target.get(name, []))
        # Fin temprano: si se definió alguna, se impone como AND con not(cond)
        not_conds = []
        for idx_src, cond in fin_conds:
            if idx_src < i_base: not_conds.append(xlsform_not(cond))
        fin_expr = "(" + " and ".join([c for c in not_conds if c]) + ")" if not_conds else None

        relevant_parts = [p for p in [manual_relevant, rel_auto, fin_expr] if p]
        relevant_final = relevant_parts[0] if len(relevant_parts)==1 else ("(" + ") and (".join(relevant_parts) + ")") if relevant_parts else None

        row = {"type": x_type, "name": name, "label": label}
        if required: row["required"] = required
        if appearance: row["appearance"] = appearance
        if choice_filter: row["choice_filter"] = choice_filter
        if relevant_final: row["relevant"] = relevant_final
        survey_rows.append(row)

        if list_name:
            usados=set()
            for opt_label in (q.get("opciones") or []):
                base = slugify_name(str(opt_label)); opt_name = asegurar_nombre_unico(base, usados); usados.add(opt_name)
                choices_rows.append({"list_name": list_name,"name": opt_name,"label": str(opt_label)})

    # Añadir preguntas en sus páginas
    for i, q in enumerate(pregs):
        if q["name"] in bloques_p2: add_question_row(q, i)
    survey_rows.append({"type":"end_group","name":"p2_datos_end"})

    survey_rows.append({"type":"begin_group","name":"p3_ip","label":"Información de Interés Policial","appearance":"field-list"})
    for i, q in enumerate(pregs):
        if q["name"] in bloques_p3: add_question_row(q, i)
    survey_rows.append({"type":"end_group","name":"p3_ip_end"})

    survey_rows.append({"type":"begin_group","name":"p4_ii","label":"Información de Interés Interno","appearance":"field-list"})
    for i, q in enumerate(pregs):
        if q["name"] in bloques_p4: add_question_row(q, i)
    survey_rows.append({"type":"end_group","name":"p4_ii_end"})

    # Choices extendidos (cascadas)
    if "choices_ext_rows" in st.session_state:
        for r in st.session_state.choices_ext_rows:
            choices_rows.append(dict(r))

    # DataFrames (incluye media::image)
    survey_cols_all = set().union(*[set(r.keys()) for r in survey_rows])
    base_cols = ["type","name","label","required","appearance","choice_filter","relevant","media::image"]
    survey_cols = [c for c in base_cols if c in survey_cols_all] + [k for k in sorted(survey_cols_all) if k not in base_cols]
    df_survey = pd.DataFrame(survey_rows, columns=survey_cols)

    choice_cols_all = set().union(*[set(r.keys()) for r in choices_rows]) if choices_rows else set()
    base_choice_cols = ["list_name","name","label"] + [c for c in sorted(choice_cols_all) if c not in {"list_name","name","label"}]
    df_choices = pd.DataFrame(choices_rows, columns=base_choice_cols) if choices_rows else pd.DataFrame(columns=base_choice_cols)

    df_settings = pd.DataFrame([{"form_title": form_title,"version": version,"default_language": idioma}],
                               columns=["form_title","version","default_language"])
    return df_survey, df_choices, df_settings

def descargar_excel_xlsform(df_survey, df_choices, df_settings, nombre_archivo):
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as w:
        df_survey.to_excel(w, "survey", index=False)
        df_choices.to_excel(w, "choices", index=False)
        df_settings.to_excel(w, "settings", index=False)
        wb = w.book; fmt = wb.add_format({"bold":True,"align":"left"})
        for sheet, df in (("survey",df_survey),("choices",df_choices),("settings",df_settings)):
            ws = w.sheets[sheet]; ws.freeze_panes(1,0); ws.set_row(0, None, fmt)
            for i,c in enumerate(df.columns): ws.set_column(i,i, max(14, min(40, len(str(c))+10)))
    buf.seek(0)
    st.download_button("📥 Descargar XLSForm", data=buf, file_name=nombre_archivo,
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       use_container_width=True)

# ========= Exportar / Vista previa =========
st.markdown("---")
st.subheader("📦 Generar XLSForm (Excel) para Survey123")

if st.button("🧮 Construir XLSForm", use_container_width=True, disabled=not st.session_state.preguntas):
    try:
        names = [q["name"] for q in st.session_state.preguntas]
        if len(names) != len(set(names)):
            st.error("Hay 'name' duplicados. Asegura unicidad antes de exportar.")
        else:
            df_survey, df_choices, df_settings = construir_xlsform(
                st.session_state.preguntas,
                form_title=st.sidebar.session_state.get("Título del formulario", "Encuesta Fuerza Pública") if False else st.session_state.get("form_title",""),
                idioma=st.session_state.get("idioma","es") if False else "es",
                version=datetime.now().strftime("%Y%m%d%H%M"),
                reglas_vis=st.session_state.reglas_visibilidad,
                reglas_fin=st.session_state.reglas_finalizar
            )
            # Corrige metadatos con los actuales de UI
            df_settings.loc[0,"form_title"] = st.session_state.get("form_title_override", None) or st.session_state.get("form_title","") or "Encuesta Fuerza Pública"
            df_settings.loc[0,"default_language"] = "es"
            df_settings.loc[0,"version"] = st.session_state.get("version_override", None) or datetime.now().strftime("%Y%m%d%H%M")

            st.success("XLSForm construido. Vista previa:")
            c1, c2, c3 = st.columns(3)
            with c1: st.markdown("**Hoja: survey**"); st.dataframe(df_survey, use_container_width=True, hide_index=True)
            with c2: st.markdown("**Hoja: choices**"); st.dataframe(df_choices, use_container_width=True, hide_index=True)
            with c3: st.markdown("**Hoja: settings**"); st.dataframe(df_settings, use_container_width=True, hide_index=True)

            nombre_archivo = slugify_name("Encuesta Fuerza Pública") + "_xlsform.xlsx"
            descargar_excel_xlsform(df_survey, df_choices, df_settings, nombre_archivo)

            if st.session_state.get("_logo_bytes"):
                st.download_button("📥 Descargar logo para carpeta media",
                                   data=st.session_state["_logo_bytes"],
                                   file_name=logo_media_name, mime="image/png",
                                   use_container_width=True)
            else:
                st.caption(f"Usando logo por defecto: **{st.session_state.get('_logo_name','001.png')}**. "
                           "Copia ese PNG a la carpeta **media** del proyecto Survey123.")

            st.info("En **Survey123 Connect**, crea la encuesta desde el XLSForm y coloca el PNG en la carpeta **media** con el MISMO nombre que aparece en `media::image`.")
    except Exception as e:
        st.error(f"Error al generar el XLSForm: {e}")

