"""HTTP API, mounted at /api/v1."""

from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from rvb_ai import __version__
from rvb_ai.audio import AudioError
from rvb_ai.safety import CATEGORIES

from .engine import Engine
from .security import require_admin

router = APIRouter(prefix="/api/v1")
admin = [Depends(require_admin)]

SPEAKER_RE = re.compile(r"^[A-Za-z0-9 _-]{1,32}$")
QUALITY_MESSAGES = {
    "too_short": "The recording is too short. Please say the whole phrase.",
    "too_quiet": "The recording is too quiet. Please move closer to the microphone.",
    "too_loud": "The recording is too loud. Please move a little away from the microphone.",
}


def engine(request: Request) -> Engine:
    return request.app.state.engine


async def read_upload(request: Request, audio: UploadFile) -> bytes:
    limit = request.app.state.settings.max_upload_bytes
    data = await audio.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, "Recording is too large.")
    return data


def check_speaker(speaker: str) -> str:
    speaker = speaker.strip()
    if not SPEAKER_RE.match(speaker):
        raise HTTPException(422, "Speaker label: 1-32 letters, numbers, spaces, '-' or '_'.")
    return speaker


class NewPhrase(BaseModel):
    english: str = Field(min_length=1, max_length=120)
    category: Literal["general", "health", "legal", "emergency"]

    @field_validator("english")
    @classmethod
    def printable(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v or not v.isprintable():
            raise ValueError("English text must be printable")
        return v


@router.get("/health")
def health():
    return {"status": "ok", "version": __version__}


@router.get("/auth/check", dependencies=admin, status_code=204)
def auth_check():
    return Response(status_code=204)


@router.get("/phrases")
def list_phrases(request: Request):
    return {"categories": list(CATEGORIES), "phrases": engine(request).phrase_list()}


@router.post("/phrases", dependencies=admin, status_code=201)
def add_phrase(request: Request, body: NewPhrase):
    return engine(request).add_phrase(body.english, body.category).to_dict()


@router.delete("/phrases/{phrase_id}", dependencies=admin)
def delete_phrase(request: Request, phrase_id: str):
    e = engine(request)
    p = e.phrases().get(phrase_id)
    if p is None:
        raise HTTPException(404, "Unknown phrase.")
    if not p.custom:
        raise HTTPException(409, "Starter phrases cannot be deleted. Delete their takes instead.")
    return {"deleted_takes": e.delete_phrase(phrase_id)}


@router.get("/takes", dependencies=admin)
def list_takes(request: Request):
    return {"takes": engine(request).storage.takes()}


@router.post("/takes", dependencies=admin, status_code=201)
async def add_take(
    request: Request,
    audio: UploadFile = File(...),
    kind: Literal["teach", "test"] = Form(...),
    speaker: str = Form(...),
    phrase_id: str = Form(""),
    note: str = Form("", max_length=200),
):
    e = engine(request)
    speaker = check_speaker(speaker)
    pid = phrase_id or None
    if pid is not None and pid not in e.phrases():
        raise HTTPException(404, "Unknown phrase.")
    if kind == "teach" and pid is None:
        raise HTTPException(422, "Teach takes need a phrase.")
    data = await read_upload(request, audio)
    try:
        return e.add_take(data, pid, kind, speaker, " ".join(note.split()))
    except AudioError as exc:
        msg = QUALITY_MESSAGES.get(str(exc), str(exc))
        raise HTTPException(422, {"code": str(exc), "message": msg}) from exc


@router.get("/takes/{take_id}/audio", dependencies=admin)
def take_audio(request: Request, take_id: str):
    e = engine(request)
    if e.storage.get_take(take_id) is None:
        raise HTTPException(404, "Unknown take.")
    return Response(e.storage.read_audio(take_id), media_type="audio/wav")


@router.delete("/takes/{take_id}", dependencies=admin)
def delete_take(request: Request, take_id: str):
    n = engine(request).delete_takes(take_id)
    if not n:
        raise HTTPException(404, "Unknown take.")
    return {"deleted": n}


@router.delete("/takes", dependencies=admin)
def delete_takes(
    request: Request,
    speaker: str | None = Query(None),
    kind: Literal["teach", "test"] | None = Query(None),
    all_: bool = Query(False, alias="all"),
):
    filters = {k: v for k, v in {"speaker": speaker, "kind": kind}.items() if v is not None}
    if not filters and not all_:
        raise HTTPException(422, "Give a speaker and/or kind, or all=true.")
    return {"deleted": engine(request).delete_takes(**filters)}


@router.get("/export", dependencies=admin)
def export(request: Request):
    e = engine(request)
    data = e.storage.export_zip([p.to_dict() for p in e.phrases().values()])
    return Response(
        data,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="rvb-recordings.zip"'},
    )


@router.post("/interpret")
async def interpret(request: Request, audio: UploadFile = File(...)):
    data = await read_upload(request, audio)
    try:
        result = engine(request).interpret(data)  # audio is not stored
    except AudioError as exc:
        raise HTTPException(422, {"code": "bad_audio", "message": str(exc)}) from exc
    if result["status"] in QUALITY_MESSAGES:
        result["message"] = QUALITY_MESSAGES[result["status"]]
    return result
