"""Source plugins from the 2026-10-16 GitHub scraper integration (user-authorized).

Methods borrowed — all from MIT-licensed repos, reimplemented with stdlib only:
- Lever public Postings API      <- omkarcloud/lever-scraper
                                     (api.lever.co/v0/postings/<slug>?mode=json, no key)
- Greenhouse boards API          <- kalil0321/ats-scrapers
                                     (boards-api.greenhouse.io/v1/boards/<slug>/jobs, no key)
                                     + its ats-companies/ CSVs for the slug directory
- Ashby posting API               <- kalil0321/ats-scrapers
                                     (api.ashbyhq.com/posting-api/job-board/<slug>, no key)
- Hiring.cafe Next.js SSR search  <- nipunsomani/job-forager
                                     (/_next/data/<buildId>/index.json?searchState=..., no key)
- LinkedIn guest-fragment detail  <- ChocoData-com/linkedin-job-scraper
                                     (method noted for future enrichment; not a lane)

Official key-based APIs (skip gracefully when the key env var is absent):
- Reed (reed.co.uk/developers)   -> REED_API_KEY
- Adzuna (developer.adzuna.com)  -> ADZUNA_APP_ID + ADZUNA_APP_KEY
- Jooble (jooble.org)            -> JOOBLE_API_KEY

Dead as of 2026-10-16:
- api.otta.com/v2/jobs -> 404 (Otta merged into Welcome to the Jungle)
- Glassdoor via jobspy -> TLS-blocked from our network + "not available for PAKISTAN"
- jobspy zip_recruiter -> TLS-blocked; jobspy google -> 0 rows; jobspy naukri -> 406 recaptcha
  (only jobspy bayt works -> integrated as jobspy_bayt)

Rejected repos (nothing reusable):
- krautsdubisq1g/ashby-job-scraper: README only, no code
- bnjunge/Remote-Jobs: frontend over the remoteok API (we already have remoteok)
- Gopu2001/Job-Reaper: 2022 selenium GUI app, stale
- orgupdate/Apify-Reed-Jobs-Scraper: Apify-platform actor (Reed official API used instead)

Every fetcher returns [] on any error — one dead source never crashes a sweep.
"""
from __future__ import annotations

import base64
import json
import os
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

# Broad title filter for the ATS lanes (AI-company boards; the main
# filter.py applies the real targeting rules downstream).
_ROLE_SUB = [
    "ai engineer", "artificial intelligence", "ml engineer", "machine learning",
    "llm", "rag", "genai", "generative ai", "prompt", "nlp", "ai developer",
    "ai/ml", "python", "backend", "back-end", "full stack", "full-stack",
    "fullstack", "software engineer", "software developer", "data engineer",
    "data scientist", "chatbot", "conversational", "voice ai", "automation",
    "platform engineer", "site reliability", "frontend", "front-end",
    "mobile", "devops",
]
_FRESH_DAYS = 30


def _stable_id(s) -> str:
    import hashlib
    return hashlib.md5(str(s or "").encode("utf-8")).hexdigest()[:16]


def _get_json(url, timeout=20, headers=None):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _post_json(url, payload, timeout=20, headers=None):
    data = json.dumps(payload).encode()
    h = {"User-Agent": _UA, "Content-Type": "application/json"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _role_ok(title) -> bool:
    t = (title or "").lower()
    return any(s in t for s in _ROLE_SUB)


def _fresh(dt, days=_FRESH_DAYS) -> bool:
    if not dt:
        return True  # keep when date unknown; downstream filter decides
    try:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).days <= days
    except Exception:
        return True


def _parse_dt(v):
    if v is None:
        return None
    try:
        if isinstance(v, (int, float)):
            ts = v / 1000 if v > 1e12 else v
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        s = str(v).strip()
        if not s:
            return None
        s = s.replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _job(source, jid, title, company, url, location=None, remote=False,
         desc=None, posted=None, salary_min=None, salary_max=None,
         salary_unit=None, email=None):
    return {
        "source": source,
        "id": jid,
        "title": title or "",
        "company": company or "",
        "description": desc or "",
        "url": url or "",
        "apply_url": url or "",
        "apply_email": email,
        "location": location or "",
        "remote": bool(remote),
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_unit": salary_unit,
        "posted_at": posted,
        "tags": [],
    }


# ---------------------------------------------------------------------------
# ATS lanes: Greenhouse / Lever / Ashby (curated AI-company slug lists)
# ---------------------------------------------------------------------------

