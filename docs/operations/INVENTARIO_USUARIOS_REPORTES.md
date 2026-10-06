# Inventario, usuarios y reportes

## Mínimos y alertas

Inventario → Mínimo configura un umbral independiente para el producto en la sucursal seleccionada. Cero desactiva la alerta. Los productos activos con existencia igual o menor al umbral aparecen en Alertas de mínimos. Se actualiza al recargar los datos después de una venta, devolución, recepción o ajuste. No envía notificaciones externas. Requiere permiso stock_write para editar.

## Usuarios

Usuarios está disponible para administración general. Permite crear, editar y desactivar usuarios, asignar roles y sucursales y cambiar contraseñas (12 a 200 caracteres). Los nombres nuevos no admiten espacios; los nombres anteriores pueden conservarse.

Cada edición revoca las sesiones de ese usuario, mediante token_version. Si te editas a ti mismo debes iniciar sesión nuevamente. No se permite desactivarse ni retirar el propio rol de administración. Se protegen los turnos abiertos antes de desactivar o cambiar rol/sucursales. El historial financiero conserva los IDs de usuarios. No se muestran hashes ni contraseñas y los cambios se auditan.

## Reportes

Reportes filtra por sucursal seleccionada, fechas inclusivas de America/Mexico_City y cajero original de la venta. Se permite hasta 366 días; más de 50,000 ventas o reembolsos requiere reducir el periodo. El permiso report controla consulta y exportación.

Ventas brutas corresponden a las ventas emitidas en el periodo. Reembolsos incluyen devoluciones y cancelaciones registradas en el periodo aunque su venta sea anterior. Total neto es bruto menos esos reembolsos. Las unidades netas también descuentan devoluciones en su fecha de registro. Pueden resultar importes o unidades negativos en periodos con más devoluciones que ventas.

Utilidad estimada = ingreso sin impuestos menos costo histórico vendido. El costo se revierte al reintegrar unidades; una devolución sin reintegro conserva el costo como pérdida. El reporte indica partidas vendidas sin costo registrado y no calcula gastos operativos. Los registros antiguos sin desglose tienen importes estimados por sus datos originales.

Descargar Excel genera un XLSX con resumen, movimientos y productos; protege los textos almacenados contra fórmulas. Imprimir / guardar PDF abre el comprobante; pulsa Imprimir y selecciona Guardar como PDF en el navegador.

## Actualizar y validar

Detén el servidor, ejecuta git pull e INICIAR_LI_POS.bat. Se instala openpyxl/tzdata y la migración respalda pos.db, conserva costos y contraseñas y añade mínimos en cero y versiones de sesión en cero. Recarga Ctrl+F5 y vuelve a iniciar sesión.

python -m pytest tests/test_high_priority.py tests/test_cancel_cut.py tests/test_returns.py tests/test_operations.py tests/test_sales.py tests/test_operations_migration.py -q

Pruebas SQLite de umbrales y sucursales, usuarios/permisos/turnos/revocación, fechas y reembolsos, utilidad, Excel y migración. Validación visual del navegador y validación PostgreSQL pendientes antes de producción.
