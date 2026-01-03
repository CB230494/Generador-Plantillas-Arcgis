# -*- coding: utf-8 -*-
# ==========================================================================================
# App: XLSForm Survey123 — Comunidad (Páginas 1 a 5)
# - Página 1: Introducción con logo + delegación + texto corto (exacto)
# - Página 2: Consentimiento Informado ORDENADO + ¿Acepta participar? (Sí/No) -> si No: end
# - Página 3: Datos demográficos (incluye Cantón + Distrito con catálogo editable)
# - Página 4: Incidencia relacionada a delitos (incluye VI con condicionales)
#            + Glosario por sección (SOLO si hay similitudes con el Word)
#            + Integración del glosario: EXACTAMENTE como tu patrón (begin_group + notes + end)
# - Página 5: Riesgos sociales (según comunidad)
#            + Glosario por sección (SOLO si hay similitudes con el Word)
#            + Integración del glosario: EXACTAMENTE como tu patrón (begin_group + notes + end)
# - Exporta XLSForm (Excel) con hojas: survey / choices / settings
# ==========================================================================================

import re
import unicodedata
from io import BytesIO
from datetime import datetime

import streamlit as st
import pandas as pd


# ==========================================================================================
# Configuración
# ==========================================================================================
st.set_page_config(page_title="XLSForm Survey123 — Comunidad (P1–P5)", layout="wide")
st.title("XLSForm Survey123 — Comunidad (Páginas 1 a 5)")

