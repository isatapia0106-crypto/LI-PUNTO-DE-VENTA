"""Validate deployment configuration without printing secrets or importing the app."""
import os
from urllib.parse import urlparse


def validate(env):
    if env.get('APP_ENV')!='production':raise ValueError('APP_ENV debe ser production')
    if not env.get('DATABASE_URL','').startswith('postgresql+psycopg://'):raise ValueError('Producción requiere PostgreSQL')
    secret=env.get('JWT_SECRET','')
    if len(secret)<48 or 'REEMPLAZAR' in secret:raise ValueError('Configura JWT_SECRET aleatorio de al menos 48 caracteres')
    public=urlparse(env.get('PUBLIC_BASE_URL',''))
    if public.scheme!='https' or not public.hostname or public.username or public.path not in ('','/'):
        raise ValueError('Configura PUBLIC_BASE_URL con el dominio HTTPS')
    if env.get('MP_MODE','test') not in ('test','live'):raise ValueError('MP_MODE debe ser test o live')
    if env.get('MP_MODE')=='live':
        if env.get('MP_LIVE_ENABLED')!='true':raise ValueError('Los cobros reales siguen deshabilitados')
        if not all(env.get(k) for k in ('MP_ACCESS_TOKEN','MP_WEBHOOK_SECRET','MP_COLLECTOR_ID','MP_EMPRESA_ID')):
            raise ValueError('Falta configuración para Mercado Pago real')
    return True

if __name__=='__main__':
    try:validate(os.environ)
    except ValueError as error:raise SystemExit(str(error))
    print('Configuración de producción verificada.')
