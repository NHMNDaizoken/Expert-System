from fastapi import APIRouter, Query

from backend.services.graph_service import GraphService


router = APIRouter(prefix="/api", tags=["graph"])


@router.get("/graph")
def graph():
    service = GraphService()
    try:
        return service.get_graph()
    finally:
        service.close()


@router.get("/graph/search")
def graph_search(q: str = Query("", min_length=0)):
    service = GraphService()
    try:
        return service.search_graph(q)
    finally:
        service.close()


@router.get("/graph/faults")
def graph_faults(
    q: str = Query("", min_length=0),
    limit: int = Query(200, ge=1, le=500),
):
    service = GraphService()
    try:
        return service.list_faults(q, limit)
    finally:
        service.close()


@router.get("/graph/fault/{fault_id}")
def fault_graph(fault_id: str):
    service = GraphService()
    try:
        return service.get_fault_graph(fault_id)
    finally:
        service.close()


@router.get("/graph/stats")
def graph_stats():
    service = GraphService()
    try:
        return service.get_stats()
    finally:
        service.close()
