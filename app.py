from hashlib import sha256
from io import BytesIO
from pathlib import Path
import warnings

import pandas as pd
import streamlit as st

from access import require_access
from geography import DataValidationError, export_csv, export_excel, normalize_header, process_geographies
from sql_generation import EMPLOYEES_SQL, generate_responsible_sql
from responsibles import RESULT_COLUMNS, filter_master, process_responsibles
from email_check import check_emails


ROOT = Path(__file__).resolve().parent
INPUT_FOLDER = ROOT / "Archivos_Entrada"
TITLE = "Extracci\u00f3n Geograf\u00edas y Correos"

st.set_page_config(page_title=TITLE, page_icon=":material/public:", layout="wide")
st.markdown(
    """<style>
    :root { --ink: #202d32; --accent: #087f83; --line: #dce6e7; }
    .stApp { background: #fbfcfc; color: var(--ink); }
    [data-testid="stSidebar"] { background: #f0f5f5; border-right: 1px solid var(--line); }
    [data-testid="stSidebar"] h3 { font-size: 1.05rem; }
    .block-container { padding-top: 2.5rem; padding-bottom: 2rem; max-width: 1500px; }
    h1 { font-size: 2.1rem !important; font-weight: 650 !important; letter-spacing: 0 !important; }
    h2 { font-size: 1.35rem !important; letter-spacing: 0 !important; }
    h3 { letter-spacing: 0 !important; }
    [data-testid="stMetric"] { border-bottom: 3px solid var(--line); padding: 0.5rem 0 1rem; }
    [data-testid="stMetricValue"] { font-size: 1.8rem; }
    [data-testid="stFileUploader"] { border-radius: 6px; }
    button { border-radius: 6px !important; }
    [data-testid="stButton"] button[kind="primary"] { background: var(--accent); border-color: var(--accent); }
    [data-testid="stTabs"] { margin-top: 1rem; }
    @media (max-width: 640px) {
      .block-container { padding: 1.5rem 1rem; }
      h1 { font-size: 1.65rem !important; overflow-wrap: anywhere; }
    }
    </style>""",
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False, max_entries=12)
def excel_sheets(content: bytes) -> list[str]:
    with pd.ExcelFile(BytesIO(content)) as workbook:
        return workbook.sheet_names


@st.cache_data(show_spinner=False, max_entries=12)
def read_excel(content: bytes, sheet: str) -> pd.DataFrame:
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Workbook contains no default style")
        return pd.read_excel(BytesIO(content), sheet_name=sheet, dtype=str, keep_default_na=False)


@st.cache_data(show_spinner=False, max_entries=4)
def read_csv(content: bytes) -> pd.DataFrame:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return pd.read_csv(BytesIO(content), sep=None, engine="python", encoding=encoding, dtype=str, keep_default_na=False)
        except UnicodeDecodeError:
            continue
    raise DataValidationError("No se ha podido leer la codificacion del CSV.")


def load_source(key: str, label: str, local_path: Path | None, use_local: bool, csv: bool = False):
    st.subheader(label)
    uploaded = st.file_uploader(
        f"Archivo de {label.lower()}", type=["csv"] if csv else ["xlsx", "xls"],
        key=f"upload_{key}", label_visibility="collapsed",
    )
    try:
        if uploaded is not None:
            content, filename = uploaded.getvalue(), uploaded.name
        elif use_local and local_path is not None and local_path.is_file():
            content, filename = local_path.read_bytes(), local_path.name
        else:
            st.caption("Sin archivo")
            return None
        digest = sha256(content).hexdigest()
        if csv:
            frame = read_csv(content)
            sheet = "CSV"
        else:
            sheets = excel_sheets(content)
            sheet = st.selectbox("Hoja", sheets, key=f"sheet_{key}_{digest}")
            frame = read_excel(content, sheet)
        st.caption(f"{filename} | {len(frame):,} filas")
        return {"data": frame, "name": filename, "sheet": sheet, "signature": digest + sheet}
    except Exception as error:
        st.error(f"No se pudo leer {label}: {error}")
        return None


