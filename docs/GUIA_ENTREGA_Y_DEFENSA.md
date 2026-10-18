# Guía de entrega y defensa · Equipo 04 · Guardián Centinela

Cierre: **domingo 18 de octubre, 23:59** (PDF en AVA + tag `ep2` + imágenes `:ep2` en GHCR).
Defensa: martes 20 o jueves 22, 15 minutos, con teclado.

---

## Parte 1 · Lo que tienen que hacer ustedes (en este orden)

### 1. Crear el repositorio (lo hace un integrante, por ejemplo Oscar)

1. GitHub → New repository → nombre `guardian-centinela` → **Public** → sin README.
2. En la carpeta del proyecto (descomprimir `guardian-centinela.zip`):

```bash
git init -b main
git add README.md .gitignore .env.example
git commit -m "chore: estructura inicial"
git remote add origin https://github.com/oscarL22997/guardian-centinela.git
git push -u origin main
git switch -c dev && git push -u origin dev
```

3. **Settings → Branches → Add branch protection rule** para `main`: «Require a pull request before merging».
   (Cuando el workflow haya corrido una vez, marcar también «Require status checks to pass».)
4. **Settings → Collaborators**: agregar a los otros dos integrantes con permiso de escritura.

### 2. Antes de subir nada: poner el usuario de GitHub en `compose.yaml`

En `compose.yaml`, reemplazar `REEMPLAZAR_USUARIO_GITHUB` por el dueño del repositorio **en minúsculas**
(5 líneas). En PowerShell:

```powershell
(Get-Content compose.yaml) -replace 'REEMPLAZAR_USUARIO_GITHUB','usuario-en-minusculas' | Set-Content compose.yaml
```

### 3. Gitflow: cada integrante integra 2 PR `feat/` con su propio usuario

Cada uno clona el repo, copia **solo sus carpetas** desde el zip y sigue el ciclo:

```bash
git switch dev && git pull
git switch -c feat/NOMBRE
# copiar las carpetas indicadas, luego:
git add <carpetas> && git commit -m "feat: ..."
git push -u origin feat/NOMBRE
# GitHub: Pull request de feat/NOMBRE hacia dev -> Merge -> borrar la rama
```

Hagan los PR **en este orden** (cada uno necesita lo anterior para que el CI quede en verde):

| # | Quién | Rama | Qué copia |
|---|---|---|---|
| 1 | Sergio | `feat/datos-tratamiento` | `datos/` (crudos, preparar.py, tests, requirements.txt) |
| 2 | Oscar | `feat/ia-modelo-v1` | `servicios/ia/` (sin la carpeta `modelo/` salvo `.gitkeep`) |
| 3 | Roberto | `feat/dominio-reglas-umbrales` | `servicios/dominio/` |
| 4 | Roberto | `feat/gateway-balanceo` | `servicios/gateway/` + `compose.yaml` |
| 5 | Sergio | `feat/front-formulario` | `servicios/front/` |
| 6 | Oscar | `feat/pipeline-ci` | `.github/`, `servicios/carga/`, `herramientas/`, `docs/` |

El PR 6 trae el workflow: desde ahí cada PR corre los tests y construye las imágenes sin publicarlas.
Si quieren más historia, pueden hacer PR pequeños extra (por ejemplo `feat/docs-arc42-ep2`).

### 4. Pasar a `main` y publicar

1. PR de `dev` hacia `main` → esperar el check verde → Merge. El workflow publica `sha-xxxxxxx` y `latest`.
2. **Hacer públicas las 5 imágenes**: perfil → Packages → `gc-gateway`, `gc-front`, `gc-dominio`, `gc-ia`, `gc-carga`
   → Package settings → Change visibility → **Public**. (Si no, el `pull` falla con `denied`.)
3. Crear el tag sobre `main`:

```bash
git switch main && git pull
git tag ep2 && git push origin ep2
```

4. Esperar el workflow del tag (publica `:ep2`). Revisar que el último workflow de `main` esté en verde.

### 5. Ensayo obligatorio (en un Windows que no sea el de quien escribió el compose)

```powershell
docker image rm $(docker image ls -q "ghcr.io/*/gc-*") 2>$null
docker compose -p equipo04 pull
docker compose -p equipo04 up -d
docker compose -p equipo04 ps        # todo healthy; carga "exited (0)"
# abrir http://localhost:8080 -> Ejemplo sospechoso -> Evaluar
docker compose -p equipo04 down -v
```

### 6. Completar el documento y entregar

1. Abrir `docs/EP2_Equipo04_Martinez-Castro-Larrieu.docx` y completar:
   - **Historial de versiones**: la fila 2.0 lista las correcciones que hicimos; **ajústenla a la retroalimentación real que les dio el profesor en EP1**.
   - **Anexo C**: reemplazar `USUARIO`, `NNNNNNNNNN` (link del run verde de main) y los `@USUARIO_*` de cada integrante.
   - **Integrantes / responsabilidades** (portada) si repartieron distinto.
   - **7.2**: si su `docker stats` da números distintos a los del documento, actualicen la columna «Memoria pico medida».
   - **Anexo B**: firmar los tres.
2. Exportar a PDF con el nombre `EP2_Equipo04_Martinez-Castro-Larrieu.pdf` (capítulos 1–10 ocupan 14 páginas, límite 15).
3. Un integrante lo sube a AVA antes de las 23:59 del domingo.

