import re, json, uuid
from datetime import datetime, timedelta, date
from urllib.parse import urlencode
import pandas as pd
import streamlit as st
import requests

APP_NAME = "Buscador de prácticas— Demo v0.3"

# -------------------------
# Utilidades
# -------------------------
def get_secret(name, default=""):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default

def norm(s):
    if not s: return ""
    s = s.lower().strip()
    for a,b in {"á":"a","é":"e","í":"i","ó":"o","ú":"u","ü":"u","ñ":"n"}.items(): s=s.replace(a,b)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", s)).strip()

def init_state():
    defaults = dict(
        search_started=False, sector_keyword="", city="", linkedin_url="", linkedin_completed=False,
        linkedin_offers=[], open_web_offers=[], duplicates=[], rejected=[], final_offers=[],
        cv_text="", cv_filename="", cv_profile={}, ranked_offers=[], generated_emails=[], events=[]
    )
    for k,v in defaults.items():
        if k not in st.session_state: st.session_state[k]=v

def event(name, payload=None):
    st.session_state.events.append({"event":name,"timestamp":datetime.now().isoformat(timespec="seconds"),"payload":payload or {}})

def linkedin_url(sector, city):
    return "https://www.linkedin.com/jobs/search-results/?" + urlencode({
        "keywords": f"prácticas {sector}", "location": city, "f_TPR": "r604800", "origin": "JOB_SEARCH_PAGE_SEARCH_BUTTON"
    })

def expanded_queries(sector, city):
    q = [
        f'"prácticas {sector}" "{city}"', f'"becario {sector}" "{city}"', f'"becaria {sector}" "{city}"',
        f'"{sector} intern" "{city}"', f'"{sector} internship" "{city}"', f'"trainee {sector}" "{city}"',
        f'site:infojobs.net "prácticas {sector}" "{city}"', f'site:indeed.com "{sector} intern" "{city}"',
        f'site:welcometothejungle.com "{sector} intern" "{city}"', f'site:greenhouse.io "{sector} intern" "{city}"',
        f'site:lever.co "{sector} intern" "{city}"', f'site:workdayjobs.com "prácticas {sector}" "{city}"',
        f'site:jobs.smartrecruiters.com "{sector} intern" "{city}"'
    ]
    if "marketing" in norm(sector):
        q += [f'"social media intern" "{city}"', f'"performance marketing intern" "{city}"', f'"growth marketing intern" "{city}"', f'"SEO intern" "{city}"', f'"SEM intern" "{city}"', f'"CRM intern" "{city}"', f'"ecommerce intern" "{city}"']
    return list(dict.fromkeys(q))

def remote_policy(text):
    t=norm(text)
    if "hibrido" in t or "hybrid" in t: return "hybrid"
    if "remoto" in t or "remote" in t or "teletrabajo" in t: return "remote"
    if "presencial" in t or "onsite" in t or "on site" in t: return "onsite"
    return "unknown"

def job_type(text):
    t=norm(text)
    if any(x in t for x in ["senior","manager","head of","director","lead","5 years","5 anos","3 years","3 anos","mas de 3 anos"]):
        return "full_time", False, "senior_or_experienced_role"
    if any(x in t for x in ["practicas","becario","becaria","intern","internship","trainee","student","contrato formativo","graduate"]):
        return "internship", True, None
    return "unknown", False, "not_clearly_internship"

def estimate_date(text):
    if not text: return None,"unknown"
    today=date.today(); t=norm(text)
    if "hoy" in t or "today" in t: return today.isoformat(),"medium"
    m=re.search(r"hace\s+(\d+)\s+d[ií]a", text, re.I) or re.search(r"(\d+)\s+day", text, re.I)
    if m: return (today-timedelta(days=int(m.group(1)))).isoformat(),"medium"
    m=re.search(r"hace\s+(\d+)\s+semana", text, re.I) or re.search(r"(\d+)\s+week", text, re.I)
    if m: return (today-timedelta(days=7*int(m.group(1)))).isoformat(),"low"
    return None,"unknown"

def city_from(text, default_city):
    if default_city and norm(default_city) in norm(text): return default_city
    for c in ["Madrid","Barcelona","Valencia","Zaragoza","Sevilla","Bilbao","Lisboa","París","Paris","Milán","Milan","Londres","London"]:
        if norm(c) in norm(text): return {"Paris":"París","Milan":"Milán","London":"Londres"}.get(c,c)
    return default_city or "unknown"