GH_SLUGS = [
    ('AI Foundry', 'aifoundry'),
    ('AMP: AI-Powered Sortation for Waste and Recycling', 'ampsortation'),
    ('ARX Robotics GmbH', 'arxroboticsgmbh'),
    ('Abaka AI', 'abakaai'),
    ('The AI Education Project', 'aiedu'),
    ('AI Squared', 'aisquared'),
    ('Clerk AI', 'clerk-ai'),
    ('FORT Robotics', 'fortrobotics'),
    ('Samaya AI', 'samayaai'),
    ('Apera AI Inc', 'aperaaiinc'),
    ('Maven Robotics', 'mavenrobotics'),
    ('Bluefish AI', 'bluefishai'),
    ('Boosted.ai', 'boostedai'),
    ('Arize AI', 'arizeai'),
    ('LG AI Research', 'lgairesearch'),
    ('Beautiful.ai', 'beautifulai'),
    ('Bedrock Robotics', 'bedrockrobotics'),
    ('Bolo AI', 'boloai'),
    ('C3 AI Ascend Internship Program: Summer 2026', 'c3ascend'),
    ('C3 AI', 'c3iot'),
    ('Cast AI', 'castaigroupinc'),
    ('Clarity AI', 'clarityai'),
    ('Cognite - AI for Industry', 'cognite'),
    ('Covariance.ai', 'covariance'),
    ('Rugged Robotics', 'ruggedrobotics'),
    ('Nimble Robotics', 'nimblerobotics'),
    ('EnCharge AI', 'enchargeai36'),
    ('energytec.ai', 'etec'),
    ('Finster AI', 'finsterai'),
    ('Fireworks AI', 'fireworksai'),
    ('Forma.ai - India Campus', 'formaaiinc3'),
    ('Persefoni AI, Inc.', 'persefoniaiinc'),
    ('Gradient AI', 'gradientai'),
    ('Hume AI', 'humeai'),
    ('Inflection AI', 'inflectionai'),
    ('Interface AI', 'interfaceai'),
    ('JazzX AI', 'jazzx-ai'),
    ('Latitude AI', 'latitude'),
    ('Lightning AI', 'lightningai'),
    ('Nansen.ai', 'nansen'),
    ('Navier AI', 'navierai'),
    ('Neuralink', 'neuralink'),
    ('Oliv AI', 'olivai'),
    ('primer.ai', 'primerai'),
    ('Proton.ai', 'protonai'),
    ('Relyance AI', 'relyance'),
    ('Renewed Vision', 'renewedvision'),
    ('Safari AI', 'safariai'),
    ('Scale AI', 'scaleai'),
    ('Scout AI', 'scoutai'),
    ('Seoul Robotics', 'seoulrobotics'),
    ('Skild AI', 'skildai-careers'),
    ('Snorkel AI', 'snorkelai'),
    ('Uare.ai', 'uareai'),
    ('Symbolica AI', 'symbolica'),
    ('Synthesis Health', 'synthesishealth'),
    ('The Allen Institute for Artificial Intelligence', 'thealleninstitute'),
    ('Together AI', 'togetherai'),
    ('Torc Robotics', 'torcrobotics'),
    ('Vast.ai', 'vastai'),
    ('Workera AI', 'workera'),
    ('Yoodli AI Roleplays', 'yoodliinc'),
    ('Legion Intelligence', 'yurtsai'),
    ('Agility Robotics', 'agilityrobotics'),
    ('AI Alignment Foundation (AIAF)', 'aiaf'),
    ('AI Security Institute', 'aisi'),
    ('Carbon Robotics', 'carbonrobotics'),
    ('Contextual AI', 'contextualai'),
    ('DEFCON AI', 'defcon'),
    ('Diligent Robotics', 'diligentrobotics'),
    ('Dusty Robotics', 'dustyrobotics'),
    ('Forma.ai', 'formaaiinc'),
    ('Future Secure AI', 'futuresecureai'),
    ('Gather AI', 'gatherai'),
    ('Gatik AI', 'gatikaiinc'),
    ('Horace Mann - Agent Opportunities', 'horacemannagents'),
    ('i.AI', 'iai'),
    ('intrinsicrobotics', 'intrinsicrobotics'),
    ('locusrobotics', 'locusrobotics'),
    ('pathrobotics', 'pathrobotics'),
    ('robotsandpencils', 'robotsandpencils'),
    ('swellmedia', 'swellmedia'),
    ('AutogenAI', 'autogenai'),
    ('Cognitiv', 'cognitiv'),
    ('Manifold AI', 'manifoldai'),
    ('Mobi.AI', 'mobi'),
    ('Zest AI', 'zestai'),
]

