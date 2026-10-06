# Mercado Pago y despliegue DigitalOcean

## Estado y alcance

Primera integración de Checkout Pro mediante Preferences API, compatible con el checkout clásico. Mercado Pago recomienda Orders API para integraciones nuevas; la ruta clásica sigue soportada. Esta implementación conserva esa ruta y no integra terminal Point ni lectura de tarjeta física.

El código genera checkouts, verifica firma HMAC de webhook, consulta el pago en la API oficial y valida cuenta receptora, empresa, MXN, importe y entorno. Sólo un pago approved puede emitir ticket integrado. Se vuelve a consultar el proveedor al confirmar. Redirecciones y datos enviados desde el navegador nunca autorizan un pago. El pago no aumenta efectivo del turno y aparece como mercado_pago en cortes y reportes.

Los cobros reales están deshabilitados por defecto. No se han utilizado credenciales reales ni desplegado contenedores en DigitalOcean. La interfaz y PostgreSQL requieren pruebas de aceptación en el servidor. Las pruebas de proveedor usan respuestas simuladas, no transacciones reales.

## Limitaciones antes de abrir cobros reales

No hay reserva de inventario durante el checkout ni ticket automático desde webhook: el cajero confirma el pago e imprime el ticket. Si el stock, precio, autorización del cajero o turno cambia, el pago se conserva para revisión y no se emite una venta inconsistente. No vuelvas a cobrar manualmente un checkout ya pagado. No crees otro checkout para un intento ambiguo; revisa el historial y la cuenta del proveedor.

La creación de preferencias guarda el intento antes de llamar a la API. Ante timeout queda creating, sin regeneración automática, para evitar enlaces duplicados. Se requiere conciliación supervisada de estos casos. Los pagos adicionales al mismo checkout, contracargos y reembolsos externos se bloquean para revisión. No existe todavía automatización de reembolsos ni recuperación completa de creación ambigua; son pendientes antes de producción sin supervisión. El historial muestra los últimos 100 checkouts.

La cuenta MP configurada pertenece a una empresa mediante MP_EMPRESA_ID. Para varias razones sociales hace falta configurar una cuenta por empresa; no se permite mezclar cuentas. No se admiten descuentos en esta primera ruta integrada. Se puede continuar con pagos manuales autorizados.

## Configurar en el servidor

1. Ten un Droplet Linux, Docker Engine con Compose y un dominio cuyo DNS apunte al servidor. En firewall expón SSH restringido a tu IP y 80/443; no publiques 5432 ni 8000.
2. Clona el proyecto en el servidor. Desde su raíz copia infrastructure/production.env.example a .env.production. Protege ese archivo y mantenlo fuera de Git.
3. Genera POSTGRES_PASSWORD hexadecimal y JWT_SECRET aleatorio. Configura DOMAIN, ACME_EMAIL y PUBLIC_BASE_URL. Las contraseñas no se incluyen en el repositorio ni en comandos de ejemplo.
4. En tu aplicación Mercado Pago configura Access Token, secreto de webhook, collector ID, MP_EMPRESA_ID y MP_MODE=test. URL de notificación: https://TU-DOMINIO/api/payments/webhook, evento payment. Usa cuentas y medios de prueba del proveedor. No pongas claves en frontend ni las compartas en el chat.

En el servidor, ejecuta desde la raíz:

```bash
docker compose --env-file .env.production -f infrastructure/compose.production.yml up -d --build
docker compose --env-file .env.production -f infrastructure/compose.production.yml ps
```

Compose inicia PostgreSQL, ejecuta migraciones, valida configuración e inicia API con usuario sin privilegios y proxy Caddy. Caddy obtiene HTTPS cuando el DNS y puertos están correctamente configurados. Si falla una migración, la API no debe arrancar. La producción no crea usuarios ni sucursales demo ni importa automáticamente tu pos.db local.

Para una instalación vacía, crea explícitamente sucursales y primer administrador:

```bash
docker compose --env-file .env.production -f infrastructure/compose.production.yml exec api python scripts/bootstrap_production.py --empresa 1 --username isata --branch Zamora --branch Zacapu
```

La contraseña se solicita oculta y se confirma. Cambia las sucursales por las reales. No ejecutes este comando para reemplazar una empresa ya operativa. La migración de datos SQLite a PostgreSQL es un trabajo separado que debe conservar IDs y movimientos; aún no está automatizada.

## Aceptación y activación

Prueba checkout aprobado, pendiente, rechazado, firma inválida, importe/cuenta/entorno distintos, doble notificación y doble confirmación. Prueba cambios de precio y stock con pago ya aprobado, cierre de turno, reembolso y conciliación. Comprueba login, roles, ventas, inventario, cortes y exportación usando PostgreSQL y prueba impresión desde los equipos.

Después de resolver los límites de conciliación y probar el flujo externo, la activación requiere credenciales de producción, MP_MODE=live y MP_LIVE_ENABLED=true. No habilites estos valores para una prueba simulada. Este documento no indica que la cuenta o sitio ya esté aprobado por Mercado Pago.

## Respaldos PostgreSQL

```bash
bash scripts/backup_postgres.sh
```

