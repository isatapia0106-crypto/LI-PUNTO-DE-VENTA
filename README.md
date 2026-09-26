# LI Punto de Venta

Base funcional de POS inspirada en los módulos y el stack documentados para TPN. El código fuente privado original de TPN no estaba disponible: **no es una copia literal**.

## Probar sin Docker

```bash
cd LI-PUNTO-DE-VENTA
python -m venv .venv
# Windows: .venv\Scripts\activate   |   Mac/Linux: source .venv/bin/activate
pip install -r backend/requirements.txt
python scripts/create_admin.py
uvicorn backend.app.main:app --reload
```

Abrir http://localhost:8000. Por defecto usa SQLite local en `pos.db`. Para PostgreSQL: `docker compose -f infrastructure/docker-compose.yml up --build`; Docker requiere virtualización habilitada. API en `/docs`.

## Módulos y alcance

Se conserva el árbol ya creado en GitHub: `backend/app/api`, `core`, `db`, `services`, `integrations`; `frontend/public` y `frontend/src/features`; `desktop`, `database`, `infrastructure`, `docs`, `scripts` y `tests`. Se reservan carpetas para ventas, caja, inventario, productos, clientes, proveedores, compras, devoluciones, traspasos, cotizaciones, facturación, reportes, usuarios, auditoría, configuración, Clip y sucursales. **Actualmente funcionan catálogo, existencias por sucursal, kardex básico, apertura/cierre de caja, retiro, venta con clave de reintento, historial, resumen y registro de auditoría.** Los demás módulos siguen pendientes.

Demo: seis sucursales configuradas para la empresa de prueba 1, usuarios con contraseña Argon2 y sesión JWT, precios antes de IVA 16%, sin procesamiento real de pagos. En producción faltan revocación y límites de intentos de inicio de sesión, pruebas de concurrencia PostgreSQL, folios fiscales, caja por cajero, facturación CFDI/PAC, Clip y modo offline con sincronización. La clave de reintento actual solo cubre ventas en línea. Las rutas de operación exigen autenticación y permisos; aún no está autorizada para ventas reales. Consulta `docs/operations/SEGURIDAD_Y_MIGRACIONES.md`.

## Pruebas

`python -m pytest -q tests` desde raíz. Cada venta descuenta existencias y crea log dentro de la misma transacción. PostgreSQL usa bloqueos de fila para cobros simultáneos. No se confirman ventas con stock insuficiente ni pagos insuficientes.

## Nota de actualización

El esquema cambió. Si tienes un `pos.db` de la demo anterior, **consérvalo** y sigue `docs/operations/SEGURIDAD_Y_MIGRACIONES.md` para migrarlo con respaldo. Alembic instala el esquema nuevo, pero no convierte automáticamente una demo antigua.

Consulta `docs/operations/ESTADO_Y_PLAN.md` para el alcance real y los siguientes módulos.