def column_picker(label: str, frame: pd.DataFrame, target: str, key: str):
    options = frame.columns.tolist()
    matches = [position for position, column in enumerate(options) if normalize_header(column) == normalize_header(target)]
    return st.selectbox(label, options, index=matches[0] if len(matches) == 1 else None, key=key, placeholder="Selecciona una columna")


st.title(TITLE)
require_access()

with st.sidebar:
    st.subheader("Archivos de entrada", icon=":material/folder_open:")
    use_local = st.toggle("Usar archivos de Archivos_Entrada", value=INPUT_FOLDER.is_dir(), key="use_local_files")
    employees = load_source("employees", "Empleados", INPUT_FOLDER / "Empleados.xlsx", use_local)
    licenses = load_source("licenses", "Licencias", INPUT_FOLDER / "Licencias.xlsx", use_local)
    responsible = load_source("responsible", "Responsables", INPUT_FOLDER / "Responsables.xlsx", use_local)
    st.divider()
    csv_paths = sorted(INPUT_FOLDER.glob("*.csv")) if INPUT_FOLDER.exists() else []
    csv_path = None
    if use_local and csv_paths:
        csv_path = st.selectbox("CSV de la carpeta", csv_paths, format_func=lambda path: path.name)
    activity = load_source("activity", "Actividad CSV", csv_path, use_local, csv=True)

geography_tab, responsible_tab, sources_tab, sql_tab = st.tabs(["Geograf\u00edas", "Responsables", "Datos de entrada", "Generar SQLs"])

