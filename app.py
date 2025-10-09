# -*- coding: utf-8 -*-
# App: Constructor de Encuestas → Exporta XLSForm para Survey123
# Edición: Fuerza Pública (preguntas exactas + condicionales + logo + todo editable)

import re, json
from io import BytesIO
from datetime import datetime

import streamlit as st
import pandas as pd

# ==========================
# Configuración de la app
# ==========================
st.set_page_config(page_title="Constructor de Encuestas – Fuerza Pública", layout="wide")
st.title("🧩 Constructor de Encuestas → XLSForm para ArcGIS Survey123")

st.markdown("""
Crea tu cuestionario y **exporta un XLSForm** (Excel con hojas `survey`, `choices`, `settings`) listo para publicar en **ArcGIS Survey123**.
- **Preguntas visibles, editables, reordenables y eliminables**
- **Condicionales** (`relevant`) tal cual indicaste
- **Logo** y **¿A quién va dirigido?** en cabecera
- **Exporta/Importa** proyecto (JSON) + **Descarga XLSForm**
""")

# ==========================
# Utilidades
# ==========================
def _rerun():
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()

TIPOS = [
    "Texto (corto)", "Párrafo (texto largo)", "Número",
    "Selección única", "Selección múltiple", "Fecha", "Hora", "GPS (ubicación)"
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

# ==========================
# Logo + destinatario en cabecera
# ==========================
DEFAULT_LOGO_PATH = "001.png"
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
        "Nombre del archivo para media::image (Survey123)",
        value=st.session_state.get("_logo_name","001.png"),
        help="Este nombre debe coincidir con el PNG que copies a la carpeta `media` del proyecto en Survey123 Connect."
    )
    st.markdown(f"<h5 style='text-align:center'>📋 {dirigido_a}</h5>", unsafe_allow_html=True)

# ==========================
# Sidebar: Metadatos + Export/Import
# ==========================
with st.sidebar:
    st.header("⚙️ Configuración")
    form_title = st.text_input("Título del formulario", value="Encuesta Fuerza Pública")
    idioma = st.selectbox("Idioma por defecto (default_language)", options=["es","en"], index=0)
    version = st.text_input("Versión (settings.version)", value=datetime.now().strftime("%Y%m%d%H%M"))

    st.markdown("---")
    st.caption("💾 Exporta/Importa tu proyecto (JSON)")
    col_exp, col_imp = st.columns([1,1])
    with col_exp:
        if st.button("Exportar proyecto (JSON)", use_container_width=True):
            proj = {
                "form_title": form_title,
                "idioma": idioma,
                "version": version,
                "preguntas": st.session_state.get("preguntas", []),
            }
            jbuf = BytesIO(json.dumps(proj, ensure_ascii=False, indent=2).encode("utf-8"))
            st.download_button("Descargar JSON", data=jbuf, file_name="proyecto_encuesta.json",
                               mime="application/json", use_container_width=True)
    with col_imp:
        upj = st.file_uploader("Importar JSON", type=["json"], label_visibility="collapsed")
        if upj is not None:
            try:
                raw = upj.read().decode("utf-8")
                data = json.loads(raw)
                st.session_state.preguntas = list(data.get("preguntas", []))
                st.success("Proyecto importado.")
                _rerun()
            except Exception as e:
                st.error(f"No se pudo importar el JSON: {e}")

# ==========================
# Estado inicial con PREGUNTAS EXACTAS
# ==========================
if "preguntas" not in st.session_state:
    st.session_state.preguntas = []

