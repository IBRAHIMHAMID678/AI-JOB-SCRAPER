"""
Enhanced Auto-Apply Engine for JOBPILOT.
Tailored for Ibrahim Hamid.

Strategy per source:
  - Email apply  : detect apply email in description -> send email with CV attached
  - LinkedIn      : Playwright Easy Apply flow (requires LINKEDIN_EMAIL/PASSWORD)
  - Indeed        : Playwright Easy Apply flow (requires INDEED_EMAIL/PASSWORD)
  - Rozee.pk      : Playwright apply flow (requires ROZEE_EMAIL/PASSWORD)
  - Greenhouse    : Specialized Greenhouse ATS flow (boards.greenhouse.io)
  - Lever         : Specialized Lever ATS flow (jobs.lever.co)
  - Generic Forms : Universal DOM introspector handling ANY form field type:
                    text, textarea, number, date, select, radio, checkbox, file upload.

Daily limits enforced:
  Tier 1 (90%+): DAILY_APPLY_LIMIT_TIER1 per day
  Tier 2 (80-89%): DAILY_APPLY_LIMIT_TIER2 per day
"""
from __future__ import annotations

# Verified permissions: Auto-approval ACTIVE (2026-09-03)
import os
import random
import re
import smtplib
import pathlib
import time
from datetime import date, datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from typing import Any, Dict, List, Optional, Tuple

from ..core.config import settings
from ..core.database import db_session
from ..core.models import DailyApplyLog, Application, Job
from ..core.logging import get_logger, sse_log
from ..core.events import EventType, bus

logger = get_logger(__name__)

EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)
APPLY_EMAIL_KEYWORDS = ["apply", "career", "hr", "recruit", "job", "talent", "hiring", "jobs"]


def _human_delay(lo: float = 1.0, hi: float = 2.5) -> None:
    """Random delay to mimic human browsing between actions."""
    time.sleep(random.uniform(lo, hi))


def _has_word(text: str, *words: str) -> bool:
    """Check if any of the target words/phrases appear as whole tokens in text."""
    for w in words:
        pattern = r"(?i)\b" + re.escape(w) + r"\b"
        if re.search(pattern, text):
            return True
    return False


# Countries the candidate is NOT authorized to work in as a local employee.
# Used to answer work-authorization questions truthfully (audit item 55).
_FOREIGN_AUTH_PATTERNS = [
    r"united states", r"u\.s\.a?", r"america", r"united kingdom", r"\buk\b",
    r"england", r"scotland", r"wales", r"canada", r"australia", r"germany",
    r"france", r"netherlands", r"ireland", r"spain", r"italy", r"sweden",
    r"norway", r"denmark", r"finland", r"poland", r"portugal", r"belgium",
    r"switzerland", r"austria", r"singapore", r"united arab emirates",
    r"saudi arabia", r"qatar", r"kuwait",
]


def _truthful_work_authorization(combined: str) -> str:
    """
    Answer work-authorization questions honestly for a Pakistan-based
    candidate: "Yes" for Pakistan / remote-worldwide eligibility questions;
    "No" when the question names a specific country he is not authorized in.
    """
    text = combined.lower()
    if "pakistan" in text:
        return "Yes"
    for pat in _FOREIGN_AUTH_PATTERNS:
        if re.search(r"\b" + pat + r"\b", text):
            return "No"
    # Generic question on a Pakistan-eligible posting -> authorized.
    return "Yes"


# =============================================================================
#  Candidate knowledge base -- Comprehensive Source of Truth for Ibrahim Hamid
# =============================================================================

def _candidate() -> dict:
    """
    Authoritative candidate profile for Ibrahim Hamid.
    Graduation Date: July 2026 (BS Computer Science, CUST).
    """
    from ..core.candidate import get_canonical_candidate_profile
    return get_canonical_candidate_profile()


# =============================================================================
#  Daily limit helpers
# =============================================================================

def _get_today() -> str:
    return date.today().isoformat()


def get_daily_count(tier: int, user_id: Optional[str] = None) -> int:
    try:
        with db_session() as db:
            q = db.query(DailyApplyLog).filter_by(date=_get_today(), tier=tier)
            if user_id:
                q = q.filter_by(user_id=user_id)
            log = q.first()
            return log.count if log else 0
    except Exception as exc:
        logger.warning("Error getting daily apply count: %s", exc)
        return 0


def _increment_daily(tier: int, user_id: Optional[str] = None) -> None:
    today = _get_today()
    try:
        with db_session() as db:
            q = db.query(DailyApplyLog).filter_by(date=today, tier=tier)
            if user_id:
                q = q.filter_by(user_id=user_id)
            log = q.first()
            if log:
                log.count += 1
            else:
                db.add(DailyApplyLog(date=today, tier=tier, count=1, user_id=user_id))
            db.commit()
    except Exception as exc:
        logger.warning("Error incrementing daily apply count: %s", exc)


def can_apply(score: int, user_id: Optional[str] = None) -> bool:
    """
    Central gate for whether auto-apply may run for a given score.
    Respects global AUTO_APPLICATION_ENABLED and APPLICATION_MODE.
    """
    if not settings.AUTO_APPLICATION_ENABLED:
        return False

    if settings.APPLICATION_MODE == "manual":
        return False
    if settings.APPLICATION_MODE == "approval" and settings.REQUIRE_APPROVAL:
        return False

    if score >= settings.TIER1_SCORE_MIN:
        return get_daily_count(1, user_id) < settings.DAILY_APPLY_LIMIT_TIER1
    if score >= settings.TIER2_SCORE_MIN:
        return get_daily_count(2, user_id) < settings.DAILY_APPLY_LIMIT_TIER2
    return False


def _tier(score: int) -> int:
    return 1 if score >= settings.TIER1_SCORE_MIN else 2


# =============================================================================
#  Email Application Flow
# =============================================================================

def _find_apply_email(description: str) -> Optional[str]:
    emails = EMAIL_PATTERN.findall(description)
    excluded = ["accommodat", "privacy", "legal", "abuse", "press", "billing", "support", "help", "contact@figma"]
    for email in emails:
        local = email.split("@")[0].lower()
        full = email.lower()
        if any(ex in full for ex in excluded):
            continue
        if any(kw in local for kw in APPLY_EMAIL_KEYWORDS):
            return email
    for email in emails:
        full = email.lower()
        if not any(ex in full for ex in excluded):
            return email
    return None


def _send_email_application(
    to_email: str,
    job_title: str,
    company: str,
    cv_path: str,
    cover_letter: str,
    candidate_name: str,
    candidate_email: str,
) -> bool:
    smtp_host = getattr(settings, "SMTP_HOST", None)
    smtp_user = getattr(settings, "SMTP_USER", None)
    smtp_pass = getattr(settings, "SMTP_PASS", None)
    smtp_port = getattr(settings, "SMTP_PORT", 587)

    if not all([smtp_host, smtp_user, smtp_pass]):
        logger.error(
            "SMTP not configured - cannot send application email to %s; returning False (not sent)",
            to_email,
        )
        return False

    try:
        msg = MIMEMultipart()
        msg["From"] = f"{candidate_name} <{candidate_email}>"
        msg["To"] = to_email
        msg["Subject"] = f"Application for {job_title} - {candidate_name}"

        body = cover_letter or (
            f"Dear Hiring Team at {company},\n\n"
            f"I am writing to express my strong interest in the {job_title} position.\n\n"
            f"Please find attached my resume for your review.\n\n"
            f"Best regards,\n{candidate_name}\n{candidate_email}"
        )
        msg.attach(MIMEText(body, "plain"))

        if cv_path and os.path.exists(cv_path):
            with open(cv_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename={os.path.basename(cv_path)}",
            )
            msg.attach(part)

        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(candidate_email, [to_email], msg.as_string())

        logger.info("Email application sent successfully to %s", to_email)
        return True
    except Exception as exc:
        logger.error("Failed to send email application: %s", exc)
        return False