LV_SLUGS = [
    ('Center for AI Safety', 'aisafety'),
    ('Apex.AI', 'apex-ai'),
    ('Boson AI', 'bosonai'),
    ('ConverseNow.ai', 'ConverseNow'),
    ('Epoch AI', 'epoch-ai'),
    ('GenBio AI', 'genbio'),
    ('Genesis AI', 'genesis-ai'),
    ('Gravis Robotics', 'gravisrobotics'),
    ('Rezolve Ai', 'groupbyinc'),
    ('Horizon Robotics', 'horizon'),
    ('Jupiter Intelligence, Inc.', 'jupiterintel'),
    ('Kenko AI', 'kenko'),
    ('KlearNow.ai', 'klearnow'),
    ('Level AI', 'levelai'),
    ('Mistral AI', 'mistral'),
    ('nEye.ai', 'neye-systems-inc.'),
    ('Pickle Robot Company', 'picklerobot'),
    ('PROCEPT BioRobotics', 'procept-biorobotics'),
    ('Promise Robotics', 'promiserobotics'),
    ('Radical AI', 'RadicalAI'),
    ('Robotics and AI Institute', 'rai'),
    ('Reliable Robotics', 'reliable'),
    ('Robust.ai', 'robust-ai'),
    ('Shield AI', 'shieldai'),
    ('Simbe Robotics', 'SimbeRobotics'),
    ('Spear AI', 'spear-ai'),
    ('Spice AI', 'spiceai'),
    ('SuperAnnotate AI', 'superannotate'),
    ('Synthego', 'synthego'),
    ('Tutor Intelligence', 'tutorintelligence'),
    ('Vision Invest', 'visioninvest'),
    ('WeRide.ai', 'weride'),
    ('Whiterabbit.ai', 'whiterabbit'),
    ('Alloy.ai', 'alloy'),
    ('Autonomous', 'autonomous'),
    ('Humble Robotics', 'humble-robotics'),
    ('Ironflow AI', 'ironflow'),
    ('Kestrel Intelligence', 'kestrel-intelligence'),
    ('nexos.ai', 'Nexos'),
    ('Safran.AI', 'safran-ai'),
    ('Ambi Robotics', 'ambirobotics'),
    ('SwiftLynx AI', 'swiftlynx'),
    ('ChefRobotics', 'ChefRobotics'),
    ('Cobaltrobotics', 'cobaltrobotics'),
    ('Modern Intelligence', 'ModernIntelligence'),
    ('Relay Robotics', 'relayrobotics.com'),
]