if "seed_cargado" not in st.session_state:
    seed = [
        # ——— Segunda Pagina
        {"tipo_ui":"Número","label":"Años de servicio (Numérica)","name":"anos_servicio","required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":None},
        {"tipo_ui":"Número","label":"Edad (Numérica)","name":"edad","required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":None},
        {"tipo_ui":"Selección única","label":"Genero","name":"genero","required":True,"opciones":["Masculino","Femenino","LGBTQ+"],"appearance":None,"choice_filter":None,"relevant":None},
        {"tipo_ui":"Selección única","label":"Escolaridad","name":"escolaridad","required":True,
         "opciones":["Ninguna","Primaria","Primaria Incompleta","Secundaria","Secundaria Incompleta","Universidad Completa","Universidad Incompleta","Técnico"],
         "appearance":None,"choice_filter":None,"relevant":None},
        {"tipo_ui":"Selección única","label":"¿Qué clase del manual de puestos desempeña en su delegación?","name":"manual_puesto","required":True,
         "opciones":["Agente I","Agente II","Sub Oficial I","Sub Oficial II","Oficial I","Jefe de Delegación","Sub Jefe de Delegación"],
         "appearance":None,"choice_filter":None,"relevant":None},

        # Subopciones exactas según selección
        {"tipo_ui":"Selección única","label":"Agente II","name":"agente_ii","required":False,
         "opciones":["Agente de Fronteras","Agente de Seguridad Turistica","Agente de Programas Preventivos","Agente de comunicaciones","Agente Armero","Agente Conductor de Vehículos Oficiales","Agente de Operaciones"],
         "appearance":None,"choice_filter":None,"relevant":"${manual_puesto}='Agente II'"},
        {"tipo_ui":"Selección única","label":"Sub Oficial I","name":"sub_oficial_i","required":False,
         "opciones":["Encargado Equipo Operativo Policial","Encargado Equipo de Seguridad Turística","Encargado Equipo de Fronteras","Encargado Programas Preventivos","Encargado Agentes Armeros","Encargado de Equipo de Comunicaciones"],
         "appearance":None,"choice_filter":None,"relevant":"${manual_puesto}='Sub Oficial I'"},
        {"tipo_ui":"Selección única","label":"Sub Oficial II","name":"sub_oficial_ii","required":False,
         "opciones":["Encargado Subgrupo Operativo Policial","Encargado Subgrupo de Seguridad Turística","Encargado Subgrupo de Fronteras","Oficial de Guardia","Encargado de Operaciones"],
         "appearance":None,"choice_filter":None,"relevant":"${manual_puesto}='Sub Oficial II'"},
        {"tipo_ui":"Selección única","label":"Oficial I","name":"oficial_i","required":False,
         "opciones":["Jefe Delegación Distrital","Encargado Grupo Operativo Policial"],
         "appearance":None,"choice_filter":None,"relevant":"${manual_puesto}='Oficial I'"},

        # ——— Informacion de Interés Policial
        {"tipo_ui":"Selección única","label":"¿Mantiene usted información relacionada a personas, grupos de personas, objetivos reincidentes, objetivos de interés policial o estructuras criminales que se dediquen a realizar actos ilícitos en su jurisdicción?*","name":"mantiene_info","required":True,"opciones":["Si","No"],"appearance":None,"choice_filter":None,"relevant":None},
        {"tipo_ui":"Selección única","label":"¿Qué tipo de actividad delictual es la que se realiza por parte de estas personas?*","name":"tipo_actividad","required":True,
         "opciones":["Bunker(espacio cerrado para la venta y distribucion de drogas)","Delitos contra la vida (Homicidios, heridos)","Venta y consumo de drogas en vía pública","Delitos sexuales","Asalto (a personas, comercio, vivienda, transporte público)","Daños a la propiedad. (Destruir, inutilizar o desaparecer)","Estafas (Billetes, documentos, oro, lotería falsos)","Estafa Informática (computadora, tarjetas, teléfonos, etc.)","Extorsión (intimidar o amenazar a otras personas con fines de lucro)","Hurto","Receptación (persona que adquiere, recibe u oculta artículos provenientes de un delito en el que no participó)","Robo a edificaciones","Robo a vivienda","Robo de ganado y agrícola","Robo a comercio","Robo de vehículos","Tacha de vehículos","Contrabando (licor, cigarrillos, medicinas, ropa, calzado, etc.)","Tráfico ilegal de personas (coyotaje)","Otro"],
         "appearance":None,"choice_filter":None,"relevant":"${mantiene_info}='Si'"},
        {"tipo_ui":"Texto (corto)","label":"¿Cuál es el nombre de la estructura criminal?*","name":"nombre_estructura","required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":"${mantiene_info}='Si'"},
        {"tipo_ui":"Párrafo (texto largo)","label":"Indique quién o quienes se dedican a estos actos criminales.(nombres, apellidos, alias, dominicilio)*","name":"quienes","required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":"${mantiene_info}='Si'"},
        {"tipo_ui":"Párrafo (texto largo)","label":"Modo de operar de esta estructura criminal (por ejemplo: venta de droga expres o en via publica, asalto a mano armada, modo de desplazamiento, etc.)*","name":"modus_operandi","required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":"${mantiene_info}='Si'"},
        {"tipo_ui":"Texto (corto)","label":"¿Cuál es el lugar o zona que usted considera más inseguro dentro de su area de responsabilidad?*","name":"zona_insegura","required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":None},
        {"tipo_ui":"Párrafo (texto largo)","label":"Describa por qué considera que esa zona es insegura*","name":"por_que_insegura","required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":None},

        # ——— Informacion de Interés Interno
        {"tipo_ui":"Párrafo (texto largo)","label":"¿Qué recurso cree usted que hacen falta en su delegación para brindar una mejor labor al servicio a la ciudadanía?","name":"recurso_falta","required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":None},
        {"tipo_ui":"Selección única","label":"¿Considera usted que las condiciones de su delegación son aptas para satisfacer sus necesidades básicas? (buen dormir, alimentación, recurso móvil, etc.)","name":"condiciones_aptas","required":True,"opciones":["Si","No"],"appearance":None,"choice_filter":None,"relevant":None},
        {"tipo_ui":"Párrafo (texto largo)","label":"Cúales condiciones considera que se pueden mejorar.","name":"condiciones_mejorar","required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":"${condiciones_aptas}='No'"},
        {"tipo_ui":"Selección única","label":"¿Considera usted que hace falta capacitación para el personal en su delegacion policial?*","name":"falta_capacitacion","required":True,"opciones":["Si","No"],"appearance":None,"choice_filter":None,"relevant":None},
        {"tipo_ui":"Párrafo (texto largo)","label":"Especifique en que áreas necesita capacitación*","name":"areas_capacitacion","required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":"${falta_capacitacion}='Si'"},
        {"tipo_ui":"Selección única","label":"¿Se siente usted motivado por la institución para brindar un buen servicio a la ciudadanía?*","name":"motivado","required":True,"opciones":["Si","No"],"appearance":None,"choice_filter":None,"relevant":None},
        {"tipo_ui":"Párrafo (texto largo)","label":"Especifique por qué lo considera así.*","name":"motivo_no","required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":"${motivado}='No'"},
        {"tipo_ui":"Selección única","label":"¿Mantiene usted conocimiento de situaciones anómalas que sucedan en su delegación? (Recuerde la información suministrada es de carácter confidencial)*","name":"anomalias","required":True,"opciones":["Si","No"],"appearance":None,"choice_filter":None,"relevant":None},
        {"tipo_ui":"Párrafo (texto largo)","label":"Especifique cuáles son las situaciones anómalas que se refiere*","name":"detalle_anomalias","required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":"${anomalias}='Si'"},
        {"tipo_ui":"Selección única","label":"¿Conoce oficiales de Fuerza Pública que se relacionen con alguna estructura criminal o cometan algún delito?*","name":"oficiales_relacionados","required":True,"opciones":["Si","No"],"appearance":None,"choice_filter":None,"relevant":None},
        {"tipo_ui":"Párrafo (texto largo)","label":"Describa la situación de la cual tiene conocimiento. (aporte nombre de la estructura, tipo de actividad, nombre de oficiales, función del oficial dentro de la organización, alias, etc.)*","name":"describe_situacion","required":True,"opciones":[],"appearance":None,"choice_filter":None,"relevant":"${oficiales_relacionados}='Si'"},
        {"tipo_ui":"Texto (corto)","label":"Desea, de manera voluntaria, dejar un medio de contacto para brindar más información (correo electrónico, número de teléfono, etc.)","name":"medio_contacto","required":False,"opciones":[],"appearance":None,"choice_filter":None,"relevant":None},
    ]
    st.session_state.preguntas = seed
    st.session_state.seed_cargado = True

