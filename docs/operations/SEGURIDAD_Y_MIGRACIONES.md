# Autenticación y migraciones

## Arranque nuevo

1. Configura `DATABASE_URL` y `JWT_SECRET` de al menos 32 bytes aleatorios (por ejemplo, con un generador de secretos local). No guardes el secreto ni contraseñas en Git.
2. Para un esquema nuevo: `APP_ENV=production alembic upgrade head`. La app no crea tablas automáticamente en producción.
3. Registra las sucursales: `APP_ENV=production python scripts/seed_branches.py --empresa-id 1`. Cambia el ID para la empresa real; esta orden no asigna razones sociales a sucursales.
4. Crea el primer administrador: `APP_ENV=production python scripts/create_admin.py`; solicita usuario y contraseña sin mostrar esta última.
5. Inicia la API y entra con el formulario de la página. El token permanece solo en memoria de la pestaña; al recargar se requiere iniciar sesión de nuevo.

`JWT_SECRET` y `DATABASE_URL` deben exportarse para cada comando. Para desarrollo, sin `APP_ENV=production`, se crean las tablas de una base SQLite nueva y se registran seis sucursales de demostración, pero todavía hay que crear el administrador.

## Base SQLite de la demo anterior

Desde la raíz del proyecto ejecuta `python scripts/upgrade_demo_sqlite.py pos.db`. Solo acepta la segunda generación de esquema (con caja y clave de reintento). Primero genera `pos.db.backup-before-auth`; si ya existe, se detiene. Agrega los campos/tablas de autenticación y marca la revisión Alembic. No borres el archivo previo ni ejecutes la migración sobre la base real sin respaldo y revisión. La demo más antigua requiere una migración distinta.

## Límites de seguridad aún abiertos

- Falta revocación de sesiones, limitación de intentos de acceso, HTTPS y pruebas de despliegue.
- Los roles restringen endpoints en la API, pero no se ha hecho una auditoría completa de seguridad.
- La asignación fiscal de sucursales y razones sociales sigue pendiente.
- Turnos y cajas por cajero implementados. Los retiros/entradas solo los registra administración; falta un flujo separado de solicitud y aprobación.
- La app no está aprobada para operación productiva ni manejo de pagos reales.


## Actualización de bloques 3, 4 y 5 (30 de septiembre de 2026)

Cierra la aplicación y su proceso de servidor antes de actualizar. Desde la carpeta del repositorio en PowerShell:

```powershell
git pull
.\.venv\Scripts\python.exe scripts/migrate_local.py
.\INICIAR_LI_POS.bat
```

El iniciador también ejecuta `migrate_local.py` para una instalación existente. La migración crea un respaldo `pos.db.backup-<fecha>` antes de cambiar el esquema. Acepta revisiones Alembic conocidas o la demo anterior con clientes, traspasos y nombre histórico. Una base no reconocida se detiene sin cambiarla; no borres `pos.db` para superar el error.

La nueva revisión es `f2b3409ac871`. Conserva importes, existencias y usuarios; añade una Caja 1 por sucursal y folios a los tickets antiguos. No inventa quién operó un turno antiguo: el administrador debe cerrarlo y abrir uno nuevo a nombre del cajero. Los costos antiguos quedan en cero porque la demo anterior no registraba costo; completa los datos antes de interpretar utilidad o valuación.

Para regresar, detén el servidor, conserva la base posterior por separado y restaura el respaldo junto con el código anterior. No se permite `alembic downgrade` de esta revisión porque descartaría información nueva de compras y cajas. Se probó restauración del respaldo en un archivo separado con los importes originales.

En PostgreSQL exporta `APP_ENV=production`, `DATABASE_URL` y `JWT_SECRET`, respalda la base y ejecuta `python -m alembic upgrade head`. Las pruebas automatizadas actuales cubren SQLite, incluyendo cobros simultáneos. La concurrencia y el despliegue de PostgreSQL quedan pendientes de validación.
