from __future__ import annotations
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from .contracts import WEBHOOK_ROUTES, WebhookRoute
from .security import RequestValidationError
from .service import PayloadTooLargeError, accept_webhook

router=APIRouter(tags=["provider-webhooks"])
_BY_CONNECTOR={r.producer_client_id.split("-",1)[0]:r for r in WEBHOOK_ROUTES}
_BY_CONNECTOR.update({"vicidial":next(r for r in WEBHOOK_ROUTES if r.producer_client_id=="vicidial-adapter")})

async def _body(request:Request)->bytes:
    maximum=request.app.state.runtime.settings.max_request_body_bytes; raw=bytearray()
    async for chunk in request.stream():
        if len(raw)+len(chunk)>maximum: raise PayloadTooLargeError(f"request body exceeds {maximum} bytes")
        raw.extend(chunk)
    return bytes(raw)

async def _accept(request:Request,route:WebhookRoute):
    headers={k.lower():v for k,v in request.headers.items()}
    claims=await request.app.state.runtime.tokens.verify(headers.get("authorization",""),expected_client_id=route.producer_client_id,required_scope=route.required_scope)
    result,status=await accept_webhook(request.app.state.runtime,route,claims=claims,method=request.method,path=request.url.path,raw_body=await _body(request),headers=headers)
    return JSONResponse(status_code=status,content=result.model_dump(mode="json"),headers={"X-Correlation-ID":result.correlation_id})

@router.post("/v1/webhooks/{connector_id}/{endpoint_key}/{webhook_id}")
async def generic_webhook(connector_id:str,endpoint_key:str,webhook_id:str,request:Request):
    route=_BY_CONNECTOR.get(connector_id)
    if route is None or not endpoint_key or not webhook_id: raise RequestValidationError("unknown webhook connector or endpoint")
    dynamic=WebhookRoute(route.producer_client_id,route.required_scope,request.url.path,route.event_types)
    return await _accept(request,dynamic)

@router.post("/webhooks/vicidial/call-result/{webhook_id}")
async def vicidial_call_result(webhook_id:str,request:Request):
    if not webhook_id: raise RequestValidationError("webhook_id is required")
    base=_BY_CONNECTOR["vicidial"]
    return await _accept(request,WebhookRoute(base.producer_client_id,base.required_scope,request.url.path,base.event_types))

@router.post("/v1/crm/events/{webhook_id}")
@router.post("/v1/crm/delivery-results/{webhook_id}")
async def crm_event(webhook_id:str,request:Request):
    if not webhook_id: raise RequestValidationError("webhook_id is required")
    base=_BY_CONNECTOR["odoo"]
    return await _accept(request,WebhookRoute(base.producer_client_id,base.required_scope,request.url.path,base.event_types))