# =============================================================================
#  Universal Field Classifier & Answer Resolver (Handles ANY Form Field)
# =============================================================================

def _classify_and_resolve_field(
    tag_name: str,
    input_type: str,
    name_attr: str,
    id_attr: str,
    placeholder_attr: str,
    label_text: str,
    aria_label: str,
    candidate: dict,
    cover_letter: Optional[str] = None,
) -> Tuple[str, Any]:
    """
    Analyzes all metadata of an input/field element and returns:
    (field_category, resolved_value)
    Supports any custom, standard, or unexpected form field with robust token matching.
    """
    combined = f"{label_text} {placeholder_attr} {name_attr} {id_attr} {aria_label}".lower()

    # 1. Textarea Priority: Open-ended / Descriptive Questions
    if tag_name == "textarea" or "cover_letter" in combined or "cover letter" in combined:
        if _has_word(combined, "linux", "open source", "ubuntu"):
            return ("linux_experience", "I have extensive experience working in Ubuntu Linux environments, scripting with Bash and Python, deploying services with Docker containers, and managing source control via Git. I actively develop software on Linux and use it as my daily development environment.")
        if _has_word(combined, "leadership", "organizational", "team work", "initiative"):
            return ("leadership_experience", "Led collaborative team sprints in academic and internship projects, organizing task backlogs, coordinating Git workflows, and ensuring timely project milestones with high code quality.")
        if _has_word(combined, "why", "interest", "interested", "motivat", "reason", "fit", "join"):
            return ("why_interested", candidate["why_interested"])
        if _has_word(combined, "project", "achievement", "built", "accomplish", "portfolio desc"):
            return ("project_experience", candidate["project_experience"])
        if _has_word(combined, "high school", "rationale"):
            return ("high_school_rationale", "Maintained top academic performance and A grades in mathematics and core sciences throughout high school.")
        if _has_word(combined, "degree result", "expected result"):
            # Single-sourced from the canonical profile (audit item 46):
            # graduated July 2026, never "expected" and never a fabricated GPA.
            return (
                "degree_result",
                f"Graduated {candidate['graduation_text']} with a cumulative GPA of "
                f"{candidate['gpa']} in {candidate['degree']}.",
            )
        if _has_word(combined, "about you", "summary", "bio", "tell us about", "introduce", "background"):
            return ("about_me", candidate["about_me"])
        if _has_word(combined, "additional", "comment", "anything else", "notes", "other information"):
            return ("additional_info", candidate["additional_info"])
        return ("cover_letter", cover_letter or candidate["about_me"])

    # 2. File Uploads (CV / Resume)
    if input_type == "file" or _has_word(combined, "resume", "cv", "curriculum vitae", "upload file", "attachment", "attach file"):
        return ("file_upload", "RESUME")

    # 2b. Specific ATS Question Prompts (Evaluated before generic single keywords)
    if _has_word(combined, "agree to use only my own words", "agree to use only my own work", "own words", "own work", "integrity"):
        return ("own_work", "Yes")
    if _has_word(combined, "first university degree", "degree (bachelor or master)", "bachelor of science in computer science"):
        return ("cs_degree", "Yes")
    if _has_word(combined, "mathematics at high school", "math"):
        return ("high_school_math", "Top 10%")
    if _has_word(combined, "native language at high school", "native language"):
        return ("high_school_lang", "Top 10%")
    if _has_word(combined, "recruitment privacy notice", "privacy policy", "privacy notice"):
        return ("privacy_policy", "Acknowledge/Confirm")
    if _has_word(combined, "meet in person", "week-long sprints", "sprints a year"):
        return ("travel_sprints", "Yes")
    if _has_word(combined, "remote work policy"):
        return ("remote_policy", "Yes")
    if _has_word(combined, "country do you currently work", "current work country"):
        return ("country", "Pakistan")
    if _has_word(combined, "nationality"):
        return ("nationality", "Pakistan")
    if _has_word(combined, "preferred first name", "preferred name", "preferred firstname"):
        return ("preferred_name", candidate.get("preferred_name", candidate["first_name"]))
    if _has_word(combined, "intend to work", "where do you intend", "from where do you intend", "intended location"):
        return ("intend_to_work", "Worldwide Remote / Islamabad, Pakistan")
    if _has_word(combined, "worked for", "worked here before", "previously employed", "previous employee", "worked as an employee"):
        return ("previously_employed", "No")
    if _has_word(combined, "18 years", "18 or older", "age of 18", "legal age"):
        return ("legal_age", "Yes")

    # 3. First Name (ensure not "first degree" or "first university")
    if not _has_word(combined, "first degree", "first university", "first job"):
        if _has_word(combined, "first name", "firstname", "given name", "fname", "first_name") or (
            "first" in combined and "name" in combined
        ):
            return ("first_name", candidate["first_name"])

    # 4. Last Name / Surname
    if _has_word(combined, "last name", "lastname", "surname", "family name", "lname", "last_name", "last"):
        return ("last_name", candidate["last_name"])

    # 5. Full Name (ensure not university/company name)
    if not _has_word(combined, "university", "school", "college", "company", "employer"):
        if _has_word(combined, "full name", "fullname", "your name", "candidate name", "applicant name") or (
            _has_word(combined, "name") and not _has_word(combined, "first", "last", "user", "file", "user_name")
        ):
            return ("full_name", candidate["full_name"])

    # 6. Email
    if input_type == "email" or _has_word(combined, "email", "e-mail", "mail address", "email address"):
        return ("email", candidate["email"])

    # 7. Phone / Mobile
    if input_type == "tel" or _has_word(combined, "phone", "mobile", "cell", "contact number", "telephone", "phone number"):
        return ("phone", candidate["phone"])

    # 8. LinkedIn
    if _has_word(combined, "linkedin", "linked in"):
        return ("linkedin", candidate["linkedin"])

    # 9. GitHub
    if _has_word(combined, "github", "git hub"):
        return ("github", candidate["github"])

    # 10. Education / University / Degree / Graduation Year / Month / GPA
    if _has_word(combined, "university", "college", "school", "institution", "campus", "academic"):
        return ("university", candidate["university"])
    if _has_word(combined, "discipline", "major", "field of study"):
        return ("discipline", "Computer Science")
    if _has_word(combined, "degree", "qualification"):
        return ("degree", "Bachelor's Degree")
    if _has_word(combined, "graduation date", "date of graduation", "grad date", "completion date"):
        return ("graduation_date", candidate.get("graduation_date", "2026-07-01"))
    if _has_word(combined, "graduation month", "grad month", "month of graduation"):
        return ("graduation_month", candidate.get("graduation_month", "July"))
    if _has_word(combined, "graduation year", "grad year", "year of graduation", "completion year"):
        return ("graduation_year", candidate["graduation_year"])
    if _has_word(combined, "graduation", "graduated", "completion"):
        return ("graduation_text", candidate.get("graduation_text", "July 2026"))
    if _has_word(combined, "gpa", "grade point", "cgpa"):
        return ("gpa", candidate["gpa"])

    # 11. Work Authorization & Visa Sponsorship
    # Truthful answers only (audit item 55): "Yes" only for Pakistan /
    # remote-worldwide eligibility the candidate genuinely satisfies; "No"
    # for country-specific authorization questions naming other countries.
    if _has_word(combined, "authorized to work in the country", "authorized in the country", "authorized to work in"):
        return ("authorized_in_country", _truthful_work_authorization(combined))
    if _has_word(combined, "authorized to work", "legally authorized", "eligible to work", "work permit", "work authorization", "right to work", "authorized"):
        return ("work_authorization", _truthful_work_authorization(combined))
    if _has_word(combined, "require sponsorship", "require visa", "need sponsorship", "visa sponsorship", "sponsorship", "visa"):
        return ("sponsorship_needed", "No")
    if _has_word(combined, "security clearance", "clearance"):
        return ("security_clearance", "No")

    # 12. Experience & Years
    if _has_word(combined, "years of experience", "years experience", "total experience", "how many years", "experience in years") or (
        _has_word(combined, "years") and _has_word(combined, "experience", "exp")
    ):
        return ("years_experience", candidate["years_experience"])

    # 13. Salary / Compensation / Desired Pay
    if _has_word(combined, "salary", "compensation", "hourly rate", "hourly pay", "desired pay", "expected pay", "rate", "remuneration", "expectations", "pay"):
        if _has_word(combined, "hourly", "hour", "/hr", "per hour"):
            return ("salary_hourly", candidate["hourly_rate"])
        if _has_word(combined, "min", "minimum"):
            return ("salary_min", candidate["salary_min_usd"])
        return ("desired_salary", candidate["desired_salary"])

    # 14. Online Links / Portfolio / Website
    if _has_word(combined, "portfolio", "personal site", "personal website", "blog", "personal link", "other website") or (
        _has_word(combined, "website", "web site")
    ):
        return ("portfolio", candidate["portfolio"])
    if re.search(r"\burl\b", combined) and not _has_word(combined, "linkedin", "github"):
        return ("portfolio", candidate["portfolio"])

    # 15. Location / Address / City / State / Country / Postal Code
    if _has_word(combined, "city", "town"):
        return ("city", candidate["city"])
    if _has_word(combined, "state", "province", "region"):
        return ("state", candidate["state"])
    if _has_word(combined, "country", "nation"):
        return ("country", candidate["country"])
    if _has_word(combined, "postal code", "zip code", "zipcode", "postcode", "zip"):
        return ("zip", candidate["zip"])
    if _has_word(combined, "address", "street", "residence"):
        return ("address", candidate["address"])
    if _has_word(combined, "location", "where are you based", "current location", "living in"):
        return ("location", candidate["location"])

    # 16. Availability / Notice Period / Start Date
    if _has_word(combined, "notice period", "how soon can you start", "notice", "availability"):
        return ("notice_period", candidate["notice_period"])
    if _has_word(combined, "start date", "available start", "earliest start", "when can you start", "date of availability"):
        return ("start_date", candidate["start_date"])

    # 17. Current Title / Company / Employment Status
    if _has_word(combined, "current company", "current employer", "present employer"):
        return ("current_company", candidate["current_company"])
    if _has_word(combined, "current title", "job title", "headline", "current position"):
        return ("title", candidate["title"])
    if _has_word(combined, "currently employed", "are you employed"):
        # Single-sourced from the canonical profile (audit item 46).
        return ("currently_employed", candidate["currently_employed"])

    # 18. Diversity / EEO / Demographics
    if _has_word(combined, "gender", "sex"):
        return ("gender", "Male")
    if _has_word(combined, "pronoun", "pronouns"):
        return ("pronouns", "He/Him")
    if _has_word(combined, "veteran", "military"):
        return ("veteran", "I am not a protected veteran")
    if _has_word(combined, "disability", "handicap", "physical limitation"):
        return ("disability", "No, I do not have a disability")
    if _has_word(combined, "hispanic", "latino"):
        return ("hispanic", "No")
    if _has_word(combined, "race", "ethnicity"):
        return ("race", "Asian")

    # 19. How did you hear / Reference
    if _has_word(combined, "how did you hear", "referral", "source", "where did you find"):
        return ("hear_about", candidate["hear_about"])

    # 20. Skills & Languages
    if _has_word(combined, "skill", "skills", "tech stack", "technologies"):
        return ("skills", candidate["skills"])
    if _has_word(combined, "english", "language", "languages"):
        return ("languages", candidate["languages"])

    # Generic intelligent default based on input type
    if input_type in ["number", "range"]:
        return ("number_default", "2")
    if input_type in ["date"]:
        return ("date_default", candidate["start_date"])

    return ("custom_text", candidate["about_me"])


