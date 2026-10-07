from dataclasses import dataclass

import pandas as pd

from geography import DataValidationError, find_column


EMPLOYEES_SQL = """select cdemplea, dsemplea, cdalias || '_indra' as login, 
(select cdpais from sidba.emprecsc emp where inactiva = 'S' and emp.cdempcsc = int.cdempcsc) as geografia,
dsintnet as mail, cdempcsc, 
(select dsempcsc from sidba.emprecsc emp where inactiva = 'S' and emp.cdempcsc = int.cdempcsc) as dsempcsc,
cdsitlab, fesitlab from intdba.empleado int where cdsitlab = '01' and cdalias is not null
union
select cdemplea, dsemplea, cdalias || '_indra' as login, 
(select cdpais from sidba.emprecsc emp where inactiva = 'S' and emp.cdempcsc = int.cdempcsc) as geografia,
dsintnet as mail, cdempcsc, 
(select dsempcsc from sidba.emprecsc emp where inactiva = 'S' and emp.cdempcsc = int.cdempcsc) as dsempcsc,
cdsitlab, fesitlab from intdba.empleado int where cdsitlab = '60' and fesitlab > '01/01/26' and cdalias is not null;"""

RESPONSIBLE_SELECT = """select dat.cdnempro, dat.cdempcsc, dat.cdrestec, dat.cdgeshor,
(select emp.dsemplea from intdba.empleado emp where dat.cdrestec = emp.cdemplea and cdsitlab = '01') respVertical,
(select emp.dsintnet from intdba.empleado emp where dat.cdrestec = emp.cdemplea and cdsitlab = '01') mailRespVertical,
(select emp.dsemplea from intdba.empleado emp where dat.cdgeshor = emp.cdemplea and cdsitlab = '01') respHorizontal,
(select emp.dsintnet from intdba.empleado emp where dat.cdgeshor = emp.cdemplea and cdsitlab = '01') mailRespHorizontal
from intdba.datproye dat
where
"""


@dataclass
class ResponsibleSQL:
    sql: str
    unique_pairs: int
    blocks: int
    omitted_rows: int


def generate_responsible_sql(licenses: pd.DataFrame) -> ResponsibleSQL:
    project_column = find_column(licenses, "proyecto")
    company_column = find_column(licenses, "cod empresa")
    projects = licenses[project_column].astype("string").fillna("").str.strip()
    companies = licenses[company_column].astype("string").fillna("").str.strip()
    valid = projects.ne("") & companies.ne("")
    pairs = pd.DataFrame({"project": projects[valid], "company": companies[valid]}).drop_duplicates()
    if pairs.empty:
        raise DataValidationError("No hay parejas de Proyecto y Cod empresa completas en Licencias.")
    values = (pairs["project"] + "-" + pairs["company"]).drop_duplicates().tolist()
    predicates = []
    for start in range(0, len(values), 1000):
        literals = ["'" + value.replace("'", "''") + "'" for value in values[start:start + 1000]]
        lines = [", ".join(literals[position:position + 8]) for position in range(0, len(literals), 8)]
        predicates.append("dat.cdnempro || '-' || dat.cdempcsc in\n(\n    " + ",\n    ".join(lines) + "\n)")
    return ResponsibleSQL(
        sql=RESPONSIBLE_SELECT + "\nor ".join(predicates) + "\n;",
        unique_pairs=len(values),
        blocks=len(predicates),
        omitted_rows=int((~valid).sum()),
    )