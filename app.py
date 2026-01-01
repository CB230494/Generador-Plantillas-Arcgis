# -*- coding: utf-8 -*-
# ==========================================================================================
# App: XLSForm Survey123 — Introducción + Consentimiento + Datos Generales (Páginas 1,2,3)
# - Página 1: Introducción con logo + nombre delegación + texto corto (exacto)
# - Página 2: Consentimiento Informado (mismo contenido) con formato más compacto
#            + pregunta ¿Acepta participar? (Sí/No)
#            + Si responde "No" => finaliza (end)
# - Página 3: Datos Generales (según imágenes) — SOLO si acepta "Sí"
#            + Condicionales en pregunta 5 (5.1 / 5.2 / 5.3 / 5.4)
# - Exporta XLSForm (Excel) con hojas: survey / choices / settings
# ==========================================================================================

import re
from io import BytesIO
from datetime import datetime

import streamlit as st
import pandas as pd

# ==========================================================================================
# Configuración
# ==========================================================================================
st.set_page_config(page_title="XLSForm Survey123 — Introducción + Consentimiento + Datos", layout="wide")
st.title("XLSForm Survey123 — Introducción + Consentimiento + Datos Generales")

st.markdown("""
Genera un **XLSForm** listo para **ArcGIS Survey123** con páginas reales (Next/Back):
- **Página 1**: Introducción (logo + delegación + texto).
- **Página 2**: Consentimiento Informado (compacto) + aceptación.
- **Página 3**: Datos Generales (con condicionales en la pregunta 5).
""")

# ==========================================================================================
# Helpers
# ==========================================================================================
def slugify_name(texto: str) -> str:
    """Convierte texto a un slug válido para XLSForm (name)."""
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