# ==========================
# Constructor: ver, reordenar, editar, eliminar, agregar
# ==========================
st.subheader("📝 Preguntas (precargadas y editables)")

if not st.session_state.preguntas:
    st.info("No hay preguntas. Agrega nuevas con el formulario de abajo.")
else:
    for idx, q in enumerate(st.session_state.preguntas):
        with st.container(border=True):
            c1, c2, c3, c4, c5 = st.columns([5,1,1,1,1])
            c1.markdown(f"**{idx+1}. {q['label']}**")
            meta = f"Tipo: {q['tipo_ui']}  •  name: `{q['name']}`  •  requerida: {'sí' if q['required'] else 'no'}"
            if q.get("relevant"): meta += f"  •  relevant: `{q['relevant']}`"
            if q.get("appearance"): meta += f"  •  appearance: `{q['appearance']}`"
            c1.caption(meta)
            if q["tipo_ui"] in ("Selección única","Selección múltiple"):
                c1.caption("Opciones: " + ", ".join(q.get("opciones") or []))

            up = c2.button("⬆️", key=f"up_{idx}", use_container_width=True, help="Subir", disabled=(idx==0))
            down = c3.button("⬇️", key=f"down_{idx}", use_container_width=True, help="Bajar", disabled=(idx==len(st.session_state.preguntas)-1))
            edit = c4.button("✏️", key=f"edit_{idx}", use_container_width=True, help="Editar")
            borrar = c5.button("🗑️", key=f"del_{idx}", use_container_width=True, help="Eliminar")

            if up:
                st.session_state.preguntas[idx-1], st.session_state.preguntas[idx] = st.session_state.preguntas[idx], st.session_state.preguntas[idx-1]
                _rerun()
            if down:
                st.session_state.preguntas[idx+1], st.session_state.preguntas[idx] = st.session_state.preguntas[idx], st.session_state.preguntas[idx+1]
                _rerun()

            if edit:
                st.markdown("**Editar**")
                ne_label = st.text_input("Etiqueta (texto exacto)", value=q["label"], key=f"e_label_{idx}")
                ne_name  = st.text_input("Name (sin espacios)", value=q["name"], key=f"e_name_{idx}")
                ne_req   = st.checkbox("Requerida", value=q["required"], key=f"e_req_{idx}")
                ne_app   = st.text_input("Appearance (opcional)", value=q.get("appearance") or "", key=f"e_app_{idx}")
                ne_rel   = st.text_input("relevant (opcional)", value=q.get("relevant") or "", key=f"e_rel_{idx}")

                ne_opciones = q.get("opciones") or []
                if q["tipo_ui"] in ("Selección única","Selección múltiple"):
                    ne_opts_txt = st.text_area("Opciones (una por línea)", value="\n".join(ne_opciones), key=f"e_opts_{idx}")
                    ne_opciones = [o.strip() for o in ne_opts_txt.splitlines() if o.strip()]

                col_ok, col_cancel = st.columns(2)
                if col_ok.button("💾 Guardar cambios", key=f"e_save_{idx}", use_container_width=True):
                    new_base = slugify_name(ne_name or ne_label)
                    usados = {qq["name"] for j, qq in enumerate(st.session_state.preguntas) if j != idx}
                    ne_name_final = new_base if new_base not in usados else asegurar_nombre_unico(new_base, usados)
                    st.session_state.preguntas[idx]["label"] = ne_label.strip() or q["label"]
                    st.session_state.preguntas[idx]["name"] = ne_name_final
                    st.session_state.preguntas[idx]["required"] = ne_req
                    st.session_state.preguntas[idx]["appearance"] = ne_app.strip() or None
                    st.session_state.preguntas[idx]["relevant"] = ne_rel.strip() or None
                    if q["tipo_ui"] in ("Selección única","Selección múltiple"):
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
# Agregar nueva pregunta
# ==========================
st.subheader("➕ Agregar nueva pregunta")
with st.form("form_add_q", clear_on_submit=True):
    tipo_ui = st.selectbox("Tipo", options=TIPOS)
    label = st.text_input("Etiqueta (texto exacto)")
    sugerido = slugify_name(label) if label else ""
    col_n1, col_n2, col_n3 = st.columns([2,1,1])
    with col_n1:
        name = st.text_input("Name (sin espacios/minúsculas)", value=sugerido)
    with col_n2:
        required = st.checkbox("Requerida", value=False)
    with col_n3:
        appearance = st.text_input("Appearance (opcional)", value="")
    opciones = []
    if tipo_ui in ("Selección única","Selección múltiple"):
        st.markdown("**Opciones (una por línea)**")
        tx = st.text_area("Opciones", height=120, placeholder="Escribe cada opción en una línea")
        if tx.strip():
            opciones = [o.strip() for o in tx.splitlines() if o.strip()]
    rel = st.text_input("relevant (opcional, ej. ${otra}='Si')")
    add = st.form_submit_button("Agregar")
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
            "relevant": (rel.strip() or None)
        })
        st.success(f"Pregunta agregada: **{label}** (name: `{unico}`)")