SKILLS = ["Excel","PowerPoint","Google Analytics","GA4","SEO","SEM","Google Ads","Meta Ads","HubSpot","Salesforce","CRM","SQL","Python","Power BI","Tableau","Canva","Figma","SAP","Paid Media","Social Media","Ecommerce","Email Marketing","WordPress","Photoshop","Illustrator","Looker Studio","R","Java","JavaScript","HTML","CSS","Power Query","ERP","WMS","TMS","Logistics","Supply Chain","Finance","Accounting","Contabilidad","Marketing","Comunicación","Data Analytics","Machine Learning","AI","Inteligencia Artificial"]
def skills(text):
    t=norm(text); return list(dict.fromkeys([s for s in SKILLS if norm(s) in t]))

def languages(text):
    t=norm(text); out=[]
    if "ingles" in t or "english" in t:
        lvl = "bilingual/native" if any(x in t for x in ["c2","native","bilingue","bilingual"]) else ("high/fluent" if any(x in t for x in ["c1","alto","fluent","advanced"]) else ("intermediate" if any(x in t for x in ["b2","intermedio","intermediate"]) else None))
        out.append({"language":"English","level":lvl})
    if "frances" in t or "french" in t: out.append({"language":"French","level":None})
    if "portugues" in t or "portuguese" in t: out.append({"language":"Portuguese","level":None})
    if "aleman" in t or "german" in t: out.append({"language":"German","level":None})
    return out

def sections(text):
    res, req, cur = [], [], None
    for line in [l.strip(" -•\t") for l in text.splitlines() if l.strip()]:
        low=norm(line)
        if any(k in low for k in ["responsabilidades","funciones","tasks","responsibilities","what you will do","your mission"]): cur="res"; continue
        if any(k in low for k in ["requisitos","requirements","qualifications","perfil","what we are looking"]): cur="req"; continue
        if cur=="res" and len(line)>3: res.append(line)
        elif cur=="req" and len(line)>3: req.append(line)
    return res[:12], req[:12]

def quality(o):
    score=0
    if o.get("title"): score+=20
    if o.get("company"): score+=15
    if len(o.get("description","") or "")>150: score+=15
    if o.get("city") and o.get("city")!="unknown": score+=10
    if o.get("published_date"): score+=10
    if o.get("source_type") in ["corporate_site","ats","linkedin","open_web","search_result"]: score+=10
    if o.get("application_url") or o.get("source_url"): score+=10
    if o.get("requirements"): score+=10
    if o.get("published_date_confidence")=="unknown": score-=10
    if len(o.get("description","") or "")<80: score-=30
    if o.get("processing_status")=="rejected": score-=50
    return max(0,min(100,score))

def parse_offer(raw, source, source_url, capture_mode, default_city, sector):
    lines=[l.strip() for l in raw.splitlines() if l.strip()]
    title=lines[0] if lines else None; company=lines[1] if len(lines)>1 else None
    pd,dc=estimate_date(raw); jt,valid,rej=job_type(raw); res,req=sections(raw)
    o={"id":str(uuid.uuid4()),"title":title,"company":company,"source":source,"source_type":"linkedin" if source=="LinkedIn" else "open_web","source_url":source_url,"application_url":source_url,
       "city":city_from(raw,default_city),"country":"Spain","remote_policy":remote_policy(raw),"published_date":pd,"published_date_text":None,"published_date_confidence":dc,"detected_at":datetime.now().isoformat(timespec="seconds"),
       "job_type":jt,"sector":sector,"description":raw,"responsibilities":res,"requirements":req,"skills":skills(raw),"languages":languages(raw),"search_keyword":sector,"search_query":f"prácticas {sector}","search_city":default_city,"search_period":"last_7_days","capture_mode":capture_mode,"duplicate_status":"unique","duplicate_of":None,"parser_confidence":0.85 if len(raw)>300 else 0.65,"processing_status":"processed" if valid else "rejected","rejection_reason":rej,"missing_fields":[]}
    o["confidence_score"]=quality(o); return o

