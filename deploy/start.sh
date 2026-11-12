#!/bin/bash
# Arranque de Odoo en Render usando DATABASE_URL (Neon PostgreSQL).
set -euo pipefail

if [ -z "${DATABASE_URL:-}" ]; then
  echo "ERROR: defina DATABASE_URL (cadena de conexión de Neon, conexión directa, no 'pooler')." >&2
  exit 1
fi

# Descompone postgresql://usuario:clave@host:puerto/basedatos?sslmode=require
eval "$(python3 - <<'PY'
import os, shlex, urllib.parse as u
p = u.urlparse(os.environ["DATABASE_URL"])
q = dict(u.parse_qsl(p.query))
vals = {
    "PGHOST": p.hostname, "PGPORT": str(p.port or 5432),
    "PGUSER": u.unquote(p.username or ""), "PGPASSWORD": u.unquote(p.password or ""),
    "PGDATABASE": p.path.lstrip("/"), "PGSSLMODE": q.get("sslmode", os.environ.get("PGSSLMODE", "require")),
}
for k, v in vals.items():
    print("export %s=%s" % (k, shlex.quote(v)))
PY
)"

CONF=/tmp/odoo.conf
cat > "$CONF" <<EOF
[options]
addons_path = /mnt/extra-addons,/usr/lib/python3/dist-packages/odoo/addons
data_dir = /tmp/odoo-data
admin_passwd = ${ODOO_MASTER_PASSWORD:-cambie-esta-clave}
db_host = ${PGHOST}
db_port = ${PGPORT}
db_user = ${PGUSER}
db_password = ${PGPASSWORD}
db_name = ${PGDATABASE}
dbfilter = ^${PGDATABASE}\$
list_db = False
proxy_mode = True
workers = 0
max_cron_threads = 0
without_demo = all
http_interface = 0.0.0.0
http_port = ${PORT:-8069}
log_level = info
EOF

EXTRA=""
if [ "${ODOO_UPDATE:-0}" = "1" ]; then
  EXTRA="-u campus_pi"   # aplica cambios del módulo en cada despliegue
fi

# -i instala el módulo sólo si aún no está instalado (primer arranque inicializa la BD)
exec odoo -c "$CONF" -d "$PGDATABASE" -i campus_pi --load-language=es_CO $EXTRA
