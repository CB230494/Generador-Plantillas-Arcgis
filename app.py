# -*- coding: utf-8 -*-
# ==========================================================================================
# APP: Generador XLSForm (Survey123) — Encuesta Policial de Percepción Institucional 2026
# Dirigida a: Fuerza Pública (Costa Rica)
#
# Funcionalidades (IGUAL a la app anterior):
# - Constructor completo: agregar/editar/ordenar/duplicar/eliminar preguntas (survey)
# - Editor de choices: crear/editar/ordenar/eliminar opciones por list_name
# - Exportar/Importar proyecto (JSON)
# - Exportar a XLSForm (Excel) con hojas: survey / choices / settings
# - Páginas reales en Survey123: settings.style = "pages"
# - Vista previa por páginas (simulador) con relevant básico
# - Consentimiento: si marca "No" finaliza y no muestra el resto
#
# Nota: Este simulador NO reemplaza Survey123; sirve para validar flujo/estructura.
# ==========================================================================================

import streamlit as st
import pandas as pd
import json
import io
from datetime import datetime
import re
import copy

# ==========================================================================================
# CONFIG STREAMLIT
# ==========================================================================================
st.set_page_config(
    page_title="Encuesta Policial 2026 (FP)",
    page_icon="🚔",
    layout="wide"
)

st.title("🚔 Generador XLSForm – Encuesta Policial de Percepción Institucional 2026 (Fuerza Pública)")

# ==========================================================================================
# SESSION STATE INIT
# ==========================================================================================
def _init_state():
    if "survey" not in st.session_state:
        st.session_state.survey = []
    if "choices" not in st.session_state:
        st.session_state.choices = []
    if "settings" not in st.session_state:
        st.session_state.settings = {
            "form_title": "Encuesta Policial de Percepción Institucional 2026",
            "form_id": "encuesta_policial_2026_fp",
            "version": datetime.now().strftime("%Y%m%d"),
        }

    # Para vista previa
    if "preview_page_idx" not in st.session_state:
        st.session_state.preview_page_idx = 0
    if "preview_answers" not in st.session_state:
        st.session_state.preview_answers = {}

_init_state()

# ==========================================================================================
# HELPERS
# ==========================================================================================
def _slug(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"_+", "_", s)
    return s[:50] if s else "campo"

def add_survey_row(
    qtype: str,
    name: str,
    label: str,
    hint: str = "",
    required: str = "",
    relevant: str = "",
    appearance: str = "",
    calculation: str = "",
    constraint: str = "",
    constraint_message: str = "",
):
    st.session_state.survey.append({
        "type": qtype,
        "name": name,
        "label": label,
        "hint": hint,
        "required": required,
        "relevant": relevant,
        "appearance": appearance,
        "calculation": calculation,
        "constraint": constraint,
        "constraint_message": constraint_message,
    })

def add_choice(list_name: str, name: str, label: str):
    st.session_state.choices.append({
        "list_name": list_name,
        "name": name,
        "label": label,
    })

def ensure_choice_list(list_name: str, items: list):
    """
    items: list of tuples (name, label)
    """
    existing = {(c.get("list_name"), c.get("name")) for c in st.session_state.choices}
    for n, lab in items:
        if (list_name, n) not in existing:
            add_choice(list_name, n, lab)

def safe_unique_name(base: str, existing_names: set):
    base = _slug(base)
    if base not in existing_names:
        return base
    i = 2
    while f"{base}_{i}" in existing_names:
        i += 1
    return f"{base}_{i}"

def move_item(lst, idx, direction):
    new_idx = idx + direction
    if 0 <= idx < len(lst) and 0 <= new_idx < len(lst):
        lst[idx], lst[new_idx] = lst[new_idx], lst[idx]
        return True
    return False

def delete_item(lst, idx):
    if 0 <= idx < len(lst):
        lst.pop(idx)
        return True
    return False

def duplicate_item(lst, idx):
    if 0 <= idx < len(lst):
        lst.insert(idx + 1, copy.deepcopy(lst[idx]))
        return True
    return False

def get_choice_lists():
    dfc = pd.DataFrame(st.session_state.choices)
    if dfc.empty:
        return []
    return sorted(dfc["list_name"].unique().tolist())

def get_choices_for_list(list_name: str):
    return [c for c in st.session_state.choices if c.get("list_name") == list_name]

def set_choices_for_list(list_name: str, new_items: list):
    st.session_state.choices = [c for c in st.session_state.choices if c.get("list_name") != list_name]
    st.session_state.choices.extend(new_items)