# -------------------------
# CV
# -------------------------
def extract_cv(upload):
    if not upload: return ""
    name=upload.name.lower(); data=upload.read()
    if name.endswith(".txt"): return data.decode("utf-8", errors="ignore")
    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
            import io
            return "\n".join([(p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages])
        except Exception as e: st.error(f"No he podido leer el PDF: {e}"); return ""
    if name.endswith(".docx"):
        try:
            from docx import Document
            import io
            return "\n".join([p.text for p in Document(io.BytesIO(data)).paragraphs])
        except Exception as e: st.error(f"No he podido leer el DOCX: {e}"); return ""
    st.error("Formato no soportado. Usa PDF, DOCX o TXT."); return ""

def cv_profile(text):
    t=norm(text)
    sectors=[s for s in ["marketing","finanzas","finance","data analytics","logistica","supply chain","recursos humanos","human resources","legal","consultoria","consulting","ventas","sales","comunicacion"] if norm(s) in t]
    edu=[e for e in ["ade","business","marketing","economia","engineering","ingenieria","derecho","law","master","grado","universidad","university"] if e in t]
    return {"skills":skills(text),"languages":languages(text),"sectors":sectors,"education_keywords":edu,"raw_text":text}

def overlap(a,b):
    aa=set(norm(x) for x in a if x); bb=set(norm(x) for x in b if x)
    if not bb: return 0, []
    inter=sorted(aa&bb); return int(round(100*len(inter)/max(1,len(bb)))), inter

def match_offer(offer, profile, cv_text):
    offer_text=" ".join([offer.get("title") or "", offer.get("description") or "", " ".join(offer.get("requirements") or []), " ".join(offer.get("skills") or [])])
    cv_sk=profile.get("skills",[]); off_sk=offer.get("skills") or skills(offer_text)
    skill_score, matched_norm = overlap(cv_sk, off_sk)
    cv_lang={norm(x.get("language","")):x for x in profile.get("languages",[])}; off_lang={norm(x.get("language","")):x for x in offer.get("languages",[])}
    lm=sorted(set(cv_lang)&set(off_lang)); lang_score=100 if lm else (70 if not off_lang else 20)
    sector_hits=[x for x in [offer.get("sector"), st.session_state.get("sector_keyword","")] if x and norm(x) in norm(cv_text)]
    sector_score=100 if sector_hits else 60
    edu_score=75 if any(w in norm(cv_text) for w in ["grado","master","universidad","university","student","estudiante"]) else 60
    q=offer.get("confidence_score",60); city_score=100 if norm(offer.get("city"))==norm(st.session_state.get("city")) else 70
    final=round(.38*skill_score+.18*lang_score+.16*sector_score+.12*edu_score+.08*q+.08*city_score)
    final=max(0,min(99,final))
    matched=[s for s in cv_sk if norm(s) in matched_norm]
    missing=[s for s in off_sk if norm(s) not in set(norm(x) for x in cv_sk)]
    strengths=[]; gaps=[]
    if matched: strengths.append("Coincidencia de habilidades: "+", ".join(matched[:8]))
    if lm: strengths.append("Coincidencia de idiomas: "+", ".join([x.title() for x in lm]))
    if sector_hits: strengths.append("El CV menciona formación o experiencia relacionada con "+", ".join(sector_hits[:3]))
    if missing: gaps.append("No aparecen claramente en el CV: "+", ".join(missing[:6]))
    ro=dict(offer); ro.update({"fit_score":final,"matched_skills":matched,"matched_languages":[x.title() for x in lm],"strengths":strengths,"gaps":gaps,"recommendation":"Muy alta" if final>=90 else ("Alta" if final>=80 else ("Media" if final>=65 else "Baja"))})
    return ro

def rank_offers(offers, profile, cv_text):
    out=[match_offer(o,profile,cv_text) for o in offers]; out.sort(key=lambda x:x.get("fit_score",0), reverse=True); return out

# -------------------------
# Email
# -------------------------
def fallback_email(offer):
    title=offer.get("title") or "la posición"; company=offer.get("company") or "su compañía"
    ms=offer.get("matched_skills",[]); ml=offer.get("matched_languages",[]); strengths=offer.get("strengths",[])
    skill_sentence=f" En particular, mi perfil encaja con competencias mencionadas en la oferta como {', '.join(ms[:5])}." if ms else ""
    lang_sentence=f" Además, cuento con el nivel de idioma requerido, especialmente en {', '.join(ml)}." if ml else ""
    strengths_sentence=(" "+strengths[0]) if strengths else ""
    return {"subject":f"Candidatura prácticas — {title}","body":f"""Estimado/a equipo de selección:

Me gustaría presentar mi candidatura para la posición de {title} en {company}. Tras revisar la oferta, considero que mi perfil puede encajar bien con las necesidades del puesto.{skill_sentence}{lang_sentence}

Actualmente estoy orientando mi desarrollo profesional hacia este ámbito y me interesa especialmente la oportunidad de aplicar mis conocimientos en un entorno real, contribuir al equipo y seguir aprendiendo.{strengths_sentence}

Adjunto mi CV para que puedan valorar mi candidatura. Quedo a su disposición para ampliar cualquier información o mantener una entrevista.

Muchas gracias por su tiempo.

Un cordial saludo,
[Nombre del alumno]"""}

def ai_email(offer, cv_text, api_key):
    if not api_key: return fallback_email(offer)
    try:
        from openai import OpenAI
        client=OpenAI(api_key=api_key)
        offer_summary={k:offer.get(k) for k in ["title","company","description","requirements","skills","fit_score","matched_skills","strengths","gaps"]}
        prompt=f"""Redacta un email de candidatura en español para unas prácticas. No inventes experiencia. Usa solo datos del CV y de la oferta. Tono profesional, breve y natural. Devuelve JSON válido con keys subject y body.

OFERTA:\n{json.dumps(offer_summary, ensure_ascii=False)}

CV:\n{cv_text[:6000]}"""
        r=client.chat.completions.create(model="gpt-4.1-mini",messages=[{"role":"system","content":"Eres experto en empleabilidad universitaria."},{"role":"user","content":prompt}],temperature=.4,response_format={"type":"json_object"})
        data=json.loads(r.choices[0].message.content)
        if "subject" in data and "body" in data: return data
        return fallback_email(offer)
    except Exception as e:
        x=fallback_email(offer); x["warning"]=f"No se pudo usar OpenAI; se generó plantilla local. Error: {e}"; return x

# -------------------------
# Open web + dedupe
# -------------------------
def serpapi(query, api_key, max_results=5):
    r=requests.get("https://serpapi.com/search.json",params={"q":query,"api_key":api_key,"engine":"google","num":max_results,"hl":"es","gl":"es"},timeout=20)
    r.raise_for_status(); data=r.json(); out=[]
    for it in data.get("organic_results",[])[:max_results]: out.append({"title":it.get("title"),"url":it.get("link"),"snippet":it.get("snippet") or "","source":it.get("source") or "Open Web"})
    return out

def make_open_offer(r, sector, city):
    text="\n".join([r.get("title") or "", r.get("source") or "Open Web", city, r.get("snippet") or ""])
    o=parse_offer(text,r.get("source") or "Open Web",r.get("url"),"open_web_search_result",city,sector)
    o["source_type"]="search_result"; o["parser_confidence"]=min(o["parser_confidence"],.55); o["confidence_score"]=min(o["confidence_score"],65)
    if o["processing_status"]=="rejected": o["processing_status"]="processed"; o["rejection_reason"]=None
    return o

SAMPLE_OPEN_WEB=[{"title":"Becario/a Marketing Digital - Madrid","url":"https://example.com/jobs/becario-marketing-digital","snippet":"Programa de prácticas de marketing digital en Madrid. Apoyo en campañas SEO, SEM, Google Analytics y reporting semanal. Convenio con universidad.","source":"Portal demo"},{"title":"Digital Marketing Intern","url":"https://example.com/jobs/digital-marketing-intern","snippet":"Internship in Madrid supporting paid media, social media and content marketing. English fluent required. 6 months.","source":"ATS demo"},{"title":"Social Media Intern Madrid","url":"https://example.com/jobs/social-media-intern","snippet":"Prácticas en social media, creación de contenidos, Canva, Meta Ads y análisis de KPIs. Madrid híbrido.","source":"Careers demo"}]

def dedupe_key(o): return "|".join([norm(o.get("company","")),norm(o.get("title","")),norm(o.get("city",""))])
def choose(a,b):
    pri={"corporate_site":1,"ats":2,"linkedin":3,"open_web":4,"search_result":5}; pa=pri.get(a.get("source_type"),99); pb=pri.get(b.get("source_type"),99)
    if pb<pa: return b,a
    if pa<pb: return a,b
    return (b,a) if len(b.get("description","") or "")>len(a.get("description","") or "") else (a,b)
def deduplicate(offers):
    u={}; dup=[]
    for o in offers:
        k=dedupe_key(o) or o.get("id")
        if k in u:
            w,l=choose(u[k],o); w.setdefault("also_found_in",[])
            if l.get("source") and l.get("source") not in w["also_found_in"]: w["also_found_in"].append(l.get("source"))
            l["duplicate_status"]="duplicate"; l["duplicate_of"]=w["id"]; dup.append(l); u[k]=w
        else:
            o.setdefault("also_found_in",[]); u[k]=o
    return list(u.values()),dup

# -------------------------
# UI
# -------------------------
init_state(); st.set_page_config(page_title=APP_NAME,page_icon="🎓",layout="wide")
st.title(APP_NAME); st.caption("Captura LinkedIn asistida + fuentes abiertas + ranking CV/oferta + emails top 5")
with st.sidebar:
    st.header("Estado")
    st.write("CV cargado:", "✅" if st.session_state.cv_text else "⏳")
    st.write("LinkedIn completado:", "✅" if st.session_state.linkedin_completed else "⏳")
    st.write("Ofertas finales:", len(st.session_state.final_offers)); st.write("Ranking:", len(st.session_state.ranked_offers)); st.write("Emails:", len(st.session_state.generated_emails))
    st.divider(); st.subheader("Claves opcionales")
    serpapi_key=st.text_input("SERPAPI_API_KEY", value=get_secret("SERPAPI_API_KEY",""), type="password")
    openai_key=st.text_input("OPENAI_API_KEY", value=get_secret("OPENAI_API_KEY",""), type="password")

tabs=st.tabs(["0. CV","1. Nueva búsqueda","2. LinkedIn asistido","3. Fuentes abiertas","4. Resultados","5. Ranking CV","6. Emails top 5"])

with tabs[0]:
    st.subheader("Subir CV")
    up=st.file_uploader("CV del alumno", type=["pdf","docx","txt"])
    if up:
        txt=extract_cv(up)
        if txt.strip():
            st.session_state.cv_text=txt; st.session_state.cv_filename=up.name; st.session_state.cv_profile=cv_profile(txt); event("cv_uploaded",{"filename":up.name,"chars":len(txt)})
            st.success(f"CV cargado: {up.name}")
    if st.session_state.cv_text:
        c1,c2,c3=st.columns(3); c1.metric("Caracteres",len(st.session_state.cv_text)); c2.metric("Skills",len(st.session_state.cv_profile.get("skills",[]))); c3.metric("Idiomas",len(st.session_state.cv_profile.get("languages",[])))
        st.json({"skills":st.session_state.cv_profile.get("skills",[]),"languages":st.session_state.cv_profile.get("languages",[]),"sectors":st.session_state.cv_profile.get("sectors",[]),"education":st.session_state.cv_profile.get("education_keywords",[])})
        with st.expander("Ver texto extraído"): st.text_area("Texto",st.session_state.cv_text,height=260)

with tabs[1]:
    st.subheader("Nueva búsqueda")
    sector=st.text_input("Palabra clave del sector", value=st.session_state.sector_keyword or "marketing digital")
    city=st.text_input("Ciudad", value=st.session_state.city or "Madrid")
    if st.button("Crear búsqueda", type="primary"):
        if not sector.strip() or not city.strip(): st.error("Necesito sector y ciudad.")
        else:
            st.session_state.sector_keyword=sector.strip(); st.session_state.city=city.strip(); st.session_state.linkedin_url=linkedin_url(sector.strip(),city.strip()); st.session_state.search_started=True; st.session_state.linkedin_completed=False; st.session_state.linkedin_offers=[]; st.session_state.open_web_offers=[]; st.session_state.duplicates=[]; st.session_state.rejected=[]; st.session_state.final_offers=[]; st.session_state.ranked_offers=[]; st.session_state.generated_emails=[]; event("search_created",{"sector":sector,"city":city}); st.success("Búsqueda creada.")
    if st.session_state.search_started:
        st.code(st.session_state.linkedin_url); st.link_button("Abrir búsqueda en LinkedIn",st.session_state.linkedin_url)
        with st.expander("Queries abiertas posteriores"): st.json(expanded_queries(st.session_state.sector_keyword, st.session_state.city)[:15])

with tabs[2]:
    st.subheader("LinkedIn asistido obligatorio")
    if not st.session_state.search_started: st.warning("Primero crea una búsqueda.")
    else:
        st.link_button("Abrir búsqueda en LinkedIn",st.session_state.linkedin_url)
        urls=st.text_area("URLs de LinkedIn Jobs, una por línea", height=90)
        if st.button("Procesar URLs LinkedIn"):
            count=0
            for url in [u.strip() for u in urls.splitlines() if u.strip()]:
                if "linkedin.com/jobs/view" not in url: st.warning(f"No parece URL de oferta: {url}"); continue
                m=re.search(r"/jobs/view/(\d+)",url); jid=m.group(1) if m else ""
                o=parse_offer(f"Oferta LinkedIn {jid}\nLinkedIn\n{st.session_state.city}\nPrácticas\nURL: {url}","LinkedIn",url,"linkedin_assisted_url",st.session_state.city,st.session_state.sector_keyword)
                o["title"]=f"Oferta LinkedIn {jid}".strip(); o["company"]="LinkedIn"; o["linkedin_job_id"]=jid; o["confidence_score"]=quality(o); st.session_state.linkedin_offers.append(o); count+=1
            if count: event("linkedin_urls_added",{"count":count}); st.success(f"URLs procesadas: {count}")
        raw=st.text_area("Texto completo de una oferta copiado desde LinkedIn", height=220)
        if st.button("Procesar texto LinkedIn"):
            if len(raw.strip())<30: st.error("Texto demasiado corto.")
            else:
                o=parse_offer(raw,"LinkedIn",None,"linkedin_assisted_text",st.session_state.city,st.session_state.sector_keyword); st.session_state.linkedin_offers.append(o); event("linkedin_text_added",{"title":o.get("title")}); st.success(f"Oferta procesada: {o.get('title')} — {o.get('company')}")
        st.write(f"Ofertas LinkedIn procesadas: **{len(st.session_state.linkedin_offers)}**")
        if st.session_state.linkedin_offers:
            df=pd.DataFrame(st.session_state.linkedin_offers); st.dataframe(df[[c for c in ["title","company","city","capture_mode","confidence_score","processing_status"] if c in df.columns]], use_container_width=True)
        confirm=st.checkbox("Confirmo que he añadido todas las ofertas relevantes visibles en LinkedIn.")
        if st.button("LinkedIn completado — desbloquear fuentes abiertas", disabled=not confirm):
            st.session_state.linkedin_completed=True; event("linkedin_completed_by_user",{"offers":len(st.session_state.linkedin_offers)}); st.success("LinkedIn completado.")

with tabs[3]:
    st.subheader("Fuentes abiertas")
    if not st.session_state.search_started: st.warning("Primero crea una búsqueda.")
    elif not st.session_state.linkedin_completed: st.error("Completa LinkedIn primero.")
    else:
        qs=expanded_queries(st.session_state.sector_keyword, st.session_state.city); maxq=st.slider("Queries",3,min(20,len(qs)),8); maxr=st.slider("Resultados por query",1,10,3)
        with st.expander("Ver queries"): st.write(qs[:maxq])
        if st.button("Ejecutar búsqueda abierta", type="primary"):
            res=[]
            if serpapi_key:
                with st.spinner("Consultando SerpAPI..."):
                    for q in qs[:maxq]:
                        try: res += serpapi(q,serpapi_key,maxr)
                        except Exception as e: st.warning(f"Error en query {q}: {e}")
            else:
                st.info("Sin SERPAPI_API_KEY: uso resultados demo."); res=SAMPLE_OPEN_WEB
            offers=[make_open_offer(r,st.session_state.sector_keyword,st.session_state.city) for r in res]
            st.session_state.open_web_offers=offers; unique,dup=deduplicate(st.session_state.linkedin_offers+offers)
            rejected=[o for o in unique if o.get("processing_status")=="rejected" or o.get("confidence_score",0)<40]; final=[o for o in unique if o not in rejected]
            st.session_state.final_offers=final; st.session_state.duplicates=dup; st.session_state.rejected=rejected; st.session_state.ranked_offers=[]; st.session_state.generated_emails=[]; event("open_web_completed",{"final":len(final),"duplicates":len(dup)}); st.success("Búsqueda abierta completada.")

with tabs[4]:
    st.subheader("Resultados consolidados")
    if not st.session_state.final_offers: st.info("Aún no hay resultados finales.")
    else:
        c1,c2,c3,c4,c5=st.columns(5); c1.metric("LinkedIn",len(st.session_state.linkedin_offers)); c2.metric("Fuentes abiertas",len(st.session_state.open_web_offers)); c3.metric("Duplicados",len(st.session_state.duplicates)); c4.metric("Descartadas",len(st.session_state.rejected)); c5.metric("Únicas",len(st.session_state.final_offers))
        df=pd.DataFrame(st.session_state.final_offers); cols=[c for c in ["title","company","source","city","remote_policy","published_date","confidence_score","source_url"] if c in df.columns]
        st.dataframe(df[cols].sort_values("confidence_score",ascending=False), use_container_width=True); st.download_button("Descargar CSV", df.to_csv(index=False).encode("utf-8"), "ofertas_practicas_consolidadas.csv", "text/csv")

with tabs[5]:
    st.subheader("Ranking CV ↔ ofertas")
    if not st.session_state.cv_text: st.warning("Sube un CV primero.")
    elif not st.session_state.final_offers: st.warning("Genera resultados consolidados primero.")
    else:
        if st.button("Calcular ranking de idoneidad", type="primary"):
            st.session_state.ranked_offers=rank_offers(st.session_state.final_offers, st.session_state.cv_profile, st.session_state.cv_text); st.session_state.generated_emails=[]; event("cv_matching_completed",{"ranked":len(st.session_state.ranked_offers)}); st.success("Ranking calculado.")
        if st.session_state.ranked_offers:
            df=pd.DataFrame(st.session_state.ranked_offers); cols=[c for c in ["fit_score","recommendation","title","company","source","city","matched_skills","matched_languages","gaps","source_url"] if c in df.columns]
            st.dataframe(df[cols], use_container_width=True); st.download_button("Descargar ranking CSV", df.to_csv(index=False).encode("utf-8"), "ranking_idoneidad_cv_ofertas.csv", "text/csv")
            st.markdown("### Top 5")
            for i,o in enumerate(st.session_state.ranked_offers[:5],1):
                with st.expander(f"{i}. {o.get('fit_score')} — {o.get('title')} — {o.get('company')}"):
                    st.write("**Fortalezas:**", o.get("strengths") or "No detectadas")
                    st.write("**Gaps:**", o.get("gaps") or "No detectados")
                    st.write("**URL:**", o.get("source_url"))

with tabs[6]:
    st.subheader("Emails para las 5 mejores ofertas")
    if not st.session_state.cv_text: st.warning("Sube un CV primero.")
    elif not st.session_state.ranked_offers: st.warning("Calcula el ranking primero.")
    else:
        st.caption("Con OPENAI_API_KEY se generan emails con IA. Sin clave, se usa plantilla local.")
        if st.button("Generar emails top 5", type="primary"):
            emails=[]
            with st.spinner("Generando emails..."):
                for o in st.session_state.ranked_offers[:5]:
                    e=ai_email(o,st.session_state.cv_text,openai_key); emails.append({"offer_id":o.get("id"),"fit_score":o.get("fit_score"),"title":o.get("title"),"company":o.get("company"),"subject":e.get("subject"),"body":e.get("body"),"warning":e.get("warning")})
            st.session_state.generated_emails=emails; event("emails_generated",{"emails":len(emails),"openai_used":bool(openai_key)}); st.success("Emails generados.")
        for i,e in enumerate(st.session_state.generated_emails,1):
            with st.expander(f"{i}. {e['fit_score']} — {e['title']} — {e['company']}", expanded=i==1):
                if e.get("warning"): st.warning(e["warning"])
                st.markdown("**Asunto**"); st.code(e["subject"], language="text")
                st.markdown("**Cuerpo**"); st.text_area("Email", e["body"], height=260, key=f"email_{i}")
        if st.session_state.generated_emails:
            df=pd.DataFrame(st.session_state.generated_emails); st.download_button("Descargar emails CSV", df.to_csv(index=False).encode("utf-8"), "emails_top5_candidaturas.csv", "text/csv")

st.divider()
with st.expander("Auditoría"):
    st.json(st.session_state.events)
