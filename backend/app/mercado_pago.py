"""Checkout Pro preferences adapter: secrets only in backend environment."""
import hashlib
import hmac
import os
import re
import httpx
from fastapi import HTTPException


def settings():
    token=os.getenv('MP_ACCESS_TOKEN',''); secret=os.getenv('MP_WEBHOOK_SECRET','')
    url=os.getenv('PUBLIC_BASE_URL','').rstrip('/')
    collector=os.getenv('MP_COLLECTOR_ID',''); company=os.getenv('MP_EMPRESA_ID','')
    if not all((token,secret,url,collector,company)) or not url.startswith('https://'):
        raise HTTPException(503,'Mercado Pago no está configurado: requiere credenciales y dominio HTTPS')
    live=os.getenv('MP_MODE','test')=='live'
    if live and os.getenv('MP_LIVE_ENABLED')!='true':
        raise HTTPException(503,'Los cobros reales están deshabilitados')
    return {'token':token,'secret':secret,'url':url,'collector':collector,'company':int(company),'live':live}


def call(method,path,payload=None,key=None):
    config=settings()
    headers={'Authorization':'Bearer '+config['token']}
    if key:headers['X-Idempotency-Key']=key
    try:
        with httpx.Client(timeout=10,follow_redirects=False) as client:
            response=client.request(method,'https://api.mercadopago.com'+path,json=payload,headers=headers)
        if response.status_code>=400:
            raise HTTPException(502,'Mercado Pago no confirmó la operación; consulta el estado antes de reintentar')
        return response.json()
    except (httpx.HTTPError,ValueError):
        raise HTTPException(502,'No se pudo consultar Mercado Pago; conserva la operación pendiente')


def verify_signature(signature,request_id,data_id):
    config=settings()
    if not signature or not request_id or not data_id or len(signature)>512 or len(request_id)>200:
        raise HTTPException(401,'Firma de notificación inválida')
    parts={}
    for part in signature.split(','):
        if '=' in part:
            k,v=part.strip().split('=',1);parts[k]=v
    if not parts.get('ts','').isdigit() or not re.fullmatch('[0-9a-fA-F]{64}',parts.get('v1','')):
        raise HTTPException(401,'Firma de notificación inválida')
    manifest=f'id:{data_id.lower()};request-id:{request_id};ts:{parts["ts"]};'
    digest=hmac.new(config['secret'].encode(),manifest.encode(),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(digest,parts['v1'].lower()):
        raise HTTPException(401,'Firma de notificación inválida')
