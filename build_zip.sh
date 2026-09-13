#!/usr/bin/env bash
# Empaqueta el add-on en un ZIP instalable para Kodi
# Uso: ./build_zip.sh [DIRECTORIO_ADDON]
# Ej.: ./build_zip.sh addon/script.cec.control

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ADDON_DIR_REL="${1:-addon/script.cec.control}"   # o addon/script.cec.control
ADDON_DIR="${ROOT_DIR}/${ADDON_DIR_REL}"
[ -d "$ADDON_DIR" ] || { echo "ERROR: No existe $ADDON_DIR"; exit 1; }
[ -f "$ADDON_DIR/addon.xml" ] || { echo "ERROR: Falta $ADDON_DIR/addon.xml"; exit 1; }

ADDON_PARENT="$(dirname "$ADDON_DIR")"
ADDON_NAME="$(basename "$ADDON_DIR")"
TARGET="$(dirname "$ADDON_DIR_REL")"
if [ "$TARGET" = "." ]; then
  TARGET="root"
fi
STAGING_ROOT=""
STAGED_PARENT="$ADDON_PARENT"

# Extraer id y version del addon.xml sin depender de herramientas externas
ADDON_ID=$(sed -n 's/.*<addon[^>]* id="\([^"]*\)".*/\1/p' "$ADDON_DIR/addon.xml" | head -n 1)
VERSION=$(sed -n 's/.*<addon[^>]* version="\([^"]*\)".*/\1/p' "$ADDON_DIR/addon.xml" | head -n 1)

[ -n "$ADDON_ID" ] || { echo "ERROR: No se pudo leer el id del add-on"; exit 1; }
[ -n "$VERSION" ] || { echo "ERROR: No se pudo leer la versión del add-on"; exit 1; }

DIST_DIR="${ROOT_DIR}/dist/${TARGET}"
OUT_ZIP="${DIST_DIR}/${ADDON_ID}-${VERSION}.zip"

mkdir -p "$DIST_DIR"

echo "==> Empaquetando ${ADDON_ID} v${VERSION} (${TARGET}) -> ${OUT_ZIP}"

# Limpiar residuos de compilación dentro del directorio del add-on (no toca tu working copy)
# OJO: xbmcvfs genera .pyc en runtime; evitamos incluirlos.
TMP_LIST=$(mktemp)
cleanup() {
  rm -f "$TMP_LIST"
  if [ -n "$STAGING_ROOT" ] && [ -d "$STAGING_ROOT" ]; then
    rm -rf "$STAGING_ROOT"
  fi
}
trap cleanup EXIT

# Crear lista de exclusiones para zip
cat > "$TMP_LIST" <<'EOF'
*.pyc
*__pycache__/*
*.pytest_cache/*
*.egg-info/*
*.pyo
.coverage
.*.swp
.DS_Store
.git/*
.github/*
.vscode/*
.idea/*
dist/*
EOF

# Cada addon se lleva solo lo que le corresponde. El suscriptor no recibe el
# paquete del publicador: la garantía de que no puede escribir en el remoto es
# que ese código no viaja con él, no un ajuste que alguien pueda cambiar.
if [ -d "${ROOT_DIR}/core/nextcloud_sync" ]; then
  STAGING_ROOT=$(mktemp -d)
  STAGED_ADDON_DIR="${STAGING_ROOT}/${ADDON_NAME}"
  mkdir -p "${STAGED_ADDON_DIR}/lib"
  cp -R "${ADDON_DIR}/." "${STAGED_ADDON_DIR}/"
  cp -R "${ROOT_DIR}/core/nextcloud_sync" "${STAGED_ADDON_DIR}/lib/"
  case "$ADDON_ID" in
    *.publish)
      [ -d "${ROOT_DIR}/publisher/nextcloud_publisher" ] &&
        cp -R "${ROOT_DIR}/publisher/nextcloud_publisher" "${STAGED_ADDON_DIR}/lib/"
      ;;
  esac
  STAGED_PARENT="${STAGING_ROOT}"
fi

# Crear zip. Usa 'zip' si está disponible; si no, cae a Python (sin dependencias externas).
if command -v zip >/dev/null 2>&1; then
  ( cd "$STAGED_PARENT" && zip -r -9 -q "$OUT_ZIP" "$ADDON_NAME" -x@"$TMP_LIST" )
else
  python3 - "$STAGED_PARENT" "$ADDON_NAME" "$OUT_ZIP" "$TMP_LIST" <<'PYZIP'
import fnmatch, os, sys, zipfile

parent, name, out_zip, list_path = sys.argv[1:5]
with open(list_path) as fh:
    patterns = [line.strip() for line in fh if line.strip()]

def excluded(rel):
    return any(fnmatch.fnmatch(rel, pat) for pat in patterns)

with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
    for root, dirs, files in os.walk(os.path.join(parent, name)):
        dirs.sort()
        for filename in sorted(files):
            full = os.path.join(root, filename)
            rel = os.path.relpath(full, parent)
            if excluded(rel):
                continue
            zf.write(full, rel)
PYZIP
fi

# Checksums útiles
( cd "$DIST_DIR" && sha256sum "$(basename "$OUT_ZIP")" > "$(basename "$OUT_ZIP").sha256" )

echo "OK: ${OUT_ZIP}"
echo "SHA256 en ${OUT_ZIP}.sha256"
