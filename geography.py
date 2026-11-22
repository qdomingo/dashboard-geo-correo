from dataclasses import dataclass
from io import BytesIO
import unicodedata

import pandas as pd


GEOGRAPHY_COLUMNS = ["id_empleado", "login", "geograf\u00eda", "Organizaci\u00f3n", "duplicados", "estado de licencia"]
ORGANIZATION_ORDER = ("MINSAIT", "CAIXABANK", "ATM")


class DataValidationError(ValueError):
    pass


def normalize_header(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value).strip().casefold())
    return "".join(character for character in text if not unicodedata.combining(character))


def find_column(frame: pd.DataFrame, name: str) -> object:
    matches = [column for column in frame.columns if normalize_header(column) == normalize_header(name)]
    if len(matches) != 1:
        raise DataValidationError(f"Debe existir una unica columna '{name}'. Columnas disponibles: {', '.join(map(str, frame.columns))}")
    return matches[0]


@dataclass
class GeographyResult:
    table: pd.DataFrame
    matched: int
    unmatched: int
    invalid_emails: int
    missing_geography: int
    conflicting_logins: int
    license_status: pd.Series
    employee_id: pd.Series
    unresolved_induced: int


def _induced_candidates(employees: pd.DataFrame, employee_logins: pd.Series, induced: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    induced = induced.reset_index(drop=True)
    employee_ids = employees[find_column(employees, "CDEMPLEA")].astype("string").fillna("").str.strip()
    ids = induced[find_column(induced, "ID")].astype("string").fillna("").str.strip()
    states = induced[find_column(induced, "Estado")].astype("string").fillna("").str.strip()
    projects = induced[find_column(induced, "C\u00f3d. Proyecto")].astype("string").str.strip().str.casefold()
    clients = induced[find_column(induced, "Cliente")].astype("string").str.strip().str.casefold()
    atm = projects.eq("atmpro").fillna(False)
    caixabank = clients.eq("caixabank").fillna(False)
    eligible = states.str.casefold().eq("asignada") & (caixabank | atm)

    lookup = pd.DataFrame({"id_empleado": employee_ids, "login": employee_logins})
    lookup = lookup.loc[lookup["id_empleado"].ne("") & lookup["login"].ne("")].drop_duplicates()
    login_by_id = lookup.drop_duplicates("id_empleado", keep=False).set_index("id_empleado")["login"]
    logins = ids.loc[eligible].map(login_by_id)
    candidates = pd.DataFrame({
        "id_empleado": ids.loc[eligible],
        "login": logins,
        "Organizaci\u00f3n": caixabank.loc[eligible].map({True: "CAIXABANK", False: "ATM"}),
        "estado de licencia": states.loc[eligible],
    })
    return candidates.loc[logins.notna()], int(logins.isna().sum())


def process_geographies(
    employees: pd.DataFrame, licenses: pd.DataFrame, induced: pd.DataFrame | None = None,
) -> GeographyResult:
    login_column = find_column(employees, "login")
    geography_column = find_column(employees, "geografia")
    mail_column = find_column(licenses, "mail")
    if employees.empty or licenses.empty:
        raise DataValidationError("Empleados y Licencias deben contener al menos una fila.")

    licenses = licenses.reset_index(drop=True)
    emails = licenses[mail_column].astype("string").fillna("").str.strip().str.casefold()
    valid_emails = emails.str.fullmatch(r"[^\s@]+@[^\s@]+", na=False)
    logins = (emails.str.split("@", n=1).str[0] + "_indra").where(valid_emails, "")
    status_columns = [column for column in licenses.columns if normalize_header(column) in ("estado", "estado de licencia")]
    license_status = (licenses[status_columns[0]].astype("string").fillna("").str.strip()
                      if len(status_columns) == 1 else pd.Series("", index=licenses.index, dtype="string"))
    id_columns = [column for column in licenses.columns if normalize_header(column) == "id_empleado"]
    employee_id = (licenses[id_columns[0]].astype("string").fillna("").str.strip()
                   if len(id_columns) == 1 else pd.Series("", index=licenses.index, dtype="string"))

    candidates = pd.DataFrame({"login": logins, "assigned": license_status.str.casefold().eq("asignada")})
    organizations = pd.DataFrame({"login": logins.loc[valid_emails & candidates["assigned"]], "Organizaci\u00f3n": "MINSAIT"})
    selected = candidates.loc[valid_emails].sort_values("assigned", ascending=False, kind="stable").drop_duplicates("login").index
    selected = selected.union(licenses.index[~valid_emails]).sort_values()

    rows = pd.DataFrame({
        "id_empleado": employee_id.loc[selected],
        "login": logins.loc[selected],
        "Organizaci\u00f3n": "MINSAIT",
        "estado de licencia": license_status.loc[selected],
    }).reset_index(drop=True)
    employee_logins = employees[login_column].astype("string").fillna("").str.strip().str.casefold()
    unresolved_induced = 0
    if induced is not None:
        added, unresolved_induced = _induced_candidates(employees, employee_logins, induced)
        organizations = pd.concat([organizations, added[["login", "Organizaci\u00f3n"]]], ignore_index=True)
        cancelled = rows["estado de licencia"].str.casefold().eq("cancelada")
        added = added.loc[~added["login"].isin(rows.loc[~cancelled, "login"])]
        caixabank = added["Organizaci\u00f3n"].eq("CAIXABANK")
        preferred = pd.concat([added.loc[caixabank], added.loc[~caixabank]]).drop_duplicates("login").sort_index()
        if not preferred.empty:
            replaced = cancelled & rows["login"].isin(preferred["login"])
            rows = pd.concat([rows.loc[~replaced], preferred], ignore_index=True)

    logins = rows["login"]
    repeated = organizations.loc[organizations["login"].duplicated(keep=False)]
    duplicate_labels = repeated.groupby("login")["Organizaci\u00f3n"].agg(
        lambda values: "duplicado(" + "-".join(sorted(set(values), key=ORGANIZATION_ORDER.index)) + ")"
    )
    rows["duplicados"] = logins.map(duplicate_labels).fillna("")
    geographies = employees[geography_column].astype("string").fillna("").str.strip()
    lookup = pd.DataFrame({"login": employee_logins, "geograf\u00eda": geographies})
    lookup = lookup.loc[lookup["login"].ne("") & lookup["login"].isin(logins)]
    nonempty = lookup.loc[lookup["geograf\u00eda"].ne("")]
    conflicts = nonempty.groupby("login")["geograf\u00eda"].nunique()
    conflict_logins = conflicts.loc[conflicts.gt(1)].index
    lookup = pd.concat([nonempty, lookup]).drop_duplicates("login", keep="first")
    lookup.loc[lookup["login"].isin(conflict_logins), "geograf\u00eda"] = ""
    mapping = lookup.set_index("login")["geograf\u00eda"]
    matched = logins.ne("") & logins.isin(mapping.index)
    rows["geograf\u00eda"] = logins.map(mapping).fillna("")
    table = rows[GEOGRAPHY_COLUMNS]
    return GeographyResult(
        table=table,
        matched=int(matched.sum()),
        unmatched=int((logins.ne("") & ~matched).sum()),
        invalid_emails=int(logins.eq("").sum()),
        missing_geography=int((matched & ~logins.isin(conflict_logins) & table["geograf\u00eda"].eq("")).sum()),
        conflicting_logins=len(conflict_logins),
        license_status=rows["estado de licencia"],
        employee_id=rows["id_empleado"],
        unresolved_induced=unresolved_induced,
    )


def export_csv(table: pd.DataFrame) -> bytes:
    safe_table = escape_formulas(table)
    return safe_table.to_csv(index=False, sep=";", lineterminator="\n").encode("utf-8-sig")


def escape_formulas(table: pd.DataFrame) -> pd.DataFrame:
    return table.map(
        lambda value: "'" + value
        if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@"))
        else value
    )


def export_excel(table: pd.DataFrame, sheet_name: str = "Geografias") -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(
        output, engine="xlsxwriter",
        engine_kwargs={"options": {"strings_to_formulas": False, "strings_to_urls": False}},
    ) as writer:
        table.to_excel(writer, sheet_name=sheet_name, index=False)
        sheet = writer.sheets[sheet_name]
        sheet.freeze_panes(1, 0)
        sheet.autofilter(0, 0, len(table), len(table.columns) - 1)
        sheet.set_column(0, len(table.columns) - 1, 28)
        sheet.set_column(0, 0, 32)
    return output.getvalue()