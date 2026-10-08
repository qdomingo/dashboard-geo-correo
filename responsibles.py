from dataclasses import dataclass

import pandas as pd

from geography import DataValidationError, find_column, normalize_header


LICENSE_FIELDS = {
    "Nombre": "nombre completo",
    "mail": "mail",
    "tipo de licencia": "licencia",
    "estado de licencia": "estado",
    "fecha alta": "fecha alta",
    "fecha baja": "fecha baja",
    "Proyecto": "proyecto",
    "Cod Empresa": "cod empresa",
}
RESPONSIBLE_FIELDS = {
    "Responsable Vertical": "respvertical",
    "Mail Responsable Vertical": "mailrespvertical",
    "Responsable Horizontal": "resphorizontal",
    "Mail Responsable Horizontal": "mailresphorizontal",
}
RESULT_COLUMNS = ["login", "id_empleado", *LICENSE_FIELDS, *RESPONSIBLE_FIELDS]
MASTER_COLUMNS = ["login", "id_empleado", "tipo de licencia", "proyecto", "mail", "Mail Responsable Vertical", "Mail Responsable Horizontal", "Excluido", "Repetidos"]


def filter_master(table: pd.DataFrame) -> pd.DataFrame:
    canceled = table["estado de licencia"].astype("string").fillna("").str.strip().str.casefold().eq("cancelada")
    master = table.loc[~canceled, ["login", "id_empleado", "tipo de licencia", "Proyecto", "mail", "Mail Responsable Vertical", "Mail Responsable Horizontal"]].copy()
    master.rename(columns={"Proyecto": "proyecto"}, inplace=True)
    master["Excluido"] = master["tipo de licencia"].astype("string").fillna("").str.strip().str.casefold().eq("github (solo repositorios)").astype(int)
    logins = master["login"].astype("string").fillna("").str.strip().str.casefold()
    master["Repetidos"] = (logins.ne("") & logins.duplicated(keep=False)).astype(int)
    return master.reset_index(drop=True)


@dataclass
class ResponsibleResult:
    table: pd.DataFrame
    matched: int
    unmatched: int
    incomplete_keys: int
    conflicting_pairs: int
    invalid_emails: int


def process_responsibles(licenses: pd.DataFrame, responsible: pd.DataFrame) -> ResponsibleResult:
    if licenses.empty:
        raise DataValidationError("Licencias debe contener al menos una fila.")
    if len(licenses.columns) < 10:
        raise DataValidationError("Licencias debe incluir la columna J (id_empleado).")
    table = pd.DataFrame({output: licenses[find_column(licenses, source)].reset_index(drop=True).fillna("") for output, source in LICENSE_FIELDS.items()})
    table.insert(0, "id_empleado", licenses.iloc[:, 9].reset_index(drop=True).fillna(""))
    emails = table["mail"].astype("string").str.strip().str.casefold()
    valid_emails = emails.str.fullmatch(r"[^\s@]+@[^\s@]+", na=False)
    table.insert(0, "login", (emails.str.split("@", n=1).str[0] + "_indra").where(valid_emails, ""))
    lookup = pd.DataFrame()
    for output, source in RESPONSIBLE_FIELDS.items():
        if source == "mailrespvertical" and not any(normalize_header(column) == source for column in responsible.columns):
            source = "milrespvertical"
        lookup[output] = responsible[find_column(responsible, source)].reset_index(drop=True).astype("string").fillna("").str.strip()
    for key, license_column, source_column in (("_project", "Proyecto", "cdnempro"), ("_company", "Cod Empresa", "cdempcsc")):
        table[key] = table[license_column].astype("string").str.strip()
        lookup[key] = responsible[find_column(responsible, source_column)].reset_index(drop=True).astype("string").fillna("").str.strip()
    keys = ["_project", "_company"]
    complete = table[keys].ne("").all(axis=1)
    lookup = lookup.loc[lookup[keys].ne("").all(axis=1)]
    lookup = lookup.merge(table.loc[complete, keys].drop_duplicates(), on=keys, how="inner", validate="many_to_one")
    conflicts = lookup.groupby(keys)[list(RESPONSIBLE_FIELDS)].nunique().gt(1).any(axis=1)
    conflict_index = conflicts.loc[conflicts].index
    conflict_rows = pd.MultiIndex.from_frame(lookup[keys]).isin(conflict_index)
    lookup.loc[conflict_rows, list(RESPONSIBLE_FIELDS)] = ""
    lookup = lookup.drop_duplicates(keys)
    merged = table.merge(lookup, on=keys, how="left", sort=False, validate="many_to_one", indicator=True)
    matched = merged["_merge"].eq("both")
    return ResponsibleResult(
        table=merged[RESULT_COLUMNS].fillna(""),
        matched=int(matched.sum()),
        unmatched=int((complete & ~matched).sum()),
        incomplete_keys=int((~complete).sum()),
        conflicting_pairs=len(conflict_index),
        invalid_emails=int((~valid_emails).sum()),
    )