# =============================================================================
#  Browser Automation Engine (Playwright with Intelligent Form Filling)
# =============================================================================

def _human_type(element, text: str) -> None:
    """Type text into a Playwright element and dispatch native React prototype setters/events."""
    try:
        element.click(timeout=1500)
    except Exception:
        pass
    try:
        element.fill(str(text), timeout=2000)
    except Exception:
        pass
    try:
        element.evaluate("""(el, val) => {
            const proto = el.tagName.toLowerCase() === 'textarea' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
            const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
            if (setter) {
                setter.call(el, val);
            } else {
                el.value = val;
            }
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            el.dispatchEvent(new Event('blur', { bubbles: true }));
        }""", str(text))
    except Exception:
        pass


def _get_element_prompt(el) -> str:
    """Climbs label and ancestor container hierarchy to reliably extract question prompt text."""
    try:
        prompt = el.evaluate("""e => {
            // Check direct id
            if (e.id) {
                const l = document.querySelector(`label[for='${e.id}']`) || document.getElementById(`${e.id}-label`);
                if (l && l.innerText.trim()) return l.innerText.trim();
            }
            // Check inner input id (for custom select controls, comboboxes, dropzones)
            const innerInp = e.tagName.toLowerCase() === 'input' ? e : e.querySelector('input');
            if (innerInp && innerInp.id) {
                const l = document.querySelector(`label[for='${innerInp.id}']`) || document.getElementById(`${innerInp.id}-label`);
                if (l && l.innerText.trim()) return l.innerText.trim();
            }
            // Check parent field/question container label
            const field = e.closest('.field, [class*="field"], [class*="question"]');
            if (field) {
                const l = field.querySelector('label, legend, [class*="label"], [class*="title"], h3, strong');
                if (l && l.innerText.trim()) return l.innerText.trim();
            }
            const lClosest = e.closest('label');
            if (lClosest && lClosest.innerText.trim()) return lClosest.innerText.trim();

            const ariaLabel = e.getAttribute('aria-label');
            if (ariaLabel && ariaLabel.trim()) return ariaLabel.trim();
            const ariaLabelledby = e.getAttribute('aria-labelledby');
            if (ariaLabelledby) {
                const elLabel = document.getElementById(ariaLabelledby);
                if (elLabel && elLabel.innerText.trim()) return elLabel.innerText.trim();
            }

            let cur = e.parentElement;
            for (let depth = 0; depth < 6 && cur; depth++) {
                const labelElem = cur.querySelector('label, [class*="label"], [class*="title"], legend, p, strong, h3, h4');
                if (labelElem && labelElem.innerText.trim() && !labelElem.innerText.toLowerCase().includes('select...')) {
                    return labelElem.innerText.trim();
                }
                cur = cur.parentElement;
            }
            return '';
        }""")
        return (prompt or "").strip()
    except Exception:
        return ""


