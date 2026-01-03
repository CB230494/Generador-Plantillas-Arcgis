# -*- coding: utf-8 -*-
# ==========================================================================================
# App: Encuesta Comunidad → XLSForm para ArcGIS Survey123 (Páginas reales + Glosario por página)
# - Página 1: Introducción (logo + texto EXACTO)
# - Página 2: Consentimiento Informado (MISMO texto) + ¿Acepta participar? (Sí/No)
#             - Si responde "No" => finaliza (end)
# - Página 3: I. DATOS DEMOGRÁFICOS (Cantón + Distrito en cascada + Edad rango + Género + Escolaridad + Relación)
# - Página 4: II. PERCEPCIÓN CIUDADANA DE SEGURIDAD EN EL DISTRITO (7–11) + condicionales 7.1 y 8.1
# - Página 5: III. RIESGOS SOCIALES Y SITUACIONALES EN EL DISTRITO (12–18)
#
# Catálogo manual: Cantón → Distrito (por lotes, permite varios distritos por cantón con ENTER)
# Glosario:
# - Carga AUTOMÁTICA desde "glosario proceso de encuestas ESS.docx" si existe junto a app.py
# - Si NO existe, permite subir el DOCX (una vez) y lo usa automáticamente
# - Solo agrega glosario por página SI hay coincidencias (términos del glosario presentes en esa página)
#
# Exporta XLSForm (Excel) con hojas: survey / choices / settings
# ==========================================================================================

import os
import re
from io import BytesIO
from datetime import datetime

import streamlit as st
import pandas as pd

# ==========================================================================================
# Configuración
# ==========================================================================================
st.set_page_config(page_title="Encuesta Comunidad → XLSForm (Survey123)", layout="wide")
st.title("🏘️ Encuesta Comunidad → XLSForm para ArcGIS Survey123")

