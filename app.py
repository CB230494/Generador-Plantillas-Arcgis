# -*- coding: utf-8 -*-
# App: Constructor de Encuestas → Exporta XLSForm para Survey123
import re
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
- Soporta **texto**, **párrafo**, **número**, **selección única**, **selección múltiple**, **fecha**, **hora** y **GPS (geopoint)**.
- **Ordena** las preguntas (subir/bajar).
- Marca **requeridas**.
- Define **opciones** para las preguntas con respuestas predeterminadas.
- Al final, descarga el **XLSForm** que puedes **subir a Survey123 Connect** (o al diseñador web de Survey123) para generar la encuesta.
""")

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
    """Convierte una etiqueta en un 'name' válido de XLSForm: minúsculas, sin espacios, a-z0-9_."""
    if not texto:
        return "campo"
    t = texto.lower()
    t = re.sub(r"[áàäâ]", "a", t)
    t = re.sub(r"[éèëê]", "e", t)
    t = re.sub(r"[íìïî]", "i", t)
    t = re.sub(r"[óòöô]", "o", t)
    t = re.sub(r"[úùüû]", "u", t)
    t = re.sub(r"ñ", "n", t)
    t = re.sub(r"[^a-z0-9]+", "_", t)
    t = t.strip("_")
    return t or "campo"

def asegurar_nombre_unico(base: str, usados: set) -> str:
    """Evita duplicados en 'name' de XLSForm añadiendo sufijo _2, _3, ... si es necesario."""
    if base not in usados:
        return base
    i = 2
    while f"{base}_{i}" in usados:
        i += 1
    return f"{base}_{i}"

def map_tipo_to_xlsform(tipo_ui: str, name: str):
    """
    Mapea el tipo elegido en UI al tipo XLSForm.
    Retorna (type_str, appearance, list_name_opcional)
    """
    if tipo_ui == "Texto (corto)":
        return ("text", None, None)
    if tipo_ui == "Párrafo (texto largo)":
        return ("text", "multiline", None)
    if tipo_ui == "Número":
        return ("integer", None, None)  # usa integer; cambia a 'decimal' si lo prefieres
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
    # fallback
    return ("text", None, None)

def construir_xlsform(preguntas, form_title: str, idioma: str, version: str):
    """
    Construye tres DataFrames: survey, choices, settings.
    preguntas: lista de dicts con:
        - tipo_ui
        - label
        - name
        - required (bool)
        - opciones (list[str]) para select_one/multiple
    """
    survey_rows = []
    choices_rows = []

    for q in preguntas:
        name = q["name"]
        label = q["label"]
        tipo_ui = q["tipo_ui"]
        required = "yes" if q.get("required") else None

        x_type, appearance, list_name = map_tipo_to_xlsform(tipo_ui, name)

        row = {
            "type": x_type,
            "name": name,
            "label": label
        }
        if required:
            row["required"] = required
        if appearance:
            row["appearance"] = appearance
        survey_rows.append(row)

        # Si la pregunta es de opciones, construimos 'choices'
        if list_name:
            opciones = q.get("opciones") or []
            # Asegurar names válidos en choices
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

    # Hojas
    df_survey = pd.DataFrame(survey_rows, columns=[c for c in ["type","name","label","required","appearance"]])
    df_choices = pd.DataFrame(choices_rows, columns=["list_name","name","label"]) if choices_rows else pd.DataFrame(columns=["list_name","name","label"])
    df_settings = pd.DataFrame([{
        "form_title": form_title,
        "version": version,
        "default_language": idioma
    }], columns=["form_title", "version", "default_language"])

    return df_survey, df_choices, df_settings

def descargar_excel_xlsform(df_survey, df_choices, df_settings, nombre_archivo: str = "encuesta_xlsform.xlsx"):
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df_survey.to_excel(writer, sheet_name="survey", index=False)
        df_choices.to_excel(writer, sheet_name="choices", index=False)
        df_settings.to_excel(writer, sheet_name="settings", index=False)

        # Un poquito de formato
        wb = writer.book
        fmt_hdr = wb.add_format({"bold": True, "align": "left"})
        for sheet in ("survey", "choices", "settings"):
            ws = writer.sheets[sheet]
            ws.freeze_panes(1, 0)
            ws.set_row(0, None, fmt_hdr)
            # auto ancho sencillo
            for col_idx, col_name in enumerate(pd.read_excel(BytesIO(buffer.getvalue()), sheet_name=sheet).columns if buffer.getbuffer().nbytes else []):
                ws.set_column(col_idx, col_idx, max(12, min(45, len(str(col_name)) + 2)))

    buffer.seek(0)
    st.download_button(
        label=f"📥 Descargar XLSForm ({nombre_archivo})",
        data=buffer,
        file_name=nombre_archivo,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

# ==========================
# Estado
# ==========================
if "preguntas" not in st.session_state:
    st.session_state.preguntas = []

# ==========================
# Sidebar: Metadatos
# ==========================
with st.sidebar:
    st.header("⚙️ Configuración")
    form_title = st.text_input("Título del formulario", value="Encuesta Sembremos Seguridad")
    idioma = st.selectbox("Idioma por defecto (default_language)", options=["es", "en"], index=0)
    version_auto = datetime.now().strftime("%Y%m%d%H%M")
    version = st.text_input("Versión (settings.version)", value=version_auto,
                            help="Survey123 usa este campo para gestionar actualizaciones.")

    st.markdown("---")
    st.caption("💾 Exporta/Importa tu proyecto (JSON) para seguir editando luego.")
    col_exp, col_imp = st.columns([1,1])
    with col_exp:
        if st.button("Exportar proyecto (JSON)", use_container_width=True):
            proj = {
                "form_title": form_title,
                "idioma": idioma,
                "version": version,
                "preguntas": st.session_state.preguntas
            }
            jbuf = BytesIO(pd.Series(proj).to_json().encode("utf-8"))
            st.download_button("Descargar JSON", data=jbuf, file_name="proyecto_encuesta.json",
                               mime="application/json", use_container_width=True)
    with col_imp:
        up = st.file_uploader("Importar JSON", type=["json"], label_visibility="collapsed")
        if up is not None:
            try:
                raw = up.read().decode("utf-8")
                # leer con pandas para ser tolerantes
                s = pd.read_json(BytesIO(raw.encode("utf-8")), typ="series")
                st.session_state.preguntas = list(s.get("preguntas", []))
                st.success("Proyecto importado.")
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
    col_n1, col_n2 = st.columns([2,1])
    with col_n1:
        name = st.text_input("Nombre interno (XLSForm 'name')", value=sugerido,
                             help="Sin espacios; minúsculas; se usará para el campo en XLSForm.")
    with col_n2:
        required = st.checkbox("Requerida", value=False)

    opciones = []
    if tipo_ui in ("Selección única", "Selección múltiple"):
        st.markdown("**Opciones (una por línea)**")
        txt_opts = st.text_area("Opciones", height=120, placeholder="Ej.:\nSí\nNo\nNo sabe / No responde")
        if txt_opts.strip():
            opciones = [o.strip() for o in txt_opts.splitlines() if o.strip()]

    add = st.form_submit_button("➕ Agregar pregunta")

# Validar y agregar
if add:
    if not label.strip():
        st.warning("Agrega una etiqueta.")
    else:
        # Normalizar y asegurar name único
        base = slugify_name(name or label)
        usados = {q["name"] for q in st.session_state.preguntas}
        unico = asegurar_nombre_unico(base, usados)
        nueva = {
            "tipo_ui": tipo_ui,
            "label": label.strip(),
            "name": unico,
            "required": required,
            "opciones": opciones
        }
        st.session_state.preguntas.append(nueva)
        st.success(f"Pregunta agregada: **{label}** (name: `{unico}`)")

# ==========================
# Lista y orden de preguntas
# ==========================
st.subheader("📚 Preguntas (ordénalas y edítalas)")

if not st.session_state.preguntas:
    st.info("Aún no has agregado preguntas.")
else:
    for idx, q in enumerate(st.session_state.preguntas):
        with st.container(border=True):
            c1, c2, c3, c4, c5 = st.columns([4,2,2,2,2])
            c1.markdown(f"**{idx+1}. {q['label']}**")
            c1.caption(f"type: {q['tipo_ui']}  •  name: `{q['name']}`  •  requerida: {'sí' if q['required'] else 'no'}")
            if q["tipo_ui"] in ("Selección única", "Selección múltiple"):
                c1.caption("Opciones: " + ", ".join(q.get("opciones") or []))

            up = c2.button("⬆️ Subir", key=f"up_{idx}", use_container_width=True, disabled=(idx == 0))
            down = c3.button("⬇️ Bajar", key=f"down_{idx}", use_container_width=True, disabled=(idx == len(st.session_state.preguntas)-1))
            edit = c4.button("✏️ Editar", key=f"edit_{idx}", use_container_width=True)
            borrar = c5.button("🗑️ Eliminar", key=f"del_{idx}", use_container_width=True)

            # Mover
            if up:
                st.session_state.preguntas[idx-1], st.session_state.preguntas[idx] = st.session_state.preguntas[idx], st.session_state.preguntas[idx-1]
                st.experimental_rerun()
            if down:
                st.session_state.preguntas[idx+1], st.session_state.preguntas[idx] = st.session_state.preguntas[idx], st.session_state.preguntas[idx+1]
                st.experimental_rerun()

            # Editar inline mínimo
            if edit:
                st.markdown("**Editar esta pregunta**")
                ne_label = st.text_input("Etiqueta", value=q["label"], key=f"e_label_{idx}")
                ne_name = st.text_input("Nombre interno (name)", value=q["name"], key=f"e_name_{idx}")
                ne_required = st.checkbox("Requerida", value=q["required"], key=f"e_req_{idx}")

                ne_opciones = q.get("opciones") or []
                if q["tipo_ui"] in ("Selección única", "Selección múltiple"):
                    ne_opts_txt = st.text_area("Opciones (una por línea)", value="\n".join(ne_opciones), key=f"e_opts_{idx}")
                    ne_opciones = [o.strip() for o in ne_opts_txt.splitlines() if o.strip()]

                col_ok, col_cancel = st.columns(2)
                if col_ok.button("💾 Guardar cambios", key=f"e_save_{idx}", use_container_width=True):
                    # validar name único (si cambió)
                    new_base = slugify_name(ne_name or ne_label)
                    usados = {qq["name"] for j, qq in enumerate(st.session_state.preguntas) if j != idx}
                    ne_name_final = new_base if new_base not in usados else asegurar_nombre_unico(new_base, usados)

                    st.session_state.preguntas[idx]["label"] = ne_label.strip() or q["label"]
                    st.session_state.preguntas[idx]["name"] = ne_name_final
                    st.session_state.preguntas[idx]["required"] = ne_required
                    if q["tipo_ui"] in ("Selección única", "Selección múltiple"):
                        st.session_state.preguntas[idx]["opciones"] = ne_opciones
                    st.success("Cambios guardados.")
                    st.experimental_rerun()
                if col_cancel.button("Cancelar", key=f"e_cancel_{idx}", use_container_width=True):
                    st.experimental_rerun()

            if borrar:
                del st.session_state.preguntas[idx]
                st.warning("Pregunta eliminada.")
                st.experimental_rerun()

# ==========================
# Exportar XLSForm
# ==========================
st.markdown("---")
st.subheader("📦 Generar XLSForm (Excel) para Survey123")

st.caption("""
El archivo incluirá:
- **survey** con tus preguntas y tipos en formato XLSForm,
- **choices** con las listas de opciones de las preguntas de selección,
- **settings** con el título, versión e idioma.
""")

if st.button("🧮 Construir XLSForm", use_container_width=True, disabled=not st.session_state.preguntas):
    try:
        # Validaciones clave
        names = [q["name"] for q in st.session_state.preguntas]
        if len(names) != len(set(names)):
            st.error("Hay 'name' duplicados. Edita las preguntas para que cada 'name' sea único.")
        else:
            df_survey, df_choices, df_settings = construir_xlsform(
                st.session_state.preguntas,
                form_title=form_title.strip() or "Encuesta",
                idioma=idioma,
                version=version.strip() or datetime.now().strftime("%Y%m%d%H%M")
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

            st.info("""
**¿Cómo publicar la encuesta en Survey123?**
1) Abre **ArcGIS Survey123 Connect** (o el diseñador web de Survey123).
2) Crea una **nueva encuesta desde un archivo** y selecciona este XLSForm que acabas de descargar.
3) Publica la encuesta. ¡Listo! Ya podrás capturar datos en web o móvil.
""")
    except Exception as e:
        st.error(f"Ocurrió un error al generar el XLSForm: {e}")

# ==========================
# Nota final
# ==========================
st.markdown("""
---
✅ **Listo para Survey123:** El XLSForm que descargas es estándar (XLSForm).  
Incluye tipos como `text`, `integer`, `date`, `time`, `geopoint`, `select_one` y `select_multiple`, y gestiona automáticamente las listas de opciones.
""")