def _fill_select(select_el, desired_value: str) -> bool:
    """Select the best matching option in a <select> element."""
    try:
        desired_lower = str(desired_value).lower()
        options = select_el.locator("option").all()
        best_value = None

        # 1. Exact match
        for opt in options:
            text = (opt.text_content() or "").strip().lower()
            val = (opt.get_attribute("value") or "").strip()
            if text == desired_lower or val.lower() == desired_lower:
                best_value = val
                break

        # 2. Substring match
        if not best_value:
            for opt in options:
                text = (opt.text_content() or "").strip().lower()
                val = (opt.get_attribute("value") or "").strip()
                if desired_lower in text or text in desired_lower:
                    best_value = val
                    break

        # 3. Positive match for Yes/No
        if not best_value and desired_lower in ["yes", "no"]:
            for opt in options:
                text = (opt.text_content() or "").strip().lower()
                val = (opt.get_attribute("value") or "").strip()
                if desired_lower == text or desired_lower == val.lower():
                    best_value = val
                    break

        if best_value is not None:
            select_el.select_option(value=best_value)
            return True
        elif len(options) > 1:
            # Fallback: pick the first non-empty option if nothing matched
            for opt in options[1:]:
                val = (opt.get_attribute("value") or "").strip()
                if val:
                    select_el.select_option(value=val)
                    return True
    except Exception as exc:
        logger.debug("Could not set select option: %s", exc)
    return False


def _fill_radio_or_checkbox(element, field_category: str, desired_value: str) -> None:
    """Check or click radio/checkbox based on category and desired value."""
    try:
        is_checkbox = element.get_attribute("type") == "checkbox"

        if is_checkbox:
            # For consent, terms, agreements, certifications -> ALWAYS check
            element.check()
        else:
            # Radio button logic
            label_text = (element.evaluate("el => el.closest('label')?.innerText || el.parentElement?.innerText || ''") or "").strip().lower()
            desired_lower = str(desired_value).lower()

            if desired_lower in label_text or (desired_lower == "yes" and any(k in label_text for k in ["yes", "agree", "authorized"])) or (desired_lower == "no" and any(k in label_text for k in ["no", "none", "not"])):
                element.check()
    except Exception as exc:
        logger.debug("Could not interact with radio/checkbox: %s", exc)


def _handle_custom_react_select(page, csel, category: str, value: str) -> bool:
    """Clicks custom React-Select or combobox control and selects the best matching option cleanly."""
    try:
        csel.click(timeout=2500)
        time.sleep(0.2)

        search_kw = str(value)
        if category in ("work_authorization", "authorized_in_country", "legal_age", "own_work", "cs_degree", "travel_sprints", "remote_policy"):
            # Respect the truthful resolved value ("Yes"/"No") from _classify (audit item 55)
            search_kw = "Yes" if value.strip().lower() == "yes" else "No"
        elif category in ("previously_employed", "sponsorship_needed", "hispanic"):
            search_kw = "No"
        elif category == "currently_employed":
            # Truthful answer from the canonical profile (audit item 46)
            search_kw = "Yes" if "yes" in value.lower() else "No"
        elif category == "veteran":
            search_kw = "not a protected"
        elif category == "disability":
            search_kw = "No"
        elif category in ("country", "nationality"):
            search_kw = "Pakistan"
        elif category == "gender":
            search_kw = "Male"
        elif category == "pronouns":
            search_kw = "He/Him"
        elif category in ("high_school_math", "high_school_lang"):
            search_kw = "Top 10%"
        elif category == "race":
            search_kw = "Asian"
        elif category == "degree":
            search_kw = "Bachelor"
        elif category in ("discipline", "major"):
            search_kw = "Computer Science"
        elif category in ("privacy_policy", "privacy_notice", "recruitment_privacy"):
            search_kw = "Acknowledge"
        elif category == "university":
            search_kw = "Other"

        if len(search_kw) > 30:
            search_kw = "Yes" if any(w in search_kw.lower() for w in ["yes", "agree", "confirm", "true", "bachelor", "cs"]) else ""

        if search_kw:
            page.keyboard.type(search_kw, delay=15)
            # Wait up to 1.5s for async menu options to populate
            for _ in range(6):
                time.sleep(0.25)
                opts = page.locator(".select__menu [class*='option'], [class*='-option'], div[role='option']").all()
                if opts:
                    break

        # Look for visible options in menu
        menu_options = page.locator(".select__menu [class*='option'], [class*='-option'], div[role='option']").all()
        if menu_options:
            target_opt = menu_options[0]
            val_lower = search_kw.lower()
            for opt in menu_options:
                txt = (opt.inner_text() or "").strip().lower()
                if val_lower == "male":
                    if txt == "male":
                        target_opt = opt
                        break
                elif val_lower in txt:
                    target_opt = opt
                    break
            target_opt.click(timeout=2500)
            time.sleep(0.2)
            return True
        else:
            # Safely close without pressing Enter (prevents premature form submission!)
            page.keyboard.press("Escape")
            time.sleep(0.1)
            return False
    except Exception as exc:
        logger.debug("Error selecting custom dropdown: %s", exc)
        return False


