# Entrega TP1 - Monitor de Procesos y Threads

Computacion II - Universidad de Mendoza - 2026

Repositorio de entrega del TP1. El trabajo implementa un monitor interactivo de procesos y threads usando Python, Docker y lectura directa de `/proc`.

## Como ejecutarlo

Desde la raiz del repositorio:

```powershell
docker compose up --build
```

Para cerrar el monitor:

```text
q
```

## Informe y codigo del TP

- Informe completo: [trabajos_practicos/TP1_monitoreo/README.md](trabajos_practicos/TP1_monitoreo/README.md)
- Codigo principal: [trabajos_practicos/TP1_monitoreo/src](trabajos_practicos/TP1_monitoreo/src)
- Consigna: [trabajos_practicos/TP1_monitoreo/consigna.md](trabajos_practicos/TP1_monitoreo/consigna.md)
- Configuracion: [trabajos_practicos/TP1_monitoreo/config.json](trabajos_practicos/TP1_monitoreo/config.json)

## Tests

```powershell
docker compose run --rm monitor python -m unittest discover -s tests
```

Tambien se puede correr localmente desde la carpeta del TP:

```powershell
cd trabajos_practicos/TP1_monitoreo
python -m unittest discover -s tests
```

## Funcionalidades incluidas

- Recoleccion periodica de procesos desde `/proc`.
- Analizadores separados para resumen, memoria, file descriptors, threads, senales, scheduling y sistema.
- Interfaz TUI con vistas navegables, filtros, ordenamiento, pin de proceso e intervalo configurable.
- Arquitectura concurrente con `multiprocessing`, `threading`, `Queue`, `Pipe`, `Manager`, `Value` y `Array`.
- Ejecucion reproducible con Docker Compose desde Windows, Linux o macOS.
