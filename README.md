# Computacion II - Trabajos practicos

Universidad de Mendoza - 2026

Este repositorio contiene el material de clase de la catedra y los trabajos practicos de la cursada.

## TP1 - Monitor de Procesos y Threads

Trabajo aprobado. Implementa un monitor interactivo de procesos y threads con Python, Docker y lectura directa de `/proc`.

Desde la raiz del repositorio:

```powershell
docker compose up --build
```

Presionar `q` para cerrar el monitor. Para ejecutar sus pruebas:

```powershell
docker compose run --rm monitor python -m unittest discover -s tests
```

El informe, la consigna y las instrucciones completas estan en [TP1_monitoreo](trabajos_practicos/TP1_monitoreo/README.md).

## TP2 - Tareas

Primer avance basado en los ejercicios de las clases 19 y 20. La consigna oficial aun no esta publicada. La API permite registrar, listar, consultar y borrar tareas, pero todavia no las ejecuta.

Para instalarlo, ejecutarlo y probarlo, ver [TP2_tareas](trabajos_practicos/TP2_tareas/README.md). La implementacion se ajustara cuando la catedra publique los requisitos definitivos.