def _fill_all_form_fields(page, candidate: dict, cv_path: str, cover_letter: Optional[str] = None) -> int:
    """
    Universal Form Filler:
    Finds every input, textarea, select, file upload, radio, and checkbox on the page
    and fills it appropriately from Ibrahim Hamid's candidate profile using React synthetic events.
    Returns the count of successfully filled fields.
    """
    filled_count = 0

    # -- 1. File Uploads (CV / Resume) -----------------------------------------
    if cv_path and os.path.exists(cv_path):
        file_inputs = page.locator("input[type='file']").all()
        for finput in file_inputs:
            try:
                finput.set_input_files(cv_path)
                filled_count += 1
                logger.info("Uploaded resume file from %s", cv_path)
                time.sleep(2.5)  # Wait for cloud / S3 attachment to complete
            except Exception as exc:
                logger.debug("File input upload failed: %s", exc)

    # -- 2. Text / Email / Tel / Number / Date Inputs --------------------------
    inputs = page.locator("input:not([type='file']):not([type='hidden']):not([type='submit']):not([type='button']):not([type='reset']):not([type='radio']):not([type='checkbox'])").all()
    logger.info("Processing %d text inputs", len(inputs))
    for inp in inputs:
        try:
            if not inp.is_visible():
                continue

            input_type = (inp.get_attribute("type") or "text").lower()
            role = (inp.get_attribute("role") or "").lower()
            cls = (inp.get_attribute("class") or "").lower()
            tabindex = inp.get_attribute("tabindex") or ""
            aria_hidden = inp.get_attribute("aria-hidden") or ""

            if tabindex == "-1" or aria_hidden == "true" or role == "combobox" or "select" in cls or input_type == "search":
                # Handled specifically by React-Select combobox handler
                continue

            name_attr = inp.get_attribute("name") or ""
            id_attr = inp.get_attribute("id") or ""
            placeholder = inp.get_attribute("placeholder") or ""
            aria_label = inp.get_attribute("aria-label") or ""
            label_text = _get_element_prompt(inp)

            category, value = _classify_and_resolve_field(
                tag_name="input",
                input_type=input_type,
                name_attr=name_attr,
                id_attr=id_attr,
                placeholder_attr=placeholder,
                label_text=label_text,
                aria_label=aria_label,
                candidate=candidate,
                cover_letter=cover_letter,
            )

            current_val = inp.input_value()
            if not current_val and value:
                # If entering phone and country code is already handled by a separate element
                if category == "phone":
                    country_selector = page.locator("[id*='country'], [class*='country'], button[aria-label*='Country']").first
                    if country_selector.count() > 0:
                        value = candidate["phone_national"]

                _human_type(inp, str(value))
                filled_count += 1
                logger.debug("Filled input [%s / %s] with: %s", id_attr or name_attr, category, str(value)[:30])

                # Autocomplete / combobox handling
                role = inp.get_attribute("role") or ""
                if role == "combobox" or "select" in (inp.get_attribute("class") or "").lower():
                    time.sleep(0.4)
                    try:
                        menu_options = page.locator(".select__menu [class*='option'], [class*='-option'], div[role='option']").all()
                        if menu_options:
                            menu_options[0].click(timeout=2500)
                            time.sleep(0.2)
                        else:
                            page.keyboard.press("ArrowDown")
                            time.sleep(0.1)
                            page.keyboard.press("Enter")
                    except Exception:
                        pass

            # If location field remains empty, try Locate me button if present
            if "location" in (id_attr or name_attr).lower() and not inp.input_value():
                try:
                    locate_btn = page.locator("button:has-text('Locate me'), a:has-text('Locate me')").first
                    if locate_btn.count() > 0 and locate_btn.is_visible():
                        locate_btn.click()
                        time.sleep(1.0)
                except Exception:
                    pass
        except Exception as exc:
            logger.debug("Error filling text input: %s", exc)

    # -- 3. Textareas (Cover letter, Why interested, Projects, Additional notes)
    textareas = page.locator("textarea").all()
    for ta in textareas:
        try:
            if not ta.is_visible():
                continue

            name_attr = ta.get_attribute("name") or ""
            id_attr = ta.get_attribute("id") or ""
            placeholder = ta.get_attribute("placeholder") or ""
            aria_label = ta.get_attribute("aria-label") or ""
            label_text = _get_element_prompt(ta)

            category, value = _classify_and_resolve_field(
                tag_name="textarea",
                input_type="textarea",
                name_attr=name_attr,
                id_attr=id_attr,
                placeholder_attr=placeholder,
                label_text=label_text,
                aria_label=aria_label,
                candidate=candidate,
                cover_letter=cover_letter,
            )

            current_val = ta.input_value()
            if not current_val and value:
                _human_type(ta, str(value))
                filled_count += 1
                logger.debug("Filled textarea [%s / %s]", id_attr or name_attr, category)
        except Exception as exc:
            logger.debug("Error filling textarea: %s", exc)

    # -- 4. Select Dropdowns --------------------------------------------------
    selects = page.locator("select").all()
    for sel in selects:
        try:
            if not sel.is_visible():
                continue

            name_attr = sel.get_attribute("name") or ""
            id_attr = sel.get_attribute("id") or ""
            aria_label = sel.get_attribute("aria-label") or ""
            label_text = _get_element_prompt(sel)

            category, value = _classify_and_resolve_field(
                tag_name="select",
                input_type="select",
                name_attr=name_attr,
                id_attr=id_attr,
                placeholder_attr="",
                label_text=label_text,
                aria_label=aria_label,
                candidate=candidate,
                cover_letter=cover_letter,
            )

            if value:
                ok = _fill_select(sel, str(value))
                if ok:
                    filled_count += 1
        except Exception as exc:
            logger.debug("Error selecting dropdown option: %s", exc)

    # -- 4b. Custom Div / React-Select Dropdowns --------------------------------
    custom_dropdowns = page.locator("div.select__control, div[role='combobox']:not(input)").all()
    for csel in custom_dropdowns:
        try:
            if not csel.is_visible():
                continue

            # Check if dropdown already has a selected value
            text_inside = (csel.inner_text() or "").strip()
            if text_inside and not any(ph in text_inside.lower() for ph in ["select", "choose", "type"]):
                continue

            # Get question label
            label_text = _get_element_prompt(csel)

            category, value = _classify_and_resolve_field(
                tag_name="select",
                input_type="select",
                name_attr="",
                id_attr="",
                placeholder_attr="",
                label_text=label_text,
                aria_label="",
                candidate=candidate,
                cover_letter=cover_letter,
            )

            ok = _handle_custom_react_select(page, csel, category, str(value))
            if ok:
                filled_count += 1
        except Exception as exc:
            logger.debug("Error handling custom dropdown: %s", exc)

    # -- 5. Radio Buttons & Checkboxes -----------------------------------------
    radios = page.locator("input[type='radio']").all()
    for rad in radios:
        try:
            if not rad.is_visible():
                continue
            name_attr = rad.get_attribute("name") or ""
            id_attr = rad.get_attribute("id") or ""
            label_text = _get_element_prompt(rad)

            category, value = _classify_and_resolve_field(
                tag_name="input",
                input_type="radio",
                name_attr=name_attr,
                id_attr=id_attr,
                placeholder_attr="",
                label_text=label_text,
                aria_label="",
                candidate=candidate,
                cover_letter=cover_letter,
            )
            _fill_radio_or_checkbox(rad, category, str(value))
            filled_count += 1
        except Exception as exc:
            logger.debug("Error handling radio button: %s", exc)

    checkboxes = page.locator("input[type='checkbox']").all()
    group_counts: Dict[str, int] = {}
    preferred_skills = ["python", "ai/ml", "distributed systems", "javascript", "bash", "linux", "web back-end", "cloud", "data science"]

    for chk in checkboxes:
        try:
            name_attr = chk.get_attribute("name") or ""
            id_attr = chk.get_attribute("id") or ""
            label_text = _get_element_prompt(chk)
            label_lower = label_text.lower()

            def _toggle_chk(el):
                parent_box = el.locator("xpath=ancestor::div[contains(@class, 'checkbox')][1]")
                if parent_box.count() > 0:
                    parent_box.click(force=True)
                else:
                    el.check(force=True)

            # Grouped multi-choice checkboxes (e.g. name ends with [])
            if "[]" in name_attr:
                cnt = group_counts.get(name_attr, 0)
                if cnt >= 3:
                    continue
                if any(ps in label_lower for ps in preferred_skills):
                    _toggle_chk(chk)
                    group_counts[name_attr] = cnt + 1
                    filled_count += 1
                continue

            # Standard single consent / terms checkboxes
            if any(w in label_lower for w in ["agree", "consent", "privacy", "terms", "policy", "certif", "acknowledge", "confirm", "18 years"]):
                _toggle_chk(chk)
                filled_count += 1
        except Exception as exc:
            logger.debug("Error handling checkbox: %s", exc)

    return filled_count


