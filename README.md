# Pedidos Anticipados · UGRPG

Tablero Streamlit con acceso mediante usuarios de PostgreSQL. El login protege
las consultas, gráficas y descargas del tablero. `tracker.py` registra la actividad
con el usuario autenticado y un identificador nuevo en cada inicio de sesión.

## Preparación

Desde esta carpeta, con Python 3.10 o posterior:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

La conexión a Firebird conserva su configuración en `.streamlit/secrets.toml`.
La conexión a PostgreSQL se configura en `.streamlit/activity_db.toml`, archivo
local excluido de Git. En una instalación nueva, copia
`.streamlit/activity_db.example.toml` con ese nombre y completa la contraseña.
En esta instalación se trasladó la configuración que tenía `tracker.py`.

## Crear el primer usuario y arrancar

```powershell
.\.venv\Scripts\python.exe manage_users.py create-user operador --name "Operador de producción"
.\.venv\Scripts\python.exe -m streamlit run app.py
```

El comando solicita la contraseña dos veces con entrada oculta; requiere un
mínimo de 12 caracteres. No existe una cuenta o contraseña predeterminada.
Crear un usuario también crea la tabla si hace falta. Para crear solamente la tabla:

```powershell
.\.venv\Scripts\python.exe manage_users.py init-db
```

Se utiliza `public.pedidos_anticipados_users` en la misma base PostgreSQL que el
registro `app_user_activity`. El historial existente no se modifica. El usuario
PostgreSQL necesita permisos de creación para `init-db` y de lectura/escritura
para autenticar y registrar actividad.

## Administrar accesos

Ejecutar desde una terminal del servidor, con acceso a la configuración local:

```powershell
.\.venv\Scripts\python.exe manage_users.py reset-password operador
.\.venv\Scripts\python.exe manage_users.py disable-user operador
.\.venv\Scripts\python.exe manage_users.py enable-user operador
```

Las contraseñas se almacenan con PBKDF2-HMAC-SHA256, 600 000 iteraciones y una
sal aleatoria. Cinco contraseñas incorrectas bloquean esa cuenta durante cinco
minutos; el bloqueo se guarda en PostgreSQL y persiste al recargar el navegador.
La sesión vence tras 30 minutos sin interacción y se verifica al interactuar de
nuevo. Desactivar la cuenta impide continuar en la siguiente interacción.
Restablecer la contraseña no cierra una sesión que ya estaba abierta; desactiva
la cuenta si necesitas revocar el acceso. Cerrar sesión borra el estado de ese
usuario. Recargar el navegador puede requerir iniciar sesión nuevamente.

Implementación basada en los [formularios de Streamlit](https://docs.streamlit.io/develop/concepts/architecture/forms)
y [PBKDF2 de Python](https://docs.python.org/3/library/hashlib.html#hashlib.pbkdf2_hmac).

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Para incluir pruebas con PostgreSQL local, después de `init-db`:

```powershell
$env:RUN_DB_TESTS = "1"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
Remove-Item Env:RUN_DB_TESTS
```

Las pruebas de base de datos insertan usuarios temporales dentro de transacciones
que se revierten al terminar; no dejan cuentas de prueba ni historial de accesos.
Las pruebas de interfaz simulan Firebird y no consultan información de producción.
