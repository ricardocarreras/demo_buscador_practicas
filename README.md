# PracticeMatch AI — Demo Agente 1

Demo Streamlit del **Agente 1: Captura de Ofertas de Prácticas**.

## Qué hace

1. Pide sector y ciudad.
2. Genera una URL de LinkedIn Jobs con:
   - `prácticas + sector`
   - ciudad
   - última semana (`f_TPR=r604800`)
3. Obliga a completar LinkedIn en modo asistido:
   - pegando URLs de ofertas; o
   - pegando texto completo copiado desde LinkedIn.
4. Solo después permite buscar en fuentes abiertas.
5. Si configuras `SERPAPI_API_KEY`, ejecuta búsquedas reales en Google vía SerpAPI.
6. Si no configuras `SERPAPI_API_KEY`, usa resultados demo.
7. Deduplica ofertas.
8. Muestra tabla final y permite descargar CSV.

## Qué no hace

- No entra en la cuenta de LinkedIn.
- No pide contraseñas.
- No automatiza candidaturas.
- No envía mensajes.
- No evita captchas.
- No scrapea perfiles.

## Instalación local

```bash
git clone <TU_REPO>
cd <TU_REPO>
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m streamlit run app.py
```

En Mac/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Despliegue en Streamlit Community Cloud

1. Sube estos archivos a GitHub:
   - `app.py`
   - `requirements.txt`
   - `.gitignore`
   - `README.md`
2. Entra en Streamlit Community Cloud.
3. Crea una app nueva desde el repositorio de GitHub.
4. Main file path: `app.py`.
5. Añade el secret si quieres búsqueda real:

```toml
SERPAPI_API_KEY = "tu_clave"
```

6. Deploy.

## Uso

1. Abre la app.
2. Introduce sector, por ejemplo `marketing digital`.
3. Introduce ciudad, por ejemplo `Madrid`.
4. Crea la búsqueda.
5. Abre LinkedIn con el botón generado.
6. Copia ofertas de LinkedIn por URL o texto.
7. Marca LinkedIn como completado.
8. Ejecuta fuentes abiertas.
9. Revisa resultados y descarga CSV.

## Próximas mejoras

- Parser LLM con salida JSON estructurada.
- Base de datos PostgreSQL.
- Usuarios/alumnos.
- Catálogo de empresas objetivo.
- Exportación Excel.
- Matching con CV.
