# Asistente LI

Botón «Asistente LI» en toda la plataforma. Requiere sesión y usa la sucursal seleccionada. Primera versión local con herramientas de consulta y clasificación de frases; no es un modelo generativo ni necesita clave/API externa. No realiza ventas, reembolsos, cierres, cambios de inventario ni consultas SQL libres.

Consultas disponibles:
- «ventas de hoy», «ventas de ayer», «ventas del 2026-10-01 al 2026-10-06». Permiso de reportes; mismos importes y reglas del reporte financiero. Fechas de México, máximo 366 días. Sin fechas se consulta hoy; para mes/semana/histórico pide intervalo exacto.
- «productos bajo mínimo». Permiso inventario o reportes; sólo productos con mínimo configurado.
- «buscar producto café» o «buscar SKU». Catálogo autorizado de la sucursal; nombre, SKU y código de barras. Precio según configuración fiscal; existencias físicas no descuentan las reservas de pago.
- «turnos de caja». Permisos existentes; cajero consulta únicamente sus turnos. Revisa hasta 100 turnos recientes y muestra abiertos.
- «cómo devolver un ticket», «cómo cerrar caja», «ayuda». Orientación con permisos específicos.

API POST /api/assistant/chat: branch_id entero positivo, message de 2 a 600 caracteres; rechaza campos adicionales. Respuesta incluye fecha de consulta, sucursal, fuente de datos y hasta 20 resultados con indicador de truncamiento. Reutiliza autorización por empresa, sucursal y rol en servidor. No guarda conversaciones ni envía datos a terceros. El historial de pantalla se borra al cambiar sucursal o cerrar sesión, con descarte de respuestas en tránsito. Historial limitado a 24 entradas.

Las frases no compatibles piden reformular. Las respuestas no representan autorización para operar ni confirmación bancaria. No proporciona credenciales. Futuro: proveedor generativo opcional con herramientas controladas, límites de gasto y revisión del contexto enviado; no está habilitado en esta versión.
