# Plan de Implementación: Especificación 007 — Sistema de Observabilidad y Logs Rotativos Persistentes

Este plan técnico desglosa la implementación de la **Especificación 007** en 3 fases secuenciales estrictas. Siguiendo la gobernanza SDD (*Spec-Anchored*), cada fase requiere el 100% de pruebas automatizadas pasando y la confirmación explícita del usuario antes de iniciar la siguiente.

---

### Fase 1: Motor Central de Logging, Sanitización de Privacidad y Seguridad `.gitignore`

- **Objetivo**: Desarrollar la utilidad modular de configuración de logs con `RotatingFileHandler` (5 MB, 3 backups), el filtro de sanitización de secretos (`PrivacyFilter`) y blindar la exclusión de ficheros de log en Git.
- **Archivos a crear/modificar**:
  - `.gitignore` [MODIFICADO: asegurar explicitamente `logs/` y `*.log*`]
  - `src/backend/utils/__init__.py` [NUEVO / MODIFICADO]
  - `src/backend/utils/logging_config.py` [NUEVO: `setup_logging`, `PrivacyFilter`, variables de entorno `LOG_MAX_BYTES`, `LOG_BACKUP_COUNT`, `LOG_LEVEL`]
  - `tests/unit/test_logging_config.py` [NUEVO: suite unitaria completa]
- **Casos de Prueba a Verificar**:
  - Creación automática del directorio contenedor y fichero de log.
  - Verificación del umbral de rotación a 5 MB y conservación de hasta 3 ficheros de backup (`.log.1`, `.log.2`, `.log.3`).
  - Ofuscación efectiva de claves Gemini (`AIza...`), tokens Bearer y patrones de contraseñas (`[REDACTED]`).
  - Respeto del nivel `INFO` por defecto y capacidad de sobreescritura mediante variables de entorno.
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/unit/test_logging_config.py
  ```
- **Criterio de Aceptación**: 100% de pruebas unitarias pasando.

---

### Fase 2: Integración en Backend FastAPI y Middleware de Observabilidad

- **Objetivo**: Integrar la inicialización centralizada de logs en el arranque del backend FastAPI y registrar de forma estructurada las peticiones HTTP entrantes.
- **Archivos a crear/modificar**:
  - `src/backend/api/main.py` [MODIFICADO: inicializar `setup_logging("logs/backend.log")` y registrar middleware HTTP de latencia]
  - `tests/integration/test_logging_backend.py` [NUEVO: verificación de escritura en `logs/backend.log` al emitir requests a la API]
- **Casos de Prueba a Verificar**:
  - El servidor inicializa y escribe el evento de arranque en `logs/backend.log`.
  - Las peticiones a los endpoints REST registran método, ruta, código de estado y duración en ms sin exponer datos sensibles.
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/integration/test_logging_backend.py
  ```
- **Criterio de Aceptación**: 100% de pruebas de integración pasando.

---

### Fase 3: Integración en Frontend Streamlit y Verificación de Suite Completa

- **Objetivo**: Configurar el logging independiente para la capa de presentación en `logs/frontend.log` y verificar la integridad global del sistema.
- **Archivos a crear/modificar**:
  - `src/frontend/api_client.py` [MODIFICADO: inicializar `setup_logging("logs/frontend.log")`]
  - `tests/unit/test_sanity.py` [MODIFICADO: prueba de inicialización y sanitización en frontend]
  - `MEMORY.md` [MODIFICADO: registrar cierre de Spec 007]
  - `specs/README.md` [MODIFICADO: actualizar estado a Completada]
- **Casos de Prueba a Verificar**:
  - Comprobación de que las llamadas de `api_client.py` generan trazas en `logs/frontend.log`.
  - Verificación de que `git status -u` no rastrea ningún archivo en `logs/`.
  - Ejecución de la suite global completa sin regresiones (211+ pruebas al 100%).
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v
  ```
- **Criterio de Aceptación**: 100% de la suite global pasando sin regresiones.
