# -*- coding: utf-8 -*-
# ==========================================================================================
# App: XLSForm Survey123 — Introducción + Consentimiento + Datos Generales + Interés Policial + Interés Interno
# - Página 1: Introducción con logo + delegación + texto corto (exacto)
# - Página 2: Consentimiento Informado ORDENADO (título + párrafos + viñetas + cierre)
#            + pregunta ¿Acepta participar? (Sí/No)
#            + Si responde "No" => finaliza (end)
# - Página 3: Datos generales (según imágenes) + condicionales en pregunta 5 (5.1–5.4)
# - Página 4: Información de interés policial (según imágenes)
#            + 6 (Sí/No) y si "Sí" se habilitan 6.1 a 6.4
#            + 7 y 8 (abiertas)
# - Página 5: Información de interés interno (según imágenes)
#            + Condicionales: 10.1 si 10="No"; 11.1 si 11="Sí"; 12.1 si 12 in ("Poco","Nada")
#                             13.1 si 13="Sí"; 14.1 si 14="Sí"
#            + 15 opcional (contacto voluntario)
# - NUEVO: Glosarios por sección (acceso opcional, sin obligar a responder)
#          * Al final de Página 4 se pregunta si desea ver glosario; si "Sí" aparece grupo glosario.
#          * Al final de Página 5 se pregunta si desea ver glosario; si "Sí" aparece grupo glosario.
#          * IMPORTANTE: En el glosario SOLO se permite devolver (Atrás). Para evitar "Siguiente",
#            el último elemento del glosario es un END condicional que aparece SOLO dentro del glosario.
#            Así el usuario no puede avanzar desde el glosario hacia el resto de la encuesta.
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
st.set_page_config(page_title="XLSForm Survey123 — (Páginas 1 a 5)", layout="wide")
st.title("XLSForm Survey123 — Introducción + Consentimiento + Datos + Interés Policial + Interés Interno")

