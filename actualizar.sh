#!/bin/bash
set -e

echo "=========================================="
echo "  🚀 Actualizando Gestor de Finanzas"
echo "=========================================="

REPO_URL="https://github.com/Raul515/GestorFinanzas"
BRANCH="${1:-develop}"

# Comprobar si existe Git y el directorio .git
if command -v git >/dev/null 2>&1 && [ -d .git ]; then
    echo "📦 Actualizando código vía Git..."
    git fetch origin "$BRANCH"
    git reset --hard "origin/$BRANCH"
else
    echo "📥 Descargando última versión desde GitHub (${BRANCH})..."
    curl -sL "${REPO_URL}/archive/refs/heads/${BRANCH}.tar.gz" | tar -xz --strip-components=1
fi

echo "🔄 Reconstruyendo contenedores Docker..."
docker compose -f docker_local/docker-compose.yml -f docker_local/docker-compose.extend.yml up -d --build

echo "=========================================="
echo "  ✅ ¡Aplicación actualizada y lista!"
echo "=========================================="
