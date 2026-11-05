from dataclasses import dataclass
from io import BytesIO
import unicodedata

import pandas as pd


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


def process_geographies(employees: pd.DataFrame, licenses: pd.DataFrame) -> GeographyResult:
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
    selected = candidates.loc[valid_emails].sort_values("assigned", ascending=False, kind="stable").drop_duplicates("login").index
    selected = selected.union(licenses.index[~valid_emails]).sort_values()
    logins = logins.loc[selected].reset_index(drop=True)
    valid_emails = valid_emails.loc[selected].reset_index(drop=True)
    license_status = license_status.loc[selected].reset_index(drop=True)
    employee_id = employee_id.loc[selected].reset_index(drop=True)
    
    employee_logins = employees[login_column].astype("string").fillna("").str.strip().str.casefold()
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
    table = pd.DataFrame({"id_empleado": employee_id, "login": logins, "geograf\u00eda": logins.map(mapping).fillna("")}).reset_index(drop=True)
    return GeographyResult(
        table=table,
        matched=int(matched.sum()),
        unmatched=int((valid_emails & ~matched).sum()),
        invalid_emails=int((~valid_emails).sum()),
        missing_geography=int((matched & ~logins.isin(conflict_logins) & table["geograf\u00eda"].set_axis(logins.index).eq("")).sum()),
        conflicting_logins=len(conflict_logins),
        license_status=license_status,
        employee_id=employee_id,
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