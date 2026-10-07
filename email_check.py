from dataclasses import dataclass
import re

import pandas as pd

from geography import DataValidationError, find_column


EMAIL_COLUMNS = ["login", "last activity at", "mail", "env\u00edo", "motivo"]
MISSING_ACTIVITY = {"", "none", "null", "nan", "nat"}


@dataclass
class EmailCheckResult:
    table: pd.DataFrame
    duplicate_assigned: int
    evaluation_date: str


def parse_date(value: object) -> pd.Timestamp:
    if isinstance(value, str) and re.match(r"^\d{4}-\d{2}-\d{2}(?:$|[T ])", value.strip()):
        return pd.to_datetime(value.strip(), format="ISO8601", errors="coerce", utc=True)
    return pd.to_datetime(value, format="mixed", dayfirst=True, errors="coerce", utc=True)


def check_emails(licenses: pd.DataFrame, activity: pd.DataFrame, today: object = None) -> EmailCheckResult:
    current = pd.Timestamp.now(tz="UTC") if today is None else parse_date(today)
    if pd.isna(current):
        raise DataValidationError("La fecha de evaluacion no es valida.")
    current = current.normalize()
    if activity.empty:
        raise DataValidationError("El CSV de actividad no contiene usuarios.")
    fields = {name: find_column(licenses, name) for name in ("mail", "estado", "licencia", "fecha alta")}
    login_column = find_column(activity, "login")
    activity_column = find_column(activity, "last activity at")
    candidates = pd.DataFrame({name: licenses[column].reset_index(drop=True).astype("string").fillna("").str.strip() for name, column in fields.items()})
    emails = candidates["mail"].str.casefold()
    valid = emails.str.fullmatch(r"[^\s@]+@[^\s@]+", na=False)
    candidates["login"] = (emails.str.split("@", n=1).str[0] + "_indra").where(valid, "")
    candidates["estado"] = candidates["estado"].str.casefold()
    candidates = candidates.loc[candidates["estado"].ne("cancelada") & candidates["login"].ne("")]
    assigned_counts = candidates.loc[candidates["estado"].eq("asignada")].groupby("login").size()
    duplicate_logins = set(assigned_counts.loc[assigned_counts.gt(1)].index)
    groups = {login: frame for login, frame in candidates.groupby("login", sort=False)}
    logins = activity[login_column].reset_index(drop=True).astype("string").fillna("").str.strip().str.casefold()
    last_activity = activity[activity_column].reset_index(drop=True).fillna("")
    rows = []
    for login, last_used in zip(logins, last_activity):
        mail, send, reason = "", "NO", ""
        group = groups.get(login)
        if group is None:
            reason = "Sin coincidencia en licencias"
        elif login in duplicate_logins:
            reason = "M\u00e1s de una licencia asignada"
        else:
            assigned = group.loc[group["estado"].eq("asignada")]
            selected = assigned if not assigned.empty else group
            if len(selected) > 1:
                reason = "Varias licencias no canceladas sin asignada"
            else:
                license_row = selected.iloc[0]
                mail = license_row["mail"]
                if license_row["licencia"].casefold() == "github (solo repositorios)":
                    reason = "S\u00f3lo Repositorios"
                elif license_row["estado"] == "asignada":
                    never_used = str(last_used).strip().casefold() in MISSING_ACTIVITY
                    reference = parse_date(license_row["fecha alta"] if never_used else last_used)
                    if pd.isna(reference):
                        reason = "Fecha de alta no valida" if never_used else "Fecha de actividad no valida"
                    elif (current - reference.normalize()).days >= 14:
                        send = "SI"
                        reason = "A\u00fan no usado" if never_used else "Sin actividad m\u00e1s de 14 d\u00edas"
        rows.append([login, last_used, mail, send, reason])
    return EmailCheckResult(
        table=pd.DataFrame(rows, columns=EMAIL_COLUMNS),
        duplicate_assigned=len(duplicate_logins.intersection(set(logins))),
        evaluation_date=current.date().isoformat(),
    )