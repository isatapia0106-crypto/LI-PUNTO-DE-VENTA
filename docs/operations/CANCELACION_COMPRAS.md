# Cancelación de órdenes de compra

En Proveedores y compras, administración puede cancelar las cantidades pendientes de una orden abierta o recibida parcialmente. Se exige motivo de 3 a 300 caracteres. Guarda motivo, fecha y usuario y emite evento purchase_cancelled.

La cancelación no elimina la orden ni revierte mercancía recibida. Conserva recepciones, cantidades recibidas, costo promedio, inventario e historial. Pendiente queda en cero y lo no recibido se muestra como cancelado. Una orden recibida completamente no puede cancelarse por este flujo; una devolución a proveedor aún no está implementada.

Nuevas recepciones de la orden cancelada devuelven conflicto. Un reintento de una recepción ya registrada devuelve su resultado sin duplicar inventario. Cancelar nuevamente con el mismo motivo devuelve la cancelación original; otro motivo devuelve conflicto. El responsable y fecha originales se conservan.

Recepción y cancelación comparten bloqueos de sucursal y orden. La operación que gana el bloqueo fija el estado que observará la siguiente. Permiso purchase_write en servidor, con aislamiento por empresa y sucursal.

Migración 3c06791e3485 añade campos nulos a órdenes antiguas, sin modificar existencias ni recepciones. El lanzador migra la base reconocida con respaldo; también puede ejecutarse python scripts/migrate_local.py. Quedan pendientes impuestos de compra, cuentas por pagar y devolución a proveedor.