with geography_tab:
    st.subheader("Geograf\u00edas", icon=":material/public:")
    ready = employees is not None and licenses is not None
    selected_login = selected_geography = selected_mail = None
    if ready:
        with st.expander("Columnas del cruce", expanded=False):
            login_area, geography_area, mail_area = st.columns(3)
            with login_area:
                selected_login = column_picker("Login de Empleados", employees["data"], "login", "login_" + employees["signature"])
            with geography_area:
                selected_geography = column_picker("Geograf\u00eda de Empleados", employees["data"], "geografia", "geo_" + employees["signature"])
            with mail_area:
                selected_mail = column_picker("Mail de Licencias", licenses["data"], "mail", "mail_" + licenses["signature"])
        ready = all(column is not None for column in (selected_login, selected_geography, selected_mail))
    signature = (employees["signature"] if employees else None, licenses["signature"] if licenses else None,
                 selected_login, selected_geography, selected_mail)
    if st.session_state.get("result_signature") != signature:
        st.session_state.pop("geography_result", None)
    if st.button("Procesar Geograf\u00edas", icon=":material/sync:", type="primary", key="process_geographies", disabled=not ready):
        st.session_state.pop("geography_result", None)
        try:
            with st.spinner("Procesando geograf\u00edas..."):
                employee_frame = employees["data"][[selected_login, selected_geography]].copy()
                employee_frame.columns = ["login", "geografia"]
                status_columns = [column for column in licenses["data"].columns if normalize_header(column) in ("estado", "estado de licencia")]
                license_frame = licenses["data"][[selected_mail]].copy()
                license_frame.columns = ["mail"]
                if len(status_columns) == 1:
                    license_frame["estado de licencia"] = licenses["data"][status_columns[0]]
                st.session_state.geography_result = process_geographies(employee_frame, license_frame)
                st.session_state.result_signature = signature
        except DataValidationError as error:
            st.error(str(error))

    result = st.session_state.get("geography_result")
    if result is None:
        if not ready:
            st.info("Pendiente de Empleados y Licencias con columnas de login, geograf\u00eda y mail.", icon=":material/info:")
        else:
            st.caption("Resultado pendiente")
        st.dataframe(pd.DataFrame(columns=["login", "geograf\u00eda", "estado de licencia"]), hide_index=True, width="stretch")
    else:
        total_area, matched_area, blank_area = st.columns(3)
        total_area.metric("Filas de Licencias", f"{len(result.table):,}")
        matched_area.metric("Coincidencias en Empleados", f"{result.matched:,}")
        blank_area.metric("Sin geograf\u00eda", f"{result.table['geograf\u00eda'].eq('').sum():,}")
        if result.invalid_emails:
            st.warning(f"{result.invalid_emails:,} filas con mail vacio o invalido: login y geograf\u00eda vacios.")
        if result.conflicting_logins:
            st.warning(f"{result.conflicting_logins:,} logins con geograf\u00edas contradictorias en Empleados: geograf\u00eda vacia en el resultado.")
        if result.unmatched or result.missing_geography:
            st.caption(f"No encontrados en Empleados: {result.unmatched:,} | Empleados sin geograf\u00eda: {result.missing_geography:,}")
        st.divider()
        search_area, filter_area = st.columns([2, 1])
        search = search_area.text_input("Buscar login", placeholder="Login", key="search")
        geography_filter = filter_area.selectbox("Geograf\u00eda", ["Todas", "Sin geograf\u00eda"] + sorted(result.table.loc[result.table["geograf\u00eda"].ne(""), "geograf\u00eda"].unique().tolist()))
        view = result.table.copy()
        view["estado de licencia"] = result.license_status
        status_columns = [column for column in licenses["data"].columns if normalize_header(column) in ("estado", "estado de licencia")]
        if len(status_columns) != 1:
            st.warning("No se ha encontrado una unica columna de estado de licencia en Licencias.")
        if search:
            view = view.loc[view["login"].str.contains(search.strip().casefold(), regex=False, na=False)]
        if geography_filter == "Sin geograf\u00eda":
            view = view.loc[view["geograf\u00eda"].eq("")]
        elif geography_filter != "Todas":
            view = view.loc[view["geograf\u00eda"].eq(geography_filter)]
        st.caption(f"{len(view):,} de {len(result.table):,} filas")
        st.dataframe(view, hide_index=True, width="stretch", height=440)
        excel_area, csv_area, _ = st.columns([1, 1, 2])
        excel_area.download_button("Exportar Excel", export_excel(result.table), "geografias.xlsx",
                                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", icon=":material/download:", width="stretch")
        csv_area.download_button("Exportar CSV", export_csv(result.table), "geografias.csv", "text/csv", icon=":material/download:", width="stretch")
        st.caption(f"Exportaci\u00f3n completa: {len(result.table):,} filas")

with responsible_tab:
    st.subheader("Responsables", icon=":material/groups:")
    responsible_signature = (licenses["signature"] if licenses else None, responsible["signature"] if responsible else None)
    if st.session_state.get("responsible_signature") != responsible_signature:
        st.session_state.pop("responsible_result", None)
        st.session_state.pop("master_table", None)
        st.session_state.pop("email_result", None)
    email_signature = (licenses["signature"] if licenses else None, activity["signature"] if activity else None, pd.Timestamp.now(tz="UTC").date().isoformat())
    if st.session_state.get("email_signature") != email_signature:
        st.session_state.pop("email_result", None)
    responsible_ready = licenses is not None and responsible is not None
    if st.button("Procesar Responsables", icon=":material/sync:", type="primary", key="process_responsibles", disabled=not responsible_ready):
        st.session_state.pop("responsible_result", None)
        st.session_state.pop("master_table", None)
        st.session_state.pop("email_result", None)
        try:
            with st.spinner("Procesando responsables..."):
                st.session_state.responsible_result = process_responsibles(licenses["data"], responsible["data"])
                st.session_state.responsible_signature = responsible_signature
        except DataValidationError as error:
            st.error(str(error))
    responsible_result = st.session_state.get("responsible_result")
    if responsible_result is None:
        if not responsible_ready:
            st.info("Pendiente de Licencias y Responsables.", icon=":material/info:")
        else:
            st.caption("Resultado pendiente")
        st.dataframe(pd.DataFrame(columns=RESULT_COLUMNS), hide_index=True, width="stretch")
    else:
        rows_area, matches_area, unmatched_area = st.columns(3)
        rows_area.metric("Filas de Licencias", f"{len(responsible_result.table):,}")
        matches_area.metric("Coincidencias en Responsables", f"{responsible_result.matched:,}")
        unmatched_area.metric("Sin coincidencia", f"{responsible_result.unmatched + responsible_result.incomplete_keys:,}")
        if responsible_result.incomplete_keys:
            st.warning(f"{responsible_result.incomplete_keys:,} filas sin Proyecto o Cod Empresa: datos de responsables vacios.")
        if responsible_result.conflicting_pairs:
            st.warning(f"{responsible_result.conflicting_pairs:,} parejas proyecto-empresa con responsables contradictorios: datos de responsables vacios.")
        if responsible_result.invalid_emails:
            st.warning(f"{responsible_result.invalid_emails:,} filas con mail vacio o invalido: login vacio.")
        search_area, filter_area = st.columns([2, 1])
        responsible_search = search_area.text_input("Buscar login, nombre, mail o proyecto", key="responsible_search")
        only_without_responsibles = filter_area.toggle("Solo sin datos de responsables", key="responsible_empty_filter")
        responsible_view = responsible_result.table
        if responsible_search:
            query = responsible_search.strip().casefold()
            search_mask = pd.Series(False, index=responsible_view.index)
            for column in ("login", "Nombre", "mail", "Proyecto"):
                search_mask |= responsible_view[column].astype("string").str.casefold().str.contains(query, regex=False, na=False)
            responsible_view = responsible_view.loc[search_mask]
        if only_without_responsibles:
            responsible_view = responsible_view.loc[responsible_view[RESULT_COLUMNS[-4:]].eq("").all(axis=1)]
        st.caption(f"{len(responsible_view):,} de {len(responsible_result.table):,} filas")
        status_colors = {
            "asignada": "background-color: #dcfce7; color: #166534; font-weight: bold;",
            "cancelada": "background-color: #fee2e2; color: #991b1b; font-weight: bold;",
        }
        styled_responsibles = responsible_view.style.map(
            lambda value: status_colors.get(str(value).strip().casefold(), ""),
            subset=["estado de licencia"],
        )
        st.dataframe(styled_responsibles, hide_index=True, width="stretch", height=440)
        excel_area, csv_area, _ = st.columns([1, 1, 2])
        excel_area.download_button("Exportar Excel", export_excel(responsible_result.table, sheet_name="Responsables"), "responsables.xlsx",
                                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="export_responsibles_excel", icon=":material/download:", width="stretch")
        csv_area.download_button("Exportar CSV", export_csv(responsible_result.table), "responsables.csv", "text/csv", key="export_responsibles_csv", icon=":material/download:", width="stretch")
        st.caption(f"Exportaci\u00f3n completa: {len(responsible_result.table):,} filas")
        st.divider()
        if st.button("Filtrar excel para maestro", icon=":material/filter_alt:", key="filter_master"):
            st.session_state.master_table = filter_master(responsible_result.table)
        master_table = st.session_state.get("master_table")
        if master_table is not None:
            st.subheader("Maestro")
            st.caption(f"{len(master_table):,} filas | {len(responsible_result.table) - len(master_table):,} licencias canceladas retiradas")
            styled_master = master_table.style.apply(
                lambda row: ["background-color: #fee2e2; color: #991b1b;" if row["Excluido"] == 1 else ""] * len(row),
                axis=1,
            )
            st.dataframe(styled_master, hide_index=True, width="stretch", height=440)
            master_export = master_table.drop(columns=["id_empleado", "tipo de licencia", "Repetidos"])
            st.download_button("Exportar Excel maestro", export_excel(master_export, sheet_name="Maestro"), "maestro.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="export_master_excel", icon=":material/download:")
            st.divider()
            if activity is None:
                st.info("Pendiente de cargar el CSV de actividad de GitHub.", icon=":material/info:")
            if st.button("Checkeo correos a enviar", icon=":material/mail:", key="check_emails", disabled=activity is None):
                st.session_state.pop("email_result", None)
                try:
                    with st.spinner("Revisando actividad y licencias..."):
                        st.session_state.email_result = check_emails(licenses["data"], activity["data"], today=email_signature[2])
                        st.session_state.email_signature = email_signature
                except DataValidationError as error:
                    st.error(str(error))
            email_result = st.session_state.get("email_result")
            if email_result is not None:
                st.subheader("Correos a enviar")
                email_table = email_result.table
                total_area, send_area = st.columns(2)
                total_area.metric("Usuarios del CSV", f"{len(email_table):,}")
                send_area.metric("Env\u00edo SI", f"{email_table['env\u00edo'].eq('SI').sum():,}")
                st.caption(f"Fecha de evaluaci\u00f3n (UTC): {email_result.evaluation_date}")
                if email_result.duplicate_assigned:
                    st.warning(f"{email_result.duplicate_assigned:,} usuarios del CSV con m\u00e1s de una licencia asignada: env\u00edo NO hasta revisar Licencias.")
                email_view = email_table
                if st.toggle("Solo env\u00edo SI", key="email_only_send"):
                    email_view = email_table.loc[email_table["env\u00edo"].eq("SI")]
                styled_emails = email_view.style.map(
                    lambda value: "background-color: #dcfce7; color: #166534; font-weight: bold;" if value == "SI" else "",
                    subset=["env\u00edo"],
                )
                st.dataframe(styled_emails, hide_index=True, width="stretch", height=440)
                excel_area, csv_area, _ = st.columns([1, 1, 2])
                excel_area.download_button("Exportar Excel correos", export_excel(email_table, sheet_name="Correos"), "correos.xlsx",
                                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="export_emails_excel", icon=":material/download:")
                csv_area.download_button("Exportar CSV correos", export_csv(email_table), "correos.csv", "text/csv", key="export_emails_csv", icon=":material/download:")


with sources_tab:
    sources = {label: source for label, source in [("Empleados", employees), ("Licencias", licenses), ("Responsables", responsible), ("Actividad CSV", activity)] if source is not None}
    if sources:
        selection = st.selectbox("Origen", list(sources))
        source = sources[selection]
        st.caption(f"{source['name']} | {source['sheet']} | {len(source['data']):,} filas | {len(source['data'].columns)} columnas")
        st.dataframe(source["data"].head(200), hide_index=True, width="stretch", height=440)
        st.caption("Vista previa: primeras 200 filas")
    else:
        st.info("Sin archivos cargados.")

with sql_tab:
    st.subheader("Generar SQLs", icon=":material/database:")
    license_signature = licenses["signature"] if licenses else None
    if st.session_state.get("sql_kind") == "responsible" and st.session_state.get("sql_license_signature") != license_signature:
        st.session_state.sql_text = ""
        st.session_state.pop("sql_summary", None)
        st.session_state.pop("sql_kind", None)
    employee_button_area, responsible_button_area = st.columns(2)
    if employee_button_area.button("Generar SQL Empleados", icon=":material/code:", key="generate_employee_sql", width="stretch"):
        st.session_state.sql_text = EMPLOYEES_SQL
        st.session_state.sql_kind = "employees"
        st.session_state.pop("sql_summary", None)
    if responsible_button_area.button("Generar SQL Responsables", icon=":material/code:", key="generate_responsible_sql", disabled=licenses is None, width="stretch"):
        st.session_state.sql_text = ""
        st.session_state.pop("sql_summary", None)
        st.session_state.pop("sql_kind", None)
        try:
            generated = generate_responsible_sql(licenses["data"])
            st.session_state.sql_text = generated.sql
            st.session_state.sql_kind = "responsible"
            st.session_state.sql_license_signature = license_signature
            st.session_state.sql_summary = (generated.unique_pairs, generated.blocks, generated.omitted_rows)
        except DataValidationError as error:
            st.error(str(error))
    st.text_area("SQL generada", key="sql_text", height=420)
    summary = st.session_state.get("sql_summary")
    if summary:
        pair_count, block_count, omitted_count = summary
        st.caption(f"{pair_count:,} parejas proyecto-empresa | {block_count} bloques IN")
        if omitted_count:
            st.warning(f"{omitted_count:,} filas omitidas por Proyecto o Cod empresa vacios.")

st.divider()
st.caption("Extracci\u00f3n Geograf\u00edas y Correos | Procesamiento local")