---

## Parte 2 · Defensa: preguntas anunciadas y cómo responderlas con teclado

Al empezar: `docker compose -p equipo04 pull` y `docker compose -p equipo04 up -d`, abrir `http://localhost:8080`.

### IE2 (18%) · `mem_limit` de la IA

```powershell
.\herramientas\generar-carga.ps1 -N 300      # ventana 1
docker stats                                 # ventana 2: mirar equipo04-ia-1 / -2
```

- Medimos ≈ 176 MB por réplica bajo carga; el límite es **256 MB = 1,45× el pico** (7.2). CPU: 3,1 ms por predicción → una réplica de 0,5 CPU atiende ≈ 160 req/s.
- Peak del caso: 5.500/min = 92 req/s → 0,28 vCPU de IA. En AWS: **Fargate 0,5 vCPU / 1 GB × 2 tareas (una por zona) = USD 36/mes** (7.3).
- Si el límite fuera menor que el consumo: OOMKilled (código 137), Docker la reinicia y el gateway manda todo a la otra réplica.

### IE4 (22%) · detener una réplica

```powershell
docker compose -p equipo04 ps                       # equipo04-ia-1 y equipo04-ia-2
# en el front: "Enviar 30 seguidas"; mientras corre:
docker stop equipo04-ia-1
docker compose -p equipo04 logs --tail 20 gateway   # se ve upstream=...:8000 y algún "502, 200" (reintento)
docker start equipo04-ia-1
```

- El usuario no ve nada: la columna «Réplica IA» pasa a mostrar solo la otra. nginx marca la réplica caída 10 s y **reintenta la misma petición en la otra** (`proxy_next_upstream`); es seguro porque `/predict` no escribe. Medido: 0 errores en 1.500 peticiones.
- Si caen las dos: decisión con **origen = reserva** (ADR-3).
- En AWS (figura 7): tareas en dos AZ; si cae una AZ, la otra sigue; RDS Multi-AZ conmuta en 60–120 s → **RTO 1–2 min, RPO 0** (réplica síncrona). Disponibilidad 99,9% = 43,8 min/mes (8.2).

### IE6 (18%) · ruta del gateway, caída de la IA, la base y la limpieza

```powershell
docker compose -p equipo04 exec gateway cat /etc/nginx/nginx.conf   # location /api/ia/ -> upstream ia_up
docker compose -p equipo04 stop ia
curl.exe -s http://localhost:8080/api/ia/health                     # 503 {"error":"servicio_no_disponible",...}
# en el front: Evaluar -> "origen: reserva" y aviso amarillo
docker compose -p equipo04 start ia
docker compose -p equipo04 exec db psql -U centinela -c "select prediccion_id, transaccion_id, decision, origen, probabilidad, version_modelo, creado_utc from predicciones order by 1 desc limit 3;"
```

- Contrato `/predict`: entrada con monto_usd, hora_local, canal, mcc, país, velocidad, datos de usuario y dispositivo; salida `probabilidad_fraude`, `razones` (5, ordenadas por peso), `version_modelo`, `replica`. Si no cumple → 422.
- **Filas descartadas: 700** de 28.421 = 97 duplicados del sistema + 250 montos negativos (reversas) + 352 montos cero + 1 hora inexistente. Los 222 reintentos NO se borran (se marcan).
- Framework: XGBoost porque sus aportes TreeSHAP desglosan cada decisión en factores (RT8) y predice en ≈ 5 ms en CPU.

### IE8 (3%) · latencia

- El front muestra la latencia total y el desglose (BD ≈ 6–8 ms, IA ≈ 5 ms, registro ≈ 2 ms). Bajo carga: p99 80 ms a 133 req/s.
- Para bajarla a la mitad: llevar los contadores de velocidad a **Redis** (consulta O(1) < 1 ms en vez de 6 consultas SQL) — ElastiCache 2 × cache.t4g.small = USD 47/mes — y llamar a la IA por Service Connect sin pasar por el gateway.

### IE10 (6%) · qué commit está corriendo

```powershell
docker image inspect ghcr.io/oscarl22997/gc-ia:ep2 | Select-String revision
```

Con ese SHA: GitHub → buscar el commit → ver el PR `dev → main` que lo trajo y el run del workflow que publicó la imagen.
Camino: `feat/ia-modelo-v1` → PR a `dev` (tests) → PR a `main` (publica sha + latest) → tag `ep2` (publica `:ep2`).
Una imagen rota se detiene en: los tests del PR, la compuerta PR-AUC ≥ 0,70 del modelo, o `nginx -t`.

### IE9 · vocabulario

Réplica, health check (activo de Docker / pasivo de nginx), contrato, límite (`mem_limit`, `cpus`), imagen, tag, digest, zona de disponibilidad, RTO/RPO, política de reserva, modo sombra, fuga de información, split temporal.

---

## Qué NO pude hacer yo (y por qué)

- Crear el repositorio, los PR con el usuario de cada uno, el tag y publicar las imágenes: requiere sus cuentas de GitHub.
- Construir las imágenes Docker aquí: el entorno no tenía acceso a Docker Hub. Todo el código se probó fuera de contenedores
  (pruebas en verde, carga idempotente, gateway nginx con 2 réplicas y caída de una réplica). La primera ejecución del workflow
  es la que construye las imágenes: si algo falla ahí, el log dice exactamente qué.
