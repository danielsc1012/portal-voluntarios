# Portal de Voluntarios · Iglesia Northwood

Portal con contraseña para ver el riesgo de agotamiento de los voluntarios de todos los
ministerios: semanas servidas en las últimas 52, rachas sin descanso, número de equipos
(meta: máximo 2) y tendencia reciente. Fuente: Planning Center Services.

- `build.py` lee Planning Center y genera la página (sin cifrar, solo dentro del runner).
- `template.html` es el portal; el riesgo se calcula en el navegador.
- `.github/workflows/actualizar.yml` corre cada lunes, cifra la página con StatiCrypt y la publica en GitHub Pages.

Ningún dato de personas se guarda en este repositorio.

**Secretos necesarios** (Settings → Secrets and variables → Actions):
`PCO_APP_ID`, `PCO_SECRET` (Personal Access Token de Planning Center) y `PORTAL_PASSWORD`.