st.markdown("""
Genera un **XLSForm** listo para **ArcGIS Survey123** con páginas reales (Next/Back):
- **Página 1**: Introducción (logo + delegación + texto).
- **Página 2**: Consentimiento Informado (ordenado) + aceptación.
- **Página 3**: Datos generales (con condicionales en la pregunta 5).
- **Página 4**: Información de interés policial (condicionales 6.1–6.4 si 6 = “Sí”).
- **Página 5**: Información de interés interno (condicionales 10.1, 11.1, 12.1, 13.1, 14.1).
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
    "La información solicitada en los siguientes apartados es de carácter "
    "confidencial, para uso institucional y análisis preventivo. No constituye denuncia formal."
)

# ==========================================================================================
# Página 5: Interés interno (NOTAS que sí van en encuesta se ponen como hint o note)
# ==========================================================================================
HINT_ABIERTA_GENERAL = "Respuesta abierta para que la persona encuestada pueda agregar la información adecuada."
HINT_ABIERTA_SIMPLE = "Respuesta abierta."
HINT_CONFIDENCIAL_INSTITUCIONAL = "La información suministrada es confidencial y de uso institucional."
HINT_ANALISIS_PREVENTIVO = (
    "Esta información será utilizada exclusivamente para análisis preventivo institucional "
    "y no sustituye los mecanismos formales de denuncia."
)

# ==========================================================================================
# Glosarios (TEXTOS COMPLETOS, SIN ACORTAR)
# ==========================================================================================
GLOS_P4_ITEMS = [
    (
        "Bunker (eje de expendio de drogas)",
        "tipo de construcción destinada a servir de refugio a consumidores de droga y a su vez es un expendio de drogas y armas."
    ),
    (
        "Extorsión",
        "el que para procurar un lucro injusto obligare a otro con intimidación o amenaza a realizar u omitir un acto o negocio jurídico con intención patrimonial perjudicial para sí mismo o para un tercero."
    ),
    (
        "Hurto",
        "quien se apoderare ilegítimamente de una cosa mueble, total o parcialmente ajena, esto en aprovechamiento del descuido."
    ),
    (
        "Receptación",
        "quien adquiriere, recibiera y ocultare dinero, cosas o bienes provenientes de un delito o interviniere en su adquisición, recepción u ocultación."
    ),
    (
        "Contrabando",
        "quien introduzca o extraiga, transporte, almacene, adquiera, venda o tenga en su poder mercadería de procedencia introducida al país, eludiendo el control aduanero."
    ),
    (
        "Delitos sexuales",
        "atentar contra la libre elección sexual, contra su pudor, dentro de estos se incluyen los delitos de violación, abusos deshonestos y acoso sexual."
    ),
    (
        "Daños/vandalismo",
        "quien destruyere, inutilizare, hiciere desaparecer, o de cualquier modo dañare cosas o bienes, incluyendo bienes del Estado, contra persona física o jurídica."
    ),
    (
        "Estafa o defraudación",
        "quien induciendo a error a otra persona o manteniéndola en él, mediante ardid o engaño, para sí o para un tercero, lesione el patrimonio ajeno."
    ),
    (
        "Fraude informático",
        "persona que, con la intención de procurar u obtener un beneficio para sí o para un tercero, influya en el resultado de un procesamiento de datos mediante la manipulación de datos, la alteración de programas o cualquier otra acción que incida en el proceso de los datos del sistema."
    ),
    (
        "Alteración de datos y sabotaje informático",
        "quien por cualquier medio accede, borre, suprima, modifique o inutilice sin autorización los datos registrados en una computadora, sistema o soporte informático, afectando su integridad, disponibilidad o funcionamiento."
    ),
    (
        "Tráfico ilegal de personas",
        "conducir o transportar a personas para su ingreso al país o salida del mismo por lugares no autorizados, o facilitar el ingreso o permanencia ilegal de personas extranjeras que ingresen al país o permanezcan ilegalmente en él."
    ),
    (
        "Robo a edificación (tacha)",
        "quien mediante el desprendimiento, ruptura, destrucción o forzamiento de cerraduras, ventanas, puertas u otros medios, entrare en una edificación, o en sus dependencias, o en un local, y sustrajere alguna cosa mueble total o parcialmente ajena."
    ),
    (
        "Robo a vivienda (tacha)",
        "quien mediante el desprendimiento, ruptura, destrucción o forzamiento de cerraduras, ventanas, puertas u otros medios, entrare en una vivienda o sus dependencias y sustrajere alguna cosa mueble total o parcialmente ajena."
    ),
    (
        "Robo a vivienda (intimidación)",
        "quien en una vivienda ajena ejecutare el apoderamiento de una cosa mueble total o parcialmente ajena mediante violencia o intimidación sobre las personas, sea para cometer el robo o para conservar su seguridad propia o de terceros, en el lugar del hecho o después."
    ),
    (
        "Robo a comercio (tacha)",
        "quien mediante desprendimiento, ruptura, destrucción o forzamiento de cerraduras, ventanas, puertas u otros medios, entrare en un local comercial o sus dependencias y sustrajere alguna cosa mueble total o parcialmente ajena."
    ),
    (
        "Robo a comercio (intimidación)",
        "apoderamiento de cosa mueble total o parcialmente ajena, mediante violencia o intimidación sobre las personas, sea para cometer el robo o para huir."
    ),
    (
        "Robo de vehículos",
        "apoderamiento o sustracción de un vehículo automotor de forma ilegítima con el fin de obtener un beneficio propio."
    ),
    (
        "Robo a vehículos (tacha)",
        "quien mediante la apertura sin autorización de un vehículo o destruyendo o forzando sus mecanismos de acceso, sustrajere alguna cosa mueble total o parcialmente ajena que se encuentre en el interior."
    ),
    (
        "Robo de motocicletas/vehículos (bajonazo)",
        "apoderamiento de un vehículo o motocicleta por medio de violencia o intimidación a la víctima."
    )
]

GLOS_P5_ITEMS = [
    (
        "Falta de capacitación policial",
        "deficiencia en la capacitación, doctrina policial, actualización jurídica, polígono y procedimientos policiales."
    ),
    (
        "Corrupción policial",
        "consiste en el uso indebido de sus atribuciones, recursos o influencias, para beneficio propio o de terceros, incluyendo ascensos, sanciones evitadas, ventajas económicas o avances en la carrera profesional e incluso fines políticos."
    ),
    (
        "Inadecuado uso del recurso policial",
        "deficiente uso de los recursos que se tienen en una delegación policial para un eficiente servicio."
    ),
    (
        "Inefectividad en el servicio de policía",
        "baja respuesta por parte de fuerza pública ante cualquier incidencia, derivado de muchos factores que son relevantes."
    ),
    (
        "Necesidades básicas insatisfechas",
        "carencias críticas en las personas para vivir de forma adecuada, como alimentación, vivienda, educación básica, ingreso mínimo, servicios públicos esenciales."
    )
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
    survey_rows.append({"type": "note", "name": "p1_logo", "label": form_title, "media::image": logo_media_name})
    survey_rows.append({"type": "note", "name": "p1_texto", "label": INTRO_CORTA_EXACTA})
    survey_rows.append({"type": "end_group", "name": "p1_end"})

    # =========================
    # Página 2: Consentimiento (ORDENADO)
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

    survey_rows.append({"type": "note", "name": "p4_intro", "label": P4_INTRO_TEXTO, "relevant": rel_si})

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

    survey_rows.append({
        "type": "note",
        "name": "p4_nota_previa_634",
        "label": NOTA_PREVIA_CONFIDENCIAL,
        "relevant": rel_6_si
    })

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

    # Acceso opcional a Glosario (NO obligatorio)
    survey_rows.append({
        "type": f"select_one {list_yesno}",
        "name": "ver_glosario_p4",
        "label": "¿Desea acceder al glosario de esta sección?",
        "required": "no",
        "appearance": "minimal",
        "relevant": rel_si
    })

    survey_rows.append({"type": "end_group", "name": "p4_end"})

    # Página 4.5: Glosario Interés policial (condicional si responde Sí)
    rel_glos_p4 = f"({rel_si}) and (${{ver_glosario_p4}}='{v_si}')"
    survey_rows.append({
        "type": "begin_group",
        "name": "p4_5_glosario",
        "label": "Glosario — Información de interés policial",
        "appearance": "field-list",
        "relevant": rel_glos_p4
    })

    survey_rows.append({
        "type": "note",
        "name": "p4_5_glosario_info",
        "label": "Para volver a la sección anterior, utilice el botón “Atrás”.",
        "relevant": rel_glos_p4
    })

    for i, (term, defin) in enumerate(GLOS_P4_ITEMS, start=1):
        survey_rows.append({
            "type": "note",
            "name": f"p4_5_term_{i}",
            "label": f"{term}: {defin}",
            "relevant": rel_glos_p4
        })

    # END SOLO en glosario: evita que el usuario avance desde glosario
    survey_rows.append({
        "type": "end",
        "name": "fin_en_glosario_p4",
        "label": "Fin del glosario. Use “Atrás” para regresar a la sección anterior y continuar con la encuesta.",
        "relevant": rel_glos_p4
    })

    survey_rows.append({"type": "end_group", "name": "p4_5_end"})

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

    # 9
    survey_rows.append({
        "type": "text",
        "name": "recursos_necesarios",
        "label": "9- Desde su experiencia operativa, indique qué recursos considera necesarios para fortalecer la labor policial en su delegación.",
        "required": "yes",
        "appearance": "multiline",
        "relevant": rel_si
    })

    # 10
    survey_rows.append({
        "type": f"select_one {list_yesno}",
        "name": "condiciones_necesidades_basicas",
        "label": "10- ¿Considera que las condiciones actuales de su delegación permiten cubrir adecuadamente sus necesidades básicas para el servicio (descanso, alimentación, recurso móvil, entre otros)?",
        "required": "yes",
        "appearance": "minimal",
        "relevant": rel_si
    })
    rel_10_no = f"({rel_si}) and (${{condiciones_necesidades_basicas}}='{v_no}')"

    # 10.1
    survey_rows.append({
        "type": "text",
        "name": "condiciones_mejorar",
        "label": "10.1- Cuáles condiciones considera que se pueden mejorar.",
        "required": "yes",
        "appearance": "multiline",
        "relevant": rel_10_no
    })

    # 11
    survey_rows.append({
        "type": f"select_one {list_yesno}",
        "name": "falta_capacitacion",
        "label": "11- ¿Considera usted que hace falta capacitación para el personal en su delegación policial?",
        "required": "yes",
        "appearance": "minimal",
        "relevant": rel_si
    })
    rel_11_si = f"({rel_si}) and (${{falta_capacitacion}}='{v_si}')"

    # 11.1
    survey_rows.append({
        "type": "text",
        "name": "areas_capacitacion",
        "label": "11.1 Especifique en qué áreas necesita capacitación.",
        "required": "yes",
        "appearance": "multiline",
        "relevant": rel_11_si
    })

    # 12
    survey_rows.append({
        "type": f"select_one {list_motivacion}",
        "name": "motivacion_medida",
        "label": "12- ¿En qué medida considera que la institución genera un entorno que favorece su motivación para la atención a la ciudadanía?",
        "required": "yes",
        "appearance": "minimal",
        "relevant": rel_si
    })
    rel_12_poco_nada = f"({rel_si}) and (${{motivacion_medida}}='{slugify_name('Poco')}' or ${{motivacion_medida}}='{slugify_name('Nada')}')"

    # 12.1
    survey_rows.append({
        "type": "text",
        "name": "motivo_motivacion_baja",
        "label": "12.1 De manera general, indique por qué lo considera así.",
        "required": "yes",
        "appearance": "multiline",
        "relevant": rel_12_poco_nada
    })

    # 13
    survey_rows.append({
        "type": f"select_one {list_yesno}",
        "name": "situaciones_internas_afectan",
        "label": "13- ¿Tiene usted conocimiento de situaciones internas que, según su criterio, afectan el adecuado funcionamiento operativo o el servicio a la ciudadanía en su delegación?",
        "required": "yes",
        "appearance": "minimal",
        "hint": HINT_CONFIDENCIAL_INSTITUCIONAL,
        "relevant": rel_si
    })
    rel_13_si = f"({rel_si}) and (${{situaciones_internas_afectan}}='{v_si}')"

    # 13.1
    survey_rows.append({
        "type": "text",
        "name": "describe_situaciones_internas",
        "label": "13.1 Describa, de manera general, las situaciones a las que se refiere, relacionadas con aspectos operativos, administrativos o de servicio.",
        "required": "yes",
        "appearance": "multiline",
        "hint": "Información confidencial.",
        "relevant": rel_13_si
    })

    # 14
    survey_rows.append({
        "type": f"select_one {list_yesno}",
        "name": "conoce_oficiales_relacionados",
        "label": "14- ¿Conoce oficiales de Fuerza Pública que se relacionen con alguna estructura criminal o cometan algún delito?",
        "required": "yes",
        "appearance": "minimal",
        "hint": HINT_ANALISIS_PREVENTIVO,
        "relevant": rel_si
    })
    rel_14_si = f"({rel_si}) and (${{conoce_oficiales_relacionados}}='{v_si}')"

    # 14.1
    survey_rows.append({
        "type": "text",
        "name": "describe_situacion_oficiales",
        "label": "14.1 Describa la situación de la cual tiene conocimiento. (aporte nombre de la estructura, tipo de actividad, nombre de oficiales, función del oficial dentro de la organización, alias, etc.)",
        "required": "yes",
        "appearance": "multiline",
        "relevant": rel_14_si
    })

    # 15 (voluntaria)
    survey_rows.append({
        "type": "text",
        "name": "medio_contacto_voluntario",
        "label": "15- Desea, de manera voluntaria, dejar un medio de contacto para brindar más información (correo electrónico, número de teléfono, etc.)",
        "required": False,
        "appearance": "multiline",
        "relevant": rel_si
    })

    # Acceso opcional a Glosario (NO obligatorio)
    survey_rows.append({
        "type": f"select_one {list_yesno}",
        "name": "ver_glosario_p5",
        "label": "¿Desea acceder al glosario de esta sección?",
        "required": "no",
        "appearance": "minimal",
        "relevant": rel_si
    })

    survey_rows.append({"type": "end_group", "name": "p5_end"})

    # Página 5.5: Glosario Interés interno (condicional si responde Sí)
    rel_glos_p5 = f"({rel_si}) and (${{ver_glosario_p5}}='{v_si}')"
    survey_rows.append({
        "type": "begin_group",
        "name": "p5_5_glosario",
        "label": "Glosario — Información de interés interno",
        "appearance": "field-list",
        "relevant": rel_glos_p5
    })

    survey_rows.append({
        "type": "note",
        "name": "p5_5_glosario_info",
        "label": "Para volver a la sección anterior, utilice el botón “Atrás”.",
        "relevant": rel_glos_p5
    })

    for i, (term, defin) in enumerate(GLOS_P5_ITEMS, start=1):
        survey_rows.append({
            "type": "note",
            "name": f"p5_5_term_{i}",
            "label": f"{term}: {defin}",
            "relevant": rel_glos_p5
        })

    # END SOLO en glosario: evita que el usuario avance desde glosario
    survey_rows.append({
        "type": "end",
        "name": "fin_en_glosario_p5",
        "label": "Fin del glosario. Use “Atrás” para regresar a la sección anterior y continuar con la encuesta.",
        "relevant": rel_glos_p5
    })

    survey_rows.append({"type": "end_group", "name": "p5_5_end"})

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