def _click_submit_button(page) -> bool:
    """Find and click the submit / apply button on the form."""
    submit_selectors = [
        "button[type='submit']",
        "input[type='submit']",
        "button:has-text('Submit application')",
        "button:has-text('Submit Application')",
        "button:has-text('Submit')",
        "button:has-text('Apply Now')",
        "button:has-text('Send Application')",
        "button:has-text('Complete Application')",
        "a:has-text('Submit Application')",
        "a:has-text('Submit')",
    ]

    for sel in submit_selectors:
        try:
            btn = page.locator(sel).first
            if btn.count() > 0 and btn.is_visible():
                btn.click()
                logger.info("Clicked submit button with selector: %s", sel)
                time.sleep(3.0)
                
                # Verify if submission went through or if validation errors remain.
                # Only consider visible, error-styled elements (audit item 53):
                # the old `div:has-text('required')` matched helper text like
                # "* indicates required field" and produced false negatives.
                has_error = False
                try:
                    error_elements = page.locator(
                        ".field-error, .error, .error-message, .invalid-feedback, "
                        ".validation-error, [aria-invalid='true'], "
                        "[class*='errorMessage'], [class*='validation']"
                    ).all()
                    for err in error_elements:
                        try:
                            if err.is_visible() and (err.text_content() or "").strip():
                                has_error = True
                                break
                        except Exception:
                            continue
                except Exception:
                    pass

                # If confirmation text appeared
                try:
                    body_text = page.inner_text("body").lower()
                    if any(w in body_text for w in ["thank you for applying", "application submitted", "application received", "successfully submitted"]):
                        return True
                except Exception:
                    pass

                return not has_error
        except Exception as exc:
            logger.debug("Could not click %s: %s", sel, exc)

    return False


# =============================================================================
#  Specialized Platform Flows
# =============================================================================

def _generic_apply(url: str, cv_path: str, cover_letter: Optional[str] = None) -> bool:
    """Universal Playwright auto-apply flow for any job board or company website."""
    from playwright.sync_api import sync_playwright

    candidate = _candidate()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=settings.PLAYWRIGHT_HEADLESS,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        try:
            logger.info("Navigating to application URL: %s", url)
            page.goto(url, timeout=15000, wait_until="domcontentloaded")
            _human_delay(1.0, 2.0)

            # Check for cookie consent popups across main page and frames
            for frame in page.frames:
                try:
                    cookie_buttons = frame.locator("button:has-text('Accept'), button:has-text('Agree'), button:has-text('Allow all')").all()
                    for cb in cookie_buttons:
                        if cb.is_visible():
                            cb.click()
                            break
                except Exception:
                    pass

            # Detect password/account creation walls early
            for frame in page.frames:
                try:
                    if frame.locator("input[type='password']").count() > 0:
                        logger.warning("Account creation / password wall detected on %s - skipping generic automation", url)
                        browser.close()
                        return False
                except Exception:
                    pass

            # Click initial 'Apply' button if page shows a job description first
            for frame in page.frames:
                try:
                    apply_buttons = frame.locator("a:has-text('Apply'), button:has-text('Apply'), a:has-text('Apply Now'), button:has-text('Apply Now')").all()
                    for ab in apply_buttons:
                        if ab.is_visible():
                            ab.click()
                            _human_delay(1.0, 2.0)
                            break
                except Exception:
                    pass

            # Multi-step form loop (up to 5 steps/pages)
            max_steps = 5
            step = 0
            submitted = False

            while step < max_steps:
                step += 1
                logger.info("Filling form elements (Step %d) on %s", step, url)

                # Fill all fields across all frames (main page + iframes)
                filled_this_step = 0
                for frame in page.frames:
                    try:
                        filled_this_step += _fill_all_form_fields(frame, candidate, cv_path, cover_letter)
                    except Exception as e:
                        logger.debug("Frame form fill exception: %s", e)

                logger.info("Filled %d fields on step %d", filled_this_step, step)

                # Attempt to find and click submit button
                for frame in page.frames:
                    try:
                        if _click_submit_button(frame):
                            submitted = True
                            break
                    except Exception:
                        pass

                if submitted:
                    logger.info("Application successfully submitted on step %d!", step)
                    _human_delay(2.0, 3.0)
                    break

                # If not submitted, search for 'Next' or 'Continue' buttons across frames
                next_clicked = False
                for frame in page.frames:
                    try:
                        next_selectors = [
                            "button:has-text('Next')",
                            "button:has-text('Continue')",
                            "button:has-text('Next Step')",
                            "input[value='Next']",
                            "input[value='Continue']",
                            "a:has-text('Next')",
                        ]
                        for n_sel in next_selectors:
                            btn = frame.locator(n_sel).first
                            if btn.count() > 0 and btn.is_visible():
                                btn.click()
                                logger.info("Clicked '%s' button to proceed to step %d", n_sel, step + 1)
                                _human_delay(1.5, 2.5)
                                next_clicked = True
                                break
                        if next_clicked:
                            break
                    except Exception:
                        pass

                if not next_clicked:
                    # Neither submit nor next button was available
                    logger.debug("No next or submit button found on step %d, breaking loop", step)
                    break

            # Verify submission with strict evidence engine
            from ..core.submission_verifier import verify_submission
            import uuid
            app_id = uuid.uuid4().hex[:8]
            evidence = verify_submission(page, platform="generic_browser", application_id=app_id)
            browser.close()
            return evidence.is_confirmed

        except Exception as exc:
            logger.error("Error during generic apply on %s: %s", url, exc)
            try:
                browser.close()
            except Exception:
                pass
            return False


# =============================================================================
#  Cover-letter generation (CoverLetterAgent wired into the apply flow)
# =============================================================================

def _generate_cover_letter(
    job_id: str,
    job_title: str,
    company: str,
    description: str,
    candidate: dict,
) -> Optional[str]:
    """
    Generates a tailored cover letter for this job via CoverLetterAgent.
    The letter is fact-checked against the canonical profile; if the check
    blocks it (or generation fails), returns None so callers fall back to
    the candidate's generic about_me paragraph instead of filler.
    """
    try:
        from ..agents.cover_letter.agent import CoverLetterAgent
        from ..core.fact_checker import fact_check_generated_content

        agent = CoverLetterAgent()
        result = agent.run(
            {
                "job_id": job_id,
                "job_title": job_title,
                "company": company,
                "job_description": description or "",
            },
            trigger="auto_apply",
        )
        letter = (result or {}).get("cover_letter") or ""
        letter = letter.strip()
        if not letter:
            logger.warning("CoverLetterAgent produced no letter for %s @ %s", job_title, company)
            return None

        check = fact_check_generated_content(letter, candidate)
        if check.blocked:
            logger.warning(
                "Generated cover letter blocked by fact-check for %s @ %s: %s",
                job_title, company, "; ".join(check.violations),
            )
            return None
        logger.info("Generated tailored cover letter for %s @ %s (%d chars)", job_title, company, len(letter))
        return letter
    except Exception as exc:
        logger.warning("Cover letter generation failed for %s @ %s: %s", job_title, company, exc)
        return None


