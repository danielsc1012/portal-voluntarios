"""Genera index.html del Portal de Voluntarios de Northwood a partir de Planning Center Services.

Lee TODOS los tipos de servicio, sus planes de las últimas 52 semanas (y las próximas 6),
quién fue programado en cada plan (equipo, posición y estado) y la lista de miembros de
cada equipo. El riesgo de agotamiento se calcula en el navegador (template.html), así los
umbrales se pueden ajustar sin volver a correr esto.

Credenciales: variables de entorno PCO_APP_ID y PCO_SECRET (Personal Access Token).
Salida: index.html SIN cifrar. El workflow lo cifra antes de publicarlo; nunca se commitea.
"""
import base64, json, os, sys, time, urllib.error, urllib.request
from datetime import date, datetime, timedelta, timezone

API = "https://api.planningcenteronline.com/services/v2"
WEEKS_BACK = 52
WEEKS_AHEAD = 6
# Posiciones/equipos que no son servicio real (p. ej. "Leaders": placeholder para que los pastores vean los planes)
EXCLUDE = {"leaders"}
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("PORTAL_OUT", os.path.join(HERE, "index.html"))

TOKEN = base64.b64encode(f"{os.environ['PCO_APP_ID']}:{os.environ['PCO_SECRET']}".encode()).decode()
_calls = 0


def get(url, allow_404=False):
    global _calls
    if not url.startswith("http"):
        url = API + url
    for attempt in range(8):
        req = urllib.request.Request(url, headers={"Authorization": f"Basic {TOKEN}", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                _calls += 1
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(int(e.headers.get("Retry-After", "20")) + 1)
                continue
            if e.code >= 500:
                time.sleep(5 * (attempt + 1))
                continue
            if e.code in (403, 404) and allow_404:
                return None
            raise
        except urllib.error.URLError:
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"No se pudo leer {url}")


def paginate(path, allow_404=False):
    url = path
    while url:
        j = get(url, allow_404)
        if j is None:
            return
        yield j
        url = j.get("links", {}).get("next")


def rel_id(obj, name):
    return ((((obj.get("relationships") or {}).get(name) or {}).get("data")) or {}).get("id")


MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def main():
    today = datetime.now(timezone(timedelta(hours=-5))).date()
    week0 = today - timedelta(days=(today.weekday() + 1) % 7)       # domingo de esta semana
    start = week0 - timedelta(weeks=WEEKS_BACK - 1)                  # domingo de hace 51 semanas
    end = week0 + timedelta(weeks=WEEKS_AHEAD + 1) - timedelta(days=1)

    # ---- tipos de servicio ----
    st_ids, st_names = [], []
    for page in paginate("/service_types?per_page=100"):
        for s in page["data"]:
            st_ids.append(s["id"])
            st_names.append(s["attributes"]["name"].strip())
    st_index = {sid: i for i, sid in enumerate(st_ids)}
    print(f"Tipos de servicio: {len(st_ids)}")

    # ---- equipos ----
    teams, team_index = [], {}

    def team_idx(tid, name=None, st=None, archived=False):
        if tid not in team_index:
            team_index[tid] = len(teams)
            teams.append([name or "Equipo", st_index.get(st, -1), 1 if archived else 0])
        return team_index[tid]

    for page in paginate("/teams?per_page=100&include=service_type"):
        for t in page["data"]:
            a = t["attributes"]
            team_idx(t["id"], (a.get("name") or "Equipo").strip(), rel_id(t, "service_type"), bool(a.get("archived_at")))
    print(f"Equipos: {len(teams)}")

    # ---- personas ----
    people, person_index = [], {}

    def person_idx(pid, name):
        if pid not in person_index:
            person_index[pid] = len(people)
            people.append([name.strip(), []])
        return person_index[pid]

    # ---- planes y programaciones ----
    assigns, nplans = [], 0
    for sid in st_ids:
        si = st_index[sid]
        url = f"/service_types/{sid}/plans?filter=after&after={start.isoformat()}&order=sort_date&per_page=100"
        for page in paginate(url, allow_404=True):
            done = False
            for p in page["data"]:
                sd = (p["attributes"].get("sort_date") or "")[:10]
                if not sd:
                    continue
                d = date.fromisoformat(sd)
                if d > end:
                    done = True
                    break
                if d < start:
                    continue
                nplans += 1
                off = (d - start).days
                seen = set()
                for mp in paginate(f"/service_types/{sid}/plans/{p['id']}/team_members?per_page=100"):
                    for m in mp["data"]:
                        a = m["attributes"]
                        pid = rel_id(m, "person")
                        if not pid or not a.get("name"):
                            continue
                        if (a.get("team_position_name") or "").strip().lower() in EXCLUDE:
                            continue
                        tid = rel_id(m, "team")
                        if tid and tid in team_index and teams[team_index[tid]][0].strip().lower() in EXCLUDE:
                            continue
                        ti = team_idx(tid, None, sid) if tid else -1
                        st = (a.get("status") or "U")[:1].upper()
                        if st not in "CUD":
                            st = "U"
                        pi = person_idx(pid, a["name"])
                        key = (pi, ti)
                        if key in seen:      # misma persona, mismo equipo, mismo plan (varias posiciones)
                            continue
                        seen.add(key)
                        assigns.append([pi, off, ti, st, si])
            if done:
                break
        print(f"  {st_names[si]}: listo ({nplans} planes acumulados)")

    # ---- quién está en la lista de cada equipo (aunque no lo programen) ----
    for tid, ti in list(team_index.items()):
        if teams[ti][2]:
            continue
        for page in paginate(f"/teams/{tid}/people?per_page=100", allow_404=True):
            for pr in page["data"]:
                pi = person_index.get(pr["id"])
                if pi is None:
                    continue    # solo nos interesa quien ha sido programado en el periodo
                if ti not in people[pi][1]:
                    people[pi][1].append(ti)

    data = {
        "gen": today.isoformat(), "start": start.isoformat(), "week0": week0.isoformat(),
        "weeks": WEEKS_BACK, "ahead": WEEKS_AHEAD,
        "st": st_names, "teams": teams, "p": people, "a": assigns,
    }
    updated = f"{today.day} de {MESES[today.month - 1]} de {today.year}"
    with open(os.path.join(HERE, "template.html"), encoding="utf-8") as f:
        tpl = f.read()
    html = tpl.replace("__UPDATED__", updated).replace(
        "__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"))
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"index.html generado: {len(people)} personas, {nplans} planes, {len(assigns)} programaciones, {_calls} consultas.")
    if not people:
        sys.exit("No se encontró a nadie programado: revisa las credenciales o los permisos del token.")


if __name__ == "__main__":
    main()
