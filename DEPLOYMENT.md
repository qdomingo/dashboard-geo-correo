# GitHub y Heroku

## Preparacion incluida

- Procfile inicia Streamlit en 0.0.0.0 con el puerto PORT asignado por Heroku. No desactiva las protecciones CORS ni XSRF.
- .python-version selecciona Python 3.14; Heroku instala su ultima version de parche disponible.
- requirements.txt fija las versiones principales verificadas. Las dependencias transitivas las resuelve pip durante la instalacion.
- .gitignore excluye datos de entrada, Excel, CSV, secretos, entorno virtual y configuracion local del editor.
- .slugignore evita incluir esos archivos en el paquete de despliegue, tambien al conectar un repositorio externo.
- GitHub Actions ejecuta las pruebas en Linux con Python 3.14 en cada push y pull request. La prueba de datos reales se omite sin los Excel; las pruebas con datos sinteticos no necesitan archivos privados.

## Subir a GitHub

Crear un repositorio privado vacio en GitHub, sin inicializarlo con README. Desde PowerShell, en la carpeta del proyecto:

```powershell
git init
git add .
git diff --cached --name-only
```

Revisar la lista antes de continuar: no debe contener Archivos_Entrada, .venv, .env, secretos, Excel ni CSV. .gitignore no elimina archivos que ya estuvieran versionados en otro repositorio.

Los siguientes comandos se ejecutan manualmente y crean el primer commit y la rama main. Sustituir USUARIO y REPOSITORIO:

```powershell
git commit -m "Preparar aplicacion Streamlit para Heroku"
git branch -M main
git remote add origin https://github.com/USUARIO/REPOSITORIO.git
git push -u origin main
```

No escribir tokens ni contrasenas en los archivos del proyecto. Autenticarse con GitHub mediante el gestor de credenciales del equipo.

## Desplegar en Heroku

1. Crear una aplicacion Heroku. Elegir la region conforme a la politica de datos de la organizacion y un plan de pago adecuado; no hay dynos gratuitos.
2. En Settings, verificar el buildpack oficial Python (heroku/python).
3. En Settings > Config Vars, crear APP_PASSWORD con una contrasena aleatoria larga y exclusiva, de al menos 20 caracteres. Introducirla directamente en Heroku; no compartirla en el repositorio, logs o chat. DYNO y PORT los proporciona Heroku; no configurarlos manualmente.
4. En Deploy > Deployment method, elegir GitHub, autorizar la integracion y seleccionar el repositorio.
5. Seleccionar main y usar Deploy Branch. Para despliegues automaticos, activar Wait for CI to pass si esta disponible.
6. En Resources, habilitar un unico dyno web. Abrir la URL HTTPS de Heroku, comprobar el acceso y subir los archivos desde la barra lateral.

Si la integracion GitHub no esta disponible en la cuenta, utilizar Heroku CLI despues de crear la aplicacion y configurar APP_PASSWORD en su panel:

```powershell
heroku login
heroku git:remote -a NOMBRE-APP
git push heroku main
heroku ps:scale web=1 -a NOMBRE-APP
heroku open -a NOMBRE-APP
```

Esta preparacion no crea recursos de pago, no publica el codigo y no despliega nada automaticamente.

## Datos y acceso

- En Heroku no se incluyen archivos locales. El interruptor de archivos locales queda desactivado cuando no existe Archivos_Entrada; subir Empleados, Licencias, Responsables y el CSV desde la interfaz segun el proceso necesario.
- No hay almacenamiento persistente ni base de datos. El sistema de archivos del dyno es efimero; reinicios y despliegues borran sesiones y cache y obligan a subir de nuevo los datos. No guardar archivos personales en el slug.
- Los archivos y los resultados se procesan en memoria en Heroku, con cache compartida dentro del proceso. Este despliegue esta pensado para un equipo de confianza, no para aislar datos entre clientes independientes.
- El acceso usa una contrasena compartida por equipo, sin cuentas individuales, MFA ni limitacion de intentos. No sustituye un SSO corporativo o una pasarela de acceso para uso amplio. Obtener aprobacion para alojar y procesar datos personales en Heroku antes de subir datos reales.
- Sin APP_PASSWORD, Heroku bloquea el acceso. La variable tambien activa la proteccion en local. Cambiar la contrasena exige iniciar sesion de nuevo; cerrar la pestana desconecta la sesion, pero no garantiza el borrado inmediato de las caches del proceso.
- Usar HTTPS y un unico dyno web para este primer despliegue Streamlit. El estado depende de la sesion WebSocket; multiples dynos requieren disenar afinidad y almacenamiento compartido.
- Streamlit admite hasta 200 MB por archivo, pero pandas puede consumir varias veces el tamano del Excel al procesarlo. Dimensionar la memoria del dyno y verificar los archivos reales antes de abrir el acceso al equipo.

## Validacion y diagnostico

Desde un entorno con las dependencias instaladas:

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

En Heroku, revisar los logs de arranque sin imprimir datos personales ni secretos:

```powershell
heroku logs --tail -a NOMBRE-APP
```

El endpoint /_stcore/health permite comprobar que Streamlit esta arrancado; no demuestra que el acceso o los cruces funcionen. Comprobar tambien login, subida, Procesar Geografias y exportacion. La pantalla incluye estado de licencia, pero Excel y CSV de Geografias deben contener solo login y geografia.