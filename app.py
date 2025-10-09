# -*- coding: utf-8 -*-
# App: Constructor de Encuestas → Exporta XLSForm para Survey123
# (páginas, condicionales exactas, intro con logo)
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
- **Páginas** con `begin_group/end_group` y `appearance=field-list`.
- **Listas en cascada** (ejemplo Cantón→Distrito CR) vía **choice_filter**.
""")

# ==========================
# Utilidades
# ==========================
def _rerun():
    if hasattr(st, "rerun"): st.rerun()
    else: st.experimental_rerun()

TIPOS = [
    "Texto (corto)", "Párrafo (texto largo)", "Número",
    "Selección única", "Selección múltiple", "Fecha", "Hora", "GPS (ubicación)"
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
    if tipo_ui == "Número": return ("integer", None, None)  # usa 'decimal' si prefieres
    if tipo_ui == "Selección única": return (f"select_one list_{name}", None, f"list_{name}")
    if tipo_ui == "Selección múltiple": return (f"select_multiple list_{name}", None, f"list_{name}")
    if tipo_ui == "Fecha": return ("date", None, None)
    if tipo_ui == "Hora": return ("time", None, None)
    if tipo_ui == "GPS (ubicación)": return ("geopoint", None, None)
    return ("text", None, None)

def xlsform_or_expr(conds):
    if not conds: return None
    return conds[0] if len(conds) == 1 else "(" + " or ".join(conds) + ")"

def xlsform_not(expr): return None if not expr else f"not({expr})"

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

# ==========================
# Intro (resumida) + logo en UI
# ==========================
INTRO_RESUMIDA = (
    "Con el fin de fortalecer la seguridad en los territorios, esta encuesta recoge "
    "percepciones y datos operativos del personal de Fuerza Pública sobre riesgos, delitos "
    "y necesidades internas de la delegación. La información es confidencial y se usará "
    "exclusivamente para orientar acciones de mejora y coordinación institucional."
)

DEFAULT_LOGO_PATH = "001.png"
col_logo, col_txt = st.columns([1, 3])
with col_logo:
    up_logo = st.file_uploader("Logo (PNG/JPG)", type=["png","jpg","jpeg"])
    if up_logo:
        st.image(up_logo, caption="Logo cargado", use_container_width=True)
        st.session_state["_logo_bytes"] = up_logo.getvalue()
        st.session_state["_logo_name"]   = up_logo.name
    else:
        try:
            st.image(DEFAULT_LOGO_PATH, caption="Logo (001.png)", use_container_width=True)
            st.session_state["_logo_bytes"] = None
            st.session_state["_logo_name"]   = "001.png"
        except Exception:
            st.warning("Sube un logo (PNG/JPG) para incluirlo en el XLSForm.")
            st.session_state["_logo_bytes"] = None
            st.session_state["_logo_name"]   = "logo.png"

with col_txt:
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    dirigido_a = st.text_input("¿A quién va dirigido?", value="Fuerza Pública – Delegación …")
    logo_media_name = st.text_input(
        "Nombre del archivo para `media::image`",
        value=st.session_state.get("_logo_name","001.png"),
        help="Usa exactamente este nombre en la carpeta `media` de Survey123 Connect."
    )
    st.markdown(
        f"<div style='font-size:20px; text-align:center; margin-top:6px;'><b>{dirigido_a}</b></div>",
        unsafe_allow_html=True
    )

# ==========================
# Estado
# ==========================
for k, v in [("preguntas", []), ("reglas_visibilidad", []), ("reglas_finalizar", []), ("choices_extra_cols", set())]:
    if k not in st.session_state: st.session_state[k] = v

# ==========================
# Seed con textos EXACTOS que pediste
# ==========================
if "seed_cargado" not in st.session_state:
    seed = [
        # ——— Segunda Pagina (datos generales)
        {"tipo_ui":"Número", "label":"Años de servicio (Numérica)", "name":"anos_servicio",
         "required":True, "opciones":[], "appearance":None, "choice_filter":None, "relevant":None},

        {"tipo_ui":"Número", "label":"Edad (Numérica)", "name":"edad",
         "required":True, "opciones":[], "appearance":None, "choice_filter":None, "relevant":None},

        {"tipo_ui":"Selección única", "label":"Genero", "name":"genero",
         "required":True, "opciones":["Masculino","Femenino","LGBTQ+"],
         "appearance":None, "choice_filter":None, "relevant":None},

        {"tipo_ui":"Selección única", "label":"Escolaridad", "name":"escolaridad",
         "required":True, "opciones":["Ninguna","Primaria","Primaria Incompleta","Secundaria","Secundaria Incompleta"," Universidad Completa"," Universidad Incompleta"," Técnico"],
         "appearance":None, "choice_filter":None, "relevant":None},

        {"tipo_ui":"Selección única", "label":"¿Qué clase del manual de puestos desempeña en su delegación?",
         "name":"manual_puesto", "required":True,
         "opciones":["Agente I","Agente II","Sub Oficial I","Sub Oficial II","Oficial I","Jefe de Delegación","Sub Jefe de Delegación"],
         "appearance":None, "choice_filter":None, "relevant":None},

        # — Subpreguntas por manual (títulos exactos como indicaste)
        {"tipo_ui":"Selección única", "label":"Agente II",
         "name":"agente_ii", "required":False,
         "opciones":["Agente de Fronteras","Agente de Seguridad Turistica","Agente de Programas Preventivos","Agente de comunicaciones","Agente Armero","Agente Conductor de Vehículos Oficiales","Agente de Operaciones"],
         "appearance":None, "choice_filter":None, "relevant":"${manual_puesto}='Agente II'"},

        {"tipo_ui":"Selección única", "label":"Sub Oficial I",
         "name":"sub_oficial_i", "required":False,
         "opciones":["Encargado Equipo Operativo Policial","Encargado Equipo de Seguridad Turística","Encargado Equipo de Fronteras","Encargado Programas Preventivos","Encargado Agentes Armeros","Encargado de Equipo de Comunicaciones"],
         "appearance":None, "choice_filter":None, "relevant":"${manual_puesto}='Sub Oficial I'"},

        {"tipo_ui":"Selección única", "label":"Sub Oficial II",
         "name":"sub_oficial_ii", "required":False,
         "opciones":["Encargado Subgrupo Operativo Policial","Encargado Subgrupo de Seguridad Turística","Encargado Subgrupo de Fronteras","Oficial de Guardia","Encargado de Operaciones"],
         "appearance":None, "choice_filter":None, "relevant":"${manual_puesto}='Sub Oficial II'"},

        {"tipo_ui":"Selección única", "label":"Oficial I",
         "name":"oficial_i", "required":False,
         "opciones":["Jefe Delegación Distrital","Encargado Grupo Operativo Policial"],
         "appearance":None, "choice_filter":None, "relevant":"${manual_puesto}='Oficial I'"},

        # ——— Informacion de Interés Policial
        {"tipo_ui":"Selección única", "label":"¿Mantiene usted información relacionada a personas, grupos de personas, objetivos reincidentes, objetivos de interés policial o estructuras criminales que se dediquen a realizar actos ilícitos en su jurisdicción?*",
         "name":"mantiene_info", "required":True, "opciones":["Si","No"], "appearance":None, "choice_filter":None, "relevant":None},

        {"tipo_ui":"Selección única", "label":"¿Qué tipo de actividad delictual es la que se realiza por parte de estas personas?*",
         "name":"tipo_actividad", "required":True,
         "opciones":["Bunker(espacio cerrado para la venta y distribucion de drogas)","Delitos contra la vida (Homicidios, heridos)","Venta y consumo de drogas en vía pública","Delitos sexuales","Asalto (a personas, comercio, vivienda, transporte público)","Daños a la propiedad. (Destruir, inutilizar o desaparecer)","Estafas (Billetes, documentos, oro, lotería falsos)","Estafa Informática (computadora, tarjetas, teléfonos, etc.)","Extorsión (intimidar o amenazar a otras personas con fines de lucro)","Hurto","Receptación (persona que adquiere, recibe u oculta artículos provenientes de un delito en el que no participó)","Robo a edificaciones","Robo a vivienda","Robo de ganado y agrícola","Robo a comercio","Robo de vehículos","Tacha de vehículos","Contrabando (licor, cigarrillos, medicinas, ropa, calzado, etc.)","Tráfico ilegal de personas (coyotaje)","Otro"],
         "appearance":None, "choice_filter":None, "relevant":"${mantiene_info}='Si'"},

        {"tipo_ui":"Texto (corto)", "label":"¿Cuál es el nombre de la estructura criminal?*", "name":"nombre_estructura",
         "required":True, "opciones":[], "appearance":None, "choice_filter":None, "relevant":"${mantiene_info}='Si'"},

        {"tipo_ui":"Párrafo (texto largo)", "label":"Indique quién o quienes se dedican a estos actos criminales.(nombres, apellidos, alias, dominicilio)*",
         "name":"quienes", "required":True, "opciones":[], "appearance":None, "choice_filter":None, "relevant":"${mantiene_info}='Si'"},

        {"tipo_ui":"Párrafo (texto largo)", "label":"Modo de operar de esta estructura criminal (por ejemplo: venta de droga expres o en via publica, asalto a mano armada, modo de desplazamiento, etc.)*",
         "name":"modus_operandi", "required":True, "opciones":[], "appearance":None, "choice_filter":None, "relevant":"${mantiene_info}='Si'"},

        {"tipo_ui":"Texto (corto)", "label":"¿Cuál es el lugar o zona que usted considera más inseguro dentro de su area de responsabilidad?*",
         "name":"zona_insegura", "required":True, "opciones":[], "appearance":None, "choice_filter":None, "relevant":None},

        {"tipo_ui":"Párrafo (texto largo)", "label":"Describa por qué considera que esa zona es insegura*",
         "name":"por_que_insegura", "required":True, "opciones":[], "appearance":None, "choice_filter":None, "relevant":None},

        # ——— Informacion de Interés Interno
        {"tipo_ui":"Párrafo (texto largo)", "label":"¿Qué recurso cree usted que hacen falta en su delegación para brindar una mejor labor al servicio a la ciudadanía?",
         "name":"recurso_falta", "required":True, "opciones":[], "appearance":None, "choice_filter":None, "relevant":None},

        {"tipo_ui":"Selección única", "label":"¿Considera usted que las condiciones de su delegación son aptas para satisfacer sus necesidades básicas? (buen dormir, alimentación, recurso móvil, etc.)",
         "name":"condiciones_aptas", "required":True, "opciones":["Si","No"], "appearance":None, "choice_filter":None, "relevant":None},

        {"tipo_ui":"Párrafo (texto largo)", "label":"Cúales condiciones considera que se pueden mejorar.",
         "name":"condiciones_mejorar", "required":True, "opciones":[], "appearance":None, "choice_filter":None, "relevant":"${condiciones_aptas}='No'"},

        {"tipo_ui":"Selección única", "label":"¿Considera usted que hace falta capacitación para el personal en su delegacion policial?*",
         "name":"falta_capacitacion", "required":True, "opciones":["Si","No"], "appearance":None, "choice_filter":None, "relevant":None},

        {"tipo_ui":"Párrafo (texto largo)", "label":"Especifique en que áreas necesita capacitación*",
         "name":"areas_capacitacion", "required":True, "opciones":[], "appearance":None, "choice_filter":None, "relevant":"${falta_capacitacion}='Si'"},

        {"tipo_ui":"Selección única", "label":"¿Se siente usted motivado por la institución para brindar un buen servicio a la ciudadanía?*",
         "name":"motivado", "required":True, "opciones":["Si","No"], "appearance":None, "choice_filter":None, "relevant":None},

        {"tipo_ui":"Párrafo (texto largo)", "label":"Especifique por qué lo considera así.*",
         "name":"motivo_no", "required":True, "opciones":[], "appearance":None, "choice_filter":None, "relevant":"${motivado}='No'"},

        {"tipo_ui":"Selección única", "label":"¿Mantiene usted conocimiento de situaciones anómalas que sucedan en su delegación? (Recuerde la información suministrada es de carácter confidencial)*",
         "name":"anomalias", "required":True, "opciones":["Si","No"], "appearance":None, "choice_filter":None, "relevant":None},

        {"tipo_ui":"Párrafo (texto largo)", "label":"Especifique cuáles son las situaciones anómalas que se refiere*",
         "name":"detalle_anomalias", "required":True, "opciones":[], "appearance":None, "choice_filter":None, "relevant":"${anomalias}='Si'"},

        {"tipo_ui":"Selección única", "label":"¿Conoce oficiales de Fuerza Pública que se relacionen con alguna estructura criminal o cometan algún delito?*",
         "name":"oficiales_relacionados", "required":True, "opciones":["Si","NO"], "appearance":None, "choice_filter":None, "relevant":None},

        {"tipo_ui":"Párrafo (texto largo)", "label":"Describa la situación de la cual tiene conocimiento. (aporte nombre de la estructura, tipo de actividad, nombre de oficiales, función del oficial dentro de la organización, alias, etc.)*",
         "name":"describe_situacion", "required":True, "opciones":[], "appearance":None, "choice_filter":None, "relevant":"${oficiales_relacionados}='Si'"},

        {"tipo_ui":"Texto (corto)", "label":"Desea, de manera voluntaria, dejar un medio de contacto para brindar más información (correo electrónico, número de teléfono, etc.)",
         "name":"medio_contacto", "required":False, "opciones":[], "appearance":None, "choice_filter":None, "relevant":None},
    ]
    st.session_state.preguntas = seed
    st.session_state.reglas_visibilidad = []   # ya van embebidas en cada pregunta
    st.session_state.reglas_finalizar = []
    st.session_state.seed_cargado = True

# ==========================
# Sidebar: Metadatos y cascadas (opcional)
# ==========================
with st.sidebar:
    st.header("⚙️ Configuración")
    form_title = st.text_input("Título del formulario", value="Encuesta Fuerza Publica")
    idioma     = st.selectbox("Idioma por defecto", options=["es","en"], index=0)
    version    = st.text_input("Versión", value=datetime.now().strftime("%Y%m%d%H%M"))

# ==========================
# Constructor opcional (agregar/editar/ordenar)
# ==========================
st.subheader("📝 Diseña tus preguntas (opcional)")
with st.form("form_add_q", clear_on_submit=False):
    tipo_ui = st.selectbox("Tipo de pregunta", options=TIPOS)
    label = st.text_input("Etiqueta (exacta)")
    sugerido = slugify_name(label) if label else ""
    col_n1, col_n2, col_n3 = st.columns([2,1,1])
    with col_n1: name = st.text_input("Nombre interno (name)", value=sugerido)
    with col_n2: required = st.checkbox("Requerida", value=False)
    with col_n3: appearance = st.text_input("Appearance (opcional)", value="")
    opciones = []
    if tipo_ui in ("Selección única","Selección múltiple"):
        st.markdown("**Opciones (una por línea)**")
        tx = st.text_area("Opciones", height=120, placeholder="Escribe cada opción en una línea")
        if tx.strip(): opciones = [o.strip() for o in tx.splitlines() if o.strip()]
    add = st.form_submit_button("➕ Agregar")
if add and label.strip():
    base = slugify_name(name or label); usados = {q["name"] for q in st.session_state.preguntas}
    unico = asegurar_nombre_unico(base, usados)
    st.session_state.preguntas.append({
        "tipo_ui": tipo_ui, "label": label.strip(), "name": unico, "required": required,
        "opciones": opciones, "appearance": (appearance.strip() or None),
        "choice_filter": None, "relevant": None
    })
    st.success(f"Agregada: {label}")

# ==========================
# Construcción XLSForm (con páginas)
# ==========================
def construir_xlsform(pregs, form_title, idioma, version):
    survey_rows, choices_rows = [], []

    # Página 1: Introducción (NOTE con imagen)
    survey_rows.append({"type":"begin_group","name":"p1","label":"Introducción a la encuesta imagen logo ESS","appearance":"field-list"})
    survey_rows.append({
        "type":"note","name":"intro",
        "label":"Con el objetivo de fortalecer la seguridad en nuestros distintos territorios, nos enfocamos en abordar las principales preocupaciones de seguridad que afectan a la población. Es fundamental colaborar de manera estrecha, no solo con las autoridades gubernamentales locales y otras instituciones, sino también con los funcionarios de Fuerza Pública. Confiamos en que, con el compromiso y la dedicación de los funcionarios de cada Delegación Policial, podremos implementar medidas efectivas para reducir la incidencia de delitos y minimizar los riesgos que directamente impactan en la seguridad de nuestra comunidad. Es de suma importancia destacar que la información proporcionada es tratada con absoluta confidencialidad y se utilizará exclusivamente con el fin de mejorar la seguridad en nuestros territorios. Agradecemos profundamente el esfuerzo continuo de la Fuerza Pública para cumplir con este crucial objetivo y garantizar la tranquilidad de nuestra comunidad. (RESUMEN aplicado en la app).",
        "media::image": logo_media_name
    })
    survey_rows.append({"type":"end_group","name":"p1_end"})

    # Página 2: Segunda Pagina
    survey_rows.append({"type":"begin_group","name":"p2","label":"Segunda Pagina","appearance":"field-list"})
    bloques_p2 = {
        "anos_servicio","edad","genero","escolaridad","manual_puesto",
        "agente_ii","sub_oficial_i","sub_oficial_ii","oficial_i"
    }

    # Página 3: Informacion de Interés Policial
    survey_rows.append({"type":"begin_group","name":"p3","label":"Informacion de Interés Policial","appearance":"field-list"})
    bloques_p3 = {
        "mantiene_info","tipo_actividad","nombre_estructura","quienes","modus_operandi",
        "zona_insegura","por_que_insegura"
    }

    # Página 4: Informacion de Interés Interno
    survey_rows.append({"type":"begin_group","name":"p4","label":"Informacion de Interés Interno","appearance":"field-list"})
    bloques_p4 = {
        "recurso_falta","condiciones_aptas","condiciones_mejorar","falta_capacitacion",
        "areas_capacitacion","motivado","motivo_no","anomalias","detalle_anomalias",
        "oficiales_relacionados","describe_situacion","medio_contacto"
    }

    # Helper para añadir filas y choices
    def add_q(q):
        x_type, default_app, list_name = map_tipo_to_xlsform(q["tipo_ui"], q["name"])
        row = {"type": x_type, "name": q["name"], "label": q["label"]}
        if q.get("required"): row["required"] = "yes"
        app = q.get("appearance") or default_app
        if app: row["appearance"] = app
        if q.get("choice_filter"): row["choice_filter"] = q["choice_filter"]
        if q.get("relevant"): row["relevant"] = q["relevant"]
        survey_rows.append(row)
        if list_name:
            usados=set()
            for opt in (q.get("opciones") or []):
                base=slugify_name(str(opt)); name=asegurar_nombre_unico(base, usados); usados.add(name)
                choices_rows.append({"list_name": list_name, "name": name, "label": str(opt)})

    # Recorrer preguntas y ubicar en su página
    for q in st.session_state.preguntas:
        nm = q["name"]
        if nm in bloques_p2:
            add_q(q)
    survey_rows.append({"type":"end_group","name":"p2_end"})

    for q in st.session_state.preguntas:
        nm = q["name"]
        if nm in bloques_p3:
            add_q(q)
    survey_rows.append({"type":"end_group","name":"p3_end"})

    for q in st.session_state.preguntas:
        nm = q["name"]
        if nm in bloques_p4:
            add_q(q)
    survey_rows.append({"type":"end_group","name":"p4_end"})

    # DataFrames (incluye media::image si está)
    survey_cols_all = set().union(*[set(r.keys()) for r in survey_rows])
    base_cols = ["type","name","label","required","appearance","choice_filter","relevant","media::image"]
    survey_cols = [c for c in base_cols if c in survey_cols_all] + [k for k in sorted(survey_cols_all) if k not in base_cols]
    df_survey = pd.DataFrame(survey_rows, columns=survey_cols)

    # Choices
    choice_cols_all = set().union(*[set(r.keys()) for r in choices_rows]) if choices_rows else set()
    base_choice_cols = ["list_name","name","label"] + [c for c in sorted(choice_cols_all) if c not in {"list_name","name","label"}]
    df_choices = pd.DataFrame(choices_rows, columns=base_choice_cols) if choices_rows else pd.DataFrame(columns=base_choice_cols)

    # Settings
    df_settings = pd.DataFrame([{
        "form_title": form_title,
        "version": version,
        "default_language": idioma
    }], columns=["form_title","version","default_language"])

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

# ==========================
# Exportar / Vista previa
# ==========================
st.markdown("---")
st.subheader("📦 Generar XLSForm (Excel) para Survey123")

if st.button("🧮 Construir XLSForm", use_container_width=True, disabled=not st.session_state.preguntas):
    try:
        # Validación names únicos
        names = [q["name"] for q in st.session_state.preguntas]
        if len(names) != len(set(names)):
            st.error("Hay 'name' duplicados. Edita para que cada 'name' sea único.")
        else:
            df_survey, df_choices, df_settings = construir_xlsform(
                st.session_state.preguntas, form_title.strip() or "Encuesta Fuerza Publica",
                idioma, version
            )
            st.success("XLSForm construido. Vista previa:")
            c1, c2, c3 = st.columns(3)
            with c1: st.markdown("**Hoja: survey**");   st.dataframe(df_survey, use_container_width=True, hide_index=True)
            with c2: st.markdown("**Hoja: choices**");  st.dataframe(df_choices, use_container_width=True, hide_index=True)
            with c3: st.markdown("**Hoja: settings**"); st.dataframe(df_settings, use_container_width=True, hide_index=True)

            descargar_excel_xlsform(
                df_survey, df_choices, df_settings,
                nombre_archivo=slugify_name(form_title)+"_xlsform.xlsx"
            )

            # Descarga del logo (si lo subiste en la app)
            if st.session_state.get("_logo_bytes"):
                st.download_button("📥 Descargar logo para carpeta media",
                                   data=st.session_state["_logo_bytes"],
                                   file_name=logo_media_name, mime="image/png",
                                   use_container_width=True)
            else:
                st.caption(f"Usando logo por defecto: **{st.session_state.get('_logo_name','001.png')}**. "
                           "Copia ese PNG a la carpeta **media** del proyecto en Survey123 Connect (mismo nombre que `media::image`).")
    except Exception as e:
        st.error(f"Ocurrió un error al generar el XLSForm: {e}")