# ==========================================================================================
# BASE DEL FORMULARIO (SE CARGA SOLO SI SURVEY ESTÁ VACÍO)
# ==========================================================================================
def ensure_base_policial_fp():
    if st.session_state.survey:
        return

    # Choices base
    ensure_choice_list("yesno", [
        ("yes", "Sí"),
        ("no", "No"),
    ])

    ensure_choice_list("age_rango", [
        ("r18_29", "18 a 29 años"),
        ("r30_44", "30 a 44 años"),
        ("r45_59", "45 a 59 años"),
        ("r60_mas", "60 años o más"),
    ])

    ensure_choice_list("gender_id", [
        ("f", "Femenino"),
        ("m", "Masculino"),
        ("nb", "Persona No Binaria"),
        ("nd", "Prefiero no decir"),
    ])

    ensure_choice_list("edu", [
        ("ninguna", "Ninguna"),
        ("prim_incomp", "Primaria incompleta"),
        ("prim_comp", "Primaria completa"),
        ("sec_incomp", "Secundaria incompleta"),
        ("sec_comp", "Secundaria completa"),
        ("tecnico", "Técnico"),
        ("uni_incomp", "Universitaria incompleta"),
        ("uni_comp", "Universitaria completa"),
    ])

    ensure_choice_list("clase_policial", [
        ("agente_i", "Agente I"),
        ("agente_ii", "Agente II"),
        ("subof_i", "Suboficial I"),
        ("subof_ii", "Suboficial II"),
        ("oficial_i", "Oficial I"),
        ("jefe_subdel", "Jefe Sub delegación (distrito)"),
        ("sub_jefe", "Sub Jefe de delegación"),
        ("jefe_del", "Jefe de delegación"),
    ])

    ensure_choice_list("funcion_principal", [
        ("jefatura", "Jefatura / supervisión"),
        ("operaciones", "Operaciones"),
        ("programas_prev", "Programas preventivos"),
        ("oficial_guardia", "Oficial de guardia"),
        ("comunicaciones", "Comunicaciones"),
        ("armeria", "Armería"),
        ("conduccion", "Conducción operativa de vehículos oficiales"),
        ("patrullaje", "Operativa / patrullaje"),
        ("fronteras", "Fronteras"),
        ("seg_turistica", "Seguridad turística"),
        ("other", "Otra función"),
    ])

    # -------------------------
    # PÁGINA 1: INTRO (EXACTA)
    # -------------------------
    intro = (
        "El presente formato corresponde a la Encuesta Policial de Percepción Institucional 2026, dirigida al "
        "personal de la Fuerza Pública, y orientada a recopilar información relevante desde la experiencia "
        "operativa y territorial del funcionariado policial, en relación con la seguridad, la convivencia y los "
        "factores de riesgo presentes en las distintas jurisdicciones del país.\n\n"
        "El instrumento incorpora la percepción del personal sobre condiciones institucionales que inciden en la "
        "prestación del servicio policial, tales como el entorno operativo de la delegación, la disponibilidad de "
        "recursos, las necesidades de capacitación y el entorno institucional que favorece la motivación para la "
        "atención a la ciudadanía.\n\n"
        "La información recopilada servirá como insumo para el análisis institucional, la planificación preventiva "
        "y la mejora continua del servicio policial.\n\n"
        "El documento se remite para su revisión y validación técnica, con el fin de asegurar su coherencia "
        "metodológica, normativa y operativa, previo a su aplicación en territorio."
    )

    add_survey_row("begin_group", "p1_intro", "Introducción", appearance="field-list")
    add_survey_row("note", "p1_intro_txt", intro)
    add_survey_row("end_group", "p1_intro_end", "")

    # -------------------------
    # PÁGINA 2: CONSENTIMIENTO (MISMA LÓGICA)
    # -------------------------
    add_survey_row("begin_group", "p2_consent", "Consentimiento informado", appearance="field-list")
    add_survey_row(
        "note",
        "p2_consent_txt",
        "La participación en esta encuesta es voluntaria. La información recopilada será utilizada exclusivamente "
        "para fines institucionales y de mejora del servicio policial. No se recopilarán datos personales que permitan "
        "la identificación directa de la persona encuestada."
    )
    add_survey_row(
        "select_one yesno",
        "consent",
        "¿Acepta participar en la encuesta?",
        required="yes"
    )
    add_survey_row(
        "note",
        "p2_no_consent_end",
        "Gracias. Al no brindar su consentimiento, la encuesta finaliza aquí.",
        relevant="${consent}='no'"
    )
    add_survey_row("end_group", "p2_consent_end", "")

    # -------------------------
    # PÁGINA 3: DATOS GENERALES (TÍTULO + INTRO EXACTA)
    # -------------------------
    add_survey_row("begin_group", "p3_datos_generales", "Datos generales", appearance="field-list")
    add_survey_row(
        "note",
        "p3_datos_intro",
        "Datos generales\n\n“Esta encuesta busca recopilar información desde la experiencia del personal de la Fuerza Pública para apoyar la planificación preventiva y la mejora del servicio policial.”",
        relevant="${consent}='yes'"
    )

    add_survey_row(
        "integer",
        "anos_servicio",
        "1- Años de servicio:",
        hint="Nota: Indique únicamente la cantidad de años completos de servicio (en números). Asignar en la herramienta un formato de 0 a 50 años.",
        required="yes",
        relevant="${consent}='yes'",
        constraint=". >= 0 and . <= 50",
        constraint_message="Debe ingresar un número entre 0 y 50."
    )

    add_survey_row(
        "select_one age_rango",
        "edad_rango",
        "2- Edad (en años cumplidos): marque con una X la categoría que incluya su edad.",
        hint="Nota: Esta pregunta se responde mediante rangos de edad.",
        required="yes",
        relevant="${consent}='yes'"
    )

    add_survey_row(
        "select_one gender_id",
        "identidad_genero",
        "3- ¿Con cuál de estas opciones se identifica?",
        hint="Nota: La respuesta es de selección única.",
        required="yes",
        relevant="${consent}='yes'"
    )

    add_survey_row(
        "select_one edu",
        "escolaridad",
        "4- Escolaridad:",
        hint="Nota: La respuesta es de selección única.",
        required="yes",
        relevant="${consent}='yes'"
    )

    add_survey_row(
        "select_one clase_policial",
        "clase_policial_actual",
        "5- ¿Cuál es su clase policial que desempeña en su delegación?",
        hint="Nota: Selección única.",
        required="yes",
        relevant="${consent}='yes'"
    )

    add_survey_row(
        "select_one funcion_principal",
        "funcion_principal_actual",
        "5.1- ¿Cuál es la función principal que desempeña actualmente en la delegación?",
        hint="Nota: Selección única.",
        required="yes",
        relevant="${consent}='yes'",
        appearance="or_other"
    )

    add_survey_row("end_group", "p3_datos_generales_end", "")

