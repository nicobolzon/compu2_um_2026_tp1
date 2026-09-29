# TP2 - Primer avance

Este directorio contiene un avance basado en los ejercicios de las clases 19 y 20.
La consigna oficial del TP2 todavia no esta publicada. Esta API valida y guarda
tareas en memoria, pero aun no las ejecuta ni tiene cola o workers. Las tareas
registradas se pierden al reiniciar el servidor; se debe usar un solo worker.

## Ejecutar en Windows (PowerShell)

Desde este directorio:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app:app --reload
```

Abrir <http://127.0.0.1:8000/docs> para probar la API.

## Probar

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

## Alcance actual

- `POST /tareas`: crear una tarea pendiente de tipo `descargar`, `hashear` o `esperar`.
- `GET /tareas`: listar las tareas, con filtro `estado` y `limite`.
- `GET /tareas/{id}`: consultar una tarea.
- `DELETE /tareas/{id}`: eliminar una tarea.
- `GET /estadisticas`: contar tareas pendientes.

La cola, la ejecucion asincronica, el almacenamiento compartido y los detalles
definitivos se decidiran cuando la catedra publique la consigna.