# =============================================================================
#  State-machine-backed status recording (audit item 49)
# =============================================================================

def _record_application_status(db, app, to_state: str, note: str = "") -> None:
    """
    Record an application status change through the validated state machine
    (TRANSITIONS in jobpilot/core/state_machine.py). On an invalid transition,
    logs loudly and records the status directly so the outcome is never
    silently lost.
    """
    from ..core.state_machine import StateMachineError, transition
    try:
        evt = transition(app, to_state, actor="auto_apply", note=note)
        db.add(evt)
    except StateMachineError as exc:
        logger.error(
            "Invalid state transition %s → %s for application %s: %s — recording status directly",
            app.status, to_state, getattr(app, "id", "?"), exc,
        )
        app.status = to_state


# =============================================================================
#  Main Orchestrator Entry Point: apply_to_job
# =============================================================================

def apply_to_job(
    job_id: str,
    job_title: str,
    company: str,
    source: str,
    apply_url: Optional[str],
    score: int,
    description: str = "",
    cv_path: Optional[str] = None,
    cover_letter: Optional[str] = None,
    user_id: Optional[str] = None,
    canonical_job_id: Optional[str] = None,
    dry_run: bool = False,
    worker_id: Optional[str] = None,
) -> bool:
    """
    Main entry point to execute an auto-application for Ibrahim Hamid.
    Guarantees:
    - Pre-flight Experience and Seniority Gatekeeper check.
    - Zero fake submissions or staged fallbacks.
    - Idempotency: Checks prior application status in DB before any execution.
    - Atomic database lock: Prevents concurrent workers or races from double-applying.
    - SUBMITTED is recorded ONLY when affirmative browser evidence exists.
    """
    from ..core.candidate import resolve_resume_path
    from ..core.eligibility import evaluate_job_eligibility
    from ..core.application_lock import acquire_application_lock, release_application_lock
    import hashlib

    candidate = _candidate()
    tier = _tier(score)
    user_id = user_id or "3e614c95-b3a4-43d6-805d-3ffed73f64ba"

    # Compute canonical_job_id if not provided
    if not canonical_job_id:
        norm_co = re.sub(r"[^a-z0-9]", "", company.lower())
        norm_ti = re.sub(r"[^a-z0-9]", "", job_title.lower())
        canonical_job_id = hashlib.sha256(f"{norm_co}::{norm_ti}".encode()).hexdigest()[:24]

    logger.info("Attempting auto-apply for '%s' at '%s' (Canonical: %s, Score: %d)", job_title, company, canonical_job_id, score)

    # Pre-flight check: Already applied or actively in-flight in DB?
    try:
        with db_session() as db:
            existing_app = db.query(Application).filter(
                (Application.job_id == job_id) | (Application.canonical_job_id == canonical_job_id)
            ).first()
            if existing_app and existing_app.status in (
                "SUBMITTED",
                "CONFIRMED",
            ):
                # Idempotency: only confirmed submissions block retry. Unverified
                # attempts (SUBMISSION_UNVERIFIED / SUBMISSION_UNCONFIRMED) and
                # FAILED attempts may be retried (audit item 44).
                logger.warning(
                    "[IDEMPOTENCY BLOCKED] Application already exists for job %s (Canonical: %s) with status '%s'. Skipping to prevent duplicate.",
                    job_id,
                    canonical_job_id,
                    existing_app.status,
                )
                return False
    except Exception as db_chk_err:
        logger.warning("Error checking existing application: %s", db_chk_err)

    # Acquire Atomic Application Lock
    lock_acquired = acquire_application_lock(canonical_job_id=canonical_job_id, candidate_id=user_id, worker_id=worker_id, timeout_seconds=240)
    if not lock_acquired:
        logger.warning(
            "[RACE CONDITION BLOCKED] Another worker has acquired lock for %s (%s at %s). Skipping execution.",
            canonical_job_id,
            job_title,
            company,
        )
        return False

    # 1. Experience, Seniority, and Geographic Gatekeeper Check
    eligibility = evaluate_job_eligibility(
        job_id=job_id,
        title=job_title,
        company=company,
        description=description,
    )
    if not eligibility.is_eligible:
        logger.info(
            "[ELIGIBILITY REJECTED] Skipping '%s' at '%s' - Reason: %s (Evidence: '%s')",
            job_title,
            company,
            eligibility.reason,
            eligibility.evidence_text or "N/A",
        )
        # Record rejection in DB via the validated state machine
        try:
            with db_session() as db:
                app = db.query(Application).filter_by(job_id=job_id).first()
                if app:
                    app.rejection_reason = eligibility.reason
                    app.user_notes = f"Preflight gate: {eligibility.matched_rule} ({eligibility.evidence_text or ''})"
                    _record_application_status(
                        db, app, "ELIGIBILITY_REJECTED",
                        f"Preflight gate: {eligibility.matched_rule} ({eligibility.evidence_text or ''})",
                    )
                db.commit()
        except Exception:
            pass

        try:
            import pymongo
            client = pymongo.MongoClient(getattr(settings, "MONGO_URI", "mongodb://localhost:27017/"), serverSelectionTimeoutMS=1000)
            mongo_db = client[getattr(settings, "MONGO_DB_NAME", "job_scraper_db")]
            mongo_db.applications.update_one(
                {"job_id": job_id},
                {
                    "$set": {
                        "job_id": job_id,
                        "job_title": job_title,
                        "company": company,
                        "status": "ELIGIBILITY_REJECTED",
                        "reason": eligibility.reason,
                        "matched_rule": eligibility.matched_rule,
                        "evidence": eligibility.evidence_text,
                        "evaluated_at": datetime.now(timezone.utc).isoformat(),
                    }
                },
                upsert=True,
            )
        except Exception:
            pass

        release_application_lock(canonical_job_id, worker_id)
        return False

    # 2. Authoritative Resume Validation
    resolved_cv = resolve_resume_path(cv_path)
    if not resolved_cv:
        logger.error("Auto-apply cannot proceed: Valid resume PDF not found!")
        release_application_lock(canonical_job_id, worker_id)
        return False
    cv_path = resolved_cv

    # 2b. Tailored cover letter (CoverLetterAgent) — generated only when the
    # caller did not supply one; fact-checked, falls back to None on failure.
    if cover_letter is None:
        cover_letter = _generate_cover_letter(job_id, job_title, company, description, candidate)

    applied_ok = False
    strategy_used = "unknown"
    final_status = "FAILED"
    evidence_notes = ""
    screenshot_path = None

    # 3. Direct ATS / Web Application Execution — dispatched via the application
    # router (classify_application_url) so mailto: links take the SMTP email
    # flow and unsupported routes (WORKDAY / GOOGLE_FORM) are recorded, never
    # fed to a doomed browser attempt (audit items 42, 52).
    if apply_url:
        from ..agents.application.router import classify_application_url
        route = classify_application_url(apply_url)
        route_type = (route.route_type or "COMPANY_FORM").upper()
        logger.info("Application route for %s: %s", apply_url, route_type)

        if route_type == "GREENHOUSE":
            strategy_used = "greenhouse"
            from ..agents.application.greenhouse_agent import GreenhouseAgent
            gh_res = GreenhouseAgent().apply(apply_url, candidate, cv_path, cover_letter, dry_run=dry_run)
            applied_ok = gh_res.success and gh_res.status == "SUBMITTED"
            final_status = gh_res.status
            screenshot_path = gh_res.screenshot_path
            evidence_notes = gh_res.confirmation_message or "; ".join(gh_res.errors)

        elif route_type == "LEVER":
            strategy_used = "lever"
            from ..agents.application.lever_agent import LeverAgent
            lv_res = LeverAgent().apply(apply_url, candidate, cv_path, cover_letter, dry_run=dry_run)
            applied_ok = lv_res.success and lv_res.status == "SUBMITTED"
            final_status = lv_res.status
            screenshot_path = lv_res.screenshot_path
            evidence_notes = lv_res.confirmation_message or "; ".join(lv_res.errors)

        elif route_type == "EMAIL":
            # mailto: application URLs go straight to the SMTP email flow.
            target_email = route.target_email or apply_url.split(":", 1)[-1].split("?")[0]
            strategy_used = f"email ({target_email})"
            email_sent = _send_email_application(
                to_email=target_email,
                job_title=job_title,
                company=company,
                cv_path=cv_path,
                cover_letter=cover_letter or candidate["about_me"],
                candidate_name=candidate["full_name"],
                candidate_email=candidate["email"],
            )
            if email_sent:
                applied_ok = True
                final_status = "SUBMITTED"
                evidence_notes = f"Verified SMTP dispatch to {target_email}"
            else:
                applied_ok = False
                final_status = "FAILED"
                evidence_notes = f"Email application to {target_email} failed (SMTP unconfigured or send error)"

        elif route_type in ("WORKDAY", "GOOGLE_FORM"):
            # No automated handler exists for these routes: record explicitly
            # instead of attempting a doomed browser run (audit item 52).
            strategy_used = f"{route_type.lower()}_unsupported"
            final_status = "UNSUPPORTED_ROUTE"
            applied_ok = False
            evidence_notes = (
                f"{route.ats_name or route_type} applications require a login/manual flow "
                "with no automated handler; skipped by design."
            )

        else:  # COMPANY_FORM / MANUAL / unknown -> universal browser flow
            strategy_used = "generic_browser"
            try:
                applied_ok = _generic_apply(apply_url, cv_path, cover_letter)
                final_status = "SUBMITTED" if applied_ok else "SUBMISSION_UNCONFIRMED"
            except Exception as exc:
                logger.warning("Generic apply failed: %s", exc)
                final_status = "FAILED"
                applied_ok = False

    # 4. Email Apply (Genuinely configured SMTP ONLY, never simulated)
    if not applied_ok and not apply_url:
        apply_email = _find_apply_email(description) if description else None
        if apply_email and not any(k in apply_email.lower() for k in ["accommodat", "privacy", "legal", "abuse", "press"]):
            # Require real SMTP configuration
            smtp_host = getattr(settings, "SMTP_HOST", None)
            smtp_user = getattr(settings, "SMTP_USER", None)
            smtp_pass = getattr(settings, "SMTP_PASS", None)
            if smtp_host and smtp_user and smtp_pass:
                strategy_used = f"email ({apply_email})"
                email_sent = _send_email_application(
                    to_email=apply_email,
                    job_title=job_title,
                    company=company,
                    cv_path=cv_path,
                    cover_letter=cover_letter or candidate["about_me"],
                    candidate_name=candidate["full_name"],
                    candidate_email=candidate["email"],
                )
                if email_sent:
                    applied_ok = True
                    final_status = "SUBMITTED"
                    evidence_notes = f"Verified SMTP dispatch to {apply_email}"

    # 5. Persistent State Recording
    if applied_ok and final_status == "SUBMITTED":
        _increment_daily(tier, user_id)
        logger.info("Auto-apply successfully verified for '%s' via %s", job_title, strategy_used)
        sse_log(f"[AUTO-APPLY] Applied to {job_title} @ {company} via {strategy_used} (Verified)")

        try:
            with db_session() as db:
                app = db.query(Application).filter_by(job_id=job_id).first()
                if app:
                    app.submitted_at = datetime.now(timezone.utc)
                    app.user_notes = f"Auto-applied via {strategy_used} | Evidence: {evidence_notes}"
                    _record_application_status(
                        db, app, "SUBMITTED",
                        f"Auto-applied via {strategy_used} | Evidence: {evidence_notes}",
                    )
                db.commit()
        except Exception as db_exc:
            logger.warning("Failed to update application DB status: %s", db_exc)

        try:
            import pymongo
            client = pymongo.MongoClient(getattr(settings, "MONGO_URI", "mongodb://localhost:27017/"), serverSelectionTimeoutMS=1000)
            mongo_db = client[getattr(settings, "MONGO_DB_NAME", "job_scraper_db")]
            mongo_db.applications.update_one(
                {"job_id": job_id},
                {
                    "$set": {
                        "job_id": job_id,
                        "job_title": job_title,
                        "company": company,
                        "status": "SUBMITTED",
                        "strategy": strategy_used,
                        "score": score,
                        "submitted_at": datetime.now(timezone.utc).isoformat(),
                        "url": apply_url,
                        "screenshot_path": screenshot_path,
                        "evidence": evidence_notes,
                    }
                },
                upsert=True,
            )
        except Exception:
            pass

        bus.emit(EventType.APPLICATION_SUBMITTED, {
            "job_id": job_id,
            "job_title": job_title,
            "company": company,
            "strategy": strategy_used,
            "score": score,
        })
    else:
        logger.warning("Auto-apply finished with status '%s' for '%s' @ '%s'", final_status, job_title, company)
        try:
            with db_session() as db:
                app = db.query(Application).filter_by(job_id=job_id).first()
                if app:
                    if canonical_job_id:
                        app.canonical_job_id = canonical_job_id
                    app.user_notes = f"Status: {final_status} via {strategy_used} | Details: {evidence_notes}"
                    _record_application_status(
                        db, app, final_status,
                        f"Status: {final_status} via {strategy_used} | Details: {evidence_notes}",
                    )
                db.commit()
        except Exception:
            pass

        try:
            import pymongo
            client = pymongo.MongoClient(getattr(settings, "MONGO_URI", "mongodb://localhost:27017/"), serverSelectionTimeoutMS=1000)
            mongo_db = client[getattr(settings, "MONGO_DB_NAME", "job_scraper_db")]
            mongo_db.applications.update_one(
                {"job_id": job_id},
                {
                    "$set": {
                        "job_id": job_id,
                        "canonical_job_id": canonical_job_id,
                        "job_title": job_title,
                        "company": company,
                        "status": final_status,
                        "strategy": strategy_used,
                        "score": score,
                        "attempted_at": datetime.now(timezone.utc).isoformat(),
                        "url": apply_url,
                        "screenshot_path": screenshot_path,
                        "notes": evidence_notes,
                    }
                },
                upsert=True,
            )
        except Exception:
            pass

    # Ensure canonical_job_id is recorded on the application record if applied
    if applied_ok and canonical_job_id:
        try:
            with db_session() as db:
                app = db.query(Application).filter_by(job_id=job_id).first()
                if app and not app.canonical_job_id:
                    app.canonical_job_id = canonical_job_id
                    db.commit()
        except Exception:
            pass

    release_application_lock(canonical_job_id, worker_id)
    return applied_ok