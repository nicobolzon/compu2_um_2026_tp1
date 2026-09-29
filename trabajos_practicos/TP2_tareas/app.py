"""API inicial de tareas; la ejecucion se agregara con la consigna del TP2."""

from itertools import count
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field


class TareaNueva(BaseModel):
    tipo: Literal["descargar", "hashear", "esperar"]
    prioridad: int = Field(default=1, ge=1, le=5)


class Tarea(TareaNueva):
    id: int
    estado: Literal["pendiente"] = "pendiente"


def crear_app() -> FastAPI:
    app = FastAPI(title="TP2 - Tareas", description="Primer avance: API sin workers")
    tareas: dict[int, Tarea] = {}
    ids = count(1)

    @app.post("/tareas", response_model=Tarea, status_code=201)
    async def crear(nueva: TareaNueva) -> Tarea:
        tarea = Tarea(id=next(ids), **nueva.model_dump())
        tareas[tarea.id] = tarea
        return tarea

    @app.get("/tareas", response_model=list[Tarea])
    async def listar(
        estado: Literal["pendiente"] | None = None,
        limite: int = Query(default=100, ge=1, le=100),
    ) -> list[Tarea]:
        resultado = list(tareas.values())
        if estado is not None:
            resultado = [tarea for tarea in resultado if tarea.estado == estado]
        return resultado[:limite]

    @app.get("/tareas/{tarea_id}", response_model=Tarea)
    async def obtener(tarea_id: int) -> Tarea:
        if tarea_id not in tareas:
            raise HTTPException(status_code=404, detail="No existe esa tarea")
        return tareas[tarea_id]

    @app.delete("/tareas/{tarea_id}", status_code=204)
    async def borrar(tarea_id: int) -> None:
        if tarea_id not in tareas:
            raise HTTPException(status_code=404, detail="No existe esa tarea")
        del tareas[tarea_id]

    @app.get("/estadisticas")
    async def estadisticas() -> dict[str, int]:
        return {"total": len(tareas), "pendientes": len(tareas)}

    return app


app = crear_app()