# ==========================
# Construcción XLSForm (survey, choices, settings)
# ==========================
def construir_xlsform(pregs, form_title: str, idioma: str, version: str):
    """
    Construye DataFrames: survey, choices, settings.
    - Inserta NOTE inicial con media::image (logo).
    - Exporta condicionales (relevant) embebidas en las preguntas.
    """
    survey_rows = []
    choices_rows = []

    # 0) NOTE inicial con logo
    survey_rows.append({
        "type": "note",
        "name": "intro",
        "label": form_title,
        "media::image": logo_media_name
    })

    # 1) Preguntas
    for q in pregs:
        x_type, default_app, list_name = map_tipo_to_xlsform(q["tipo_ui"], q["name"])
        row = {
            "type": x_type,
            "name": q["name"],
            "label": q["label"]
        }
        if q.get("required"): row["required"] = "yes"
        app = q.get("appearance") or default_app
        if app: row["appearance"] = app
        if q.get("choice_filter"): row["choice_filter"] = q["choice_filter"]
        if q.get("relevant"): row["relevant"] = q["relevant"]
        survey_rows.append(row)

        # Choices si aplica
        if list_name:
            usados = set()
            for opt_label in (q.get("opciones") or []):
                base = slugify_name(str(opt_label))
                opt_name = asegurar_nombre_unico(base, usados)
                usados.add(opt_name)
                choices_rows.append({
                    "list_name": list_name,
                    "name": opt_name,
                    "label": str(opt_label)
                })

    # DataFrames
    # survey: asegurar columnas (incluye media::image)
    survey_cols_all = set()
    for r in survey_rows:
        survey_cols_all.update(r.keys())
    base_cols = ["type","name","label","required","appearance","choice_filter","relevant","media::image"]
    survey_cols = [c for c in base_cols if c in survey_cols_all]
    for k in sorted(survey_cols_all):
        if k not in survey_cols:
            survey_cols.append(k)
    df_survey  = pd.DataFrame(survey_rows,  columns=survey_cols)

    # choices
    choices_cols_all = set()
    for r in choices_rows:
        choices_cols_all.update(r.keys())
    base_choice_cols = ["list_name","name","label"]
    for extra in sorted(choices_cols_all):
        if extra not in base_choice_cols:
            base_choice_cols.append(extra)
    df_choices = pd.DataFrame(choices_rows, columns=base_choice_cols) if choices_rows else pd.DataFrame(columns=base_choice_cols)

    # settings
    df_settings = pd.DataFrame([{
        "form_title": form_title,
        "version": version,
        "default_language": idioma
    }], columns=["form_title","version","default_language"])

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
            for col_idx, col_name in enumerate(df.columns):
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

