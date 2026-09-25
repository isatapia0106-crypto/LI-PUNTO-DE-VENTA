# LI Punto de Venta

Base funcional de POS inspirada en los módulos y el stack documentados para TPN. El código fuente privado original de TPN no estaba disponible: **no es una copia literal**.

## Probar sin Docker

```bash
cd LI-PUNTO-DE-VENTA
python -m venv .venv
# Windows: .venv\Scripts\activate   |   Mac/Linux: source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload
```

Abrir http://localhost:8000. Por defecto usa SQLite local en `pos.db`. Para PostgreSQL: `docker compose -f infrastructure/docker-compose.yml up --build`; Docker requiere virtualización habilitada. API en `/docs`.

## Módulos y alcance

Se conserva el árbol ya creado en GitHub: `backend/app/api`, `core`, `db`, `services`, `integrations`; `frontend/public` y `frontend/src/features`; `desktop`, `database`, `infrastructure`, `docs`, `scripts` y `tests`. Se reservan carpetas para ventas, caja, inventario, productos, clientes, proveedores, compras, devoluciones, traspasos, cotizaciones, facturación, reportes, usuarios, auditoría, configuración, Clip y sucursales. **Únicamente catálogo, stock, venta, historial y registro de auditoría tienen código funcional** en este primer módulo.

Demo: sucursal 1, identidad empresa 1, precios antes de IVA 16%, sin procesamiento real de pagos. En producción falta JWT/RBAC, aislamiento de sucursal validado contra el usuario, Alembic, caja/cortes, facturación CFDI/PAC, Clip, modo offline con sincronización e idempotencia. `APP_ENV=production` bloquea operaciones mientras falte autenticación. Nunca uses la demo para ventas reales.

## Pruebas

`python -m pytest -q tests` desde raíz. Cada venta descuenta existencias y crea log dentro de la misma transacción. PostgreSQL usa bloqueos de fila para cobros simultáneos. No se confirman ventas con stock insuficiente ni pagos insuficientes.
