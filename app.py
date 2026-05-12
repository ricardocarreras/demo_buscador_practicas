import re
import uuid
from datetime import datetime, timedelta, date
from urllib.parse import urlencode

import pandas as pd
import requests
import streamlit as st

APP_NAME = "PracticeMatch AI — Demo Agente 1"


def init_state():
    defaults = {
        "search_started": False,
        "sector_keyword": "",
        "city": "",
        "linkedin_url": "",
        "linkedin_completed": False,
        "linkedin_offers": [],
        "open_web_offers": [],
        "duplicates": [],
        "rejected": [],
        "final_offers": [],
        "events": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def add_event(event_type, payload=None):
    st.session_state.events.append({
        "event": event_type,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "payload": payload or {},
    })


def normalize_text(value: str) -> str:
    if not value:
        return ""
    value = value.lower().strip()
    replacements = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ü": "u", "ñ": "n"}
    for a, b in replacements.items():
        value = value.replace(a, b)
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def build_linkedin_url(sector_keyword: str, city: str) -> str:
    params = {
        "keywords": f"prácticas {sector_keyword}".strip(),
        "location": city,
        "f_TPR": "r604800",
        "origin": "JOB_SEARCH_PAGE_SEARCH_BUTTON",
    }
    return "https://www.linkedin.com/jobs/search-results/?" + urlencode(params)


def expanded_queries(sector_keyword: str, city: str):
    base = sector_keyword.strip()
    queries = [
        f'"prácticas {base}" "{city}"',
        f'"becario {base}" "{city}"',
        f'"becaria {base}" "{city}"',
        f'"{base} intern" "{city}"',
        f'"{base} internship" "{city}"',
        f'"trainee {base}" "{city}"',
        f'site:infojobs.net "prácticas {base}" "{city}"',
        f'site:indeed.com "{base} intern" "{city}"',
        f'site:welcometothejungle.com "{base} intern" "{city}"',
        f'site:greenhouse.io "{base} intern" "{city}"',
        f'site:lever.co "{base} intern" "{city}"',
        f'site:workdayjobs.com "prácticas {base}" "{city}"',
        f'site:jobs.smartrecruiters.com "{base} intern" "{city}"',
        f'site:teamtailor.com "{base} intern" "{city}"',
    ]
    if "marketing" in normalize_text(base):
        queries.extend([
            f'"social media intern" "{city}"',
            f'"performance marketing intern" "{city}"',
            f'"growth marketing intern" "{city}"',
            f'"SEO intern" "{city}"',
            f'"SEM intern" "{city}"',
            f'"content marketing intern" "{city}"',
            f'"CRM intern" "{city}"',
            f'"ecommerce intern" "{city}"',
            f'"trade marketing intern" "{city}"',
            f'"brand marketing intern" "{city}"',
        ])
    return list(dict.fromkeys(queries))


def classify_remote_policy(text: str) -> str:
    t = normalize_text(text)
    if any(x in t for x in ["hibrido", "hybrid"]):
        return "hybrid"
    if any(x in t for x in ["remoto", "remote", "teletrabajo"]):
        return "remote"
    if any(x in t for x in ["presencial", "on site", "onsite"]):
        return "onsite"
    return "unknown"


def classify_job_type(text: str):
    t = normalize_text(text)
    positive = ["practicas", "becario", "becaria", "intern", "internship", "trainee", "student", "contrato formativo", "graduate"]
    negative = ["senior", "manager", "head of", "director", "lead", "5 years", "5 anos", "3 years", "3 anos", "mas de 3 anos"]
    if any(n in t for n in negative):
        return "full_time", False, "senior_or_experienced_role"
    if any(p in t for p in positive):
        return "internship", True, None
    return "unknown", False, "not_clearly_internship"


def estimate_date_from_text(text: str):
    if not text:
        return None, "unknown"
    today = date.today()
    t = normalize_text(text)
    if "hoy" in t or "today" in t or "just now" in t:
        return today.isoformat(), "medium"
    m = re.search(r"hace\s+(\d+)\s+d[ií]a", text, re.IGNORECASE) or re.search(r"(\d+)\s+day", text, re.IGNORECASE)
    if m:
        return (today - timedelta(days=int(m.group(1)))).isoformat(), "medium"
    m = re.search(r"hace\s+(\d+)\s+semana", text, re.IGNORECASE) or re.search(r"(\d+)\s+week", text, re.IGNORECASE)
    if m:
        return (today - timedelta(days=7 * int(m.group(1)))).isoformat(), "low"
    return None, "unknown"


def extract_city(text: str, default_city: str) -> str:
    if default_city and normalize_text(default_city) in normalize_text(text):
        return default_city
    known = ["Madrid", "Barcelona", "Valencia", "Zaragoza", "Sevilla", "Bilbao", "Lisboa", "Paris", "París", "Milan", "Milán", "London", "Londres"]
    for c in known:
        if normalize_text(c) in normalize_text(text):
            return {"Paris": "París", "Milan": "Milán", "London": "Londres"}.get(c, c)
    return default_city or "unknown"


def extract_skills(text: str):
    catalog = ["Excel", "PowerPoint", "Google Analytics", "GA4", "SEO", "SEM", "Google Ads", "Meta Ads", "HubSpot", "Salesforce", "CRM", "SQL", "Python", "Power BI", "Tableau", "Canva", "Figma", "SAP", "Paid Media", "Social Media", "Ecommerce", "Email Marketing"]
    t = normalize_text(text)
    return [skill for skill in catalog if normalize_text(skill) in t]


def extract_languages(text: str):
    t = normalize_text(text)
    languages = []
    if "ingles" in t or "english" in t:
        level = None
        if any(x in t for x in ["c1", "alto", "fluent", "advanced"]):
            level = "high/fluent"
        elif any(x in t for x in ["b2", "intermedio", "intermediate"]):
            level = "intermediate"
        languages.append({"language": "English", "level": level})
    if "frances" in t or "french" in t:
        languages.append({"language": "French", "level": None})
    if "portugues" in t or "portuguese" in t:
        languages.append({"language": "Portuguese", "level": None})
    return languages


def split_sections(text: str):
    lines = [line.strip(" -•\t") for line in text.splitlines() if line.strip()]
    responsibilities, requirements = [], []
    current = None
    for line in lines:
        low = normalize_text(line)
        if any(k in low for k in ["responsabilidades", "funciones", "tasks", "responsibilities", "what you will do"]):
            current = "responsibilities"
            continue
        if any(k in low for k in ["requisitos", "requirements", "qualifications", "perfil", "what we are looking"]):
            current = "requirements"
            continue
        if current == "responsibilities" and len(line) > 3:
            responsibilities.append(line)
        elif current == "requirements" and len(line) > 3:
            requirements.append(line)
    return responsibilities[:12], requirements[:12]


def score_offer_quality(offer: dict) -> int:
    score = 0
    if offer.get("title"):
        score += 20
    if offer.get("company"):
        score += 15
    if offer.get("description") and len(offer["description"]) > 150:
        score += 15
    if offer.get("city") and offer.get("city") != "unknown":
        score += 10
    if offer.get("published_date"):
        score += 10
    if offer.get("source_type") in ["corporate_site", "ats", "linkedin", "open_web", "search_result"]:
        score += 10
    if offer.get("application_url") or offer.get("source_url"):
        score += 10
    if offer.get("requirements"):
        score += 10
    if offer.get("published_date_confidence") == "unknown":
        score -= 10
    if not offer.get("description") or len(offer.get("description", "")) < 80:
        score -= 30
    if offer.get("processing_status") == "rejected":
        score -= 50
    return max(0, min(100, score))


def parse_offer_text(raw_text: str, source: str, source_url: str | None, capture_mode: str, default_city: str, sector_keyword: str):
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    title = lines[0] if len(lines) >= 1 else None
    company = lines[1] if len(lines) >= 2 else None
    published_date, date_conf = estimate_date_from_text(raw_text)
    job_type, is_valid, rejection_reason = classify_job_type(raw_text)
    responsibilities, requirements = split_sections(raw_text)
    missing = []
    if not title:
        missing.append("title")
    if not company:
        missing.append("company")
    if len(raw_text) < 80:
        missing.append("description")
    offer = {
        "id": str(uuid.uuid4()),
        "title": title,
        "company": company,
        "source": source,
        "source_type": "linkedin" if source == "LinkedIn" else "search_result",
        "source_url": source_url,
        "application_url": source_url,
        "city": extract_city(raw_text, default_city),
        "country": "Spain",
        "remote_policy": classify_remote_policy(raw_text),
        "published_date": published_date,
        "published_date_text": None,
        "published_date_confidence": date_conf,
        "detected_at": datetime.now().isoformat(timespec="seconds"),
        "job_type": job_type,
        "sector": sector_keyword,
        "description": raw_text,
        "responsibilities": responsibilities,
        "requirements": requirements,
        "skills": extract_skills(raw_text),
        "languages": extract_languages(raw_text),
        "search_keyword": sector_keyword,
        "search_query": f"prácticas {sector_keyword}",
        "search_city": default_city,
        "search_period": "last_7_days",
        "capture_mode": capture_mode,
        "duplicate_status": "unique",
        "duplicate_of": None,
        "parser_confidence": 0.75 if len(raw_text) > 200 else 0.55,
        "confidence_score": None,
        "processing_status": "processed" if is_valid else "rejected",
        "rejection_reason": rejection_reason,
        "missing_fields": missing,
    }
    offer["confidence_score"] = score_offer_quality(offer)
    return offer


def dedupe_key(offer):
    return "|".join([normalize_text(offer.get("company", "")), normalize_text(offer.get("title", "")), normalize_text(offer.get("city", ""))])


SOURCE_PRIORITY = {"corporate_site": 1, "ats": 2, "linkedin": 3, "open_web": 4, "search_result": 5}


def choose_canonical(a, b):
    pa = SOURCE_PRIORITY.get(a.get("source_type"), 99)
    pb = SOURCE_PRIORITY.get(b.get("source_type"), 99)
    if pb < pa:
        return b, a
    if pa < pb:
        return a, b
    if len(b.get("description", "")) > len(a.get("description", "")):
        return b, a
    return a, b


def deduplicate(offers):
    unique, duplicates = {}, []
    for offer in offers:
        key = dedupe_key(offer) or offer.get("id")
        if key in unique:
            winner, loser = choose_canonical(unique[key], offer)
            winner.setdefault("also_found_in", [])
            if loser.get("source") and loser.get("source") not in winner["also_found_in"]:
                winner["also_found_in"].append(loser.get("source"))
            loser["duplicate_status"] = "duplicate"
            loser["duplicate_of"] = winner["id"]
            duplicates.append(loser)
            unique[key] = winner
        else:
            offer.setdefault("also_found_in", [])
            unique[key] = offer
    return list(unique.values()), duplicates


def serpapi_search(query: str, api_key: str, max_results: int = 5):
    params = {"q": query, "api_key": api_key, "engine": "google", "num": max_results, "hl": "es", "gl": "es"}
    response = requests.get("https://serpapi.com/search.json", params=params, timeout=20)
    response.raise_for_status()
    data = response.json()
    return [
        {
            "title": item.get("title"),
            "url": item.get("link"),
            "snippet": item.get("snippet") or "",
            "source": item.get("source") or "Open Web",
        }
        for item in data.get("organic_results", [])[:max_results]
    ]


SAMPLE_OPEN_WEB = [
    {"title": "Becario/a Marketing Digital - Madrid", "url": "https://example.com/jobs/becario-marketing-digital", "snippet": "Programa de prácticas de marketing digital en Madrid. Apoyo en campañas SEO, SEM, Google Analytics y reporting semanal. Convenio con universidad.", "source": "Portal demo"},
    {"title": "Digital Marketing Intern", "url": "https://example.com/jobs/digital-marketing-intern", "snippet": "Internship in Madrid supporting paid media, social media and content marketing. English fluent required. 6 months.", "source": "ATS demo"},
    {"title": "Social Media Intern Madrid", "url": "https://example.com/jobs/social-media-intern", "snippet": "Prácticas en social media, creación de contenidos, Canva, Meta Ads y análisis de KPIs. Madrid híbrido.", "source": "Careers demo"},
]


def make_open_web_offer(result: dict, sector_keyword: str, city: str):
    text = "\n".join([result.get("title") or "", result.get("source") or "Open Web", city, result.get("snippet") or ""])
    offer = parse_offer_text(text, result.get("source") or "Open Web", result.get("url"), "open_web_search_result", city, sector_keyword)
    offer["source_type"] = "search_result"
    offer["parser_confidence"] = min(offer["parser_confidence"], 0.55)
    offer["confidence_score"] = min(offer["confidence_score"], 65)
    if offer["processing_status"] == "rejected":
        offer["processing_status"] = "processed"
        offer["rejection_reason"] = None
    return offer


init_state()
st.set_page_config(page_title=APP_NAME, page_icon="🎓", layout="wide")
st.title(APP_NAME)
st.caption("Demo v0.1 — LinkedIn asistido obligatorio + búsqueda abierta + deduplicación")

with st.sidebar:
    st.header("Estado")
    st.write("LinkedIn completado:", "✅" if st.session_state.linkedin_completed else "⏳")
    st.write("Ofertas LinkedIn:", len(st.session_state.linkedin_offers))
    st.write("Ofertas fuentes abiertas:", len(st.session_state.open_web_offers))
    st.write("Duplicados:", len(st.session_state.duplicates))
    st.write("Final:", len(st.session_state.final_offers))
    st.divider()
    try:
        default_serpapi_key = st.secrets.get("SERPAPI_API_KEY", "")
    except Exception:
        default_serpapi_key = ""

    serpapi_key = st.text_input(
        "SERPAPI_API_KEY opcional",
        value=default_serpapi_key,
        type="password",
        help="Si no la pones, la app usa resultados demo."
    )

tab1, tab2, tab3, tab4, tab5 = st.tabs(["1. Nueva búsqueda", "2. LinkedIn asistido", "3. Fuentes abiertas", "4. Resultados", "5. Auditoría"])

with tab1:
    st.subheader("Nueva búsqueda")
    sector = st.text_input("Palabra clave del sector", value=st.session_state.sector_keyword or "marketing digital")
    city = st.text_input("Ciudad", value=st.session_state.city or "Madrid")
    if st.button("Crear búsqueda", type="primary"):
        if not sector.strip() or not city.strip():
            st.error("Necesito sector y ciudad.")
        else:
            st.session_state.sector_keyword = sector.strip()
            st.session_state.city = city.strip()
            st.session_state.linkedin_url = build_linkedin_url(sector.strip(), city.strip())
            st.session_state.search_started = True
            st.session_state.linkedin_completed = False
            st.session_state.linkedin_offers = []
            st.session_state.open_web_offers = []
            st.session_state.duplicates = []
            st.session_state.rejected = []
            st.session_state.final_offers = []
            st.session_state.events = []
            add_event("search_created", {"sector_keyword": sector.strip(), "city": city.strip(), "linkedin_url": st.session_state.linkedin_url})
            st.success("Búsqueda creada. Ve a la pestaña 'LinkedIn asistido'.")
    if st.session_state.search_started:
        st.info("Búsqueda LinkedIn obligatoria generada:")
        st.code(st.session_state.linkedin_url, language="text")
        st.link_button("Abrir búsqueda en LinkedIn", st.session_state.linkedin_url)
        with st.expander("Queries abiertas posteriores"):
            st.json(expanded_queries(st.session_state.sector_keyword, st.session_state.city))

with tab2:
    st.subheader("LinkedIn asistido obligatorio")
    if not st.session_state.search_started:
        st.warning("Primero crea una búsqueda en la pestaña 1.")
    else:
        st.write("Abre LinkedIn desde el perfil del alumno. Añade ofertas por URL o pegando el texto completo.")
        st.link_button("Abrir búsqueda en LinkedIn", st.session_state.linkedin_url)
        st.markdown("### A. Pegar URLs de ofertas")
        urls_text = st.text_area("Pega URLs de LinkedIn Jobs, una por línea", height=110)
        if st.button("Procesar URLs LinkedIn"):
            urls = [u.strip() for u in urls_text.splitlines() if u.strip()]
            processed = 0
            for url in urls:
                if "linkedin.com/jobs/view" not in url:
                    st.warning(f"No parece una URL de oferta LinkedIn: {url}")
                    continue
                job_id_match = re.search(r"/jobs/view/(\d+)", url)
                job_id = job_id_match.group(1) if job_id_match else None
                raw_text = f"Oferta LinkedIn {job_id or ''}\nLinkedIn\n{st.session_state.city}\nPrácticas\nURL: {url}"
                offer = parse_offer_text(raw_text, "LinkedIn", url, "linkedin_assisted_url", st.session_state.city, st.session_state.sector_keyword)
                offer["title"] = f"Oferta LinkedIn {job_id or ''}".strip()
                offer["company"] = "LinkedIn"
                offer["linkedin_job_id"] = job_id
                offer["confidence_score"] = score_offer_quality(offer)
                st.session_state.linkedin_offers.append(offer)
                processed += 1
            if processed:
                add_event("linkedin_urls_added", {"count": processed})
                st.success(f"URLs procesadas: {processed}. Para mejor calidad, pega también el texto completo.")
        st.markdown("### B. Pegar texto completo de una oferta")
        raw_offer_text = st.text_area("Texto de la oferta copiado desde LinkedIn", height=220, placeholder="Digital Marketing Intern\nEmpresa X\nMadrid\nHace 3 días\nPrácticas · Híbrido\n\nAcerca del empleo...")
        if st.button("Procesar texto LinkedIn"):
            if len(raw_offer_text.strip()) < 30:
                st.error("El texto parece demasiado corto.")
            else:
                offer = parse_offer_text(raw_offer_text, "LinkedIn", None, "linkedin_assisted_text", st.session_state.city, st.session_state.sector_keyword)
                st.session_state.linkedin_offers.append(offer)
                add_event("linkedin_text_added", {"title": offer.get("title"), "company": offer.get("company")})
                st.success(f"Oferta procesada: {offer.get('title')} — {offer.get('company')}")
        st.markdown("### C. Cerrar LinkedIn")
        st.write(f"Ofertas LinkedIn procesadas: **{len(st.session_state.linkedin_offers)}**")
        if st.session_state.linkedin_offers:
            df_linkedin = pd.DataFrame(st.session_state.linkedin_offers)
            st.dataframe(df_linkedin[["title", "company", "city", "capture_mode", "confidence_score", "processing_status"]], use_container_width=True)
        confirm = st.checkbox("Confirmo que he añadido todas las ofertas relevantes visibles en LinkedIn para esta búsqueda.")
        if st.button("LinkedIn completado — desbloquear fuentes abiertas", disabled=not confirm):
            st.session_state.linkedin_completed = True
            add_event("linkedin_completed_by_user", {"linkedin_offers": len(st.session_state.linkedin_offers)})
            st.success("LinkedIn completado. Ya puedes pasar a fuentes abiertas.")

with tab3:
    st.subheader("Fuentes abiertas")
    if not st.session_state.search_started:
        st.warning("Primero crea una búsqueda.")
    elif not st.session_state.linkedin_completed:
        st.error("LinkedIn es obligatorio. Completa primero la pestaña 2.")
    else:
        queries = expanded_queries(st.session_state.sector_keyword, st.session_state.city)
        max_queries = st.slider("Número de queries a ejecutar", 3, min(20, len(queries)), 8)
        max_results = st.slider("Resultados por query", 1, 10, 3)
        with st.expander("Ver queries"):
            st.write(queries[:max_queries])
        if st.button("Ejecutar búsqueda abierta", type="primary"):
            open_results = []
            if serpapi_key:
                with st.spinner("Consultando SerpAPI..."):
                    for q in queries[:max_queries]:
                        try:
                            open_results.extend(serpapi_search(q, serpapi_key, max_results=max_results))
                        except Exception as exc:
                            st.warning(f"Error en query: {q} — {exc}")
            else:
                st.info("No hay SERPAPI_API_KEY. Uso resultados demo.")
                open_results = SAMPLE_OPEN_WEB
            offers = [make_open_web_offer(r, st.session_state.sector_keyword, st.session_state.city) for r in open_results]
            st.session_state.open_web_offers = offers
            all_offers = st.session_state.linkedin_offers + st.session_state.open_web_offers
            unique, duplicates = deduplicate(all_offers)
            rejected = [o for o in unique if o.get("processing_status") == "rejected" or o.get("confidence_score", 0) < 40]
            final = [o for o in unique if o not in rejected]
            st.session_state.final_offers = final
            st.session_state.duplicates = duplicates
            st.session_state.rejected = rejected
            add_event("open_web_completed", {"open_results": len(open_results), "open_offers": len(offers), "duplicates": len(duplicates), "final": len(final)})
            st.success("Búsqueda abierta completada. Ve a Resultados.")
        if st.session_state.open_web_offers:
            st.dataframe(pd.DataFrame(st.session_state.open_web_offers)[["title", "company", "source", "city", "confidence_score", "source_url"]], use_container_width=True)

with tab4:
    st.subheader("Resultados consolidados")
    if not st.session_state.final_offers:
        st.info("Aún no hay resultados finales. Completa LinkedIn y fuentes abiertas.")
    else:
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("LinkedIn", len(st.session_state.linkedin_offers))
        c2.metric("Fuentes abiertas", len(st.session_state.open_web_offers))
        c3.metric("Duplicados", len(st.session_state.duplicates))
        c4.metric("Descartadas", len(st.session_state.rejected))
        c5.metric("Válidas únicas", len(st.session_state.final_offers))
        df = pd.DataFrame(st.session_state.final_offers)
        cols = ["title", "company", "source", "city", "remote_policy", "published_date", "confidence_score", "source_url"]
        st.dataframe(df[[c for c in cols if c in df.columns]].sort_values("confidence_score", ascending=False), use_container_width=True)
        st.download_button("Descargar CSV", df.to_csv(index=False).encode("utf-8"), file_name="ofertas_practicas_consolidadas.csv", mime="text/csv")
        with st.expander("Ver JSON"):
            st.json(st.session_state.final_offers)

with tab5:
    st.subheader("Auditoría")
    st.json(st.session_state.events)