AB_SLUGS = [
    ('Adaptive ML', 'adaptive-ml'),
    ('Additive AI', 'additiveai'),
    ('Agent', 'agent'),
    ('Agentio', 'agentio'),
    ('Agentis Capital Advisors', 'agentis-capital-advisors'),
    ('Alex AI', 'alexai'),
    ('Altimate.ai', 'altimate'),
    ('Anam AI', 'anam'),
    ('Arbiter AI', 'arbiter-ai'),
    ('Arena Intelligence, Inc.', 'arena'),
    ('Ataraxis AI', 'ataraxis-ai'),
    ('Axelera AI', 'axelera'),
    ('Basis AI', 'basis-ai'),
    ('Beacon AI', 'beaconai'),
    ('Bifrost AI', 'bifrost'),
    ('Blockit AI', 'blockit'),
    ('Boam AI', 'boam'),
    ('Broccoli AI', 'broccoli'),
    ('Cambio AI Inc.', 'cambio'),
    ('Character.AI', 'character'),
    ('Charge Robotics', 'charge-robotics'),
    ('Citadel AI', 'citadel-ai'),
    ('Cognition', 'cognition'),
    ('Coram AI', 'coram-ai'),
    ('Cortea AI', 'cortea'),
    ('Cosmic Robotics', 'cosmic-robotics'),
    ('Coworker.ai', 'coworker'),
    ('David AI', 'david-ai'),
    ('Dedale Intelligence', 'dedale-intelligence'),
    ('Deductive AI', 'deductive'),
    ('Distyl AI', 'distyl'),
    ('Dyna Robotics', 'dyna-robotics'),
    ('Eloquent AI', 'eloquentai'),
    ('Essential AI', 'essentialai'),
    ('fastino.ai', 'fastino-ai'),
    ('Featherless AI', 'featherlessai'),
    ('Fiddler AI', 'fiddler-ai'),
    ('Hellyeah AI', 'finalroundai'),
    ('Flink Robotics', 'flink'),
    ('Fractional AI', 'fractional-ai'),
    ('Gecko Robotics', 'gecko-robotics'),
    ('The General Intelligence Company of New York', 'generalintelligencecompany'),
    ('GrayMatter Robotics', 'graymatter-robotics'),
    ('Guild.ai', 'guild'),
    ('Hayden AI', 'haydenai'),
    ('Hamming AI', 'hamming ai'),
    ('Horizon3 AI', 'horizon3ai'),
    ('Inferact', 'inferact'),
    ('Inference', 'inference'),
    ('Julius AI', 'julius'),
    ('Junior AI', 'junior'),
    ('CPOHQ + Knoetic AI', 'knoetic'),
    ('Liquid AI', 'liquid-ai'),
    ('MagicSchool AI', 'magicschool'),
    ('Manus AI', 'manusai'),
    ('Mirelo AI', 'mirelo'),
    ('Moonshot AI', 'moonshot-ai'),
    ('Moonvalley AI', 'moonvalley-ai'),
    ('Neural Concept', 'neuralconcept'),
    ('Neuroscale AI', 'neuroscale'),
    ('Norm Ai', 'norm-ai'),
    ('Orchard Robotics', 'orchard'),
    ('P-1 AI', 'p-1 ai'),
    ('Palladio AI', 'palladio'),
    ('Pareto.AI', 'pareto-ai'),
    ('Peec AI', 'peec'),
    ('Physical Intelligence', 'physicalintelligence'),
    ('ProRata.ai', 'prorata'),
    ('Quintess AI', 'quintess-ai'),
    ('Reimagine Robotics, Inc.', 'r2'),
    ('Rad AI', 'radai'),
    ('Raspberry AI', 'raspberry'),
    ('Read AI, Inc.', 'read-ai'),
    ('Reflex Robotics', 'reflexrobotics'),
    ('Relevance AI', 'relevanceai'),
    ('Retell AI', 'retell-ai'),
    ('Revise Robotics', 'reviserobotics'),
    ('Ribbon AI', 'ribbon-ai'),
    ('Robin Ai', 'robin-ai'),
    ('SalesAPE.ai', 'salesape-ai'),
    ('Saris AI', 'saris-ai'),
    ('Scrollmark', 'scrollmark'),
    ('Serif.ai', 'serif'),
    ('Serve Robotics', 'serverobotics'),
    ('Siena AI', 'siena'),
    ('Signal AI', 'signal-ai'),
    ('Slingshot AI', 'slingshotai'),
    ('Spear AI', 'spear-ai'),
    ('Sprout.ai', 'sprout-ai'),
    ('Sully.ai', 'sully-ai'),
    ('Sunday Robotics', 'sunday'),
    ('Sunrise Robotics Corporation', 'sunrise'),
    ('Synthesia', 'synthesia'),
    ('Synthflow AI', 'synthflow'),
    ('TENEX.AI', 'tenex'),
    ('Terra AI', 'terraai'),
    ('TerraFirma Robotics', 'terrafirma'),
    ('Thread AI', 'thread-ai'),
    ('Viggle AI', 'viggle'),
    ('Watney Robotics', 'watneyrobotics'),
    ('Witness AI', 'witnessai'),
    ('Wokelo AI', 'wokelo-ai'),
    ('Wordsmith AI', 'wordsmith'),
    ('AgentMail', 'agentmail'),
    ('Artificial Intelligence Underwriting Company', 'aiuc'),
    ('Arthur Robotics', 'arthur'),
    ('Artificial Analysis, Inc.', 'artificialanalysis'),
    ('Atrix AI', 'atrix'),
    ('Avantos AI', 'avantos'),
    ('Blue AI', 'blue-ai'),
    ('Bretton AI', 'brettonai'),
    ('Brightstar.AI', 'brightstar-ai'),
    ('Build AI', 'build-ai'),
    ('Candid Intelligence', 'candidintelligence'),
    ('Cellular Intelligence', 'cellular-intelligence'),
    ('Clinically AI', 'clinicallyai'),
    ('Coactive AI', 'coactive'),
    ('Company.ai', 'company-ai'),
    ('Conveo.ai', 'conveo'),
    ('Coral AI', 'coralai'),
    ('CYBRET AI', 'cybret'),
    ('Delfa AI', 'delfa'),
    ('Dialogue AI', 'dialogueai'),
    ('Domu AI', 'domu'),
    ('Eleos AI Research', 'eleos'),
    ('Emerald AI', 'emerald-ai'),
    ('Espresso AI', 'espresso'),
    ('Evolve AI Ltd', 'evolve'),
    ('FAR.AI', 'far.ai'),
    ('Farsight AI', 'farsight'),
    ('Fermi AI', 'fermi ai'),
    ('Air Space Intelligence', 'airspace-intelligence.com'),
    ('Allminds', 'allminds'),
    ('Ambient.ai', 'ambient.ai'),
    ('Anyone AI', 'anyone-ai'),
    ('Asari AI', 'asari.ai'),
    ('Foundry Robotics Inc.', 'foundry-robotics'),
    ('FutureFit AI', 'futurefitai'),
    ('GC AI', 'gc-ai'),
    ('Genesis Molecular AI', 'genesis-molecular-ai'),
    ('Geordie AI', 'geordieai'),
    ('Goodie AI', 'goodie-ai'),
    ('Grand Intelligence', 'grand'),
    ('Gritt Robotics Inc', 'gritt'),
    ('Grotto AI', 'grotto'),
    ('GrowthX AI', 'growthx ai'),
    ('Happyrobot Inc.', 'happyrobot.ai'),
    ('Harmattan AI', 'harmattan-ai'),
    ('Harrison.ai', 'harrison.ai'),
    ('Hebbia AI', 'hebbia-ai'),
    ('Helm.ai', 'helm-ai'),
    ("Hilbert's AI", 'hilberts'),
    ('Hippocratic AI', 'hippocratic ai'),
    ('imper.ai', 'imper'),
    ('Ineffable Intelligence', 'ineffable'),
    ('Jampack AI', 'jampack-ai'),
    ('Jerry.ai', 'jerry.ai'),
    ('Kamiwaza AI', 'kamiwaza'),
    ('Bedrock Robotics Inc', 'bedrock-robotics'),
    ('Linda AI', 'linda'),
    ('LiteLLM', 'litellm'),
    ('Loki Robotics', 'loki'),
    ('Lotus Health AI', 'lotushealth'),
    ('Lovelace AI', 'lovelace'),
    ('Mind Robotics', 'mindrobotics'),
    ('Machine Intelligence Research Institute', 'miri'),
    ('Manex AI GmbH', 'manex'),
    ('Matter Intelligence', 'matter-intelligence'),
    ('Mirai Robotics', 'mirai-robotics'),
    ('Myriad AI', 'myriad-ai'),
    ('Nace AI', 'nace.ai'),
    ('Navi AI', 'navi'),
    ('nexos.ai', 'nexos-ai'),
    ('Nexus Cognitive Technologies', 'nexus-cognitive'),
    ('Nightfall AI', 'nightfall-ai'),
    ('NODA AI', 'noda-ai'),
    ('Nova Intelligence', 'novaintelligence'),
    ('Novita AI', 'novita-ai'),
    ('Numos AI, inc.', 'numosai'),
    ('Omada.ai', 'omadaai'),
    ('OpenArt AI', 'openart'),
    ('Pano AI', 'pano-ai'),
    ('Prosper AI', 'prosper-ai'),
    ('Clearly AI', 'clearly-ai'),
    ('Corvus Robotics', 'corvus-robotics'),
    ('Credo.AI', 'credo.ai'),
    ('Physical Superintelligence', 'psi'),
    ('Pivot Robotics', 'pivotrobotics'),
    ('Preql AI', 'preql'),
    ('Protex AI', 'protex ai'),
    ('Pytho AI', 'pytho-ai'),
    ('QED.ai', 'qed-ai'),
    ('Raylu AI', 'raylu-ai'),
    ('Reliable Robotics Corporation', 'reliable-robotics'),
    ('Remedy Robotics', 'remedyrobotics'),
    ('Resolve AI', 'resolve ai'),
    ('Rhoda AI', 'rhoda-ai'),
    ('Ricursive Intelligence', 'ricursive intelligence'),
    ('The Robot Learning Company', 'robot-learning-co'),
    ('Roots AI', 'roots-automation'),
    ('Seven AI', 'sevenai'),
    ('Simon AI', 'simondata'),
    ('Simple AI', 'simple-ai'),
    ('Spacial AI', 'spacial'),
    ('Starpath Robotics', 'starpath.space'),
    ('Stay AI', 'stayai'),
    ('Stratum AI', 'stratum-ai'),
    ('Symmetry AI', 'symmetry'),
    ('Synthetic', 'synthetic'),
    ('Tavrn.ai', 'tavrn'),
    ('Teton.ai', 'teton'),
    ('Titan AI', 'titan-ai'),
    ('Tonic AI', 'tonicai'),
    ('Tray.ai', 'tray-ai'),
    ('Trexo Robotics', 'trexo robotics'),
    ('Tribe AI', 'tribe-ai'),
    ('Tycho.AI', 'tycho-ai'),
    ('Union.ai', 'union'),
    ('Uniti AI', 'uniti'),
    ('kos.ai', 'kos.ai'),
    ('Vic.ai', 'vic.ai'),
    ('Viz.ai', 'viz.ai'),
    ('Bild AI', 'bild-ai'),
    ('Yuma AI', 'yumaai'),
    ('Zeit AI (YC S24)', 'zeit-ai'),
]


