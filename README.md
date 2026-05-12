# PracticeMatch AI — Demo v0.3

Demo Streamlit con subida de CV, captura asistida de LinkedIn, búsqueda abierta, ranking CV/oferta y generación de emails top 5.

## Local

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m streamlit run app.py
```

## Secrets opcionales

```toml
SERPAPI_API_KEY = "tu_clave_serpapi"
OPENAI_API_KEY = "tu_clave_openai"
```

La app funciona sin claves: usa resultados demo y plantillas de email locales.
