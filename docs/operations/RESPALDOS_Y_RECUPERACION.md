# Respaldos y recuperación local

El iniciador Windows crea un respaldo verificado antes de abrir el servidor. El respaldo incluye la base SQLite completa: usuarios y hashes, ventas, caja, inventario y auditoría. Cada copia contiene un archivo `.db` y un manifiesto `.json` con fecha UTC, versión de esquema, conteos y SHA-256. No incluye código, configuración, documentos externos ni bases PostgreSQL.

## Crear y consultar

Desde la carpeta del proyecto en PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts/local_backups.py create
.\.venv\Scripts\python.exe scripts/local_backups.py list
```

Se guardan en `backups/`. Las copias no se eliminan automáticamente. Copia periódicamente ambos archivos a otro disco o una ubicación de respaldo con acceso restringido. Una copia en el mismo disco no protege contra pérdida del equipo. Git ignora respaldos y archivos WAL; no los subas como código.

Puedes verificar una copia sin restaurarla:

```powershell
.\.venv\Scripts\python.exe scripts/local_backups.py verify "backups\LI-POS-FECHA.db"
```

Reemplaza FECHA por el nombre que muestra list. El manifiesto detecta cambios accidentales; no es una firma digital ni prueba de autenticidad contra alguien que modifique ambos archivos.

## Restaurar

1. Detén el servidor usando `Stop-Process -Id NUMERO` con el identificador que mostró el inicio. Cierra cualquier otro proceso que use pos.db. No registres ventas durante la recuperación.
2. Consulta y verifica la copia que quieres recuperar.
3. Ejecuta el comando siguiente reemplazando el nombre:

```powershell
.\.venv\Scripts\python.exe scripts/local_backups.py restore "backups\LI-POS-FECHA.db" --server-stopped
```

4. El script muestra destino y respaldo. Escribe RESTAURAR únicamente si quieres sustituir los datos actuales por los de esa fecha. Las operaciones posteriores al respaldo dejarán de aparecer.
5. Conserva la copia previa que imprime el script. Inicia INICIAR_LI_POS.bat; verificará y migrará el esquema si corresponde. Inicia sesión nuevamente.

La herramienta bloquea restauración si el puerto local 8000 está activo. Esto no detecta servidores en otros puertos ni otros procesos: --server-stopped es tu declaración de que los detuviste. Se utiliza la API de backup de SQLite, sin borrar archivos WAL ni sustituir archivos abiertos. Antes de modificar una base existente se conserva una copia verificada; si la base actual está corrupta, el proceso se detiene. Conserva la base corrupta y sus archivos laterales y restaura hacia una ruta nueva para revisar, sin borrar evidencia.

Para una prueba aislada puedes usar un destino nuevo:

```powershell
.\.venv\Scripts\python.exe scripts/local_backups.py --database "recuperacion_prueba.db" restore "backups\LI-POS-FECHA.db" --server-stopped
```

Las opciones --database y --directory se colocan antes del comando. Los respaldos creados automáticamente por migraciones antiguas no tienen este manifiesto y no se restauran con esta herramienta. Conserva esas copias para una recuperación supervisada.

## Validación

python -m pytest tests/test_backups.py -q

Pruebas aisladas de recuperación exacta, copia previa, modificación detectada por SHA-256, confirmación requerida, WAL confirmado, bases ajenas/corruptas y comandos create/list/verify. Falta comprobar el iniciador PowerShell en la máquina Windows y realizar una prueba con una copia de los datos reales.