def _gh_board(args):
    name, slug = args
    try:
        data = _get_json(
            f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true")
    except Exception:
        return []
    out = []
    for j in data.get("jobs") or []:
        title = j.get("title") or ""
        if not _role_ok(title):
            continue
        posted = _parse_dt(j.get("first_published") or j.get("updated_at"))
        if not _fresh(posted):
            continue
        loc = (j.get("location") or {}).get("name", "") if isinstance(
            j.get("location"), dict) else str(j.get("location") or "")
        desc = re.sub(r"<[^>]+>", " ", j.get("content") or "")
        desc = re.sub(r"\s+", " ", desc).strip()[:4000]
        out.append(_job(
            "ats_greenhouse", f"gh-{slug}-{j.get('id')}", title, name,
            j.get("absolute_url") or f"https://job-boards.greenhouse.io/{slug}",
            location=loc,
            remote=bool(re.search(r"\bremote\b", loc + " " + desc, re.I)),
            desc=desc, posted=posted))
    return out


def fetch_ats_greenhouse() -> list[dict]:
    """Greenhouse boards of ~87 AI companies (public boards API, no key)."""
    jobs = []
    try:
        with ThreadPoolExecutor(max_workers=8) as ex:
            for rows in ex.map(_gh_board, GH_SLUGS):
                jobs.extend(rows)
    except Exception:
        pass
    return jobs


def _lv_board(args):
    name, slug = args
    out = []
    for host in ("api.lever.co", "api.eu.lever.co"):
        try:
            data = _get_json(f"https://{host}/v0/postings/{slug}?mode=json")
            break
        except Exception:
            data = None
    if not data:
        return []
    items = data if isinstance(data, list) else data.get("postings") or []
    for j in items:
        title = j.get("text") or ""
        if not _role_ok(title):
            continue
        posted = _parse_dt(j.get("createdAt"))
        if not _fresh(posted):
            continue
        cats = j.get("categories") or {}
        loc = cats.get("location") or ""
        desc = re.sub(r"<[^>]+>", " ", j.get("description") or "")
        desc = re.sub(r"\s+", " ", desc).strip()[:4000]
        out.append(_job(
            "ats_lever", f"lv-{slug}-{j.get('id')}", title, name,
            j.get("hostedUrl") or j.get("applyUrl") or f"https://jobs.lever.co/{slug}",
            location=loc,
            remote=bool(re.search(r"\bremote\b", loc + " " + desc, re.I)),
            desc=desc, posted=posted))
    return out


def fetch_ats_lever() -> list[dict]:
    """Lever boards of ~46 AI companies (public postings API, no key)."""
    jobs = []
    try:
        with ThreadPoolExecutor(max_workers=8) as ex:
            for rows in ex.map(_lv_board, LV_SLUGS):
                jobs.extend(rows)
    except Exception:
        pass
    return jobs


def _ab_board(args):
    name, slug = args
    try:
        data = _get_json(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    except Exception:
        return []
    out = []
    for j in data.get("jobs") or []:
        title = j.get("title") or ""
        if not _role_ok(title):
            continue
        posted = _parse_dt(j.get("publishedAt"))
        if not _fresh(posted):
            continue
        loc = j.get("locationName") or ""
        desc = re.sub(r"<[^>]+>", " ", j.get("descriptionHtml") or j.get("descriptionPlain") or "")
        desc = re.sub(r"\s+", " ", desc).strip()[:4000]
        comp = None
        org = j.get("organizationName") or j.get("organizationHost")
        out.append(_job(
            "ats_ashby", f"ab-{slug}-{j.get('id')}", title, name,
            j.get("jobUrl") or f"https://jobs.ashbyhq.com/{slug}",
            location=loc,
            remote=bool(re.search(r"\bremote\b", loc + " " + desc, re.I)),
            desc=desc, posted=posted))
    return out


def fetch_ats_ashby() -> list[dict]:
    """Ashby boards of ~225 AI companies (public posting API, no key)."""
    jobs = []
    try:
        with ThreadPoolExecutor(max_workers=8) as ex:
            for rows in ex.map(_ab_board, AB_SLUGS):
                jobs.extend(rows)
    except Exception:
        pass
    return jobs


# ---------------------------------------------------------------------------
# Official key APIs (skip gracefully without keys)
# ---------------------------------------------------------------------------

def fetch_reed() -> list[dict]:
    """Reed.co.uk official API. Needs REED_API_KEY env var."""
    key = os.environ.get("REED_API_KEY", "").strip()
    if not key:
        return []
    jobs = []
    try:
        creds = base64.b64encode(f"{key}:".encode()).decode()
        headers = {"User-Agent": _UA, "Authorization": f"Basic {creds}"}
        for kw in ["AI Engineer", "Machine Learning Engineer", "Python Developer"]:
            q = urllib.parse.urlencode({
                "keywords": kw, "locationName": "Remote",
                "resultsToTake": 50, "resultsToSkip": 0})
            data = _get_json(f"https://www.reed.co.uk/api/1.0/search?{q}",
                             headers=headers)
            for r in data.get("results") or []:
                title = r.get("jobTitle") or ""
                posted = _parse_dt(r.get("date"))
                if not _fresh(posted):
                    continue
                jobs.append(_job(
                    "reed", f"reed-{r.get('jobId')}", title,
                    r.get("employerName"), r.get("jobUrl"),
                    location=r.get("locationName"),
                    remote=True, posted=posted,
                    salary_min=r.get("minimumSalary"),
                    salary_max=r.get("maximumSalary"),
                    salary_unit="year" if r.get("currency") == "GBP" else None))
    except Exception:
        return []
    return jobs


def fetch_adzuna() -> list[dict]:
    """Adzuna official API (UK). Needs ADZUNA_APP_ID + ADZUNA_APP_KEY."""
    app_id = os.environ.get("ADZUNA_APP_ID", "").strip()
    app_key = os.environ.get("ADZUNA_APP_KEY", "").strip()
    if not (app_id and app_key):
        return []
    jobs = []
    try:
        for kw in ["AI Engineer", "Machine Learning Engineer", "Python Developer"]:
            q = urllib.parse.urlencode({
                "app_id": app_id, "app_key": app_key,
                "results_per_page": 50, "what": kw,
                "sort_by": "date", "max_days_old": 30})
            data = _get_json(
                f"https://api.adzuna.com/v1/api/jobs/gb/search/1?{q}")
            for r in data.get("results") or []:
                comp = r.get("company") or {}
                loc = r.get("location") or {}
                desc = r.get("description") or ""
                jobs.append(_job(
                    "adzuna", f"adz-{_stable_id(r.get('redirect_url'))}",
                    r.get("title"), comp.get("display_name"),
                    r.get("redirect_url"),
                    location=loc.get("display_name"),
                    remote=bool(re.search(r"\bremote\b", desc, re.I)),
                    desc=desc[:4000], posted=_parse_dt(r.get("created")),
                    salary_min=r.get("salary_min"),
                    salary_max=r.get("salary_max"), salary_unit="year"))
    except Exception:
        return []
    return jobs


def fetch_jooble() -> list[dict]:
    """Jooble official API. Needs JOOBLE_API_KEY env var."""
    key = os.environ.get("JOOBLE_API_KEY", "").strip()
    if not key:
        return []
    jobs = []
    try:
        for kw, loc in [("AI Engineer", "United Kingdom"),
                        ("Python Developer", "United Kingdom"),
                        ("Machine Learning Engineer", "Remote")]:
            data = _post_json(f"https://jooble.org/api/{key}",
                              {"keywords": kw, "location": loc})
            for r in data.get("jobs") or []:
                title = r.get("title") or ""
                jobs.append(_job(
                    "jooble", f"joob-{_stable_id(r.get('link'))}", title,
                    r.get("company"), r.get("link"),
                    location=r.get("location"),
                    remote=bool(re.search(r"\bremote\b",
                                          (r.get("location") or "") + " " + (r.get("snippet") or ""),
                                          re.I)),
                    desc=(r.get("snippet") or "")[:4000],
                    posted=_parse_dt(r.get("updated"))))
    except Exception:
        return []
    return jobs


# ---------------------------------------------------------------------------
# Hiring.cafe (unofficial Next.js SSR endpoint; pattern from job-forager, MIT)
# ---------------------------------------------------------------------------

_HC_HEADERS = {
    "User-Agent": _UA,
    "Accept": "*/*",
    "Referer": "https://hiring.cafe/",
    "x-nextjs-data": "1",
}
_HC_BUILD = None


def _hc_build_id():
    global _HC_BUILD
    if _HC_BUILD:
        return _HC_BUILD
    for bid in ("rNM3CB7RcWaQ3BT2siD_a", "BSfMOoCHeSpj01n-FYLak"):
        url = f"https://hiring.cafe/_next/data/{bid}/index.json?searchState=%7B%7D"
        try:
            req = urllib.request.Request(url, headers=_HC_HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp.read()
            _HC_BUILD = bid
            return bid
        except urllib.error.HTTPError as e:
            if e.code == 404:
                m = re.search(r'"buildId":"([^"]+)"',
                              e.read().decode("utf-8", "replace"))
                if m and m.group(1) != bid:
                    _HC_BUILD = m.group(1)
                    return _HC_BUILD
        except Exception:
            continue
    return None


def fetch_hiringcafe() -> list[dict]:
    """Hiring.cafe remote AI/software jobs (unofficial SSR endpoint, no key)."""
    bid = _hc_build_id()
    if not bid:
        return []
    jobs = []
    try:
        for kw in ["AI Engineer", "Machine Learning Engineer", "Python Developer"]:
            state = urllib.parse.quote(json.dumps(
                {"searchQuery": kw, "workplaceTypes": ["remote"]}))
            url = f"https://hiring.cafe/_next/data/{bid}/index.json?searchState={state}"
            req = urllib.request.Request(url, headers=_HC_HEADERS)
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8", "replace")
            # The endpoint now returns HTML with SSR data embedded in
            # __NEXT_DATA__ (props.pageProps.ssrHits).
            m = re.search(
                r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
                body, re.S)
            if not m:
                continue
            try:
                data = json.loads(m.group(1))
            except Exception:
                continue
            hits = (data.get("props", {}).get("pageProps") or {}).get("ssrHits") or []
            for j in hits:
                v5 = j.get("v5_processed_job_data") or {}
                info = j.get("job_information") or {}
                title = (j.get("title") or v5.get("core_job_title")
                         or info.get("job_title_raw") or "")
                if not _role_ok(title):
                    continue
                company = (v5.get("company_name")
                           or (j.get("enriched_company_data") or {}).get("name")
                           or j.get("board_token") or "")
                loc = v5.get("formatted_workplace_location") or ""
                wt = str(v5.get("workplace_type") or "").lower()
                jobs.append(_job(
                    "hiringcafe", f"hc-{j.get('id')}", title, company,
                    j.get("apply_url") or j.get("job_url") or "https://hiring.cafe/",
                    location=loc, remote=(wt == "remote"),
                    desc=str(v5.get("description") or "")[:4000],
                    posted=_parse_dt(j.get("posted_at") or v5.get("posted_date")),
                    salary_min=v5.get("yearly_min_compensation"),
                    salary_max=v5.get("yearly_max_compensation"),
                    salary_unit="year"))
    except Exception:
        return []
    return jobs


# ---------------------------------------------------------------------------
# jobspy extra modules (already installed; we only used linkedin + indeed_pk)
# ---------------------------------------------------------------------------

def fetch_jobspy_extra() -> list[dict]:
    """Bayt via jobspy (works from our network; company/location parsed from URL).

    Tested 2026-10-16: zip_recruiter = TLS-blocked, google = 0 rows,
    naukri = 406 recaptcha, glassdoor = TLS-blocked + no Pakistan support.
    """
    try:
        from jobspy import scrape_jobs
    except Exception:
        return []
    jobs = []
    terms = ["AI Engineer", "Python Developer", "Machine Learning Engineer"]
    for term in terms:
        try:
            df = scrape_jobs(site_name=["bayt"], search_term=term,
                             location="Pakistan", results_wanted=20,
                             hours_old=720)
        except Exception:
            continue
        for _, r in df.iterrows():
            desc = str(r.get("description") or "")
            url = str(r.get("job_url") or "")
            m = re.search(r"bayt\.com/en/([^/]+)/jobs/", url)
            loc = m.group(1).replace("-", " ").title() if m else ""
            jobs.append(_job(
                "jobspy_bayt", f"js-bayt-{r.get('id') or _stable_id(url)}",
                str(r.get("title") or ""), str(r.get("company") or ""),
                url, location=loc,
                remote=bool(re.search(r"\bremote\b", loc + " " + desc, re.I)),
                desc=desc[:4000], posted=_parse_dt(r.get("date_posted"))))
    return jobs


FETCHERS = {
    "ats_greenhouse": fetch_ats_greenhouse,
    "ats_lever": fetch_ats_lever,
    "ats_ashby": fetch_ats_ashby,
    "reed": fetch_reed,
    "adzuna": fetch_adzuna,
    "jooble": fetch_jooble,
    "hiringcafe": fetch_hiringcafe,
    "jobspy_bayt": fetch_jobspy_extra,
}


if __name__ == "__main__":
    import sys
    names = sys.argv[1:] or list(FETCHERS)
    for name in names:
        fn = FETCHERS[name]
        try:
            rows = fn()
            print(f"{name}: {len(rows)} jobs", flush=True)
            if rows:
                r = rows[0]
                print(f"  sample: {r['title']!r} @ {r['company']!r} | {r['location']!r} | {r['posted_at']}")
        except Exception as e:
            print(f"{name}: ERROR {type(e).__name__}: {e}")
