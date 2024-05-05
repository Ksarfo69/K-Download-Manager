import asyncio
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.middlewares import log_request
from app.schemas import KDMSettingsPayload, DownloadFileStateResponse, DownloadRequest
from app.services.download_service import kdm

router = APIRouter(prefix="/api", dependencies=[Depends(log_request)])


@router.get("/history", status_code=200)
async def history(in_progress: bool = False, start: int = None, limit: int = 10):
    r = await kdm.get_history(in_progress=in_progress, start=start, limit=limit)
    return r


@router.post("/download", status_code=200)
async def download(p: DownloadRequest) -> DownloadFileStateResponse:
    r = await kdm.add(p.url)
    return r


@router.post("/resume/{f_id}", status_code=204)
async def resume(f_id: str):
    ...


@router.post("/pause/{f_id}", status_code=204)
async def pause(f_id: str):
    ...


@router.delete("/delete/{f_id}", status_code=204)
async def delete(f_id: str):
    ...


@router.get("/preferences", status_code=200)
async def get_preferences():
    r = await kdm.get_preferences()
    return r


@router.patch("/preferences", status_code=204)
async def update_preferences(preferences: KDMSettingsPayload):
    await kdm.update_preferences(preferences)


@router.get("/events", status_code=200)
async def get_events():
    async def event_generator():
        while True:
            events = await kdm.get_download_state_events()

            if events:
                s = json.dumps(events)
                yield s

            await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