st.markdown("""
Genera un **XLSForm** listo para **ArcGIS Survey123** con páginas reales (Next/Back):
- **Página 1**: Introducción (logo + texto).
- **Página 2**: Consentimiento Informado + aceptación (Sí/No) + fin temprano.
- **Página 3**: Datos Demográficos (Cantón→Distrito + campos).
- **Página 4**: Percepción Ciudadana (7–11) con condicionales 7.1 y 8.1.
- **Página 5**: Riesgos Sociales y Situacionales (12–18).
- **Glosario por página (solo si aplica)**: se agrega automáticamente si hay términos del glosario presentes en esa sección.
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

def normalize_txt(s: str) -> str:
    if s is None:
        return ""
    t = str(s).lower().strip()
    t = re.sub(r"[áàäâ]", "a", t)
    t = re.sub(r"[éèëê]", "e", t)
    t = re.sub(r"[íìïî]", "i", t)
    t = re.sub(r"[óòöô]", "o", t)
    t = re.sub(r"[úùüû]", "u", t)
    t = t.replace("ñ", "n")
    t = re.sub(r"\s+", " ", t)
    return t

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
                ws.set_column(col_idx, col_idx, max(14, min(90, len(str(col_name)) + 10)))

    buffer.seek(0)
    st.download_button(
        label=f"📥 Descargar XLSForm ({nombre_archivo})",
        data=buffer,
        file_name=nombre_archivo,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

def add_choice_list(choices_rows, list_name: str, labels: list[str]):
    """Agrega una lista de choices (list_name/name/label)."""
    usados = set()
    for lab in labels:
        nm = slugify_name(lab)
        if nm in usados:
            i = 2
            while f"{nm}_{i}" in usados:
                i += 1
            nm = f"{nm}_{i}"
        usados.add(nm)
        choices_rows.append({"list_name": list_name, "name": nm, "label": lab})

def _append_choice_unique(rows: list, row: dict):
    """Inserta fila en choices evitando duplicados por (list_name,name)."""
    key = (row.get("list_name"), row.get("name"))
    exists = any((r.get("list_name"), r.get("name")) == key for r in rows)
    if not exists:
        rows.append(row)

# ==========================================================================================
# Glosario AUTO
# ==========================================================================================
GLOSSARY_DOCX_DEFAULT = "glosario proceso de encuestas ESS.docx"

def cargar_glosario_desde_docx_bytes(docx_bytes: bytes) -> dict:
    """
    Lee un DOCX (bytes) y construye dict {termino: definicion} usando patrón "Término: definición".
    No recorta ni resume: toma el texto tal cual esté en el DOCX.
    """
    if not docx_bytes:
        return {}
    try:
        from docx import Document
        doc = Document(BytesIO(docx_bytes))
    except Exception:
        return {}

    gloss = {}
    for p in doc.paragraphs:
        txt = (p.text or "").strip()
        if not txt or ":" not in txt:
            continue
        term, defi = txt.split(":", 1)
        term = term.strip()
        defi = defi.strip()
        if term and defi and term not in gloss:
            gloss[term] = defi
    return gloss

def cargar_glosario_auto() -> dict:
    """
    Auto-carga:
    - Si ya está en session_state, úsalo.
    - Si existe archivo local con el nombre default, cárgalo.
    - Si no existe, queda vacío hasta que el usuario suba el DOCX.
    """
    if "glosario_dict" in st.session_state and isinstance(st.session_state.glosario_dict, dict):
        return st.session_state.glosario_dict

    if os.path.exists(GLOSSARY_DOCX_DEFAULT):
        try:
            with open(GLOSSARY_DOCX_DEFAULT, "rb") as f:
                b = f.read()
            gd = cargar_glosario_desde_docx_bytes(b)
            st.session_state.glosario_dict = gd
            st.session_state.glosario_docx_name = GLOSSARY_DOCX_DEFAULT
            st.session_state.glosario_docx_bytes = b
            return gd
        except Exception:
            pass

    st.session_state.glosario_dict = {}
    return {}

def detectar_terminos_glosario(gloss: dict, texto_compuesto: str):
    """Retorna [(termino, definicion)] si el término aparece en el texto de la página (normalizado)."""
    if not gloss:
        return []
    tnorm = normalize_txt(texto_compuesto)
    hallados = []
    for term, defi in gloss.items():
        term_norm = normalize_txt(term)

        variantes = [term_norm]
        # Si el término tiene paréntesis, también buscar la parte base
        if "(" in term:
            base = term.split("(", 1)[0].strip()
            if base:
                variantes.append(normalize_txt(base))

        found = any(v and (v in tnorm) for v in variantes)
        if found:
            hallados.append((term, defi))
    hallados.sort(key=lambda x: normalize_txt(x[0]))
    return hallados

# ==========================================================================================
# Inputs: Logo + "Lugar" (comunidad)
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
    lugar = st.text_input("Nombre del lugar / Comunidad", value="San Carlos Oeste")
    logo_media_name = st.text_input(
        "Nombre de archivo para `media::image`",
        value=st.session_state.get("_logo_name", "001.png"),
        help="Debe coincidir con el archivo dentro de la carpeta `media/` del proyecto Survey123 (Connect)."
    )

form_title = f"Encuesta Comunidad – {lugar.strip()}" if lugar.strip() else "Encuesta Comunidad"
st.markdown(f"### {form_title}")

# ==========================================================================================
# Glosario: carga automática + uploader (solo si no existe)
# ==========================================================================================
gloss = cargar_glosario_auto()

with st.expander("📘 Glosario (carga automática)", expanded=False):
    if gloss:
        st.success(f"Glosario cargado automáticamente ({len(gloss)} términos).")
        st.caption("Se agregará SOLO en las páginas donde haya coincidencias de términos.")
        st.dataframe(pd.DataFrame(
            [{"Término": k, "Definición": v} for k, v in gloss.items()]
        ), use_container_width=True, hide_index=True)
    else:
        st.warning(
            "No se encontró el archivo de glosario junto al app.py. "
            "Si querés, subilo aquí UNA vez y la app lo usará automáticamente."
        )
        up_g = st.file_uploader("Subir glosario (DOCX)", type=["docx"], key="up_glosario_docx")
        if up_g:
            b = up_g.getvalue()
            gd = cargar_glosario_desde_docx_bytes(b)
            st.session_state.glosario_dict = gd
            st.session_state.glosario_docx_name = up_g.name
            st.session_state.glosario_docx_bytes = b
            gloss = gd
            st.success(f"Glosario cargado: {len(gloss)} términos.")

# ==========================================================================================
# Textos EXACTOS solicitados (P1 + P2)
# ==========================================================================================
INTRO_COMUNIDAD_EXACTA = (
    "Con el fin de hacer más segura nuestra comunidad, deseamos concentrarnos en los \n"
    "problemas de seguridad más importantes. Queremos trabajar en conjunto con el gobierno \n"
    "local, otras instituciones y la comunidad para reducir los delitos y riesgos que afectan a las \n"
    "personas. \n"
    "Es importante recordarle que la información que usted nos proporcione es confidencial y se \n"
    "utilizará únicamente para mejorar la seguridad en nuestra área."
)

CONSENT_TITLE = "Consentimiento Informado para la Participación en la Encuesta"

CONSENT_PARRAFOS = [
    "Usted está siendo invitado(a) a participar de forma libre y voluntaria en una encuesta sobre seguridad, convivencia y percepción ciudadana, dirigida a personas mayores de 18 años.",
    "El objetivo de esta encuesta es recopilar información de carácter preventivo y estadístico, con el fin de apoyar la planificación de acciones de prevención, mejora de la convivencia y fortalecimiento de la seguridad en comunidades y zonas comerciales.",
    "La participación es totalmente voluntaria. Usted puede negarse a responder cualquier pregunta, así como retirarse de la encuesta en cualquier momento, sin que ello genere consecuencia alguna.",
    "De conformidad con lo dispuesto en el artículo 5 de la Ley N.º 8968, Ley de Protección de la Persona frente al Tratamiento de sus Datos Personales, se le informa que:"
]

CONSENT_BULLETS = [
    "Finalidad del tratamiento: La información recopilada será utilizada exclusivamente para fines estadísticos, analíticos y preventivos, y no para investigaciones penales, procesos judiciales, sanciones administrativas ni procedimientos disciplinarios.",
    "Datos personales: Algunos apartados permiten, de forma voluntaria, el suministro de datos personales o información de contacto.",
    "Tratamiento de los datos: Los datos serán almacenados, analizados y resguardados bajo criterios de confidencialidad y seguridad, conforme a la normativa vigente.",
    "Destinatarios y acceso: La información será conocida únicamente por el personal autorizado del Ministerio de Seguridad Pública, para los fines indicados. No será cedida a terceros ajenos a estos fines.",
    "Responsable de la base de datos: El Ministerio de Seguridad Pública, a través de la Dirección de Programas Policiales Preventivos, Oficina Estrategia Integral de Prevención para la Seguridad Pública (EIPSEP / Estrategia Sembremos Seguridad) será el responsable del tratamiento y custodia de la información recolectada.",
    "Derechos de la persona participante: Usted conserva el derecho a la autodeterminación informativa y a decidir libremente sobre el suministro de sus datos."
]

CONSENT_CIERRE = [
    "Las respuestas brindadas no constituyen denuncias formales, ni sustituyen los mecanismos legales correspondientes.",
    "Al continuar con la encuesta, usted manifiesta haber leído y comprendido la información anterior y otorga su consentimiento informado para participar."
]

# ==========================================================================================
# Catálogo manual: Cantón → Distrito (por lotes) — permite varios distritos con ENTER
# ==========================================================================================
if "choices_ext_rows" not in st.session_state:
    st.session_state.choices_ext_rows = []

st.markdown("## 🗺️ Catálogo Cantón → Distrito (por lotes)")

with st.expander("Agrega un lote (un Cantón y varios Distritos)", expanded=True):
    col_c1, col_c2 = st.columns(2)
    canton_txt = col_c1.text_input("Cantón (una vez)", value="")
    distritos_txt = col_c2.text_area(
        "Distritos (uno por línea) — podés pegar varios y dar ENTER",
        value="",
        height=120
    )

    col_b1, col_b2 = st.columns([1, 1])
    add_lote = col_b1.button("Agregar lote", type="primary", use_container_width=True)
    clear_all = col_b2.button("Limpiar catálogo", use_container_width=True)

    if clear_all:
        st.session_state.choices_ext_rows = []
        st.success("Catálogo limpiado.")

    if add_lote:
        c = canton_txt.strip()
        distritos = [d.strip() for d in distritos_txt.splitlines() if d.strip()]
        if not c or not distritos:
            st.error("Debes indicar Cantón y al menos un Distrito (uno por línea).")
        else:
            slug_c = slugify_name(c)

            # Placeholders (una sola vez)
            _append_choice_unique(st.session_state.choices_ext_rows, {
                "list_name": "list_canton", "name": "__pick_canton__", "label": "— escoja un cantón —"
            })
            _append_choice_unique(st.session_state.choices_ext_rows, {
                "list_name": "list_distrito", "name": "__pick_distrito__", "label": "— escoja un cantón —", "any": "1"
            })

            # Cantón
            _append_choice_unique(st.session_state.choices_ext_rows, {
                "list_name": "list_canton", "name": slug_c, "label": c
            })

            # Distritos (pueden ser varios)
            usados_d = set()
            for d in distritos:
                base = slugify_name(d)
                nm = base
                if nm in usados_d:
                    i = 2
                    while f"{nm}_{i}" in usados_d:
                        i += 1
                    nm = f"{nm}_{i}"
                usados_d.add(nm)

                _append_choice_unique(st.session_state.choices_ext_rows, {
                    "list_name": "list_distrito", "name": nm, "label": d, "canton_key": slug_c
                })

            st.success(f"Lote agregado: {c} → {len(distritos)} distrito(s).")

if st.session_state.choices_ext_rows:
    st.dataframe(pd.DataFrame(st.session_state.choices_ext_rows), use_container_width=True, hide_index=True, height=260)

# ==========================================================================================
# Construcción XLSForm (survey / choices / settings)
# ==========================================================================================
def construir_xlsform(form_title: str, logo_media_name: str, idioma: str, version: str):
    survey_rows = []
    choices_rows = []

    # =========================
    # Choices base
    # =========================
    list_yesno = "yesno"
    add_choice_list(choices_rows, list_yesno, ["Sí", "No"])
    v_si = slugify_name("Sí")
    v_no = slugify_name("No")

    list_edad = "edad_rangos"
    add_choice_list(choices_rows, list_edad, ["18 a 29 años", "30 a 44 años", "45 a 59 años", "60 años o más"])

    list_genero = "genero"
    add_choice_list(choices_rows, list_genero, ["Femenino", "Masculino", "Persona No Binaria", "Prefiero no decir"])

    list_escolaridad = "escolaridad"
    add_choice_list(choices_rows, list_escolaridad, [
        "Ninguna",
        "Primaria incompleta",
        "Primaria completa",
        "Secundaria incompleta",
        "Secundaria completa",
        "Técnico",
        "Universitaria incompleta",
        "Universitaria completa",
    ])

    list_relacion = "relacion_zona"
    add_choice_list(choices_rows, list_relacion, [
        "Vivo en la zona",
        "Trabajo en la zona",
        "Visito la zona",
        "Estudio en la zona"
    ])

    # Escala 1–5 + No aplica
    list_escala_1a5 = "escala_1a5"
    add_choice_list(choices_rows, list_escala_1a5, [
        "Muy inseguro (1)",
        "Inseguro (2)",
        "Ni seguro ni inseguro (3)",
        "Seguro (4)",
        "Muy seguro (5)",
        "No aplica"
    ])

    list_perc_7 = "perc_7"
    add_choice_list(choices_rows, list_perc_7, [
        "Muy inseguro",
        "Inseguro",
        "Ni seguro ni inseguro",
        "Seguro",
        "Muy seguro"
    ])

    list_comp_8 = "comp_8"
    add_choice_list(choices_rows, list_comp_8, [
        "1 (Mucho Menos Seguro)",
        "2 (Menos Seguro)",
        "3 (Se mantiene igual)",
        "4 (Más Seguro)",
        "5 (Mucho Más Seguro)"
    ])

    # 7.1 (selección múltiple)
    list_7_1 = "preg_7_1"
    add_choice_list(choices_rows, list_7_1, [
        "Venta o distribución de drogas",
        "Consumo de drogas en espacios públicos",
        "Consumo de alcohol en espacios públicos",
        "Riñas o peleas frecuentes",
        "Asaltos o robos a personas",
        "Robos a viviendas o comercios",
        "Amenazas o extorsiones",
        "Balaceras, detonaciones o ruidos similares",
        "Presencia de grupos que generan temor",
        "Vandalismo o daños intencionales",
        "Poca iluminación en calles o espacios públicos",
        "Lotes baldíos o abandonados",
        "Casas o edificios abandonados",
        "Calles en mal estado",
        "Falta de limpieza o acumulación de basura",
        "Paradas de bus inseguras",
        "Falta de cámaras de seguridad",
        "Comercios inseguros o sin control",
        "Daños frecuentes a la propiedad",
        "Presencia de personas en situación de calle",
        "Ventas ambulantes desordenadas",
        "Problemas con transporte informal",
        "Zonas donde se concentra consumo de alcohol o drogas",
        "Puntos conflictivos recurrentes",
        "Falta de patrullajes visibles",
        "Falta de presencia policial en la zona",
        "Situaciones de violencia intrafamiliar",
        "Situaciones de violencia de género",
        "Otro problema que considere importante"
    ])

    # 9 (matriz): zonas
    list_zonas_9 = "zonas_9"
    add_choice_list(choices_rows, list_zonas_9, [
        "Discotecas, bares, sitios de entretenimiento",
        "Espacios recreativos (parques, play, plaza de deportes)",
        "Lugar de residencia (casa de habitación)",
        "Paradas y/o estaciones de buses, taxis, trenes",
        "Puentes peatonales",
        "Transporte público",
        "Zona bancaria",
        "Zona de comercio",
        "Zonas residenciales (calles y barrios, distinto a su casa)",
        "Zonas francas",
        "Lugares de interés turístico",
        "Centros educativos",
        "Zonas con deficiencia de iluminación"
    ])

    # 10: tipo de espacio más inseguro
    list_10 = "preg_10"
    add_choice_list(choices_rows, list_10, [
        "Discotecas, bares, sitios de entretenimiento",
        "Espacios recreativos (parques, play, plaza de deportes)",
        "Lugar de residencia (casa de habitación)",
        "Paradas y/o estaciones de buses, taxis, trenes",
        "Puentes peatonales",
        "Transporte público",
        "Zona bancaria",
        "Zona comercial",
        "Zonas francas",
        "Zonas residenciales (calles y barrios, distinto a su casa)",
        "Lugares de interés turístico",
        "Centros educativos",
        "Zonas con deficiencia de iluminación",
        "Otros"
    ])

    # 12 (selección múltiple)
    list_12 = "preg_12"
    add_choice_list(choices_rows, list_12, [
        "Problemas vecinales o conflictos entre vecinos",
        "Personas en situación de ocio",
        "Presencia de personas en situación de calle",
        "Zona donde se ejerce prostitución",
        "Desvinculación escolar (deserción escolar)",
        "Falta de oportunidades laborales",
        "Acumulación de basura, aguas negras o mal alcantarillado",
        "Carencia o inexistencia de alumbrado público",
        "Lotes baldíos",
        "Cuarterías",
        "Asentamientos informales o precarios",
        "Pérdida de espacios públicos (parques, polideportivos u otros)",
        "Consumo de alcohol en vía pública",
        "Ventas informales desordenadas",
        "Escándalos musicales o ruidos excesivos",
        "Otro problema que considere importante"
    ])

    # 13 (selección múltiple)
    list_13 = "preg_13"
    add_choice_list(choices_rows, list_13, [
        "Falta de oferta educativa",
        "Falta de oferta deportiva",
        "Falta de oferta recreativa",
        "Falta de actividades culturales"
    ])

    # 14 (selección múltiple)
    list_14 = "preg_14"
    add_choice_list(choices_rows, list_14, [
        "Área privada",
        "Área pública",
        "No se observa consumo"
    ])

    # 15 (selección múltiple)
    list_15 = "preg_15"
    add_choice_list(choices_rows, list_15, [
        "Calles en mal estado",
        "Falta de señalización de tránsito",
        "Carencia o inexistencia de aceras"
    ])

    # 16 (selección múltiple)
    list_16 = "preg_16"
    add_choice_list(choices_rows, list_16, [
        "Casa de habitación (Espacio Cerrado)",
        "Edificación abandonada",
        "Lote baldío",
        "Otro"
    ])

    # 17 (selección múltiple)
    list_17 = "preg_17"
    add_choice_list(choices_rows, list_17, [
        "Informal (taxis piratas)",
        "Plataformas (digitales)"
    ])

    # 18 (selección múltiple)
    list_18 = "preg_18"
    add_choice_list(choices_rows, list_18, [
        "Falta de presencia policial",
        "Presencia policial insuficiente",
        "Presencia policial solo en ciertos horarios",
        "No observa presencia policial"
    ])

    # =========================
    # Choices: catálogo Cantón → Distrito (manual)
    # =========================
    for r in st.session_state.choices_ext_rows:
        choices_rows.append(dict(r))

    # =========================
    # Página 1: Introducción
    # =========================
    survey_rows.append({"type": "begin_group", "name": "p1_intro", "label": "Introducción", "appearance": "field-list"})
    survey_rows.append({"type": "note", "name": "p1_logo", "label": form_title, "media::image": logo_media_name})
    survey_rows.append({"type": "note", "name": "p1_texto", "label": INTRO_COMUNIDAD_EXACTA})
    survey_rows.append({"type": "end_group", "name": "p1_end"})

    # =========================
    # Página 2: Consentimiento
    # =========================
    survey_rows.append({"type": "begin_group", "name": "p2_consent", "label": "Consentimiento Informado", "appearance": "field-list"})
    survey_rows.append({"type": "note", "name": "p2_titulo", "label": CONSENT_TITLE})

    for i, p in enumerate(CONSENT_PARRAFOS, start=1):
        survey_rows.append({"type": "note", "name": f"p2_p_{i}", "label": p})

    for j, b in enumerate(CONSENT_BULLETS, start=1):
        survey_rows.append({"type": "note", "name": f"p2_b_{j}", "label": f"• {b}"})

    for k, c in enumerate(CONSENT_CIERRE, start=1):
        survey_rows.append({"type": "note", "name": f"p2_c_{k}", "label": c})

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

    rel_si = f"${{acepta_participar}}='{v_si}'"

    # =========================
    # Página 3: Datos demográficos
    # =========================
    # Texto de página para detectar glosario (labels + opciones relevantes)
    p3_text = " ".join([
        "Datos demográficos",
        "Cantón Distrito Edad Género Escolaridad relación con la zona",
        "Vivo Trabajo Visito Estudio"
    ])
    p3_glos = detectar_terminos_glosario(gloss, p3_text)

    survey_rows.append({"type": "begin_group", "name": "p3_demograficos", "label": "Datos demográficos", "appearance": "field-list", "relevant": rel_si})

    # Cantón
    survey_rows.append({
        "type": "select_one list_canton",
        "name": "canton",
        "label": "1. Cantón:",
        "required": "yes",
        "relevant": rel_si,
        "constraint": ". != '__pick_canton__'",
        "constraint_message": "Seleccione un cantón válido."
    })

    # Distrito (cascada)
    survey_rows.append({
        "type": "select_one list_distrito",
        "name": "distrito",
        "label": "2. Distrito:",
        "required": "yes",
        "relevant": rel_si,
        "choice_filter": "canton_key=${canton} or any='1'",
        "constraint": ". != '__pick_distrito__'",
        "constraint_message": "Seleccione un distrito válido."
    })

    # Edad (rango)
    survey_rows.append({
        "type": f"select_one {list_edad}",
        "name": "edad_rango",
        "label": "3. Edad (en años cumplidos): marque con una X la categoría que incluya su edad.",
        "required": "yes",
        "relevant": rel_si
    })

    # Género
    survey_rows.append({
        "type": f"select_one {list_genero}",
        "name": "genero",
        "label": "4. ¿Con cuál de estas opciones se identifica?",
        "required": "yes",
        "relevant": rel_si
    })

    # Escolaridad
    survey_rows.append({
        "type": f"select_one {list_escolaridad}",
        "name": "escolaridad",
        "label": "5. Escolaridad:",
        "required": "yes",
        "relevant": rel_si
    })

    # Relación con la zona (según imagen: selección única)
    survey_rows.append({
        "type": f"select_one {list_relacion}",
        "name": "relacion_zona",
        "label": "6. ¿Cuál es su relación con la zona?",
        "required": "yes",
        "relevant": rel_si
    })

    # Glosario (solo si aplica)
    if p3_glos:
        survey_rows.append({
            "type": f"select_one {list_yesno}",
            "name": "p3_ver_glosario",
            "label": "¿Desea acceder al glosario de esta sección?",
            "required": "",
            "appearance": "minimal",
            "relevant": rel_si
        })
    survey_rows.append({"type": "end_group", "name": "p3_end"})

    if p3_glos:
        rel_p3_g = f"({rel_si}) and (${{p3_ver_glosario}}='{v_si}')"
        survey_rows.append({"type": "begin_group", "name": "p3_glosario", "label": "Glosario", "appearance": "field-list", "relevant": rel_p3_g})
        survey_rows.append({"type": "note", "name": "p3_glos_nota", "label": "Glosario de esta sección. Para regresar a la página anterior, use el botón ATRÁS.", "relevant": rel_p3_g})
        for i, (term, defi) in enumerate(p3_glos, start=1):
            survey_rows.append({"type": "note", "name": f"p3_g_{i}", "label": f"{term}: {defi}", "relevant": rel_p3_g})
        survey_rows.append({"type": "end_group", "name": "p3_glos_end"})

    # =========================
    # Página 4: Percepción ciudadana (7–11)
    # =========================
    p4_text = " ".join([
        "Percepción ciudadana seguridad distrito",
        "Muy inseguro Inseguro Ni seguro ni inseguro Seguro Muy seguro",
        "Venta o distribución de drogas Consumo de drogas alcohol Riñas Asaltos Robos Amenazas extorsiones Balaceras",
        "Vandalismo Daños a la propiedad Estafa Contrabando Hurto Receptación Delitos sexuales"
    ])
    p4_glos = detectar_terminos_glosario(gloss, p4_text)

    survey_rows.append({"type": "begin_group", "name": "p4_percepcion", "label": "Percepción ciudadana de seguridad en el distrito", "appearance": "field-list", "relevant": rel_si})

    # 7
    survey_rows.append({
        "type": f"select_one {list_perc_7}",
        "name": "preg_7",
        "label": "7. ¿Qué tan seguro percibe usted el distrito donde reside o transita?",
        "required": "yes",
        "appearance": "minimal",
        "relevant": rel_si
    })

    rel_7_1 = f"({rel_si}) and (${{preg_7}}='{slugify_name('Muy inseguro')}' or ${{preg_7}}='{slugify_name('Inseguro')}')"

    # 7.1
    survey_rows.append({
        "type": f"select_multiple {list_7_1}",
        "name": "preg_7_1",
        "label": "7.1. Indique por qué considera el distrito inseguro (Marque todas las situaciones que usted percibe que ocurren con mayor frecuencia en su comunidad):",
        "required": "yes",
        "relevant": rel_7_1
    })

    survey_rows.append({
        "type": "note",
        "name": "nota_7_1",
        "label": "Esta pregunta recoge percepción general y no constituye denuncia.",
        "relevant": rel_7_1
    })

    # 8
    survey_rows.append({
        "type": f"select_one {list_comp_8}",
        "name": "preg_8",
        "label": "8. ¿Cómo se percibe la seguridad en este distrito este año en comparación con el año anterior?",
        "required": "yes",
        "appearance": "minimal",
        "relevant": rel_si
    })

    # 8.1 (si selecciona cualquier opción 1..5, pasa a 8.1 -> en práctica siempre aplica)
    rel_8_1 = f"({rel_si}) and (${{preg_8}}!='')"
    survey_rows.append({
        "type": "text",
        "name": "preg_8_1",
        "label": "8.1. Indique por qué:",
        "required": "yes",
        "appearance": "multiline",
        "relevant": rel_8_1
    })

    # 9 matriz (select_one por fila)
    survey_rows.append({
        "type": "begin_group",
        "name": "preg_9_grp",
        "label": "9. Indique qué tan seguros percibe, en términos de seguridad, en los siguientes espacios de su Distrito:",
        "appearance": "field-list",
        "relevant": rel_si
    })
    survey_rows.append({
        "type": f"select_one {list_escala_1a5}",
        "name": "p9_discotecas",
        "label": "Discotecas, bares, sitios de entretenimiento",
        "required": "yes",
        "relevant": rel_si
    })
    survey_rows.append({
        "type": f"select_one {list_escala_1a5}",
        "name": "p9_recreativos",
        "label": "Espacios recreativos (parques, play, plaza de deportes)",
        "required": "yes",
        "relevant": rel_si
    })
    survey_rows.append({
        "type": f"select_one {list_escala_1a5}",
        "name": "p9_residencia",
        "label": "Lugar de residencia (casa de habitación)",
        "required": "yes",
        "relevant": rel_si
    })
    survey_rows.append({
        "type": f"select_one {list_escala_1a5}",
        "name": "p9_paradas",
        "label": "Paradas y/o estaciones de buses, taxis, trenes",
        "required": "yes",
        "relevant": rel_si
    })
    survey_rows.append({
        "type": f"select_one {list_escala_1a5}",
        "name": "p9_puentes",
        "label": "Puentes peatonales",
        "required": "yes",
        "relevant": rel_si
    })
    survey_rows.append({
        "type": f"select_one {list_escala_1a5}",
        "name": "p9_transporte",
        "label": "Transporte público",
        "required": "yes",
        "relevant": rel_si
    })
    survey_rows.append({
        "type": f"select_one {list_escala_1a5}",
        "name": "p9_bancaria",
        "label": "Zona bancaria",
        "required": "yes",
        "relevant": rel_si
    })
    survey_rows.append({
        "type": f"select_one {list_escala_1a5}",
        "name": "p9_comercio",
        "label": "Zona de comercio",
        "required": "yes",
        "relevant": rel_si
    })
    survey_rows.append({
        "type": f"select_one {list_escala_1a5}",
        "name": "p9_zonas_res",
        "label": "Zonas residenciales (calles y barrios, distinto a su casa)",
        "required": "yes",
        "relevant": rel_si
    })
    survey_rows.append({
        "type": f"select_one {list_escala_1a5}",
        "name": "p9_zonas_fr",
        "label": "Zonas francas",
        "required": "yes",
        "relevant": rel_si
    })
    survey_rows.append({
        "type": f"select_one {list_escala_1a5}",
        "name": "p9_turistico",
        "label": "Lugares de interés turístico",
        "required": "yes",
        "relevant": rel_si
    })
    survey_rows.append({
        "type": f"select_one {list_escala_1a5}",
        "name": "p9_educativos",
        "label": "Centros educativos",
        "required": "yes",
        "relevant": rel_si
    })
    survey_rows.append({
        "type": f"select_one {list_escala_1a5}",
        "name": "p9_iluminacion",
        "label": "Zonas con deficiencia de iluminación",
        "required": "yes",
        "relevant": rel_si
    })
    survey_rows.append({"type": "end_group", "name": "preg_9_grp_end"})

    # 10
    survey_rows.append({
        "type": f"select_one {list_10}",
        "name": "preg_10",
        "label": "10. Según su percepción ¿cuál de los siguientes tipos de espacios del distrito considera más inseguro?",
        "required": "yes",
        "appearance": "minimal",
        "relevant": rel_si
    })

    # 11
    survey_rows.append({
        "type": "text",
        "name": "preg_11",
        "label": "11. Según su percepción, describa brevemente por qué considera inseguro el tipo de espacio seleccionado en la pregunta anterior.",
        "required": "yes",
        "appearance": "multiline",
        "relevant": rel_si
    })

    # Glosario (solo si aplica)
    if p4_glos:
        survey_rows.append({
            "type": f"select_one {list_yesno}",
            "name": "p4_ver_glosario",
            "label": "¿Desea acceder al glosario de esta sección?",
            "required": "",
            "appearance": "minimal",
            "relevant": rel_si
        })

    survey_rows.append({"type": "end_group", "name": "p4_end"})

    if p4_glos:
        rel_p4_g = f"({rel_si}) and (${{p4_ver_glosario}}='{v_si}')"
        survey_rows.append({"type": "begin_group", "name": "p4_glosario", "label": "Glosario", "appearance": "field-list", "relevant": rel_p4_g})
        survey_rows.append({"type": "note", "name": "p4_glos_nota", "label": "Glosario de esta sección. Para regresar a la página anterior, use el botón ATRÁS.", "relevant": rel_p4_g})
        for i, (term, defi) in enumerate(p4_glos, start=1):
            survey_rows.append({"type": "note", "name": f"p4_g_{i}", "label": f"{term}: {defi}", "relevant": rel_p4_g})
        survey_rows.append({"type": "end_group", "name": "p4_glos_end"})

    # =========================
    # Página 5: Riesgos sociales y situacionales (12–18)
    # =========================
    p5_text = " ".join([
        "Riesgos sociales situacionales distrito",
        "Problemas vecinales Personas en situacion de ocio",
        "Prostitucion Desvinculacion escolar",
        "Asentamientos informales precarios",
        "Consumo de alcohol en via publica",
        "Cuarterias Lotes baldios",
        "Bunkeres puntos de venta de drogas",
        "Transporte informal taxis piratas",
        "Presencia policial insuficiente"
    ])
    p5_glos = detectar_terminos_glosario(gloss, p5_text)

    survey_rows.append({"type": "begin_group", "name": "p5_riesgos", "label": "Riesgos sociales y situacionales en el distrito", "appearance": "field-list", "relevant": rel_si})

    survey_rows.append({
        "type": "note",
        "name": "p5_intro",
        "label": "A continuación, se presentará una lista de problemáticas que se catalogan como factores situacionales, con la finalidad de que seleccione aquellos que considere que ocurren en su distrito.",
        "relevant": rel_si
    })

    # 12
    survey_rows.append({
        "type": f"select_multiple {list_12}",
        "name": "preg_12",
        "label": "12. Según su percepción u observación, seleccione las problemáticas que afectan su distrito:",
        "required": "yes",
        "relevant": rel_si
    })

    survey_rows.append({
        "type": "note",
        "name": "nota_12",
        "label": "Nota: esta pregunta es de selección múltiple, se engloba estas problemáticas en una sola pregunta ya que ninguno de ellas se subdivide.",
        "relevant": rel_si
    })

    # 13
    survey_rows.append({
        "type": f"select_multiple {list_13}",
        "name": "preg_13",
        "label": "13. En relación con la inversión social en su distrito, indique cuáles de las siguientes carencias identifica:",
        "required": "yes",
        "relevant": rel_si
    })

    # 14
    survey_rows.append({
        "type": f"select_multiple {list_14}",
        "name": "preg_14",
        "label": "14. Según su percepción u observación, indique dónde se presenta consumo de drogas en el distrito:",
        "required": "yes",
        "relevant": rel_si
    })

    # 15
    survey_rows.append({
        "type": f"select_multiple {list_15}",
        "name": "preg_15",
        "label": "15. Indique las principales deficiencias de infraestructura vial que afectan su distrito:",
        "required": "yes",
        "relevant": rel_si
    })

    # 16
    survey_rows.append({
        "type": f"select_multiple {list_16}",
        "name": "preg_16",
        "label": "16. Según su percepción u observación, indique en qué tipo de espacios se identifica la existencia de puntos de venta de drogas (búnkeres) en el distrito:",
        "required": "yes",
        "relevant": rel_si
    })

    # 17
    survey_rows.append({
        "type": f"select_multiple {list_17}",
        "name": "preg_17",
        "label": "17. En relación con el transporte en su distrito, indique cuáles situaciones representan una afectación:",
        "required": "yes",
        "relevant": rel_si
    })

    # 18
    survey_rows.append({
        "type": f"select_multiple {list_18}",
        "name": "preg_18",
        "label": "18. En relación con la presencia policial en su distrito, indique cuál de las siguientes situaciones identifica:",
        "required": "yes",
        "relevant": rel_si
    })

    # Glosario (solo si aplica)
    if p5_glos:
        survey_rows.append({
            "type": f"select_one {list_yesno}",
            "name": "p5_ver_glosario",
            "label": "¿Desea acceder al glosario de esta sección?",
            "required": "",
            "appearance": "minimal",
            "relevant": rel_si
        })

    survey_rows.append({"type": "end_group", "name": "p5_end"})

    if p5_glos:
        rel_p5_g = f"({rel_si}) and (${{p5_ver_glosario}}='{v_si}')"
        survey_rows.append({"type": "begin_group", "name": "p5_glosario", "label": "Glosario", "appearance": "field-list", "relevant": rel_p5_g})
        survey_rows.append({"type": "note", "name": "p5_glos_nota", "label": "Glosario de esta sección. Para regresar a la página anterior, use el botón ATRÁS.", "relevant": rel_p5_g})
        for i, (term, defi) in enumerate(p5_glos, start=1):
            survey_rows.append({"type": "note", "name": f"p5_g_{i}", "label": f"{term}: {defi}", "relevant": rel_p5_g})
        survey_rows.append({"type": "end_group", "name": "p5_glos_end"})

    # =========================
    # DataFrames
    # =========================
    survey_cols = [
        "type", "name", "label", "required", "appearance",
        "relevant", "media::image", "constraint", "constraint_message", "choice_filter"
    ]
    df_survey = pd.DataFrame(survey_rows, columns=survey_cols).fillna("")

    # choices: incluir columnas extra si existen (canton_key / any)
    all_choice_keys = set()
    for r in choices_rows:
        all_choice_keys.update(r.keys())
    base_choice_cols = ["list_name", "name", "label"]
    for k in sorted(all_choice_keys):
        if k not in base_choice_cols:
            base_choice_cols.append(k)
    df_choices = pd.DataFrame(choices_rows, columns=base_choice_cols).fillna("")

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
