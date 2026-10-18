# Guardián Centinela · Kipu Pagos (Caso 3) · Equipo 04

Detección de fraude en línea, explicable y auditable. Primera versión de la arquitectura (EP2),
corriendo completa en contenedores.

## Levantar el sistema (defensa)

```powershell
docker compose -p equipo04 pull
docker compose -p equipo04 up -d
# abrir http://localhost:8080
```

Al terminar: `docker compose -p equipo04 down -v`

## Piezas

| Servicio | Carpeta | Imagen | Qué hace |
|---|---|---|---|
| gateway | `servicios/gateway` | `gc-gateway` | nginx, único puerto (8080). `/` → front, `/api/dominio/` → dominio, `/api/ia/` → ia (2 réplicas) |
| front | `servicios/front` | `gc-front` | Formulario de evaluación, resultado con razones, últimas decisiones |
| dominio | `servicios/dominio` | `gc-dominio` | Reglas duras, velocidad, umbrales, política de reserva. Único que usa la base |
| ia | `servicios/ia` | `gc-ia` | XGBoost + TreeSHAP. `POST /predict`, `GET /health` |
| carga | `servicios/carga` | `gc-carga` | Crea el esquema y carga los datos tratados una vez, sin duplicar |
| db | — | `postgres:16-alpine` | Base con volumen `datos-pg` |

Tratamiento de datos: `datos/preparar.py` (crudos en `datos/crudos/`). Entrenamiento: `servicios/ia/entrenar.py`.
Pipeline: `.github/workflows/ci.yml`. Diagramas Mermaid: `docs/diagramas/`.


## Endpoints útiles (por el gateway)

- `POST /api/dominio/evaluar` — evalúa una transacción
- `GET /api/dominio/predicciones?limit=20` · `GET /api/dominio/predicciones/{transaccion_id}` (reproducir decisión, RF7)
- `GET /api/dominio/resumen` · `GET /api/dominio/umbrales`
- `POST /api/ia/predict` · `GET /api/ia/health` · `GET /api/ia/modelo` · `GET /api/ia/metrics`

## Medir (IE2 / IE8)

```powershell
.\herramientas\generar-carga.ps1 -N 300      # o: python herramientas/generar_carga.py --n 600 --concurrencia 10
docker stats                                 # en otra ventana
```