Genera dump custom de PostgreSQL, comprueba que pg_restore puede leer el catálogo y guarda SHA-256. Copia el dump y la huella a otra ubicación. Verificar el catálogo no sustituye una restauración completa: ensaya recuperación en una base aislada antes de operar. Los respaldos SQLite de Windows no respaldan este servidor. No borres volúmenes de Docker para actualizar.

## Validación local

python -m pytest tests/test_integrated_payments.py tests/test_backups.py tests/test_high_priority.py tests/test_cancel_cut.py tests/test_returns.py tests/test_operations.py tests/test_sales.py tests/test_operations_migration.py -q

Referencias oficiales: https://www.mercadopago.com.mx/developers/en/reference/online-payments/checkout-pro-preferences/overview ; https://www.mercadopago.com.mx/developers/en/docs/checkout-pro-preferences/additional-content/notifications/webhooks ; https://caddyserver.com/docs/automatic-https ; https://docs.docker.com/compose/how-tos/startup-order/ ; https://www.postgresql.org/docs/16/app-pgdump.html

## Prioridades altas: reservas y conciliación

Los checkouts nuevos reservan unidades bajo el mismo bloqueo de sucursal que las
ventas, ajustes, traspasos y conteos. Las unidades se descuentan físicamente y la
reserva se consume en una sola transacción al emitir el ticket. El precio, nombre,
unidad y tratamiento fiscal quedan congelados al crear el checkout. El costo se
registra al entregar. Los cobros anteriores a esta migración siguen sin reserva.

El botón **Consultar proveedor** consulta pagos por la referencia del checkout y
verifica cada recurso con la API; recupera aprobaciones aunque falte el webhook.
No crea otro cobro ni emite un ticket por sí solo. Los reembolsos y contracargos de
ventas entregadas quedan como incidencias persistentes visibles, sin cambiar caja,
inventario o ventas automáticamente. Múltiples pagos se marcan para revisión.

**Cancelación de reservas:** usa **Cancelar checkout**, escribe el motivo y
confirma. El sistema registra solicitante, motivo y fecha antes de contactar al
proveedor, bloquea la emisión de tickets y oculta el enlace. Vence la preferencia,
verifica mediante GET que quedó vencida, consulta los pagos y cancela los que estén
pending, in_process o authorized; después vuelve a consultar el proveedor.
Únicamente libera la reserva si todos los pagos encontrados están cancelled o
rejected y no aparece una incidencia concurrente. La cancelación repetida devuelve
el mismo resultado. No suma unidades: la reserva no había descontado inventario.

Un error, timeout, búsqueda incompleta o preferencia desconocida mantiene la
reserva; **Reintentar cancelación** retoma el proceso persistido. Si la creación
original perdió la respuesta, busca una preferencia única por external_reference;
no crea otra. Si no encuentra ninguna o encuentra varias, conserva la reserva.
Los checkouts nuevos tienen vigencia de 30 minutos; **vencer el enlace no libera
inventario automáticamente**. La liberación se ejecuta mediante el botón con las
verificaciones anteriores. No hay tarea programada de liberación.

**Pagos tardíos:** una consulta no puede garantizar que nunca llegue una aprobación
posterior. Un webhook o conciliación de un pago no terminal tras liberar la reserva
registra una incidencia durable. El checkout permanece cancelado y no puede emitir
ticket, ni reclamar inventario ya liberado. Requiere revisión y reembolso externo;
no se ejecutan reembolsos remotos ni asientos automáticos. Los estados aprobados o
las ventas entregadas no se cancelan por este flujo. Cerrar el turno antes de emitir
el ticket de un pago aprobado sigue requiriendo intervención.

La conducta de vencimiento de preferencias y cancelación de pagos debe verificarse
con Mercado Pago en una prueba controlada. Las pruebas locales simulan respuestas
del proveedor y no sustituyen esa validación.

## Validación de PostgreSQL y recuperación

El workflow `production-validation.yml` prepara PostgreSQL 16, aplica Alembic,
ejecuta las pruebas financieras e inventario contra PostgreSQL, crea un respaldo,
lo restaura en **otra base aislada**, compara todas las filas y construye la imagen.
Su resultado en GitHub debe revisarse antes de desplegar; haber añadido el workflow
no implica que haya pasado. No utiliza credenciales reales de Mercado Pago.

Para comprobar una restauración real, detén escrituras y restaura el dump en una
base separada. Configura `DATABASE_URL` con la fuente y ejecuta:

```bash
python scripts/verify_postgres_restore.py --restored-url 'postgresql+psycopg://usuario:clave@servidor/base_aislada'
```

No publiques la contraseña en el historial: usa variables de entorno locales para
construir el argumento. La comparación lee todas las filas; para bases grandes
requiere suficiente memoria. Conserva fuente y respaldo hasta terminar la revisión.
La migración de los datos locales de `pos.db` a PostgreSQL todavía requiere una
copia autorizada de la base y validación de sus datos: no está automatizada aquí.
El despliegue requiere IP, dominio y configuración privada en el servidor. Las
pruebas de pagos reales requieren cuentas de prueba del proveedor y HTTPS accesible.