st.markdown("""
Genera un **XLSForm** listo para **ArcGIS Survey123** con páginas reales (Next/Back):
- **Página 1**: Introducción.
- **Página 2**: Consentimiento Informado + aceptación.
- **Página 3**: Datos demográficos (incluye **Cantón + Distrito**).
- **Página 4**: Incidencia relacionada a delitos (incluye **Violencia Intrafamiliar** con condicionales).
- **Página 5**: Riesgos sociales.
- **Glosario por sección (P4 y P5)**: se integra **solo si hay similitudes** con el glosario Word.
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
                ws.set_column(col_idx, col_idx, max(14, min(110, len(str(col_name)) + 10)))

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
    for lab in labels:
        choices_rows.append({
            "list_name": list_name,
            "name": slugify_name(lab),
            "label": lab
        })


def _norm_txt(s: str) -> str:
    """Minúsculas + sin tildes (para match robusto)."""
    s = (s or "").lower()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return s


# ==========================================================================================
# Glosario: leer DOCX + buscar similitudes
# ==========================================================================================
def cargar_glosario_docx_bytes(docx_bytes: bytes) -> dict:
    """
    Lee glosario desde DOCX.
    Soporta:
      - Párrafos 'Término: definición'
      - Tablas (col1 término, col2 definición)
    """
    from docx import Document
    from io import BytesIO as _BIO

    doc = Document(_BIO(docx_bytes))
    glos = {}

    # Párrafos "Término: Definición"
    for p in doc.paragraphs:
        txt = (p.text or "").strip()
        if not txt:
            continue
        txt = txt.replace("\t", ": ")
        if ":" in txt:
            term, defin = txt.split(":", 1)
            term = term.strip()
            defin = defin.strip()
            if term and defin:
                glos[term] = defin

    # Tablas (si existen)
    try:
        for table in doc.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells]
                if len(cells) >= 2 and cells[0] and cells[1]:
                    term = cells[0].strip()
                    defin = cells[1].strip()
                    if term and defin:
                        glos[term] = defin
    except Exception:
        pass

    return glos


def cargar_glosario_docx_auto() -> dict:
    """
    Carga automáticamente el glosario:
    1) Si el usuario sube el DOCX, usa ese.
    2) Si no, intenta leerlo desde rutas conocidas (local o /mnt/data).
    """
    # 1) uploader
    st.markdown("---")
    st.subheader("📘 Glosario (Word) — carga automática")
    up = st.file_uploader("Glosario Word (.docx)", type=["docx"], help="Sube el glosario que ya me pasaste (DOCX).")

    if up is not None:
        try:
            return cargar_glosario_docx_bytes(up.getvalue())
        except Exception as e:
            st.error(f"No se pudo leer el DOCX cargado: {e}")
            return {}

    # 2) rutas conocidas (por si está en el proyecto)
    rutas = [
        "glosario proceso de encuestas ESS.docx",
        "/mnt/data/glosario proceso de encuestas ESS.docx",
    ]
    for rp in rutas:
        try:
            with open(rp, "rb") as f:
                return cargar_glosario_docx_bytes(f.read())
        except Exception:
            continue

    st.warning("No se encontró el DOCX automáticamente. Súbelo arriba para activar el glosario por similitudes.")
    return {}


def buscar_similitudes(glosario: dict, textos: list[str]) -> list[tuple[str, str]]:
    """
    Devuelve [(termino, definicion)] solo para términos que aparecen en los textos de la página.
    Match robusto: minúsculas + sin tildes + frontera alfanumérica.
    """
    if not glosario:
        return []
    corpus = _norm_txt("\n".join([t for t in textos if t]))
    hits = []
    for term, defin in glosario.items():
        tt = _norm_txt(term).strip()
        if not tt:
            continue
        # match por palabra / frase con fronteras alfanuméricas
        if re.search(rf"(?<![a-z0-9]){re.escape(tt)}(?![a-z0-9])", corpus):
            hits.append((term, defin))

    # sin duplicados
    seen = set()
    out = []
    for t, d in hits:
        if t not in seen:
            out.append((t, d))
            seen.add(t)
    return out


# Cargar glosario (UNA vez por sesión)
if "glosario_doc" not in st.session_state:
    st.session_state.glosario_doc = {}

if st.session_state.glosario_doc == {}:
    st.session_state.glosario_doc = cargar_glosario_docx_auto()


# ==========================================================================================
# Inputs (logo + delegación)
# ==========================================================================================
DEFAULT_LOGO_PATH = "001.png"

col_logo, col_txt = st.columns([1, 3], vertical_alignment="center")

with col_logo:
    up_logo = st.file_uploader("Logo (PNG/JPG)", type=["png", "jpg", "jpeg"], key="logo_uploader")
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
    delegacion = st.text_input("Nombre del lugar / comunidad", value="San Carlos Oeste")
    logo_media_name = st.text_input(
        "Nombre de archivo para `media::image`",
        value=st.session_state.get("_logo_name", "001.png"),
        help="Debe coincidir con el archivo dentro de la carpeta `media/` en Survey123 Connect."
    )

form_title = f"Encuesta Comunidad – {delegacion.strip()}" if delegacion.strip() else "Encuesta Comunidad"
st.markdown(f"### {form_title}")


# ==========================================================================================
# Catálogo Cantón → Distritos (como ANTES: varios distritos por líneas)
# ==========================================================================================
st.markdown("---")
st.subheader("📍 Catálogo Cantón → Distritos (para Survey123)")

if "catalogo_cantones" not in st.session_state:
    # { slug_canton: {"label": "Canton", "distritos": [(slug_dist, "Distrito"), ...]} }
    st.session_state.catalogo_cantones = {}

with st.expander("Agregar cantón y varios distritos (uno por línea) — COMO ANTES", expanded=True):
    c1, c2 = st.columns([1, 2])
    canton_txt = c1.text_input("Cantón (una vez)", value="", key="canton_txt")
    distritos_txt = c2.text_area(
        "Distritos (uno por línea para ese cantón)",
        value="",
        height=140,
        key="distritos_txt",
        help="Pegá o escribí varios distritos, UNO por línea. Luego presioná Agregar."
    )

    b1, b2 = st.columns([1, 1])
    if b1.button("Agregar / Actualizar cantón", type="primary", use_container_width=True):
        c = canton_txt.strip()
        dlist = [d.strip() for d in distritos_txt.splitlines() if d.strip()]
        if not c or not dlist:
            st.error("Debe indicar un Cantón y al menos un Distrito (uno por línea).")
        else:
            sc = slugify_name(c)
            if sc not in st.session_state.catalogo_cantones:
                st.session_state.catalogo_cantones[sc] = {"label": c, "distritos": []}
            else:
                st.session_state.catalogo_cantones[sc]["label"] = c

            existentes = {sd for sd, _ in st.session_state.catalogo_cantones[sc]["distritos"]}
            for d in dlist:
                sd = slugify_name(d)
                if sd not in existentes:
                    st.session_state.catalogo_cantones[sc]["distritos"].append((sd, d))
                    existentes.add(sd)

            st.success(f"Listo: {c} → {len(st.session_state.catalogo_cantones[sc]['distritos'])} distritos guardados.")

    if b2.button("Limpiar catálogo completo", use_container_width=True):
        st.session_state.catalogo_cantones = {}
        st.success("Catálogo limpiado.")

# Vista previa del catálogo
if st.session_state.catalogo_cantones:
    rows_prev = []
    for _, obj in st.session_state.catalogo_cantones.items():
        canton_label = obj["label"]
        for _, dlab in obj["distritos"]:
            rows_prev.append({"Cantón": canton_label, "Distrito": dlab})
    st.dataframe(pd.DataFrame(rows_prev), use_container_width=True, hide_index=True, height=260)
else:
    st.info("Aún no has cargado cantones/distritos. Podés cargarlo antes de generar el XLSForm.")


# ==========================================================================================
# Textos EXACTOS solicitados (P1 y P2)
# ==========================================================================================
INTRO_CORTA_EXACTA = (
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
    "Destinatarios y acceso: La información será conocida únicamente por el personal autorizado, para los fines indicados. No será cedida a terceros ajenos a estos fines.",
    "Responsable de la base de datos: El Ministerio de Seguridad Pública, a través de las dependencias competentes, será responsable del tratamiento y custodia de la información recolectada.",
    "Derechos de la persona participante: Usted conserva el derecho a la autodeterminación informativa y a decidir libremente sobre el suministro de sus datos."
]

CONSENT_CIERRE = [
    "Las respuestas brindadas no constituyen denuncias formales, ni sustituyen los mecanismos legales correspondientes.",
    "Al continuar con la encuesta, usted manifiesta haber leído y comprendido la información anterior y otorga su consentimiento informado para participar."
]


# ==========================================================================================
# Construcción XLSForm (MISMA LÓGICA que tu patrón)
# ==========================================================================================
def construir_xlsform(form_title: str, logo_media_name: str, idioma: str, version: str, glosario: dict):
    survey_rows = []
    choices_rows = []

    # =========================
    # Choices base
    # =========================
    list_yesno = "yesno"
    v_si = slugify_name("Sí")
    v_no = slugify_name("No")
    add_choice_list(choices_rows, list_yesno, ["Sí", "No"])

    # =========================
    # Cantón/Distrito con choice_filter
    # =========================
    list_canton = "list_canton"
    list_distrito = "list_distrito"

    # placeholders (para forzar selección)
    choices_rows.append({"list_name": list_canton, "name": "__pick_canton__", "label": "— escoja un cantón —"})
    choices_rows.append({"list_name": list_distrito, "name": "__pick_distrito__", "label": "— escoja un cantón —", "canton_key": "", "any": "1"})

    for sc, obj in st.session_state.catalogo_cantones.items():
        choices_rows.append({"list_name": list_canton, "name": sc, "label": obj["label"]})
        for sd, dlab in obj["distritos"]:
            choices_rows.append({"list_name": list_distrito, "name": sd, "label": dlab, "canton_key": sc})

    # =========================
    # Choices: Demográficos
    # =========================
    list_genero = "genero"
    add_choice_list(choices_rows, list_genero, ["Masculino", "Femenino", "LGTBQ+"])

    list_escolaridad = "escolaridad"
    add_choice_list(choices_rows, list_escolaridad, [
        "Ninguna",
        "Primaria",
        "Primaria incompleta",
        "Secundaria completa",
        "Secundaria incompleta",
        "Universitaria",
        "Universitaria incompleta",
        "Técnico",
    ])

    list_relacion = "relacion_zona"
    add_choice_list(choices_rows, list_relacion, ["Vivo en la zona", "Trabajo en la zona", "Visito la zona"])

    # P4
    list_seguridad_si_no = "seguridad_barrio"
    add_choice_list(choices_rows, list_seguridad_si_no, ["Sí", "No"])

    list_comp_anual = "comparacion_anual"
    add_choice_list(choices_rows, list_comp_anual, ["Más seguro", "Igual", "Menos seguro"])

    list_seg_lugares = "seguro_inseguro_noexiste"
    add_choice_list(choices_rows, list_seg_lugares, ["Seguro", "Inseguro", "No existe en el Barrio"])

    list_incidencia_delitos = "incidencia_delitos"
    add_choice_list(choices_rows, list_incidencia_delitos, [
        "Disturbios en vía pública.(Riñas o Agresión)",
        "Daños a la propiedad. (Destruir, inutilizar o desaparecer).",
        "Extorsión (intimidar o amenazar a otras personas con fines de lucro).",
        "Hurto. (sustracción de artículos mediante el descuido).",
        "Receptación (persona que adquiere, recibe u oculta artículos provenientes de un delito en el que no participó).",
        "Contrabando (licor, cigarrillos, medicinas, ropa, calzado, etc.)",
        "Maltrato animal",
        "Tráfico ilegal de personas (coyotaje)"
    ])

    list_venta_drogas = "venta_drogas"
    add_choice_list(choices_rows, list_venta_drogas, ["bunker espacio cerrado", "vía pública", "exprés"])

    list_delitos_vida = "delitos_vida"
    add_choice_list(choices_rows, list_delitos_vida, ["Homicidios", "Heridos"])

    list_delitos_sexuales = "delitos_sexuales"
    add_choice_list(choices_rows, list_delitos_sexuales, ["Abuso sexual", "Acoso sexual", "Violación"])

    list_asaltos = "asaltos"
    add_choice_list(choices_rows, list_asaltos, ["Asalto a personas", "Asalto a comercio", "Asalto a vivienda", "Asalto a transporte público"])

    list_estafas = "estafas"
    add_choice_list(choices_rows, list_estafas, [
        "Billetes falso",
        "Documentos falsos",
        "Estafa (Oro)",
        "Lotería falsos",
        "Estafas informáticas",
        "Estafa telefónica",
        "Estafa con tarjetas"
    ])

    list_robo_fuerza = "robo_fuerza"
    add_choice_list(choices_rows, list_robo_fuerza, [
        "Tacha a comercio",
        "Tacha a edificaciones",
        "Tacha a vivienda",
        "Tacha de vehículos",
        "Robo de Ganado Abigeato (Destace de ganado)",
        "Robo de bienes agrícola",
        "Robo de vehículos",
        "Robo de cable",
        "Robo de combustible"
    ])

    list_abandono = "abandono_personas"
    add_choice_list(choices_rows, list_abandono, ["Abandono de adulto mayor", "Abandono de menor de edad", "Abandono de incapaz"])

    list_explotacion = "explotacion_infantil"
    add_choice_list(choices_rows, list_explotacion, ["Sexual", "Laboral"])

    list_ambientales = "delitos_ambientales"
    add_choice_list(choices_rows, list_ambientales, ["Caza ilegal", "Pesca ilegal", "Tala ilegal"])

    list_trata = "trata_personas"
    add_choice_list(choices_rows, list_trata, ["Con fines laborales", "Con fines sexuales"])

    list_vi_tipos = "vi_tipos"
    add_choice_list(choices_rows, list_vi_tipos, [
        "Violencia psicológica (gritos, amenazas, burlas, maltratos, etc)",
        "Violencia física (golpes, empujones, etc)",
        "Violencia patrimonial (destrucción o retención de artículos, documentos, dinero, etc)",
        "Violencia sexual (actos sexuales no consentido)"
    ])

    list_eval_fp = "eval_fp"
    add_choice_list(choices_rows, list_eval_fp, ["Excelente", "Bueno", "Regular", "Malo"])

    # P5
    list_riesgos = "riesgos_sociales"
    add_choice_list(choices_rows, list_riesgos, [
        "Escándalos musicales.",
        "Falta de oportunidades laborales.",
        "Problemas Vecinales.",
        "Asentamientos ilegales (conocido como precarios).",
        "Personas en situación de calle.",
        "Desvinculación escolar (deserción escolar)",
        "Zona de prostitución",
        "Consumo de alcohol en vía pública",
        "Personas con exceso de tiempo de ocio",
        "Acumulación de basuras, aguas negras, mal alcantarillado.",
        "Carencia o inexistencia de alumbrado público.",
        "Cuarterías",
        "Lotes baldíos.",
        "Ventas informales",
        "Pérdida de espacios públicos (parques, polideportivos, etc.).",
        "Otro"
    ])

    # =========================
    # Página 1: Introducción
    # =========================
    survey_rows.append({"type": "begin_group", "name": "p1_intro", "label": "Introducción", "appearance": "field-list"})
    survey_rows.append({"type": "note", "name": "p1_logo", "label": form_title, "media::image": logo_media_name})
    survey_rows.append({"type": "note", "name": "p1_texto", "label": INTRO_CORTA_EXACTA})
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

    survey_rows.append({
        "type": "end",
        "name": "fin_por_no",
        "label": "Gracias. Usted indicó que no acepta participar en esta encuesta.",
        "relevant": f"${{acepta_participar}}='{v_no}'"
    })

    rel_si = f"${{acepta_participar}}='{v_si}'"

    # =========================
    # Página 3: Datos demográficos (Cantón + Distrito)
    # =========================
    survey_rows.append({
        "type": "begin_group",
        "name": "p3_demograficos",
        "label": "Datos demográficos",
        "appearance": "field-list",
        "relevant": rel_si
    })

    survey_rows.append({
        "type": f"select_one {list_canton}",
        "name": "canton",
        "label": "Cantón",
        "required": "yes",
        "constraint": ". != '__pick_canton__'",
        "constraint_message": "Seleccione un cantón válido.",
        "relevant": rel_si
    })

    survey_rows.append({
        "type": f"select_one {list_distrito}",
        "name": "distrito",
        "label": "Distrito",
        "required": "yes",
        "choice_filter": "canton_key=${canton} or any='1'",
        "constraint": ". != '__pick_distrito__'",
        "constraint_message": "Seleccione un distrito válido.",
        "relevant": rel_si
    })

    survey_rows.append({
        "type": "integer",
        "name": "edad",
        "label": "Edad",
        "required": "yes",
        "constraint": ". >= 0 and . <= 120",
        "constraint_message": "Indique una edad válida.",
        "relevant": rel_si
    })

    survey_rows.append({
        "type": f"select_one {list_genero}",
        "name": "genero",
        "label": "Género",
        "required": "yes",
        "relevant": rel_si
    })

    survey_rows.append({
        "type": f"select_one {list_escolaridad}",
        "name": "escolaridad",
        "label": "Escolaridad",
        "required": "yes",
        "relevant": rel_si
    })

    survey_rows.append({
        "type": f"select_multiple {list_relacion}",
        "name": "relacion_zona",
        "label": "¿Cuál es su relación con la zona?",
        "required": "yes",
        "relevant": rel_si
    })

    survey_rows.append({"type": "end_group", "name": "p3_end"})

    # =========================
    # Página 4: Delitos
    # =========================
    survey_rows.append({
        "type": "begin_group",
        "name": "p4_delitos",
        "label": "Incidencia relacionada a delitos",
        "appearance": "field-list",
        "relevant": rel_si
    })

    survey_rows.append({
        "type": f"select_one {list_seguridad_si_no}",
        "name": "se_siente_seguro",
        "label": "¿Se siente seguro en su barrio?",
        "required": "yes",
        "appearance": "minimal",
        "relevant": rel_si
    })

    rel_inseguro = f"({rel_si}) and (${{se_siente_seguro}}='{slugify_name('No')}')"
    survey_rows.append({
        "type": "text",
        "name": "motivo_inseguridad",
        "label": "Indique por qué considera el barrio inseguro",
        "required": "yes",
        "appearance": "multiline",
        "relevant": rel_inseguro
    })

    survey_rows.append({
        "type": f"select_one {list_comp_anual}",
        "name": "comparacion_anual",
        "label": "¿Cómo se siente respecto a la seguridad en su barrio este año comparado con el anterior?",
        "required": "yes",
        "appearance": "minimal",
        "relevant": rel_si
    })

    survey_rows.append({
        "type": "text",
        "name": "motivo_comparacion",
        "label": "Indique por qué.",
        "required": "yes",
        "appearance": "multiline",
        "relevant": rel_si
    })

    # Lugares
    lugares = [
        ("lugar_entretenimiento", "Discotecas, bares, sitios de entretenimiento"),
        ("espacios_recreativos", "Espacios recreativos"),
        ("lugar_residencia", "Lugar de residencia"),
        ("paradas_estaciones", "Paradas/estaciones (buses, taxis, trenes)"),
        ("puentes_peatonales", "Puentes peatonales"),
        ("transporte_publico", "Transporte público"),
        ("zona_bancaria", "Zona bancaria"),
        ("zona_comercio", "Zona de comercio"),
        ("zonas_residenciales", "Zonas residenciales"),
        ("lugares_turisticos", "Lugares de interés turístico"),
    ]
    for name, lab in lugares:
        survey_rows.append({
            "type": f"select_one {list_seg_lugares}",
            "name": name,
            "label": lab,
            "required": "yes",
            "relevant": rel_si
        })

    survey_rows.append({
        "type": "text",
        "name": "zona_mas_insegura",
        "label": "¿Cuál es el lugar o zona más inseguro en su barrio? (opcional)",
        "required": "no",
        "relevant": rel_si
    })
    survey_rows.append({
        "type": "text",
        "name": "porque_insegura",
        "label": "Describa por qué considera que esa zona es insegura (opcional)",
        "required": "no",
        "appearance": "multiline",
        "relevant": rel_si
    })

    # Delitos
    survey_rows.append({
        "type": f"select_multiple {list_incidencia_delitos}",
        "name": "incidencia_delitos",
        "label": "Incidencia relacionada a delitos",
        "required": "no",
        "relevant": rel_si
    })

    survey_rows.append({
        "type": f"select_multiple {list_venta_drogas}",
        "name": "venta_drogas",
        "label": "Venta de drogas",
        "required": "no",
        "relevant": rel_si
    })

    survey_rows.append({
        "type": f"select_multiple {list_delitos_vida}",
        "name": "delitos_vida",
        "label": "Delitos contra la vida",
        "required": "no",
        "relevant": rel_si
    })

    survey_rows.append({
        "type": f"select_multiple {list_delitos_sexuales}",
        "name": "delitos_sexuales",
        "label": "Delitos sexuales",
        "required": "no",
        "relevant": rel_si
    })

    survey_rows.append({
        "type": f"select_multiple {list_asaltos}",
        "name": "asaltos",
        "label": "Asaltos",
        "required": "no",
        "relevant": rel_si
    })

    survey_rows.append({
        "type": f"select_multiple {list_estafas}",
        "name": "estafas",
        "label": "Estafas",
        "required": "no",
        "relevant": rel_si
    })

    survey_rows.append({
        "type": f"select_multiple {list_robo_fuerza}",
        "name": "robo_fuerza",
        "label": "Robo (sustracción con fuerza)",
        "required": "no",
        "relevant": rel_si
    })

    survey_rows.append({
        "type": f"select_multiple {list_abandono}",
        "name": "abandono_personas",
        "label": "Abandono de personas",
        "required": "no",
        "relevant": rel_si
    })

    survey_rows.append({
        "type": f"select_multiple {list_explotacion}",
        "name": "explotacion_infantil",
        "label": "Explotación infantil",
        "required": "no",
        "relevant": rel_si
    })

    survey_rows.append({
        "type": f"select_multiple {list_ambientales}",
        "name": "delitos_ambientales",
        "label": "Delitos ambientales",
        "required": "no",
        "relevant": rel_si
    })

    survey_rows.append({
        "type": f"select_multiple {list_trata}",
        "name": "trata_personas",
        "label": "Trata de personas",
        "required": "no",
        "relevant": rel_si
    })

    # VI
    survey_rows.append({
        "type": f"select_one {list_yesno}",
        "name": "vi",
        "label": "Violencia Intrafamiliar",
        "required": "no",
        "appearance": "minimal",
        "relevant": rel_si
    })

    rel_vi_si = f"({rel_si}) and (${{vi}}='{v_si}')"

    survey_rows.append({
        "type": f"select_one {list_yesno}",
        "name": "vi_victima_ultimo_anno",
        "label": "¿Ha sido víctima o conoce a alguien que haya sido víctima de VI en el último año?",
        "required": "yes",
        "appearance": "minimal",
        "relevant": rel_vi_si
    })

    survey_rows.append({
        "type": f"select_multiple {list_vi_tipos}",
        "name": "vi_tipos",
        "label": "Tipos de Violencia Intrafamiliar (marque todos los que correspondan)",
        "required": "yes",
        "relevant": rel_vi_si
    })

    survey_rows.append({
        "type": f"select_one {list_yesno}",
        "name": "vi_fp_abordaje",
        "label": "¿Fue abordado por Fuerza Pública?",
        "required": "yes",
        "appearance": "minimal",
        "relevant": rel_vi_si
    })

    rel_vi_abordaje_si = f"({rel_vi_si}) and (${{vi_fp_abordaje}}='{v_si}')"
    survey_rows.append({
        "type": f"select_one {list_eval_fp}",
        "name": "vi_fp_eval",
        "label": "¿Cómo fue el abordaje de la Fuerza Pública?",
        "required": "yes",
        "appearance": "minimal",
        "relevant": rel_vi_abordaje_si
    })

    # ===========
    # Glosario P4 (MISMA INTEGRACIÓN QUE TU CÓDIGO)
    # ===========
    textos_p4 = []
    for r in survey_rows:
        if r.get("name", "").startswith("p4_") or r.get("name", "") in {
            "se_siente_seguro", "motivo_inseguridad", "comparacion_anual", "motivo_comparacion",
            "incidencia_delitos", "venta_drogas", "delitos_vida", "delitos_sexuales", "asaltos", "estafas",
            "robo_fuerza", "abandono_personas", "explotacion_infantil", "delitos_ambientales", "trata_personas",
            "vi", "vi_victima_ultimo_anno", "vi_tipos", "vi_fp_abordaje", "vi_fp_eval"
        }:
            if r.get("label"):
                textos_p4.append(str(r["label"]))

    # también sumar opciones (por si el término aparece ahí)
    textos_p4.append(" ".join([
        "bunker", "búnker", "extorsión", "hurto", "receptación", "contrabando", "tráfico ilegal de personas",
        "delitos sexuales", "violencia intrafamiliar", "tacha"
    ]))

    GLOS_P4_ITEMS = buscar_similitudes(glosario, textos_p4)

    if GLOS_P4_ITEMS:
        survey_rows.append({
            "type": f"select_one {list_yesno}",
            "name": "ver_glosario_p4",
            "label": "¿Desea acceder al glosario de esta sección?",
            "required": "no",
            "appearance": "minimal",
            "relevant": rel_si
        })

    survey_rows.append({"type": "end_group", "name": "p4_end"})

    if GLOS_P4_ITEMS:
        rel_glos_p4 = f"({rel_si}) and (${{ver_glosario_p4}}='{v_si}')"
        survey_rows.append({
            "type": "begin_group",
            "name": "p4_5_glosario",
            "label": "Glosario — Incidencia relacionada a delitos",
            "appearance": "field-list",
            "relevant": rel_glos_p4
        })

        survey_rows.append({
            "type": "note",
            "name": "p4_5_glosario_info",
            "label": "Para volver a la sección anterior, utilice el botón “Anterior”.",
            "relevant": rel_glos_p4
        })

        for i, (term, defin) in enumerate(GLOS_P4_ITEMS, start=1):
            survey_rows.append({
                "type": "note",
                "name": f"p4_5_term_{i}",
                "label": f"{term}: {defin}",
                "relevant": rel_glos_p4
            })

        # END SOLO en glosario (MISMA LÓGICA TUYA)
        survey_rows.append({
            "type": "end",
            "name": "fin_en_glosario_p4",
            "label": "Fin del glosario. Use “Anterior” para regresar a la sección anterior y continuar con la encuesta.",
            "relevant": rel_glos_p4
        })

        survey_rows.append({"type": "end_group", "name": "p4_5_end"})

    # =========================
    # Página 5: Riesgos sociales
    # =========================
    survey_rows.append({
        "type": "begin_group",
        "name": "p5_riesgos",
        "label": "Riesgos Sociales",
        "appearance": "field-list",
        "relevant": rel_si
    })

    survey_rows.append({
        "type": f"select_multiple {list_riesgos}",
        "name": "riesgos_sociales",
        "label": "Indique cuáles riesgos o problemáticas se presentan en su comunidad (puede marcar varias).",
        "required": "no",
        "relevant": rel_si
    })

    survey_rows.append({
        "type": "text",
        "name": "riesgo_otro",
        "label": "Si marcó “Otro”, especifique (opcional).",
        "required": "no",
        "relevant": rel_si
    })

    # ===========
    # Glosario P5 (MISMA INTEGRACIÓN QUE TU CÓDIGO)
    # ===========
    textos_p5 = []
    for r in survey_rows:
        if r.get("name", "").startswith("p5_") or r.get("name", "") in {"riesgos_sociales", "riesgo_otro"}:
            if r.get("label"):
                textos_p5.append(str(r["label"]))

    textos_p5.append(" ".join([
        "necesidades básicas insatisfechas", "ocio", "personas en situación de calle", "cuarterías",
        "asentamientos ilegales", "deserción escolar"
    ]))

    GLOS_P5_ITEMS = buscar_similitudes(glosario, textos_p5)

    if GLOS_P5_ITEMS:
        survey_rows.append({
            "type": f"select_one {list_yesno}",
            "name": "ver_glosario_p5",
            "label": "¿Desea acceder al glosario de esta sección?",
            "required": "no",
            "appearance": "minimal",
            "relevant": rel_si
        })

    survey_rows.append({"type": "end_group", "name": "p5_end"})

    if GLOS_P5_ITEMS:
        rel_glos_p5 = f"({rel_si}) and (${{ver_glosario_p5}}='{v_si}')"
        survey_rows.append({
            "type": "begin_group",
            "name": "p5_5_glosario",
            "label": "Glosario — Riesgos Sociales",
            "appearance": "field-list",
            "relevant": rel_glos_p5
        })

        survey_rows.append({
            "type": "note",
            "name": "p5_5_glosario_info",
            "label": "Para volver a la sección anterior, utilice el botón “Anterior”.",
            "relevant": rel_glos_p5
        })

        for i, (term, defin) in enumerate(GLOS_P5_ITEMS, start=1):
            survey_rows.append({
                "type": "note",
                "name": f"p5_5_term_{i}",
                "label": f"{term}: {defin}",
                "relevant": rel_glos_p5
            })

        # END SOLO en glosario (MISMA LÓGICA TUYA)
        survey_rows.append({
            "type": "end",
            "name": "fin_en_glosario_p5",
            "label": "Fin del glosario. Use “Anterior” para regresar a la sección anterior y continuar con la encuesta.",
            "relevant": rel_glos_p5
        })

        survey_rows.append({"type": "end_group", "name": "p5_5_end"})

    # =========================
    # DataFrames
    # =========================
    survey_cols = [
        "type", "name", "label", "required", "appearance",
        "relevant", "media::image", "constraint", "constraint_message", "hint", "choice_filter"
    ]
    df_survey = pd.DataFrame(survey_rows, columns=survey_cols).fillna("")

    # choices: incluimos columnas extra (canton_key, any) aunque estén vacías
    choices_cols = ["list_name", "name", "label", "canton_key", "any"]
    df_choices = pd.DataFrame(choices_rows)
    for col in choices_cols:
        if col not in df_choices.columns:
            df_choices[col] = ""
    df_choices = df_choices[choices_cols].fillna("")

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
        version=version.strip() or version_auto,
        glosario=st.session_state.glosario_doc
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
4) Cantón/Distrito se filtra por `choice_filter` (canton_key).
""")