ensure_base_policial_fp()

# ==========================================================================================
# UI: VISTAS PRINCIPALES
# ==========================================================================================
st.markdown("---")
menu = st.radio(
    "📌 Navegación",
    ["📄 Formulario", "🧩 Constructor / Editor", "💾 Proyecto (JSON)", "📤 Exportar XLSForm", "👁️ Vista previa"],
    horizontal=True
)

# ==========================================================================================
# VISTA 1: FORMULARIO (texto fijo visible)
# ==========================================================================================
if menu == "📄 Formulario":
    st.subheader("📄 Contenido base (Fuerza Pública)")
    st.info("Esta sección muestra el contenido base cargado. Para editarlo, use **Constructor / Editor**.")

    with st.expander("🔎 Survey (completo)"):
        st.dataframe(pd.DataFrame(st.session_state.survey), use_container_width=True, height=420)

    with st.expander("🔎 Choices (completo)"):
        st.dataframe(pd.DataFrame(st.session_state.choices), use_container_width=True, height=300)

# ==========================================================================================
# VISTA 2: CONSTRUCTOR / EDITOR
# ==========================================================================================
elif menu == "🧩 Constructor / Editor":
    st.subheader("🧩 Constructor / Editor del formulario")

    tab_survey, tab_choices, tab_settings = st.tabs(["📝 Survey", "📚 Choices", "⚙️ Settings"])

    # -------------------------
    # TAB SURVEY
    # -------------------------
    with tab_survey:
        st.markdown("### 📝 Preguntas / Estructura (Survey)")
        survey_df = pd.DataFrame(st.session_state.survey)
        if survey_df.empty:
            st.info("No hay preguntas cargadas todavía.")
        else:
            show_cols = ["type", "name", "label", "relevant", "required", "appearance", "constraint"]
            cols_exist = [c for c in show_cols if c in survey_df.columns]
            st.dataframe(survey_df[cols_exist], use_container_width=True, height=280)

        st.markdown("### ➕ Agregar nueva fila al Survey")
        with st.expander("Agregar (pregunta / nota / grupo)"):
            existing_names = {r.get("name") for r in st.session_state.survey if r.get("name")}

            colA, colB = st.columns([1, 1])
            with colA:
                new_type = st.selectbox(
                    "Tipo (XLSForm)",
                    [
                        "note",
                        "text",
                        "integer",
                        "decimal",
                        "date",
                        "select_one yesno",
                        "select_one age_rango",
                        "select_one gender_id",
                        "select_one edu",
                        "select_one clase_policial",
                        "select_one funcion_principal",
                        "begin_group",
                        "end_group",
                    ],
                    index=0
                )
            with colB:
                new_label = st.text_input("Label / Pregunta", value="", key="add_label")

            new_name_base = st.text_input("Name (identificador)", value=_slug(new_label) if new_label else "", key="add_name")
            new_name = safe_unique_name(new_name_base or "campo", existing_names)

            new_hint = st.text_input("Hint (nota corta)", value="", key="add_hint")

            colC, colD, colE = st.columns(3)
            with colC:
                new_required = st.selectbox("Required", ["", "yes"], index=0, key="add_req")
            with colD:
                new_relevant = st.text_input("Relevant (condición)", value="", key="add_rel")
            with colE:
                new_appearance = st.text_input("Appearance", value="", key="add_app")

            colF, colG = st.columns(2)
            with colF:
                new_constraint = st.text_input("Constraint", value="", key="add_con")
            with colG:
                new_constraint_message = st.text_input("Constraint message", value="", key="add_conmsg")

            if st.button("✅ Agregar al Survey", use_container_width=True):
                add_survey_row(
                    qtype=new_type,
                    name=new_name if new_type != "end_group" else (new_name or f"end_{len(st.session_state.survey)+1}"),
                    label=new_label if new_type != "end_group" else "",
                    hint=new_hint,
                    required=new_required,
                    relevant=new_relevant,
                    appearance=new_appearance,
                    constraint=new_constraint,
                    constraint_message=new_constraint_message
                )
                st.success("Fila agregada al Survey.")

        st.markdown("### 🛠️ Editar / Ordenar / Eliminar filas (Survey)")
        if st.session_state.survey:
            idx = st.number_input(
                "Índice de fila (0..n-1)",
                min_value=0,
                max_value=max(0, len(st.session_state.survey) - 1),
                value=0,
                step=1
            )
            idx = int(idx)
            row = st.session_state.survey[idx]

            st.write("Fila seleccionada:")
            st.code(json.dumps(row, ensure_ascii=False, indent=2), language="json")

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                if st.button("⬆️ Subir", use_container_width=True):
                    st.success("Movido arriba.") if move_item(st.session_state.survey, idx, -1) else st.warning("No se puede subir más.")
            with col2:
                if st.button("⬇️ Bajar", use_container_width=True):
                    st.success("Movido abajo.") if move_item(st.session_state.survey, idx, +1) else st.warning("No se puede bajar más.")
            with col3:
                if st.button("📄 Duplicar", use_container_width=True):
                    if duplicate_item(st.session_state.survey, idx):
                        existing = {r.get("name") for r in st.session_state.survey if r.get("name")}
                        dup = st.session_state.survey[idx + 1]
                        if dup.get("name"):
                            dup["name"] = safe_unique_name(dup["name"], existing)
                        st.success("Duplicado.")
            with col4:
                if st.button("🗑️ Eliminar", use_container_width=True):
                    st.success("Eliminado.") if delete_item(st.session_state.survey, idx) else st.warning("No se pudo eliminar.")

            st.markdown("#### ✏️ Editor de campos")
            e_type = st.text_input("type", value=row.get("type", ""), key="edit_type")
            e_name = st.text_input("name", value=row.get("name", ""), key="edit_name")
            e_label = st.text_area("label", value=row.get("label", ""), height=80, key="edit_label")
            e_hint = st.text_area("hint", value=row.get("hint", ""), height=60, key="edit_hint")

            colR1, colR2, colR3 = st.columns(3)
            with colR1:
                e_required = st.text_input("required", value=row.get("required", ""), key="edit_required")
            with colR2:
                e_relevant = st.text_input("relevant", value=row.get("relevant", ""), key="edit_relevant")
            with colR3:
                e_appearance = st.text_input("appearance", value=row.get("appearance", ""), key="edit_appearance")

            colR4, colR5 = st.columns(2)
            with colR4:
                e_constraint = st.text_input("constraint", value=row.get("constraint", ""), key="edit_constraint")
            with colR5:
                e_constraint_message = st.text_input("constraint_message", value=row.get("constraint_message", ""), key="edit_constraint_message")

            if st.button("💾 Guardar cambios en esta fila", use_container_width=True):
                st.session_state.survey[idx] = {
                    "type": e_type.strip(),
                    "name": e_name.strip(),
                    "label": e_label,
                    "hint": e_hint,
                    "required": e_required.strip(),
                    "relevant": e_relevant.strip(),
                    "appearance": e_appearance.strip(),
                    "calculation": row.get("calculation", ""),
                    "constraint": e_constraint.strip(),
                    "constraint_message": e_constraint_message.strip(),
                }
                st.success("Cambios guardados.")

            st.info(
                "Para páginas reales (style='pages') usamos:\n"
                "- begin_group (label = título de la página)\n"
                "- end_group para cerrar.\n"
                "Para cortar por consentimiento, el resto va con relevant ${consent}='yes'."
            )

    # -------------------------
    # TAB CHOICES
    # -------------------------
    with tab_choices:
        st.markdown("### 📚 Opciones (Choices)")
        choices_df = pd.DataFrame(st.session_state.choices)
        if choices_df.empty:
            st.info("No hay opciones cargadas todavía.")
        else:
            st.dataframe(choices_df, use_container_width=True, height=260)

        st.markdown("### ➕ Crear lista de opciones nueva")
        with st.expander("Crear nueva list_name"):
            new_list = st.text_input("Nombre de lista (list_name)", value="", key="new_listname")
            if st.button("✅ Crear lista vacía", use_container_width=True):
                new_list = _slug(new_list)
                if not new_list:
                    st.error("Digite un list_name válido.")
                else:
                    st.success(f"Lista '{new_list}' lista para usar. (Agregue ítems abajo)")

        st.markdown("### 🧾 Editar una lista existente")
        lists = get_choice_lists()
        if not lists:
            st.warning("No hay listas para editar aún.")
        else:
            sel_list = st.selectbox("Seleccione list_name", lists, index=0, key="sel_list")
            items = get_choices_for_list(sel_list)

            st.write(f"Ítems en **{sel_list}**:")
            st.dataframe(pd.DataFrame(items), use_container_width=True, height=220) if items else st.info("Esta lista está vacía.")

            st.markdown("#### ➕ Agregar ítem")
            colI1, colI2 = st.columns([1, 2])
            with colI1:
                item_name = st.text_input("name (valor)", value="", key="item_name")
            with colI2:
                item_label = st.text_input("label (texto)", value="", key="item_label")

            if st.button("➕ Agregar opción", use_container_width=True):
                item_name_s = _slug(item_name) if item_name else _slug(item_label)
                if not item_name_s:
                    st.error("Debe indicar name o label.")
                else:
                    exists = any(c.get("list_name") == sel_list and c.get("name") == item_name_s for c in st.session_state.choices)
                    if exists:
                        st.error("Ya existe esa opción (mismo name) en esta lista.")
                    else:
                        add_choice(sel_list, item_name_s, item_label.strip() or item_name_s)
                        st.success("Opción agregada.")

            st.markdown("#### 🛠️ Ordenar / Eliminar ítems")
            if items:
                idx_c = st.number_input("Índice de opción (0..n-1)", min_value=0, max_value=len(items)-1, value=0, step=1, key="idx_choice")
                idx_c = int(idx_c)

                colC1, colC2, colC3 = st.columns(3)
                with colC1:
                    if st.button("⬆️ Subir opción", use_container_width=True):
                        st.success("Opción movida arriba.") if move_item(items, idx_c, -1) else st.warning("No se puede subir más.")
                        set_choices_for_list(sel_list, items)
                with colC2:
                    if st.button("⬇️ Bajar opción", use_container_width=True):
                        st.success("Opción movida abajo.") if move_item(items, idx_c, +1) else st.warning("No se puede bajar más.")
                        set_choices_for_list(sel_list, items)
                with colC3:
                    if st.button("🗑️ Eliminar opción", use_container_width=True):
                        st.success("Opción eliminada.") if delete_item(items, idx_c) else st.warning("No se pudo eliminar.")
                        set_choices_for_list(sel_list, items)

                st.markdown("#### ✏️ Editar opción seleccionada")
                opt = items[idx_c]
                e_opt_name = st.text_input("Editar name", value=opt.get("name", ""), key="edit_opt_name")
                e_opt_label = st.text_input("Editar label", value=opt.get("label", ""), key="edit_opt_label")

                if st.button("💾 Guardar cambios de opción", use_container_width=True):
                    e_opt_name_s = _slug(e_opt_name) if e_opt_name else opt.get("name", "")
                    if e_opt_name_s != opt.get("name"):
                        dup = any(c.get("list_name") == sel_list and c.get("name") == e_opt_name_s for c in items)
                        if dup:
                            st.error("Ese name ya existe en la lista.")
                        else:
                            opt["name"] = e_opt_name_s
                            opt["label"] = e_opt_label
                            set_choices_for_list(sel_list, items)
                            st.success("Opción actualizada.")
                    else:
                        opt["label"] = e_opt_label
                        set_choices_for_list(sel_list, items)
                        st.success("Opción actualizada.")

    # -------------------------
    # TAB SETTINGS
    # -------------------------
    with tab_settings:
        st.markdown("### ⚙️ Settings del formulario")
        st.session_state.settings["form_title"] = st.text_input(
            "Título del formulario (form_title)",
            value=st.session_state.settings.get("form_title", "Encuesta Policial de Percepción Institucional 2026"),
            key="set_title"
        )
        st.session_state.settings["form_id"] = st.text_input(
            "ID del formulario (form_id)",
            value=st.session_state.settings.get("form_id", "encuesta_policial_2026_fp"),
            key="set_id"
        )
        st.session_state.settings["version"] = st.text_input(
            "Versión",
            value=st.session_state.settings.get("version", datetime.now().strftime("%Y%m%d")),
            key="set_ver"
        )
        st.info("Estos settings se exportan en la hoja 'settings' del XLSForm. Se agrega style=pages automáticamente al exportar.")

    st.markdown("---")
    colX1, colX2, colX3 = st.columns(3)
    with colX1:
        if st.button("🧹 Reiniciar SOLO Survey (preguntas)", use_container_width=True):
            st.session_state.survey = []
            st.success("Survey reiniciado. (Choices y Settings se mantienen)")
    with colX2:
        if st.button("🧹 Reiniciar SOLO Choices (opciones)", use_container_width=True):
            st.session_state.choices = []
            st.success("Choices reiniciado. (Survey y Settings se mantienen)")
    with colX3:
        if st.button("♻️ Reiniciar TODO (Survey + Choices + Settings)", use_container_width=True):
            st.session_state.survey = []
            st.session_state.choices = []
            st.session_state.settings = {
                "form_title": "Encuesta Policial de Percepción Institucional 2026",
                "form_id": "encuesta_policial_2026_fp",
                "version": datetime.now().strftime("%Y%m%d"),
            }
            st.session_state.preview_page_idx = 0
            st.session_state.preview_answers = {}
            st.success("Todo reiniciado.")