def descargar_xlsform(df_survey, df_choices, df_settings, nombre_archivo: str):
    """Genera y descarga el XLSForm (Excel)."""
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
            for col_idx, col_name in enumerate(df.columns):
                ws.set_column(col_idx, col_idx, max(14, min(80, len(str(col_name)) + 10)))

    buffer.seek(0)
    st.download_button(
        label=f"📥 Descargar XLSForm ({nombre_archivo})",
        data=buffer,
        file_name=nombre_archivo,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

# ==========================================================================================
# Inputs (logo + delegación)
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
    delegacion = st.text_input("Nombre de la Delegación", value="San Carlos Oeste")
    logo_media_name = st.text_input(
        "Nombre de archivo para `media::image`",
        value=st.session_state.get("_logo_name", "001.png"),
        help="Debe coincidir con el archivo dentro de la carpeta `media/` del proyecto Survey123 (Connect)."
    )

form_title = f"Encuesta Fuerza Pública – Delegación {delegacion.strip()}" if delegacion.strip() else "Encuesta Fuerza Pública"
st.markdown(f"### {form_title}")

# ==========================================================================================
# Textos EXACTOS solicitados
# ==========================================================================================
INTRO_CORTA_EXACTA = (
    "Esta encuesta busca recopilar información desde la experiencia del personal de la \n"
    "Fuerza Pública para apoyar la planificación preventiva y la mejora del servicio policial."
)

# Consentimiento (mismo contenido, más compacto en 1 NOTE)
CONSENT_TITLE = "Consentimiento Informado para la Participación en la Encuesta"

CONSENT_TXT_COMPACTO = (
    "Usted está siendo invitado(a) a participar de forma libre y voluntaria en una encuesta sobre seguridad, "
    "convivencia y percepción ciudadana, dirigida a personas mayores de 18 años.\n\n"
    "El objetivo de esta encuesta es recopilar información de carácter preventivo y estadístico, con el fin "
    "de apoyar la planificación de acciones de prevención, mejora de la convivencia y fortalecimiento de "
    "la seguridad en comunidades y zonas comerciales.\n\n"
    "La participación es totalmente voluntaria. Usted puede negarse a responder cualquier pregunta, así "
    "como retirarse de la encuesta en cualquier momento, sin que ello genere consecuencia alguna.\n\n"
    "De conformidad con lo dispuesto en el artículo 5 de la Ley N.º 8968, Ley de Protección de la Persona "
    "frente al Tratamiento de sus Datos Personales, se le informa que:\n"
    "• Finalidad del tratamiento: La información recopilada será utilizada exclusivamente para fines "
    "estadísticos, analíticos y preventivos, y no para investigaciones penales, procesos judiciales, "
    "sanciones administrativas ni procedimientos disciplinarios.\n"
    "• Datos personales: Algunos apartados permiten, de forma voluntaria, el suministro de datos "
    "personales o información de contacto.\n"
    "• Tratamiento de los datos: Los datos serán almacenados, analizados y resguardados bajo criterios "
    "de confidencialidad y seguridad, conforme a la normativa vigente.\n"
    "• Destinatarios y acceso: La información será conocida únicamente por el personal autorizado "
    "de la Fuerza Pública / Ministerio de Seguridad Pública, para los fines indicados. No será cedida "
    "a terceros ajenos a estos fines.\n"
    "• Responsable de la base de datos: El Ministerio de Seguridad Pública, a través de la Dirección "
    "de Programas Policiales Preventivos, Oficina Estrategia Integral de Prevención para la Seguridad "
    "Pública (EIPSEP / Estrategia Sembremos Seguridad) será el responsable del tratamiento y custodia "
    "de la información recolectada.\n"
    "• Derechos de la persona participante: Usted conserva el derecho a la autodeterminación informativa "
    "y a decidir libremente sobre el suministro de sus datos.\n\n"
    "Las respuestas brindadas no constituyen denuncias formales, ni sustituyen los mecanismos legales "
    "correspondientes.\n\n"
    "Al continuar con la encuesta, usted manifiesta haber leído y comprendido la información anterior "
    "y otorga su consentimiento informado para participar."
)

# ==========================================================================================
# Construcción XLSForm
# ==========================================================================================
def construir_xlsform(form_title: str, logo_media_name: str, idioma: str, version: str):
    survey_rows = []
    choices_rows = []

    # =========================
    # Choices (listas)
    # =========================
    # Sí/No (aceptación)
    list_yesno = "yesno"
    v_si = slugify_name("Sí")
    v_no = slugify_name("No")
    choices_rows.extend([
        {"list_name": list_yesno, "name": v_si, "label": "Sí"},
        {"list_name": list_yesno, "name": v_no, "label": "No"},
    ])

    # Edad (rangos)
    list_edad = "edad_rangos"
    edad_opts = ["18 a 29 años", "30 a 44 años", "45 a 59 años", "60 años o más"]
    for o in edad_opts:
        choices_rows.append({"list_name": list_edad, "name": slugify_name(o), "label": o})

    # Género
    list_genero = "genero"
    genero_opts = ["Femenino", "Masculino", "Persona No Binaria", "Prefiero no decir"]
    for o in genero_opts:
        choices_rows.append({"list_name": list_genero, "name": slugify_name(o), "label": o})

    # Escolaridad
    list_escolaridad = "escolaridad"
    escolaridad_opts = [
        "Ninguna",
        "Primaria incompleta",
        "Primaria completa",
        "Secundaria incompleta",
        "Secundaria completa",
        "Técnico",
        "Universitaria incompleta",
        "Universitaria completa",
    ]
    for o in escolaridad_opts:
        choices_rows.append({"list_name": list_escolaridad, "name": slugify_name(o), "label": o})

    # Clase policial (pregunta 5)
    list_clase = "clase_policial"
    clase_opts = [
        "Agente I",
        "Agente II",
        "Suboficial I",
        "Suboficial II",
        "Oficial I",
        "Sub Jefe de delegación",
        "Jefe de delegación",
    ]
    for o in clase_opts:
        choices_rows.append({"list_name": list_clase, "name": slugify_name(o), "label": o})

    # 5.1 Agente II (sublista)
    list_agente_ii = "agente_ii_det"
    agente_ii_opts = [
        "Agente de Fronteras",
        "Agente de Programa Preventivo",
        "Agente Armero",
        "Agente Conductor Operacional de Vehículos Oficiales",
        "Agente de Seguridad Turística",
        "Agente de Comunicaciones",
        "Agente de Operaciones",
    ]
    for o in agente_ii_opts:
        choices_rows.append({"list_name": list_agente_ii, "name": slugify_name(o), "label": o})

    # 5.2 Suboficial I (sublista)
    list_subof_i = "suboficial_i_det"
    subof_i_opts = [
        "Encargado Equipo Operativo Policial",
        "Encargado Equipo de Seguridad Turística",
        "Encargado Equipo de Fronteras",
        "Encargado Equipo de Comunicaciones",
        "Encargado de Programas Preventivos",
        "Encargado Agentes Armeros",
    ]
    for o in subof_i_opts:
        choices_rows.append({"list_name": list_subof_i, "name": slugify_name(o), "label": o})

    # 5.3 Suboficial II (sublista)
    list_subof_ii = "suboficial_ii_det"
    subof_ii_opts = [
        "Encargado Subgrupo Operativo Policial",
        "Encargado Subgrupo de Seguridad Turística",
        "Encargado Subgrupo de Fronteras",
        "Oficial de Guardia",
        "Encargado de Operaciones",
    ]
    for o in subof_ii_opts:
        choices_rows.append({"list_name": list_subof_ii, "name": slugify_name(o), "label": o})

    # 5.4 Oficial I (sublista)
    list_of_i = "oficial_i_det"
    of_i_opts = [
        "Jefe Delegación Distrital",
        "Encargado Grupo Operativo Policial",
    ]
    for o in of_i_opts:
        choices_rows.append({"list_name": list_of_i, "name": slugify_name(o), "label": o})

    # =========================
    # Página 1: Introducción (SIN la palabra “Portada”)
    # =========================
    survey_rows.append({
        "type": "begin_group",
        "name": "p1_intro",
        "label": "Introducción",
        "appearance": "field-list"
    })
    survey_rows.append({
        "type": "note",
        "name": "p1_logo",
        "label": form_title,
        "media::image": logo_media_name
    })
    survey_rows.append({
        "type": "note",
        "name": "p1_texto",
        "label": INTRO_CORTA_EXACTA
    })
    survey_rows.append({"type": "end_group", "name": "p1_end"})

    # =========================
    # Página 2: Consentimiento (compacto)
    # =========================
    survey_rows.append({
        "type": "begin_group",
        "name": "p2_consent",
        "label": "Consentimiento Informado",
        "appearance": "field-list"
    })
    survey_rows.append({
        "type": "note",
        "name": "p2_titulo",
        "label": CONSENT_TITLE
    })
    survey_rows.append({
        "type": "note",
        "name": "p2_texto",
        "label": CONSENT_TXT_COMPACTO
    })
    survey_rows.append({
        "type": f"select_one {list_yesno}",
        "name": "acepta_participar",
        "label": "¿Acepta participar en esta encuesta?",
        "required": "yes",
        "appearance": "minimal"
    })
    survey_rows.append({"type": "end_group", "name": "p2_end"})

    # Finalizar si NO acepta
    survey_rows.append({
        "type": "end",
        "name": "fin_por_no",
        "label": "Gracias. Usted indicó que no acepta participar en esta encuesta.",
        "relevant": f"${{acepta_participar}}='{v_no}'"
    })

    # =========================
    # Página 3: Datos Generales (SOLO si acepta SÍ)
    # =========================
    rel_si = f"${{acepta_participar}}='{v_si}'"

    survey_rows.append({
        "type": "begin_group",
        "name": "p3_datos_generales",
        "label": "Datos generales",
        "appearance": "field-list",
        "relevant": rel_si
    })

    # 1 Años de servicio (0 a 50)
    survey_rows.append({
        "type": "integer",
        "name": "anos_servicio",
        "label": "1- Años de servicio:",
        "required": "yes",
        "constraint": ". >= 0 and . <= 50",
        "constraint_message": "Debe ser un número entre 0 y 50.",
        "hint": "Indique únicamente la cantidad de años completos de servicio (en números). Asignar un formato de 0 a 50 años.",
        "relevant": rel_si
    })

    # 2 Edad (rangos)
    survey_rows.append({
        "type": f"select_one {list_edad}",
        "name": "edad_rango",
        "label": "2- Edad (en años cumplidos): marque con una X la categoría que incluya su edad.",
        "required": "yes",
        "relevant": rel_si
    })

    # 3 Género
    survey_rows.append({
        "type": f"select_one {list_genero}",
        "name": "genero",
        "label": "3- ¿Con cuál de estas opciones se identifica?",
        "required": "yes",
        "relevant": rel_si
    })

    # 4 Escolaridad
    survey_rows.append({
        "type": f"select_one {list_escolaridad}",
        "name": "escolaridad",
        "label": "4- Escolaridad:",
        "required": "yes",
        "relevant": rel_si
    })

    # 5 Clase policial
    survey_rows.append({
        "type": f"select_one {list_clase}",
        "name": "clase_policial",
        "label": "5- ¿Qué clase policial desempeña en su delegación?",
        "required": "yes",
        "relevant": rel_si
    })

    # Condicionales según nota (5.1 / 5.2 / 5.3 / 5.4)
    rel_agente_ii = f"({rel_si}) and (${{clase_policial}}='{slugify_name('Agente II')}')"
    rel_subof_i   = f"({rel_si}) and (${{clase_policial}}='{slugify_name('Suboficial I')}')"
    rel_subof_ii  = f"({rel_si}) and (${{clase_policial}}='{slugify_name('Suboficial II')}')"
    rel_of_i      = f"({rel_si}) and (${{clase_policial}}='{slugify_name('Oficial I')}')"

    survey_rows.append({
        "type": f"select_one {list_agente_ii}",
        "name": "agente_ii",
        "label": "5.1- Agente II",
        "required": "yes",
        "relevant": rel_agente_ii
    })

    survey_rows.append({
        "type": f"select_one {list_subof_i}",
        "name": "suboficial_i",
        "label": "5.2- Suboficial I",
        "required": "yes",
        "relevant": rel_subof_i
    })

    survey_rows.append({
        "type": f"select_one {list_subof_ii}",
        "name": "suboficial_ii",
        "label": "5.3- Suboficial II",
        "required": "yes",
        "relevant": rel_subof_ii
    })

    survey_rows.append({
        "type": f"select_one {list_of_i}",
        "name": "oficial_i",
        "label": "5.4 Oficial I",
        "required": "yes",
        "relevant": rel_of_i
    })

    survey_rows.append({"type": "end_group", "name": "p3_end"})

    # =========================
    # DataFrames
    # =========================
    survey_cols = [
        "type", "name", "label", "required", "appearance",
        "relevant", "media::image", "constraint", "constraint_message", "hint"
    ]
    df_survey = pd.DataFrame(survey_rows, columns=survey_cols).fillna("")
    df_choices = pd.DataFrame(choices_rows, columns=["list_name", "name", "label"]).fillna("")
    df_settings = pd.DataFrame([{
        "form_title": form_title,
        "version": version,
        "default_language": idioma,
        "style": "pages"
    }], columns=["form_title", "version", "default_language", "style"]).fillna("")

    return df_survey, df_choices, df_settings

# ==========================================================================================
# Exportar
# ==========================================================================================
st.markdown("---")
st.subheader("📦 Generar XLSForm (Survey123)")

idioma = st.selectbox("Idioma (default_language)", options=["es", "en"], index=0)
version_auto = datetime.now().strftime("%Y%m%d%H%M")
version = st.text_input("Versión (settings.version)", value=version_auto)

if st.button("🧮 Construir XLSForm", use_container_width=True):
    df_survey, df_choices, df_settings = construir_xlsform(
        form_title=form_title,
        logo_media_name=logo_media_name,
        idioma=idioma,
        version=version.strip() or version_auto
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

    nombre_archivo = slugify_name(form_title) + "_xlsform.xlsx"
    descargar_xlsform(df_survey, df_choices, df_settings, nombre_archivo)

    # Descargar logo para media/
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
""")