if st.button("🧮 Construir XLSForm", use_container_width=True, disabled=not st.session_state.preguntas):
    try:
        names = [q["name"] for q in st.session_state.preguntas]
        if len(names) != len(set(names)):
            st.error("Hay 'name' duplicados. Edita las preguntas para que cada 'name' sea único.")
        else:
            df_survey, df_choices, df_settings = construir_xlsform(
                st.session_state.preguntas,
                form_title=form_title.strip() or "Encuesta Fuerza Pública",
                idioma=idioma,
                version=version.strip() or datetime.now().strftime("%Y%m%d%H%M"),
            )

            st.success("XLSForm construido. Vista previa rápida:")
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

            nombre_archivo = slugify_name(form_title or "Encuesta Fuerza Pública") + "_xlsform.xlsx"
            descargar_excel_xlsform(df_survey, df_choices, df_settings, nombre_archivo=nombre_archivo)

            # Botón para descargar el logo subido (para carpeta media en Survey123)
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
2) Crea **nueva encuesta desde archivo** y selecciona el XLSForm descargado.
3) Copia el PNG del logo a la carpeta **media** del proyecto con el MISMO nombre que aparece en `media::image`.
4) Publica. Las condiciones (`relevant`) se aplican automáticamente.
""")
    except Exception as e:
        st.error(f"Ocurrió un error al generar el XLSForm: {e}")
