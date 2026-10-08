# Conteos masivos

Inventario → Conteo masivo. Captura de 1 a 100 productos por envío con motivo. Los campos vacíos se omiten; cero es conteo explícito. Filtro por nombre/SKU sólo cambia visibilidad: cantidades capturadas en filas ocultas siguen incluidas y la confirmación lo explica.

El sistema toma existencias esperadas al abrir el formulario. Antes de registrar valida empresa, sucursal, permiso count_write, productos únicos, cantidades enteras no negativas, stock esperado y reservas vigentes. Si falla una partida no aplica ninguna. Tras un conflicto se debe revisar el conteo completo contra existencias actualizadas; no reenvía automáticamente sobrescribiendo movimientos.

Transacción bajo bloqueo de sucursal y existencias ordenadas por producto. Conserva grupo durable, actor, fecha, motivo y partidas; cada producto registra InventoryCount, kardex y auditoría existentes. Añade evento count_batch_reconciled por grupo. El costo promedio registrado no cambia; sobrantes sin costo previo requieren revisión de valoración.

API POST /api/stock/counts/batch con Idempotency-Key. Payload branch_id, reason y items (product_id, expected, counted). Reintento con misma clave y datos, en cualquier orden de partidas, devuelve el grupo original. Cambiar cantidades, motivo, sucursal o conjunto de productos con esa clave da conflicto. El conteo físico es manual; todavía no admite carga CSV, borrador persistido ni captura offline.

Migración 704abd5278c9 crea tabla vacía de grupos. Los conteos anteriores permanecen intactos. Detener servidor, ejecutar scripts/migrate_local.py y reiniciar. Pruebas cubren permisos, reversión completa ante errores, duplicados, reintentos, reservas y concurrencia.
