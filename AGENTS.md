# AGENTS.md — Directrices Operativas para Agentes

Este repositorio sigue la metodología **Desarrollo Guiado por Especificaciones (Spec-Driven Development - SDD)** en **modo anclado a especificaciones**. Todos los agentes que trabajen en este código deben cumplir estrictamente las normas expuestas a continuación.

---

## 1. Ley Suprema: La Constitución

Antes de planificar, diseñar o escribir una sola línea de código, lee y cumple íntegramente:
👉 **[docs/constitution.md](file:///c:/Users/Raul_515/Desktop/ProyectosAntigravity/GestorFinanzas/docs/constitution.md)**

Si alguna tarea, instrucción o decisión entra en conflicto con la Constitución, **detente de inmediato** y consulta al usuario.

---

## 2. Flujo Anclado a Especificaciones (Spec-Anchored)

1. **Mandato de Especificaciones**:
   - Nada se implementa sin una especificación formalmente aprobada en el directorio `specs/`.
   - Si un caso borde, decisión técnica o fórmula contable no está definido en la especificación activa, **detente y pregunta** al usuario. Queda terminantemente prohibido hacer suposiciones sobre lógica financiera.
2. **Implementación Estrictamente Fase a Fase con Puerta de Confirmación**:
   - Toda especificación dividida en fases debe ejecutarse de forma estrictamente secuencial, **una sola fase a la vez**.
   - Al concluir cada fase y verificar que la totalidad de sus pruebas automatizadas pasan al 100%, el agente debe **detenerse obligatoriamente**, resumir los entregables completados y solicitar confirmación/autorización explícita al usuario antes de pasar a la siguiente fase.
   - Queda **terminantemente prohibido implementar múltiples fases de golpe** o encadenar fases consecutivas sin la validación previa del usuario.
3. **Arquitectura Desacoplada**:
   - Los algoritmos financieros (presupuesto 50/30/20, desviaciones, cálculos de fondos de seguridad e indicadores) y las herramientas de agentes deben implementarse como servicios o funciones puras testeables bajo `src/backend/services/`.
   - La interfaz de Streamlit (`src/frontend/`) es exclusivamente una capa de presentación visual.
4. **Veracidad Cuantitativa y Ámbito Acotado de Pruebas**:
   - Prohibido simular, alucinar o falsear métricas financieras en código de producción.
   - **Ámbito Acotado de Pruebas (Sin Suite Global Innecesaria)**: Durante el desarrollo de cada fase, **queda prohibido ejecutar la suite global completa de pruebas del sistema**. Se deben ejecutar únicamente las pruebas de la fase recién implementada y las pruebas asociadas a la especificación activa (`.\venv\Scripts\pytest -v <pruebas_de_la_spec>`). No se deben volver a ejecutar pruebas de componentes consolidados que no han sido tocados.
   - Toda lógica desarrollada requiere que las pruebas de la fase y de la especificación pasen al 100% antes de considerar completada cualquier fase.
5. **Protección Patrimonial y Salvaguarda de Seguridad**:
   - **Regla innegociable**: Jamás sugerir, asignar o permitir inversiones con riesgo si el fondo de emergencia no cubre al menos 3 meses de gastos fijos esenciales.
6. **Seguridad Pre-Commit y Verificación de `.gitignore`**:
   - **Protocolo obligatorio antes de cada commit**:
     1. Ejecutar `git status -u` para inspeccionar la totalidad de archivos creados o modificados.
     2. Verificar activamente que ningún archivo nuevo o modificado contenga claves API, tokens, contraseñas, bases de datos locales (`finanzas.db`) o volcados de datos reales.
     3. Confirmar que los archivos temporales o sensibles queden debidamente registrados en `.gitignore` antes de ejecutar `git add` o `git commit`.
7. **Convenciones de Idioma y Nomenclatura (Opción 1 - Estándar Internacional)**:
   - **Código Backend, Base de Datos y API (100% en Inglés)**: Tablas, columnas, modelos SQLAlchemy, esquemas Pydantic, routers, endpoints, funciones y variables redactados en inglés (ej. `Category`, `Transaction`, `MonthlyBudget`, `EmergencyFund`, `MarketCache`, `amount`, `current_balance`, `/categories`, `/advisor/safety-status`).
   - **Interfaz de Usuario, Documentación y Explicaciones (100% en Español)**: Interfaz gráfica de Streamlit, documentación (`specs/`, `README.md`, guías), docstrings explicativos y comunicación en el chat en español.
   - **Commits en Git**: Estándar *Conventional Commits* con tipo y ámbito en inglés y descripción en español (`feat(scope): descripción en español`).
8. **Exclusión de Carpetas de Habilidades de Terceros**:
   - Las carpetas `.agents/` y `.claude/` contienen skills y configuraciones de agentes descargadas de terceros; quedan excluidas de cualquier refactorización, traducción o modificación de idioma.
9. **Observabilidad Obligatoria y Prohibición de Fallos Silenciosos (`Silent Failures`)**:
   - Queda estrictamente prohibido silenciar excepciones mediante `pass` sin registrar el fallo en un log descriptivo.
   - En clientes de red (`src/frontend/api_client.py`), servicios y controladores, se debe usar el módulo estándar `logging` con niveles adecuados (`logger.warning`, `logger.error`), registrando la URL invocada, códigos de error HTTP y el detalle del fallo.
   - Preservar la privacidad: nunca imprimir ni loguear datos sensibles (claves API, tokens o credenciales).
10. **Estrategia de Ramas en Git (SDD Branching Model)**:
    - **Estructura de Ramas**:
      - `main`: Rama de producción y estabilidad consolidada. Contiene exclusivamente versiones probadas y validadas en uso real por el usuario.
      - `develop`: Rama base de integración continua donde residen las especificaciones completamente concluidas y verificadas.
      - `feat/spec-XXX-nombre`: Rama de trabajo efímera que nace de `develop` para cada nueva especificación aprobada (a partir de la Spec 008).
    - **Ciclo de Vida de una Especificación**:
      1. Antes de iniciar la Fase 1 de una nueva spec, el agente creará y cambiará a la rama efímera desde `develop`: `git checkout -b feat/spec-XXX-nombre develop`.
      2. Todas las fases de la especificación se desarrollan, prueban y commitean secuencialmente en dicha rama.
      3. Al concluir la totalidad de las fases y pasar el 100% de las pruebas, se solicita confirmación al usuario para fusionar a `develop` (`git checkout develop` + `git merge feat/spec-XXX-nombre`) y eliminar la rama efímera (`git branch -d feat/spec-XXX-nombre`).
      4. El paso de `develop` a `main` se realiza mediante fast-forward / merge atómico cuando el usuario valide en uso real las especificaciones integradas en `develop`.
11. **Declaración Obligatoria y Paridad Estricta de Dependencias (`requirements/`)**:
    - **Regla innegociable de cero dependencias implícitas**: Siempre que una especificación, refactorización o corrección requiera una librería externa (ej. `openpyxl`, `python-multipart`, etc.) o se instale un paquete en el entorno virtual local (`venv`), **es estrictamente obligatorio registrarla de inmediato en su manifiesto correspondiente** (`requirements/backend.txt` para dependencias consumidas por `src/backend/` o `requirements/frontend.txt` para `src/frontend/`).
    - **Prohibición de suposiciones de entorno**: El entorno virtual local `venv` es compartido entre backend y frontend y puede contener dependencias transitivas (ej. `streamlit` instalando `python-multipart`). **Queda terminantemente prohibido asumir que una librería presente en `venv` existe en los contenedores aislados de Docker o en producción**.
    - **Puerta de Verificación Pre-Merge**: Antes de solicitar la aprobación de cualquier fase o fusión de rama, el agente debe auditar activamente que todos los paquetes importados en el código estén declarados en sus respectivos `requirements/*.txt`, garantizando que `docker compose up --build` y el actualizador OTA levanten sin fallos de dependencias faltantes.

---

## 3. Comandos Oficiales de Verificación y Ejecución

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

  ### Reglas de ejecución de tests
  - Los tests de integración (`tests/integration/`) requieren acceso a red local (`localhost` / `127.0.0.1`) debido a `TestClient`.
  - Ejecutar siempre los comandos de `pytest` fuera del sandbox restringido de red, o solicitar explícitamente permisos de red local (`network: host`/`local`) antes de lanzar la suite de integración.
  - Usar un timeout explícito para evitar bloqueos si un socket no responde.
  
- **Comprobación de Sintaxis Python**:
  ```powershell
  .\venv\Scripts\python -m compileall src tests
  ```
- **Iniciar Backend (FastAPI)**:
  ```powershell
  $env:PYTHONPATH="src"
  .\venv\Scripts\uvicorn backend.main:app --reload --port 8000
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

## 4. Mantenimiento de la Memoria Persistente

Actualiza **[MEMORY.md](file:///c:/Users/Raul_515/Desktop/ProyectosAntigravity/GestorFinanzas/MEMORY.md)** siempre que:
- Se tome o refine una decisión arquitectónica o de nomenclatura.
- Se inicie o concluya una especificación o fase de desarrollo.
- Se identifiquen deudas técnicas o restricciones críticas del sistema.