# ==========================================================================================
# VISTA 3: PROYECTO JSON (EXPORT/IMPORT)
# ==========================================================================================
elif menu == "💾 Proyecto (JSON)":
    st.subheader("💾 Proyecto (JSON) — Exportar / Importar")

    def export_project_dict():
        return {
            "meta": {
                "app": "Generador XLSForm - Encuesta Policial 2026 (Fuerza Pública)",
                "exported_at": datetime.now().isoformat(timespec="seconds"),
            },
            "settings": st.session_state.settings,
            "survey": st.session_state.survey,
            "choices": st.session_state.choices,
        }

    def validate_project_dict(data: dict):
        if not isinstance(data, dict):
            return False, "El archivo no contiene un objeto JSON válido."

        for k in ("settings", "survey", "choices"):
            if k not in data:
                return False, f"Falta la llave '{k}' en el proyecto."

        if not isinstance(data["settings"], dict):
            return False, "settings debe ser un objeto."
        if not isinstance(data["survey"], list):
            return False, "survey debe ser una lista."
        if not isinstance(data["choices"], list):
            return False, "choices debe ser una lista."

        required_survey_keys = {"type", "name", "label", "hint", "required", "relevant", "appearance",
                               "calculation", "constraint", "constraint_message"}
        for i, row in enumerate(data["survey"]):
            if not isinstance(row, dict):
                return False, f"survey[{i}] no es un objeto."
            missing = required_survey_keys - set(row.keys())
            if missing:
                return False, f"survey[{i}] está incompleto. Faltan: {', '.join(sorted(missing))}"

        required_choice_keys = {"list_name", "name", "label"}
        for i, row in enumerate(data["choices"]):
            if not isinstance(row, dict):
                return False, f"choices[{i}] no es un objeto."
            missing = required_choice_keys - set(row.keys())
            if missing:
                return False, f"choices[{i}] está incompleto. Faltan: {', '.join(sorted(missing))}"

        return True, "OK"

    colP1, colP2 = st.columns([1, 1])

    with colP1:
        st.markdown("### ⬇️ Exportar proyecto")
        project = export_project_dict()
        project_json = json.dumps(project, ensure_ascii=False, indent=2)

        st.download_button(
            "📥 Descargar proyecto (.json)",
            data=project_json.encode("utf-8"),
            file_name=f"{st.session_state.settings.get('form_id','encuesta_policial_2026_fp')}_proyecto.json",
            mime="application/json",
            use_container_width=True
        )

        with st.expander("Ver JSON (solo lectura)"):
            st.code(project_json, language="json")

    with colP2:
        st.markdown("### ⬆️ Importar proyecto")
        up = st.file_uploader("Cargar proyecto .json", type=["json"], accept_multiple_files=False)
        if up is not None:
            try:
                raw = up.read().decode("utf-8")
                data = json.loads(raw)
                ok, msg = validate_project_dict(data)
                if not ok:
                    st.error(f"No se puede importar: {msg}")
                else:
                    st.session_state.settings = data["settings"]
                    st.session_state.survey = data["survey"]
                    st.session_state.choices = data["choices"]
                    st.success("✅ Proyecto importado correctamente.")
            except Exception as e:
                st.error(f"Error al leer el JSON: {e}")

    st.info("Consejo: Exportá el proyecto cada vez que hagás cambios grandes. Así nunca perdés tu avance.")

