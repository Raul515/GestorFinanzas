# Especificación 007: Sistema de Observabilidad y Logs Rotativos Persistentes (RotatingFileHandler Independiente)

## 1. Resumen Ejecutivo y Visión

Actualmente, el **Gestor de Finanzas Personales** implementa el Principio 13 de la Constitución mediante el uso del módulo estándar `logging` en los servicios de negocio, endpoints y cliente frontend (`logger = logging.getLogger(__name__)`), prohibiendo los fallos silenciosos (*silent failures*). Sin embargo, el sistema presenta dos limitaciones críticas:

1. **Falta de Persistencia en Disco**: Las trazas se emiten exclusivamente a la consola del proceso (`stdout`/`stderr`), perdiéndose de forma irreversible al reiniciar terminales, apagar servidores o reiniciar contenedores Docker.
2. **Mezcla de Trazas y Ausencia de Sanitización**: No existe una separación limpia entre los eventos del servidor API (FastAPI) y la capa cliente (Streamlit), y no se cuenta con un mecanismo determinista que garantice que claves de API (como `GEMINI_API_KEY`) o tokens de red queden ofuscados antes de grabarse en disco (Principios 10 y 11 de la Constitución).

Tras consultar y acordar las preferencias de diseño con el usuario, el **objetivo** de esta especificación es dotar al sistema de una arquitectura de observabilidad desacoplada y persistente en disco:
- **Ficheros Separados por Componente**: Persistencia independiente en `logs/backend.log` (para el servidor FastAPI y servicios de dominio) y `logs/frontend.log` (para la interfaz y cliente de red en Streamlit).
- **Capacidad y Rotación Acotada**: Rotación por tamaño mediante `RotatingFileHandler` con un límite estricto de **5 MB por fichero** y conservación de **hasta 3 copias de respaldo** (`.log.1`, `.log.2`, `.log.3`), garantizando un consumo máximo predecible de ~15 MB por componente.
- **Nivel de Detalle**: Nivel predeterminado `INFO` (registrando arranque, llamadas a endpoints, cambios contables, eventos y errores), parametrizable mediante variables de entorno en `.env`.
- **Sanitización de Privacidad**: Filtro de seguridad (`PrivacyFilter`) que enmascara automáticamente tokens Bearer, contraseñas y claves de API antes de persistir los registros.
- **Acceso Exclusivo en Servidor/Disco**: Sin sobrecarga en la interfaz gráfica; los logs se consultan de manera externa vía explorador o consola.

---

## 2. Usuarios y Casos de Uso

- **Desarrollador y Administrador del Sistema**:
  - Necesita auditar errores 4xx/5xx, cuellos de botella de red y caídas de proveedores externos inspeccionando directamente `logs/backend.log` o `logs/frontend.log`.
  - Necesita certeza de que los archivos de registro nunca crecerán sin control ni saturarán el espacio de almacenamiento.
- **Usuario y Protección de Datos Personales**:
  - Requiere garantía incondicional de que sus credenciales personales nunca queden registradas en texto plano en los archivos de log locales.

---

## 3. Historias de Usuario (HU)

- **HU-1 (Logs Independientes Backend y Frontend)**: Como desarrollador, quiero que las trazas de FastAPI se escriban en `logs/backend.log` y las de Streamlit en `logs/frontend.log` para aislar con claridad el origen de cualquier incidencia.
- **HU-2 (Rotación y Límite de Espacio)**: Como operador, quiero que cada fichero rote al alcanzar 5 MB y mantenga un máximo de 3 copias históricas para limitar el consumo en disco a un máximo seguro.
- **HU-3 (Filtro de Sanitización de Privacidad)**: Como usuario consciente de la seguridad, quiero que el sistema enmascare automáticamente cualquier clave API o token que aparezca en los logs.
- **HU-4 (Configurabilidad por Entorno)**: Como desarrollador, quiero poder cambiar el nivel de log (`DEBUG`, `INFO`, `WARNING`, `ERROR`) mediante `.env` sin modificar el código.

---

## 4. Requisitos Funcionales (RF)

### RF-1: Motor de Configuración de Logging (`src/backend/utils/logging_config.py`)
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE proveer la función `setup_logging(log_file: str, log_level: Optional[str] = None, max_bytes: Optional[int] = None, backup_count: Optional[int] = None) -> logging.Logger`.
- **Criterio EARS (Event-driven)**: CUANDO se invoque `setup_logging()`, EL SISTEMA DEBE verificar la existencia del directorio padre (`logs/`) y crearlo automáticamente si no existe.
- **Criterio EARS (State-driven)**: MIENTRAS la aplicación registre eventos, EL SISTEMA DEBE formatear cada línea con el estándar:
  `%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s`.
- **Criterio EARS (Event-driven)**: CUANDO el archivo de log alcance `max_bytes` (5 MB por defecto), `RotatingFileHandler` DEBE rotarlo conservando como máximo `backup_count` (3 copias de respaldo).

### RF-2: Filtro de Sanitización de Privacidad (`PrivacyFilter`)
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE implementar `PrivacyFilter(logging.Filter)` e incorporarlo a todos los handlers activos.
- **Criterio EARS (Event-driven)**: CUANDO el contenido de un `LogRecord` contenga patrones de claves API (ej. Google AI `AIza[0-9A-Za-z-_]{35}`), cabeceras de autorización (`Bearer\s+[A-Za-z0-9-_.]+`), o asignaciones de secretos (`api_key=...`, `password=...`), EL SISTEMA DEBE sustituir la porción confidencial por `[REDACTED]`.

### RF-3: Inicialización en Backend FastAPI y Middleware de Peticiones
- **Criterio EARS (Event-driven)**: CUANDO arranque el servidor backend (`src/backend/api/main.py`), EL SISTEMA DEBE inicializar el logging hacia `logs/backend.log`.
- **Criterio EARS (Event-driven)**: CUANDO el backend reciba una petición HTTP, un middleware de observabilidad DEBE registrar el método, la ruta solicitada, el código de estado HTTP y el tiempo de respuesta en milisegundos.

### RF-4: Inicialización en Frontend Streamlit
- **Criterio EARS (Event-driven)**: CUANDO arranque o importe el cliente frontend (`src/frontend/api_client.py`), EL SISTEMA DEBE inicializar el logging hacia `logs/frontend.log` utilizando los mismos parámetros de rotación y el filtro de privacidad.

---

## 5. Requisitos No Funcionales (RNF)

- **RNF-1 (Convenciones de Idioma - Opción 1)**:
  - Nombres de funciones, clases y módulos en inglés: `setup_logging`, `PrivacyFilter`, `RotatingFileHandler`, `max_bytes`, `backup_count`, `request_logging_middleware`.
  - Documentación técnica y especificación 100% en español.
- **RNF-2 (Exclusión Innegociable en Git)**:
  - El directorio `logs/` y los patrones `*.log*` deben estar estrictamente registrados en `.gitignore` para cumplir con el Principio 11 de la Constitución.
- **RNF-3 (Rendimiento e I/O Eficiente)**:
  - Escritura con codificación UTF-8 y manejo sin excepciones no capturadas durante la rotación.
- **RNF-4 (Pruebas Automatizadas Obligatorias)**:
  - Cobertura completa con `pytest` al 100% antes de dar por cerrada cada fase.

