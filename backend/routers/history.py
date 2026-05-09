"""Transcript history endpoints."""

from fastapi import APIRouter, HTTPException

from backend.history import HistoryStore, Transcript

router = APIRouter()
_store: HistoryStore | None = None


def _get_store() -> HistoryStore:
    global _store
    if _store is None:
        _store = HistoryStore()
    return _store


@router.get("/", response_model=list[Transcript])
def list_history(
    limit: int = 50, offset: int = 0, search: str = ""
) -> list[Transcript]:
    return _get_store().list(limit=limit, offset=offset, search=search)


@router.delete("/{transcript_id}")
def delete_entry(transcript_id: int) -> dict:
    ok = _get_store().delete(transcript_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Not found")
    return {"deleted": transcript_id}


@router.delete("/")
def clear_history() -> dict:
    _get_store().clear()
    return {"status": "cleared"}
