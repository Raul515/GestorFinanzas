# AGENTS.md — Directrices Operativas para Agentes

Este repositorio sigue la metodología **Desarrollo Guiado por Especificaciones (Spec-Driven Development - SDD)** en **modo anclado a especificaciones**. Todos los agentes que trabajen en este código deben cumplir estrictamente las normas operativas expuestas a continuación.

---

## 1. Ley Suprema: La Constitución

Antes de planificar, diseñar o escribir una sola línea de código, lee y cumple íntegramente los principios arquitectónicos, financieros y de calidad definidos en:
👉 **[docs/constitution.md](file:///c:/Users/Raul_515/Desktop/ProyectosAntigravity/GestorFinanzas/docs/constitution.md)**

Si alguna tarea, instrucción o decisión entra en conflicto con la Constitución, **detente de inmediato** y consulta al usuario.

---

## 2. Flujo Operativo Anclado a Especificaciones (SDD)

1. **Mandato de Especificaciones**:
   - Nada se implementa sin una especificación formalmente aprobada en el directorio `specs/`.
   - Si un caso borde, decisión técnica o fórmula contable no está definido en la especificación activa, **detente y pregunta** al usuario. Queda terminantemente prohibido hacer suposiciones sobre lógica financiera.
2. **Implementación Estrictamente Fase a Fase con Puerta de Confirmación**:
   - Toda especificación dividida en fases debe ejecutarse de forma estrictamente secuencial, **una sola fase a la vez**.
   - Al concluir cada fase y verificar que la totalidad de sus pruebas automatizadas pasan al 100%, el agente debe **detenerse obligatoriamente**, resumir los entregables completados y solicitar confirmación/autorización explícita al usuario antes de pasar a la siguiente fase.
   - Queda **terminantemente prohibido implementar múltiples fases de golpe** o encadenar fases consecutivas sin la validación previa del usuario.
3. **Exclusión de Carpetas de Habilidades de Terceros**:
   - Las carpetas `.agents/` y `.claude/` contienen skills y configuraciones de agentes descargadas de terceros; quedan excluidas de cualquier refactorización, traducción o modificación de idioma.

---

## 3. Política y Reglas de Pruebas Automatizadas

1. **Puerta de Calidad Obligatoria**:
   - Toda lógica desarrollada requiere que el 100% de las pruebas de la fase y de la especificación activa pasen antes de considerar completada la fase.
2. **Ámbito Acotado de Pruebas (Sin Suite Global Innecesaria)**:
   - Durante el desarrollo de cada fase, **queda prohibido ejecutar la suite global completa de pruebas del sistema**.
   - Ejecuta únicamente las pruebas de la fase recién implementada y de la especificación activa (`.\venv\Scripts\pytest -v <pruebas_de_la_spec>`), sin volver a ejecutar pruebas de componentes consolidados que no han sido tocados.
3. **Permisos de Red Local en Entornos de Prueba**:
   - Los tests de integración (`tests/integration/`) requieren acceso a red local (`localhost` / `127.0.0.1`) debido a `TestClient`.
   - Ejecutar los comandos de `pytest` fuera del sandbox restringido de red o solicitar permisos explícitos de red local, usando un timeout explícito para evitar bloqueos si un socket no responde.

---

## 4. Estrategia Git, Ramas y Seguridad Pre-Commit

1. **Estrategia de Ramas (SDD Branching Model)**:
   - **Estructura de Ramas**:
     - `main`: Rama de producción y estabilidad consolidada. Contiene exclusivamente versiones probadas y validadas en uso real por el usuario.
     - `develop`: Rama base de integración continua donde residen las especificaciones completamente concluidas y verificadas.
     - `feat/spec-XXX-nombre`: Rama de trabajo efímera que nace de `develop` para cada nueva especificación aprobada (a partir de la Spec 008).
   - **Ciclo de Vida de una Especificación**:
     1. Antes de iniciar la Fase 1 de una nueva spec, crear y cambiar a la rama efímera desde `develop`: `git checkout -b feat/spec-XXX-nombre develop`.
     2. Desarrollar, probar y commitear secuencialmente todas las fases en dicha rama.
     3. Al concluir la totalidad de las fases con el 100% de pruebas en verde, solicitar confirmación al usuario para fusionar a `develop` (`git checkout develop` + `git merge feat/spec-XXX-nombre`) y eliminar la rama efímera (`git branch -d feat/spec-XXX-nombre`).
     4. El paso de `develop` a `main` se realiza mediante *fast-forward* / *merge* atómico cuando el usuario valide en uso real las especificaciones integradas en `develop`.
2. **Protocolo Obligatorio de Seguridad Pre-Commit**:
   - Antes de cualquier commit:
     1. Ejecutar `git status -u` para inspeccionar la totalidad de archivos creados o modificados.
     2. Verificar activamente que ningún archivo en preparación (`staging`) contenga claves API, tokens, contraseñas, ficheros de entorno (`.env*`), bases de datos locales (`finanzas.db`) ni volcados de datos reales.
     3. Confirmar que los archivos temporales o sensibles queden debidamente registrados en `.gitignore` antes de ejecutar `git add` o `git commit`.
     4. Preguntar siempre al desarrollador para obtener autorización explícita; nunca realizar `commit` ni `push` sin permiso previo.
3. **Estándar de Mensajes de Commit**:
   - Utilizar *Conventional Commits* con tipo y ámbito en inglés y descripción en español (ej. `feat(scope): descripción en español`).

---

## 5. Comandos Oficiales de Verificación y Ejecución

Verifica siempre los cambios utilizando el entorno virtual local oficial (`venv`):

- **Gestión de Ramas por Especificación**:
  ```powershell
  # Crear rama para nueva spec
  git checkout -b feat/spec-XXX-nombre develop

  # Fusionar a develop al finalizar la spec
  git checkout develop
  git merge feat/spec-XXX-nombre
  ```
- **Ejecutar Pruebas de la Fase / Especificación Activa**:
  ```powershell
  .\venv\Scripts\pytest -v tests/unit/test_<modulo>.py tests/integration/test_<modulo>.py
  ```
- **Comprobación de Sintaxis Python**:
  ```powershell
  .\venv\Scripts\python -m compileall src tests
  ```
- **Iniciar Backend (FastAPI)**:
  ```powershell
  $env:PYTHONPATH="src"
  .\venv\Scripts\uvicorn backend.api.main:app --reload --port 8000
  ```
- **Iniciar Frontend (Streamlit)**:
  ```powershell
  .\venv\Scripts\streamlit run src/frontend/app.py
  ```
- **Docker Compose (Entorno Local Completo)**:
  ```powershell
  cd docker_local
  docker compose -f docker-compose.yml -f docker-compose.extend.yml up --build
  ```

---

## 6. Mantenimiento de la Memoria Persistente

Actualiza **[MEMORY.md](file:///c:/Users/Raul_515/Desktop/ProyectosAntigravity/GestorFinanzas/MEMORY.md)** siempre que:
- Se tome o refine una decisión arquitectónica o de nomenclatura.
- Se inicie o concluya una especificación o fase de desarrollo.
- Se identifiquen deudas técnicas o restricciones críticas del sistema.
