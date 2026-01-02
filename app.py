# -*- coding: utf-8 -*-
# ==========================================================================================
# App: XLSForm Survey123 — Introducción + Consentimiento + Datos Generales + Interés Policial + Interés Interno
# + Glosario por página (acceso opcional) SIN crear columnas en la tabla (bind::esri:fieldType = null)
# ==========================================================================================

import re
from io import BytesIO
from datetime import datetime

import streamlit as st
import pandas as pd

# ==========================================================================================
# Configuración
# ==========================================================================================
st.set_page_config(page_title="XLSForm Survey123 — (Páginas 1 a 5)", layout="wide")
st.title("XLSForm Survey123 — Introducción + Consentimiento + Datos + Interés Policial + Interés Interno")

st.markdown("""
Genera un **XLSForm** listo para **ArcGIS Survey123** con páginas reales (Next/Back):
- **Página 1**: Introducción (logo + delegación + texto).
- **Página 2**: Consentimiento Informado (ordenado) + aceptación.
- **Página 3**: Datos generales (con condicionales en la pregunta 5).
- **Página 4**: Información de interés policial (condicionales 6.1–6.4 si 6 = “Sí”).
- **Página 5**: Información de interés interno (condicionales 10.1, 11.1, 12.1, 13.1, 14.1).
- **Glosario por página**: pregunta opcional al final de cada sección; si dicen “Sí”, se abre una página “Glosario”.
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
    for lab in labels:
        choices_rows.append({
            "list_name": list_name,
            "name": slugify_name(lab),
            "label": lab
        })

def add_note(survey_rows, name: str, label: str, relevant: str = ""):
    """
    NOTE visible en encuesta pero NO crea campo en la tabla:
    bind::esri:fieldType = null
    """
    survey_rows.append({
        "type": "note",
        "name": name,
        "label": label,
        "relevant": relevant or "",
        "bind::esri:fieldType": "null"
    })

def add_glossary_page(survey_rows, page_name: str, page_label: str, relevant: str, items: list[tuple[str, str]]):
    """
    Página de glosario como grupo independiente.
    items: [(termino, definicion_larga), ...]  (SIN recortar)
    """
    survey_rows.append({
        "type": "begin_group",
        "name": page_name,
        "label": page_label,
        "appearance": "field-list",
        "relevant": relevant or ""
    })

    for i, (term, defi) in enumerate(items, start=1):
        add_note(
            survey_rows,
            name=f"{page_name}_term_{i}",
            label=f"**{term}**\n\n{defi}",
            relevant=relevant or ""
        )

    survey_rows.append({"type": "end_group", "name": f"{page_name}_end"})

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
# Textos EXACTOS solicitados (P1 y P2)
# ==========================================================================================
INTRO_CORTA_EXACTA = (
    "Esta encuesta busca recopilar información desde la experiencia del personal de la \n"
    "Fuerza Pública para apoyar la planificación preventiva y la mejora del servicio policial."
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
    "Destinatarios y acceso: La información será conocida únicamente por el personal autorizado de la Fuerza Pública / Ministerio de Seguridad Pública, para los fines indicados. No será cedida a terceros ajenos a estos fines.",
    "Responsable de la base de datos: El Ministerio de Seguridad Pública, a través de la Dirección de Programas Policiales Preventivos, Oficina Estrategia Integral de Prevención para la Seguridad Pública (EIPSEP / Estrategia Sembremos Seguridad) será el responsable del tratamiento y custodia de la información recolectada.",
    "Derechos de la persona participante: Usted conserva el derecho a la autodeterminación informativa y a decidir libremente sobre el suministro de sus datos."
]

CONSENT_CIERRE = [
    "Las respuestas brindadas no constituyen denuncias formales, ni sustituyen los mecanismos legales correspondientes.",
    "Al continuar con la encuesta, usted manifiesta haber leído y comprendido la información anterior y otorga su consentimiento informado para participar."
]

# ==========================================================================================
# Página 4: Interés policial (texto visible que SÍ va en la encuesta)
# ==========================================================================================
P4_INTRO_TITULO = "Información de interés policial"
P4_INTRO_TEXTO = (
    "En este apartado, el objetivo principal es comprender las estructuras criminales y las "
    "problemáticas de interés policial presentes en la jurisdicción de la delegación. A través "
    "de esto se busca obtener una visión clara de la naturaleza y dinámicas de las organizaciones "
    "criminales en la zona."
)

NOTA_PREVIA_CONFIDENCIAL = (
    "Nota previa: La información solicitada en los siguientes apartados es de carácter "
    "confidencial, para uso institucional y análisis preventivo. No constituye denuncia formal."
)

# ==========================================================================================
# Glosarios (SIN recortar textos)
# ==========================================================================================
GLOSARIO_P2 = [
    ("Consentimiento informado", "Manifestación libre y voluntaria de la persona participante, luego de haber leído y comprendido la finalidad de la encuesta, el uso de los datos y sus derechos."),
    ("Autodeterminación informativa", "Derecho de la persona a decidir sobre el suministro, uso, acceso y tratamiento de sus datos personales, conforme a la normativa aplicable.")
]

GLOSARIO_P3 = [
    ("Años de servicio", "Cantidad de años completos de servicio (en números). En la herramienta debe utilizarse un formato de 0 a 50 años."),
    ("Escolaridad", "Nivel de estudios alcanzado (selección única según las opciones disponibles)."),
    ("Clase policial", "Categoría/puesto que desempeña en la delegación. Dependiendo de la opción seleccionada, se habilitan subpreguntas (5.1 a 5.4).")
]

GLOSARIO_P4 = [
    ("Estructura criminal", "Grupo u organización que desarrolla actividades ilícitas de manera organizada dentro de una jurisdicción."),
    ("Búnker", "Punto de venta y distribución de drogas. Búnker (espacio cerrado para la venta y distribución de drogas)."),
    ("Modus operandi", "Modo de operar de una estructura criminal (por ejemplo: venta de droga exprés o en vía pública, asalto a mano armada, modo de desplazamiento, etc.)."),
    ("Extorsión", "el que para procurar un lucro injusto obligare a otro con int...ción patrimonial perjudicial para sí mismo o para un tercero."),
    ("Hurto", "quien se apoderare ilegítimamente de una cosa mueble, total o parcialmente ajena, esto en aprovechamiento del descuido"),
    ("Receptación", "quien adquiriere, recibiera y ocultare dinero, cosas o bienes...ipo o interviniere en su adquisición, recepción o ocultación."),
    ("Contrabando", "quien introduzca o extraiga, transporte, almacene, adquiera, ...ocedencia introducida al país, eludiendo el control aduanero."),
    ("Delitos sexuales", "atentar contra la libre elección sexual, contra su pudor, dent...n los delitos de violación, abusos deshonestos y acoso sexual."),
    ("Daños/vandalismo", "quien destruyere, inutilizare, hiciere desaparecer, o de cualq...maniales (bienes del estado), contra persona física o jurídica"),
    ("Estafa o defraudación", "quien induciendo a error a otra persona o manteniéndola en él...rídico para sí o para un tercero, lesione el patrimonio ajeno")
]

GLOSARIO_P5 = [
    ("Recurso móvil", "Medio de transporte operativo necesario para el servicio (por ejemplo: patrulla, motocicleta u otro recurso de movilidad)."),
    ("Necesidades básicas", "Condiciones mínimas necesarias para la prestación del servicio (descanso, alimentación, condiciones físicas mínimas, entre otros)."),
    ("Capacitación", "Proceso de formación requerido para mejorar competencias del personal según las necesidades identificadas."),
    ("Información confidencial", "Información de uso institucional y análisis preventivo. No constituye denuncia formal y debe tratarse con reserva conforme a la normativa aplicable.")
]

# ==========================================================================================
# Construcción XLSForm
# ==========================================================================================
def construir_xlsform(form_title: str, logo_media_name: str, idioma: str, version: str):
    survey_rows = []
    choices_rows = []

    # =========================
    # Choices (listas)
    # =========================
    list_yesno = "yesno"
    v_si = slugify_name("Sí")
    v_no = slugify_name("No")
    add_choice_list(choices_rows, list_yesno, ["Sí", "No"])

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

    list_clase = "clase_policial"
    add_choice_list(choices_rows, list_clase, [
        "Agente I",
        "Agente II",
        "Suboficial I",
        "Suboficial II",
        "Oficial I",
        "Sub Jefe de delegación",
        "Jefe de delegación",
    ])

    list_agente_ii = "agente_ii_det"
    add_choice_list(choices_rows, list_agente_ii, [
        "Agente de Fronteras",
        "Agente de Programa Preventivo",
        "Agente Armero",
        "Agente Conductor Operacional de Vehículos Oficiales",
        "Agente de Seguridad Turística",
        "Agente de Comunicaciones",
        "Agente de Operaciones",
    ])

    list_subof_i = "suboficial_i_det"
    add_choice_list(choices_rows, list_subof_i, [
        "Encargado Equipo Operativo Policial",
        "Encargado Equipo de Seguridad Turística",
        "Encargado Equipo de Fronteras",
        "Encargado Equipo de Comunicaciones",
        "Encargado de Programas Preventivos",
        "Encargado Agentes Armeros",
    ])

    list_subof_ii = "suboficial_ii_det"
    add_choice_list(choices_rows, list_subof_ii, [
        "Encargado Subgrupo Operativo Policial",
        "Encargado Subgrupo de Seguridad Turística",
        "Encargado Subgrupo de Fronteras",
        "Oficial de Guardia",
        "Encargado de Operaciones",
    ])

    list_of_i = "oficial_i_det"
    add_choice_list(choices_rows, list_of_i, [
        "Jefe Delegación Distrital",
        "Encargado Grupo Operativo Policial",
    ])

    # Página 4 - Actividad delictiva (6.1)
    list_actividad_delictiva = "actividad_delictiva"
    actividad_opts = [
        "Punto de Venta y distribución de Drogas. Búnker (espacio cerrado para la venta y distribución de drogas).",
        "Delitos contra la vida (Homicidios, heridos, femicidios).",
        "Venta y consumo de drogas en vía pública.",
        "Delitos sexuales",
        "Asalto (a personas, comercio, vivienda, transporte público).",
        "Daños a la propiedad. (Destruir, inutilizar o desaparecer).",
        "Estafas (Billetes, documentos, oro, lotería falsos).",
        "Estafa Informática (computadora, tarjetas, teléfonos, etc.).",
        "Extorsión (intimidar o amenazar a otras personas con fines de lucro).",
        "Hurto.",
        "Receptación (persona que adquiere, recibe u oculta artículos provenientes de un delito en el que no participó).",
        "Robo a edificaciones.",
        "Robo a vivienda.",
        "Robo de ganado y agrícola.",
        "Robo a comercio",
        "Robo de vehículos.",
        "Tacha de vehículos.",
        "Contrabando (licor, cigarrillos, medicinas, ropa, calzado, etc.)",
        "Tráfico de personas (coyotaje)",
        "Otro"
    ]
    add_choice_list(choices_rows, list_actividad_delictiva, actividad_opts)

    # Página 5 - Motivación (12)
    list_motivacion = "motivacion"
    motivacion_opts = ["Mucho", "Algo", "Poco", "Nada"]
    add_choice_list(choices_rows, list_motivacion, motivacion_opts)

    # =========================
    # Página 1: Introducción (SIN "Portada")
    # =========================
    survey_rows.append({"type": "begin_group", "name": "p1_intro", "label": "Introducción", "appearance": "field-list"})
    add_note(survey_rows, name="p1_logo", label=form_title, relevant="")
    survey_rows[-1]["media::image"] = logo_media_name  # mantener note con imagen sin crear campo
    add_note(survey_rows, name="p1_texto", label=INTRO_CORTA_EXACTA, relevant="")
    survey_rows.append({"type": "end_group", "name": "p1_end"})

    # (Glosario P1 opcional)
    survey_rows.append({
        "type": f"select_one {list_yesno}",
        "name": "p1_ver_glosario",
        "label": "¿Desea acceder al glosario de esta sección?",
        "required": "",
        "appearance": "minimal"
    })
    add_glossary_page(
        survey_rows,
        page_name="p1_glosario",
        page_label="Glosario — Introducción",
        relevant=f"${{p1_ver_glosario}}='{v_si}'",
        items=[
            ("Encuesta", "Instrumento para recopilar información con fines preventivos y estadísticos."),
            ("Servicio policial", "Labores que realiza el personal para la atención de la ciudadanía y la prevención.")
        ]
    )

    # =========================
    # Página 2: Consentimiento (ORDENADO)  NOTE sin campos en tabla
    # =========================
    survey_rows.append({"type": "begin_group", "name": "p2_consent", "label": "Consentimiento Informado", "appearance": "field-list"})
    add_note(survey_rows, name="p2_titulo", label=CONSENT_TITLE, relevant="")

    for i, p in enumerate(CONSENT_PARRAFOS, start=1):
        add_note(survey_rows, name=f"p2_p_{i}", label=p, relevant="")

    for j, b in enumerate(CONSENT_BULLETS, start=1):
        add_note(survey_rows, name=f"p2_b_{j}", label=f"• {b}", relevant="")

    for k, c in enumerate(CONSENT_CIERRE, start=1):
        add_note(survey_rows, name=f"p2_c_{k}", label=c, relevant="")

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

    # Glosario P2 (opcional)
    survey_rows.append({
        "type": f"select_one {list_yesno}",
        "name": "p2_ver_glosario",
        "label": "¿Desea acceder al glosario de esta sección?",
        "required": "",
        "appearance": "minimal",
        "relevant": f"${{acepta_participar}}='{v_si}'"
    })
    add_glossary_page(
        survey_rows,
        page_name="p2_glosario",
        page_label="Glosario — Consentimiento Informado",
        relevant=f"(${{acepta_participar}}='{v_si}') and (${{p2_ver_glosario}}='{v_si}')",
        items=GLOSARIO_P2
    )

    # =========================
    # Relevante base: solo si acepta SÍ
    # =========================
    rel_si = f"${{acepta_participar}}='{v_si}'"

    # =========================
    # Página 3: Datos generales
    # =========================
    survey_rows.append({
        "type": "begin_group",
        "name": "p3_datos_generales",
        "label": "Datos generales",
        "appearance": "field-list",
        "relevant": rel_si
    })

    survey_rows.append({
        "type": "integer",
        "name": "anos_servicio",
        "label": "1- Años de servicio:",
        "required": "yes",
        "constraint": ". >= 0 and . <= 50",
        "constraint_message": "Debe ser un número entre 0 y 50.",
        "relevant": rel_si
    })

    survey_rows.append({
        "type": f"select_one {list_edad}",
        "name": "edad_rango",
        "label": "2- Edad.",
        "required": "yes",
        "relevant": rel_si
    })

    survey_rows.append({
        "type": f"select_one {list_genero}",
        "name": "genero",
        "label": "3- ¿Con cuál de estas opciones se identifica?",
        "required": "yes",
        "relevant": rel_si
    })

    survey_rows.append({
        "type": f"select_one {list_escolaridad}",
        "name": "escolaridad",
        "label": "4- Escolaridad:",
        "required": "yes",
        "relevant": rel_si
    })

    survey_rows.append({
        "type": f"select_one {list_clase}",
        "name": "clase_policial",
        "label": "5- ¿Qué clase policial desempeña en su delegación?",
        "required": "yes",
        "relevant": rel_si
    })

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

    # Glosario P3 (opcional)
    survey_rows.append({
        "type": f"select_one {list_yesno}",
        "name": "p3_ver_glosario",
        "label": "¿Desea acceder al glosario de esta sección?",
        "required": "",
        "appearance": "minimal",
        "relevant": rel_si
    })
    add_glossary_page(
        survey_rows,
        page_name="p3_glosario",
        page_label="Glosario — Datos generales",
        relevant=f"({rel_si}) and (${{p3_ver_glosario}}='{v_si}')",
        items=GLOSARIO_P3
    )

    # =========================
    # Página 4: Interés policial
    # =========================
    survey_rows.append({
        "type": "begin_group",
        "name": "p4_interes_policial",
        "label": P4_INTRO_TITULO,
        "appearance": "field-list",
        "relevant": rel_si
    })

    add_note(survey_rows, name="p4_intro", label=P4_INTRO_TEXTO, relevant=rel_si)

    survey_rows.append({
        "type": f"select_one {list_yesno}",
        "name": "conocimiento_estructuras",
        "label": "6- ¿Cuenta usted con conocimiento operativo sobre personas, grupos u organizaciones que desarrollen actividades ilícitas en su jurisdicción?",
        "required": "yes",
        "appearance": "minimal",
        "relevant": rel_si
    })

    rel_6_si = f"({rel_si}) and (${{conocimiento_estructuras}}='{v_si}')"

    survey_rows.append({
        "type": f"select_multiple {list_actividad_delictiva}",
        "name": "tipo_actividad_delictiva",
        "label": "6.1 ¿Qué tipo de actividad delictiva es la que se realiza por parte de estas personas?",
        "required": "yes",
        "relevant": rel_6_si
    })

    add_note(survey_rows, name="p4_nota_previa_634", label=NOTA_PREVIA_CONFIDENCIAL, relevant=rel_6_si)

    survey_rows.append({
        "type": "text",
        "name": "nombre_estructura_criminal",
        "label": "6.2 ¿Cuál es el nombre de la estructura criminal?",
        "required": "yes",
        "relevant": rel_6_si
    })

    survey_rows.append({
        "type": "text",
        "name": "quienes_actos_criminales",
        "label": "6.3- Indique quién o quiénes se dedican a estos actos criminales. (nombres, apellidos, alias, domicilio)",
        "required": "yes",
        "appearance": "multiline",
        "relevant": rel_6_si
    })

    survey_rows.append({
        "type": "text",
        "name": "modo_operar_estructura",
        "label": "6.4 Modo de operar de esta estructura criminal (por ejemplo: venta de droga exprés o en vía pública, asalto a mano armada, modo de desplazamiento, etc.)",
        "required": "yes",
        "appearance": "multiline",
        "relevant": rel_6_si
    })

    survey_rows.append({
        "type": "text",
        "name": "zona_mayor_inseguridad",
        "label": "7- Indique el lugar, sector o zona que, según su criterio operativo, presenta mayores condiciones de inseguridad dentro de su área de responsabilidad.",
        "required": "yes",
        "appearance": "multiline",
        "relevant": rel_si
    })

    survey_rows.append({
        "type": "text",
        "name": "condiciones_riesgo_zona",
        "label": "8- Describa las principales situaciones o condiciones de riesgo que inciden en la inseguridad de esa zona.",
        "required": "yes",
        "appearance": "multiline",
        "relevant": rel_si
    })

    survey_rows.append({"type": "end_group", "name": "p4_end"})

    # Glosario P4 (opcional)
    survey_rows.append({
        "type": f"select_one {list_yesno}",
        "name": "p4_ver_glosario",
        "label": "¿Desea acceder al glosario de esta sección?",
        "required": "",
        "appearance": "minimal",
        "relevant": rel_si
    })
    add_glossary_page(
        survey_rows,
        page_name="p4_glosario",
        page_label="Glosario — Información de interés policial",
        relevant=f"({rel_si}) and (${{p4_ver_glosario}}='{v_si}')",
        items=GLOSARIO_P4
    )

    # =========================
    # Página 5: Interés interno
    # =========================
    survey_rows.append({
        "type": "begin_group",
        "name": "p5_interes_interno",
        "label": "Información de interés interno",
        "appearance": "field-list",
        "relevant": rel_si
    })

    survey_rows.append({
        "type": "text",
        "name": "recursos_necesarios",
        "label": "9- Desde su experiencia operativa, indique qué recursos considera necesarios para fortalecer la labor policial en su delegación.",
        "required": "yes",
        "appearance": "multiline",
        "relevant": rel_si
    })

    survey_rows.append({
        "type": f"select_one {list_yesno}",
        "name": "condiciones_necesidades_basicas",
        "label": "10- ¿Considera que las condiciones actuales de su delegación permiten cubrir adecuadamente sus necesidades básicas para el servicio (descanso, alimentación, recurso móvil, entre otros)?",
        "required": "yes",
        "appearance": "minimal",
        "relevant": rel_si
    })
    rel_10_no = f"({rel_si}) and (${{condiciones_necesidades_basicas}}='{v_no}')"

    survey_rows.append({
        "type": "text",
        "name": "condiciones_mejorar",
        "label": "10.1- Cuáles condiciones considera que se pueden mejorar.",
        "required": "yes",
        "appearance": "multiline",
        "relevant": rel_10_no
    })

    survey_rows.append({
        "type": f"select_one {list_yesno}",
        "name": "falta_capacitacion",
        "label": "11- ¿Considera usted que hace falta capacitación para el personal en su delegación policial?",
        "required": "yes",
        "appearance": "minimal",
        "relevant": rel_si
    })
    rel_11_si = f"({rel_si}) and (${{falta_capacitacion}}='{v_si}')"

    survey_rows.append({
        "type": "text",
        "name": "areas_capacitacion",
        "label": "11.1 Especifique en qué áreas necesita capacitación.",
        "required": "yes",
        "appearance": "multiline",
        "relevant": rel_11_si
    })

    survey_rows.append({
        "type": f"select_one {list_motivacion}",
        "name": "motivacion_medida",
        "label": "12- ¿En qué medida considera que la institución genera un entorno que favorece su motivación para la atención a la ciudadanía?",
        "required": "yes",
        "appearance": "minimal",
        "relevant": rel_si
    })
    rel_12_poco_nada = f"({rel_si}) and (${{motivacion_medida}}='{slugify_name('Poco')}' or ${{motivacion_medida}}='{slugify_name('Nada')}')"

    survey_rows.append({
        "type": "text",
        "name": "motivo_motivacion_baja",
        "label": "12.1 De manera general, indique por qué lo considera así.",
        "required": "yes",
        "appearance": "multiline",
        "relevant": rel_12_poco_nada
    })

    survey_rows.append({
        "type": f"select_one {list_yesno}",
        "name": "situaciones_internas_afectan",
        "label": "13- ¿Tiene usted conocimiento de situaciones internas que, según su criterio, afectan el adecuado funcionamiento operativo o el servicio a la ciudadanía en su delegación?",
        "required": "yes",
        "appearance": "minimal",
        "relevant": rel_si
    })
    rel_13_si = f"({rel_si}) and (${{situaciones_internas_afectan}}='{v_si}')"

    survey_rows.append({
        "type": "text",
        "name": "describe_situaciones_internas",
        "label": "13.1 Describa, de manera general, las situaciones a las que se refiere, relacionadas con aspectos operativos, administrativos o de servicio.",
        "required": "yes",
        "appearance": "multiline",
        "relevant": rel_13_si
    })

    survey_rows.append({
        "type": f"select_one {list_yesno}",
        "name": "conoce_oficiales_relacionados",
        "label": "14- ¿Conoce oficiales de Fuerza Pública que se relacionen con alguna estructura criminal o cometan algún delito?",
        "required": "yes",
        "appearance": "minimal",
        "relevant": rel_si
    })
    rel_14_si = f"({rel_si}) and (${{conoce_oficiales_relacionados}}='{v_si}')"

    survey_rows.append({
        "type": "text",
        "name": "describe_situacion_oficiales",
        "label": "14.1 Describa la situación de la cual tiene conocimiento. (aporte nombre de la estructura, tipo de actividad, nombre de oficiales, función del oficial dentro de la organización, alias, etc.)",
        "required": "yes",
        "appearance": "multiline",
        "relevant": rel_14_si
    })

    # 15 (voluntaria) -> required vacío (NO False)
    survey_rows.append({
        "type": "text",
        "name": "medio_contacto_voluntario",
        "label": "15- Desea, de manera voluntaria, dejar un medio de contacto para brindar más información (correo electrónico, número de teléfono, etc.)",
        "required": "",
        "appearance": "multiline",
        "relevant": rel_si
    })

    survey_rows.append({"type": "end_group", "name": "p5_end"})

    # Glosario P5 (opcional)
    survey_rows.append({
        "type": f"select_one {list_yesno}",
        "name": "p5_ver_glosario",
        "label": "¿Desea acceder al glosario de esta sección?",
        "required": "",
        "appearance": "minimal",
        "relevant": rel_si
    })
    add_glossary_page(
        survey_rows,
        page_name="p5_glosario",
        page_label="Glosario — Información de interés interno",
        relevant=f"({rel_si}) and (${{p5_ver_glosario}}='{v_si}')",
        items=GLOSARIO_P5
    )

    # =========================
    # DataFrames
    # =========================
    survey_cols = [
        "type", "name", "label", "required", "appearance",
        "relevant", "media::image", "constraint", "constraint_message", "hint",
        "bind::esri:fieldType"
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
4) IMPORTANTE: Los textos largos (notes) ya NO crean columnas en la tabla porque se marcó `bind::esri:fieldType = null`.  
""")
