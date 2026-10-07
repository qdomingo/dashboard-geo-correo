# Extraccion Geografias y Correos

Aplicacion en Python y Streamlit para uso local o despliegue en Heroku. Tablas de geografias (Empleados y Licencias) y responsables (Licencias y Responsables), con generacion de SQLs para extraer datos y chequeo de correos mediante el CSV de actividad.

## Ejecucion

Desde la carpeta del proyecto, con Python 3.14 (version usada en las pruebas y en Heroku):

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m streamlit run app.py
```

Abrir la direccion local que muestra Streamlit. Los datos se procesan en memoria y no se modifican los originales. En modo local no se envian a servicios externos. En Heroku los archivos subidos se transmiten al servidor de Heroku para procesarlos. La telemetria de Streamlit esta desactivada. El arranque local escucha solo en localhost; el Procfile adapta la direccion y el puerto al entorno Heroku.

## GitHub y Heroku

Consulta [DEPLOYMENT.md](DEPLOYMENT.md) para publicar el codigo en GitHub y conectarlo con Heroku. No subir archivos de entrada, exportaciones ni secretos. En Heroku se exige la variable APP_PASSWORD antes de permitir el acceso; en local es opcional. No se ha creado ni publicado ningun repositorio remoto desde este proyecto.

## Archivos

Hay tres apartados de Excel (Empleados, Licencias y Responsables) y uno de CSV. Por defecto se usan los archivos presentes en `Archivos_Entrada`. Un archivo subido tiene prioridad sobre el de la carpeta. Para trabajar exclusivamente con subidas, desactivar el interruptor de archivos locales. Es posible elegir hojas y configurar las tres columnas del cruce si sus nombres cambian.

Las hojas iniciales de los archivos actuales son `Exportar Hoja de Trabajo` en Empleados y `O-Licencias` en Licencias. Se detectan `LOGIN`, `GEOGRAFIA` y `Mail` sin distinguir mayusculas, acentos o espacios exteriores.

## Reglas de Geografias

- La base es Licencias: se mantiene una fila por cada fila leida, en el mismo orden, incluidos usuarios repetidos. No se filtra por estado ni por tipo de licencia.
- El mail se convierte en login tomando la parte anterior a `@` y anadiendo `_indra`. Se normalizan espacios exteriores y mayusculas tanto en mail como en login.
- El cruce es exacto tras normalizar: no se corrigen erratas ni se hacen coincidencias aproximadas. `edomigo_indra` y `edomingo_indra` son usuarios distintos.
- La geografia procede de Empleados. Un login no encontrado conserva su login y deja la geografia vacia.
- Un mail vacio o invalido conserva la fila con ambas columnas vacias y genera un aviso.
- Los duplicados de Empleados no multiplican el resultado. Si un login tiene una unica geografia no vacia, se utiliza esa. Si tiene varias geografias distintas y figura en Licencias, se deja su geografia vacia y se muestra un aviso. No se elige arbitrariamente una geografia.
- El resultado tiene exactamente las columnas `login` y `geografia` (esta ultima se muestra y exporta con tilde).
- La tabla en pantalla muestra tambien `estado de licencia`, tomado de la columna Estado de Licencias y conservando su orden. Esta columna es solo visual: Excel y CSV exportan unicamente login y geografia.
- Cambiar los archivos, hojas o columnas del cruce invalida el resultado anterior. Responsables y CSV no son necesarios para Procesar Geografias.

Los botones exportan la tabla completa, independientemente de los filtros de pantalla. Excel incluye filtros y cabecera fija. CSV utiliza separador `;` y UTF-8 con BOM para Excel en espanol. Las exportaciones protegen contra formulas procedentes de valores de entrada; el CSV antepone una comilla simple a valores que podrian interpretarse como formulas.

## Responsables

La pestana Responsables cruza Licencias con Responsables mediante Proyecto y Cod Empresa frente a CDNEMPRO y CDEMPCSC. Se comparan como dos campos separados, quitando espacios exteriores, sin coincidencias aproximadas. No necesita Empleados ni el CSV.

Procesar Responsables conserva todas las filas de Licencias, su orden, duplicados y estados. El resultado tiene estas 14 columnas:

`login`, `id_empleado`, `Nombre`, `mail`, `tipo de licencia`, `estado de licencia`, `fecha alta`, `fecha baja`, `Proyecto`, `Cod Empresa`, `Responsable Vertical`, `Mail Responsable Vertical`, `Responsable Horizontal`, `Mail Responsable Horizontal`.

El login se deriva del mail igual que en Geografias. id_empleado procede siempre de la columna J (decima columna) de la hoja seleccionada de Licencias, aunque no tenga titulo; en el archivo actual su cabecera es ID. El resto de datos de Licencias conserva los valores leidos, incluidos mail, fechas e identificadores textuales con ceros iniciales.

Los cuatro campos de responsables proceden de RESPVERTICAL, MAILRESPVERTICAL, RESPHORIZONTAL y MAILRESPHORIZONTAL. Se admite tambien la cabecera milrespvertical indicada como variante. Las cabeceras no distinguen mayusculas, acentos ni espacios exteriores.

Si no hay coincidencia o falta algun componente de la clave, los cuatro campos de responsables quedan vacios. Los duplicados identicos no multiplican filas. Si una pareja de proyecto-empresa tiene datos contradictorios en Responsables, esos cuatro campos quedan vacios y se muestra un aviso. Los mails invalidos dejan solo el login vacio, conservando el resto de la fila.

Hay busqueda por login, nombre, mail o proyecto y un filtro de filas sin datos de responsables. Las exportaciones Excel y CSV contienen la tabla completa, independientemente de los filtros. Cambiar Licencias o Responsables, o sus hojas, invalida el resultado anterior.

## Maestro

Debajo del resultado de Responsables, Filtrar excel para maestro genera una segunda tabla desde el resultado completo, sin aplicar los filtros visuales de busqueda. Retira las licencias Cancelada (sin distinguir mayusculas ni espacios exteriores), conserva el orden y duplicados y muestra solo login, id_empleado, tipo de licencia, proyecto, mail, Mail Responsable Vertical, Mail Responsable Horizontal y Excluido.

Excluido es un entero: 1 para Github (solo repositorios) y 0 para el resto. Las filas con 1 se muestran en rojo y permanecen en el maestro. Exportar Excel maestro descarga la tabla con esos valores numericos; el color se aplica en pantalla. Reprocesar Responsables o cambiar los archivos u hojas invalida el maestro anterior.

## Checkeo Correos a Enviar

Debajo del Maestro, el boton Checkeo correos a enviar necesita el CSV de actividad cargado. Genera una tabla con login, last activity at, mail, envio (con tilde en pantalla) y motivo. Conserva todas las filas y el orden del CSV, incluso usuarios sin licencia coincidente. Cruza directamente con Licencias por el login derivado del mail; no depende de los filtros visuales ni de las filas excluidas del Maestro. No envia correos.

- Se descartan las licencias Cancelada antes del cruce. Sin coincidencia, envio NO y motivo Sin coincidencia en licencias (incluye usuarios con todas las licencias canceladas).
- Se prioriza la unica licencia Asignada. Si hay mas de una asignada para un login del CSV, se avisa, no se elige ninguna arbitrariamente y queda NO con motivo Mas de una licencia asignada. Si hay varias no canceladas sin asignada, tambien queda NO para revision.
- Github (solo repositorios) siempre queda NO con motivo Solo Repositorios. Los demas estados distintos de Asignada no generan envio.
- Para Asignada, 14 dias o mas desde Last Activity At produce SI y motivo Sin actividad mas de 14 dias. Si la actividad es None, vacia o nula, se usa Fecha alta: con 14 dias o mas produce SI y motivo Aun no usado; antes queda NO sin motivo.
- El umbral se calcula por fechas de calendario UTC respecto al dia actual del servidor, incluyendo exactamente 14 dias. Last Authenticated At no interviene. Fechas ISO y fechas espanolas dia/mes/ano se interpretan separadamente; fechas futuras no activan envio y fechas invalidas quedan NO con motivo de revision.
- Las exportaciones contienen toda la tabla, incluido NO, aunque este activo Solo envio SI. Cambiar Licencias, CSV o el dia de evaluacion invalida el resultado anterior; volver a procesar Responsables tambien lo borra.

## Generar SQLs

La pestana Generar SQLs contiene dos botones y un area de texto editable para copiar la consulta y ejecutarla manualmente en la BBDD. La aplicacion no se conecta ni ejecuta SQL.

- Generar SQL Empleados reproduce la consulta estatica suministrada, incluida la fecha literal `01/01/26`. Su interpretacion depende de la configuracion de fechas de la sesion Oracle.
- Generar SQL Responsables utiliza las columnas Proyecto y Cod empresa de la hoja seleccionada en Licencias, sin filtros de estado. Elimina espacios exteriores y parejas repetidas, conserva el orden de aparicion y forma los valores `proyecto-empresa`.
- Los valores se distribuyen en clausulas IN de hasta 1000 elementos, unidas por OR. Las comillas simples de los datos se escapan como literales SQL.
- Las filas sin proyecto o empresa se omiten con un aviso. Si faltan columnas o no hay parejas completas, se muestra un error sin generar una consulta incompleta.
- Cambiar el archivo o la hoja de Licencias borra la SQL de Responsables anterior para evitar copiar una consulta obsoleta. La SQL de Empleados no depende de los archivos.

## Pruebas

```powershell
python -m unittest discover -s tests -v
```

La prueba de interfaz con datos locales necesita los archivos de entrada y se omite cuando no estan disponibles. No contiene ni publica datos personales.