# ==========================================================================================
# VISTA 4: EXPORTAR XLSFORM (EXCEL)
# ==========================================================================================
elif menu == "📤 Exportar XLSForm":
    st.subheader("📤 Exportar a XLSForm (Excel) para ArcGIS Survey123")

    def build_xlsform_dataframes():
        survey_df = pd.DataFrame(st.session_state.survey)
        if survey_df.empty:
            survey_df = pd.DataFrame(columns=[
                "type", "name", "label", "hint", "required", "relevant", "appearance",
                "calculation", "constraint", "constraint_message"
            ])

        survey_cols = [
            "type", "name", "label", "hint", "required", "relevant", "appearance",
            "calculation", "constraint", "constraint_message"
        ]
        for c in survey_cols:
            if c not in survey_df.columns:
                survey_df[c] = ""
        survey_df = survey_df[survey_cols].fillna("")

        choices_df = pd.DataFrame(st.session_state.choices)
        if choices_df.empty:
            choices_df = pd.DataFrame(columns=["list_name", "name", "label"])
        for c in ["list_name", "name", "label"]:
            if c not in choices_df.columns:
                choices_df[c] = ""
        choices_df = choices_df[["list_name", "name", "label"]].fillna("")

        s = st.session_state.settings or {}
        settings_df = pd.DataFrame([{
            "form_title": s.get("form_title", "Encuesta Policial de Percepción Institucional 2026"),
            "form_id": s.get("form_id", "encuesta_policial_2026_fp"),
            "version": s.get("version", datetime.now().strftime("%Y%m%d")),
            "style": "pages",
            "default_language": "Español",
        }])

        return survey_df, choices_df, settings_df

    def to_xlsx_bytes(survey_df, choices_df, settings_df):
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            survey_df.to_excel(writer, index=False, sheet_name="survey")
            choices_df.to_excel(writer, index=False, sheet_name="choices")
            settings_df.to_excel(writer, index=False, sheet_name="settings")
        output.seek(0)
        return output.getvalue()

    colE1, colE2 = st.columns([1, 1])

    with colE1:
        st.markdown("### ✅ Verificación rápida")

        names = [r.get("name", "") for r in st.session_state.survey if r.get("name", "")]
        dup_names = sorted({n for n in names if names.count(n) > 1})
        if dup_names:
            st.error("Hay nombres duplicados (name) en Survey. Esto puede romper el XLSForm:")
            st.write(dup_names)
        else:
            st.success("No se detectan nombres duplicados en Survey.")

        pairs = [(c.get("list_name", ""), c.get("name", "")) for c in st.session_state.choices]
        dup_pairs = sorted({p for p in pairs if pairs.count(p) > 1})
        if dup_pairs:
            st.error("Hay opciones duplicadas en Choices (mismo list_name + name):")
            st.write(dup_pairs)
        else:
            st.success("No se detectan duplicados en Choices.")

    with colE2:
        st.markdown("### 📥 Descargar XLSForm (.xlsx)")
        survey_df, choices_df, settings_df = build_xlsform_dataframes()
        xlsx_bytes = to_xlsx_bytes(survey_df, choices_df, settings_df)
        file_name = f"{st.session_state.settings.get('form_id','encuesta_policial_2026_fp')}.xlsx"

        st.download_button(
            "📥 Descargar XLSForm",
            data=xlsx_bytes,
            file_name=file_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

        with st.expander("👀 Vista previa (survey/choices/settings)"):
            st.markdown("**survey**")
            st.dataframe(survey_df, use_container_width=True, height=200)
            st.markdown("**choices**")
            st.dataframe(choices_df, use_container_width=True, height=180)
            st.markdown("**settings**")
            st.dataframe(settings_df, use_container_width=True, height=120)

# ==========================================================================================
# VISTA 5: VISTA PREVIA (SIMULADOR)
# ==========================================================================================
elif menu == "👁️ Vista previa":
    st.subheader("👁️ Vista previa por páginas (simulador)")

    def _get_answer(ans: dict, name: str):
        return ans.get(name, "")

    def _eval_simple_expr(expr: str, answers: dict) -> bool:
        """
        Soporta relevant típico:
        ${consent}='yes'
        ${x}!='y'
        (${a}='x' and ${b}='y') or ${c}='z'

        Si hay caracteres no esperados o falla eval → True (no ocultar por error).
        """
        if not expr or not str(expr).strip():
            return True
        s = str(expr).strip()

        def repl(m):
            field = m.group(1)
            val = str(_get_answer(answers, field))
            val = val.replace("'", "\\'")
            return f"'{val}'"

        s = re.sub(r"\$\{([A-Za-z0-9_]+)\}", repl, s)
        s = re.sub(r"(?<![=!<>])=(?!=)", "==", s)  # '=' -> '=='

        s = re.sub(r"\s+", " ", s).strip()

        allowed = re.compile(r"^[\s\w'\\\(\)\=\!\<\>\.\-]+$")
        if not allowed.match(s):
            return True

        try:
            return bool(eval(s, {"__builtins__": {}}, {}))
        except Exception:
            return True

    def build_pages_from_survey(survey_rows: list):
        pages = []
        current = None
        orphan = []

        for r in survey_rows:
            t = (r.get("type") or "").strip()
            if t == "begin_group":
                if orphan:
                    pages.append({"name": "sin_pagina", "title": "Sin página", "rows": orphan})
                    orphan = []
                current = {
                    "name": r.get("name") or f"page_{len(pages)+1}",
                    "title": r.get("label") or "Página",
                    "rows": []
                }
                continue

            if t == "end_group":
                if current is not None:
                    pages.append(current)
                    current = None
                continue

            if current is None:
                orphan.append(r)
            else:
                current["rows"].append(r)

        if current is not None:
            pages.append(current)
        if orphan:
            pages.append({"name": "sin_pagina", "title": "Sin página", "rows": orphan})

        return pages

    def render_row(row: dict, answers: dict):
        qtype = (row.get("type") or "").strip()
        name = (row.get("name") or "").strip()
        label = row.get("label") or ""
        hint = row.get("hint") or ""
        required = (row.get("required") or "").strip().lower() == "yes"
        appearance = (row.get("appearance") or "").strip()

        if qtype in ("begin_group", "end_group", "begin_repeat", "end_repeat"):
            return

        if qtype == "note":
            st.markdown(label.replace("\n", "  \n"))
            if hint:
                st.caption(hint)
            return

        req_star = " *" if required else ""
        show_label = f"{label}{req_star}"

        if qtype.startswith("select_one"):
            list_name = qtype.split(" ", 1)[1].strip() if " " in qtype else ""
            opts = [c for c in st.session_state.choices if c.get("list_name") == list_name]
            labels = [c.get("label", "") for c in opts]
            values = [c.get("name", "") for c in opts]

            if "or_other" in appearance:
                labels2 = labels + ["Otra (especifique)"]
                values2 = values + ["__other__"]
                sel = st.radio(show_label, labels2, index=0 if labels2 else None, key=f"prev_{name}")
                if sel == "Otra (especifique)":
                    answers[name] = "__other__"
                    other_txt = st.text_input("Especifique:", key=f"prev_{name}_other")
                    answers[f"{name}_other"] = other_txt
                else:
                    answers[name] = values2[labels2.index(sel)]
                if hint:
                    st.caption(hint)
                return

            sel = st.radio(show_label, labels, index=0 if labels else None, key=f"prev_{name}")
            answers[name] = values[labels.index(sel)] if labels else ""
            if hint:
                st.caption(hint)
            return

        if qtype.startswith("select_multiple"):
            list_name = qtype.split(" ", 1)[1].strip() if " " in qtype else ""
            opts = [c for c in st.session_state.choices if c.get("list_name") == list_name]
            labels = [c.get("label", "") for c in opts]
            values = [c.get("name", "") for c in opts]
            sel = st.multiselect(show_label, labels, default=[], key=f"prev_{name}")
            picked = [values[labels.index(x)] for x in sel] if labels else []
            answers[name] = " ".join(picked)
            if hint:
                st.caption(hint)
            return

        if qtype == "integer":
            val = st.number_input(show_label, step=1, value=0, key=f"prev_{name}")
            answers[name] = str(int(val))
            if hint:
                st.caption(hint)
            return

        if qtype == "decimal":
            val = st.number_input(show_label, step=0.1, value=0.0, key=f"prev_{name}")
            answers[name] = str(val)
            if hint:
                st.caption(hint)
            return

        if qtype == "text":
            val = st.text_input(show_label, key=f"prev_{name}")
            answers[name] = val
            if hint:
                st.caption(hint)
            return

        if qtype == "date":
            val = st.date_input(show_label, key=f"prev_{name}")
            answers[name] = str(val)
            if hint:
                st.caption(hint)
            return

        val = st.text_input(f"{show_label} (tipo: {qtype})", key=f"prev_{name}")
        answers[name] = val
        if hint:
            st.caption(hint)

    pages = build_pages_from_survey(st.session_state.survey)

    answers = st.session_state.preview_answers
    consent_val = answers.get("consent", "")
    force_end = (consent_val == "no")

    top1, top2, top3 = st.columns([1, 2, 1])
    with top1:
        if st.button("🔄 Reiniciar vista previa", use_container_width=True):
            st.session_state.preview_page_idx = 0
            st.session_state.preview_answers = {}
            st.success("Vista previa reiniciada.")
            st.stop()

    with top2:
        if pages:
            st.progress((st.session_state.preview_page_idx + 1) / len(pages))
            st.caption(f"Página {st.session_state.preview_page_idx + 1} de {len(pages)}")
        else:
            st.warning("No hay páginas (begin_group/end_group) en el Survey.")
            st.stop()

    with top3:
        with st.expander("📌 Respuestas (debug)"):
            st.code(json.dumps(answers, ensure_ascii=False, indent=2), language="json")

    page = pages[st.session_state.preview_page_idx]
    st.markdown(f"### 📄 {page['title']}")

    for row in page["rows"]:
        if force_end and page["name"] not in ("p1_intro", "p2_consent"):
            continue

        rel = row.get("relevant", "")
        if _eval_simple_expr(rel, answers):
            render_row(row, answers)

    nav1, nav2, nav3 = st.columns([1, 1, 1])
    with nav1:
        if st.button("⬅️ Anterior", use_container_width=True):
            st.session_state.preview_page_idx = max(0, st.session_state.preview_page_idx - 1)

    with nav2:
        if force_end and page["name"] == "p2_consent":
            st.info("Encuesta finalizada por falta de consentimiento.")
        else:
            if st.button("Siguiente ➡️", use_container_width=True):
                st.session_state.preview_page_idx = min(len(pages) - 1, st.session_state.preview_page_idx + 1)

    with nav3:
        st.write("")

# ==========================================================================================
# FOOTER
# ==========================================================================================
st.markdown("---")
st.caption("✅ App completa lista (una sola porción). Fuerza Pública 2026. Exporta XLSForm con style=pages y mantiene flujo de consentimiento.")






