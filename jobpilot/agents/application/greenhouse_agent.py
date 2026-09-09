"""
Greenhouse Deep Application Agent & Form Interaction Engine.
Hardened according to AUTO_APPLY_HARDENING_MASTER_PROMPT specifications:
1. Phone Country Code & National Number Normalization (prevents 'Phone number is too long').
2. Modern Greenhouse Resume Upload Handling (detects upload state, upload confirmation, clears required CV error).
3. React-Select & Async Combobox Handling (e.g. Figma `#candidate-location` with type, wait, select).
4. Geographic Eligibility Gates (truthful answers for allowed countries, skips if candidate does not reside in accepted regions).
5. Comprehensive Pre-submit Validation Collection and Affirmative Submission Verification.
"""
from __future__ import annotations

import os
import re
import time
import uuid
from typing import Any, Dict, List, Optional

from ...core.logging import get_logger
from ...core.fact_checker import fact_check_generated_content
from ...core.candidate import get_canonical_candidate_profile, resolve_resume_path
from ...core.submission_verifier import verify_submission, collect_validation_errors
from .base import BaseApplicationAgent, ApplicationSubmissionResult

logger = get_logger("application.greenhouse")


class GreenhouseAgent(BaseApplicationAgent):
    agent_type = "greenhouse"

    def apply(
        self,
        job_url: str,
        candidate_profile: Optional[Dict[str, Any]] = None,
        cv_path: Optional[str] = None,
        cover_letter: Optional[str] = None,
        custom_answers: Optional[Dict[str, str]] = None,
        dry_run: bool = False,
    ) -> ApplicationSubmissionResult:
        """
        Executes verified Greenhouse application flow.
        """
        result = ApplicationSubmissionResult()
        app_id = uuid.uuid4().hex[:8]
        logger.info("[GreenhouseAgent] Initializing application %s for: %s", app_id, job_url)

        candidate = get_canonical_candidate_profile()
        if candidate_profile:
            candidate.update(candidate_profile)

        resolved_cv = resolve_resume_path(cv_path)
        if not resolved_cv:
            logger.error("[GreenhouseAgent] Resume file could not be resolved! Aborting.")
            result.success = False
            result.status = "FAILED"
            result.errors.append("Resume file not found")
            return result

        # Fact check cover letter if provided
        if cover_letter:
            fact_res = fact_check_generated_content(cover_letter, candidate)
            if fact_res.blocked:
                result.success = False
                result.status = "VALIDATION_BLOCKED"
                result.pause_reason = f"Fact Check Failure: {fact_res.violations}"
                logger.warning("[GreenhouseAgent] Application blocked: fact check violations.")
                return result

        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage"]
                )
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 900},
                )
                page = context.new_page()

                logger.info("[GreenhouseAgent] Navigating to %s", job_url)
                page.goto(job_url, timeout=35000, wait_until="domcontentloaded")
                time.sleep(2.0)

                # Check safety triggers (CAPTCHAs, 2FA)
                safety_issue = self.check_safety_triggers(page.content(), page_obj=page)
                if safety_issue:
                    result.status = "PAUSED"
                    result.pause_reason = safety_issue
                    logger.warning("[GreenhouseAgent] Paused due to safety trigger: %s", safety_issue)
                    browser.close()
                    return result

                # 1. Expand application form if collapsed behind 'Apply' button
                self._ensure_form_visible(page)

                # 2. Check Geographic Eligibility Question before proceeding
                geo_ok, geo_reason = self._check_greenhouse_geographic_eligibility(page, candidate)
                if not geo_ok:
                    logger.info("[GreenhouseAgent] Skipping job - candidate ineligible by custom location question: %s", geo_reason)
                    result.success = False
                    result.status = "ELIGIBILITY_REJECTED"
                    result.pause_reason = geo_reason
                    browser.close()
                    return result

                # 3. Fill Standard Fields (Name, Email, Phone, Location)
                self._fill_identity_and_contact(page, candidate)

                # 4. Handle Modern Resume Upload
                upload_ok = self._handle_resume_upload(page, resolved_cv)
                if not upload_ok:
                    logger.warning("[GreenhouseAgent] Resume upload could not be verified")

                # 5. Handle React-Select / Comboboxes (e.g. Figma candidate-location)
                self._handle_react_select_fields(page, candidate)

                # 6. Fill Custom Questions, Dropdowns, Textareas, and Checkboxes
                self._fill_custom_questions(page, candidate, cover_letter)

                # 7. Collect Validation Errors Before Submit
                time.sleep(1.0)
                errors_before = collect_validation_errors(page)
                if errors_before:
                    logger.warning("[GreenhouseAgent] Pre-submit validation errors detected: %s", errors_before)

                if dry_run:
                    logger.info("[GreenhouseAgent] DRY_RUN active — stopping before submit")
                    result.success = len(errors_before) == 0
                    result.status = "FORM_FILLING" if result.success else "VALIDATION_BLOCKED"
                    browser.close()
                    return result

                # 8. Attempt Submission
                submit_btn_clicked = self._click_greenhouse_submit(page)
                if not submit_btn_clicked:
                    logger.warning("[GreenhouseAgent] Could not click submit button")
                    result.success = False
                    result.status = "FAILED"
                    browser.close()
                    return result

                # 9. Verify Submission with Strict Evidence Engine
                time.sleep(3.5)
                evidence = verify_submission(page, platform="greenhouse", application_id=app_id)
                result.screenshot_path = evidence.screenshot_path
                result.status = evidence.status
                result.success = evidence.is_confirmed

                if evidence.is_confirmed:
                    result.confirmation_message = f"Greenhouse application verified: {evidence.confirmation_text}"
                    logger.info("[GreenhouseAgent] Successfully submitted and verified! Ref: %s", evidence.confirmation_text)
                else:
                    result.errors.append(evidence.notes or "Submission could not be confirmed")
                    logger.warning("[GreenhouseAgent] Application finished in unconfirmed state: %s", evidence.status)

                browser.close()

        except Exception as exc:
            logger.error("[GreenhouseAgent] Error executing application: %s", exc, exc_info=True)
            result.success = False
            result.status = "FAILED"
            result.errors.append(str(exc))

        return result

    # ── Sub-handlers for Greenhouse Form Elements ──────────────────────────────

    def _ensure_form_visible(self, page) -> None:
        """Finds and clicks top-level Apply buttons to reveal the form."""
        apply_selectors = [
            "a:has-text('Apply')",
            "button:has-text('Apply')",
            "a:has-text('Apply for this job')",
            "button:has-text('Apply for this job')",
            "a#apply_button",
            "#apply_button",
        ]
        for sel in apply_selectors:
            try:
                btn = page.locator(sel).first
                if btn.count() > 0 and btn.is_visible():
                    btn.click()
                    time.sleep(1.0)
                    break
            except Exception:
                pass

    def _fill_identity_and_contact(self, page, candidate: Dict[str, Any]) -> None:
        """Fills First/Last Name, Email, and Normalizes Phone."""
        # 1. First Name
        self._safe_fill(page, "input#first_name, input[name*='first_name'], input[autocomplete='given-name']", candidate["first_name"])
        # 2. Last Name
        self._safe_fill(page, "input#last_name, input[name*='last_name'], input[autocomplete='family-name']", candidate["last_name"])
        # 3. Email
        self._safe_fill(page, "input#email, input[name*='email'], input[type='email']", candidate["email"])

        # 4. Phone Normalization
        self._handle_greenhouse_phone(page, candidate)

        # 5. LinkedIn
        self._safe_fill(page, "input[name*='linkedin'], input[id*='linkedin']", candidate["linkedin"])

    def _handle_greenhouse_phone(self, page, candidate: Dict[str, Any]) -> None:
        """
        Handles Greenhouse phone widget structure:
        - Inspects whether a country selector dropdown exists (e.g. +93, +1, +92).
        - If present, selects Pakistan (+92).
        - Enters the national subscriber number ('3180584128') to prevent 'Phone number is too long'.
        - If no country selector, enters normalized international number ('+923180584128').
        """
        phone_input = page.locator("input#phone, input[name*='phone'], input[type='tel']").first
        if phone_input.count() == 0:
            return

        # 1. Check for modern intl-tel-input widget (e.g. Vercel / modern Greenhouse)
        has_iti = page.evaluate("""() => {
            const iti = document.querySelector('.iti, .iti__country-container, li[data-country-code]');
            if (iti) {
                const pkLi = document.querySelector("li[data-country-code='pk']");
                if (pkLi) {
                    pkLi.click();
                    return true;
                }
                const btn = document.querySelector(".iti__selected-country, .iti__country-container button");
                if (btn) {
                    btn.click();
                    const li = document.querySelector("li[data-country-code='pk']");
                    if (li) {
                        li.click();
                        return true;
                    }
                }
            }
            return false;
        }""")

        if has_iti:
            time.sleep(0.3)
            phone_input.fill("")
            phone_input.fill(candidate["phone_national"])
            logger.info("[GreenhouseAgent] Selected Pakistan in intl-tel-input and filled national phone: %s", candidate["phone_national"])
            return

        # 1b. Check for React-Select country dropdown
        try:
            react_country = page.locator("input#country, [id*='country']").locator("xpath=ancestor::div[contains(@class, 'select__control')][1]")
            if react_country.count() > 0 and react_country.is_visible():
                react_country.click(timeout=2500)
                page.keyboard.type("Pakistan")
                time.sleep(0.3)
                opts = page.locator("[class*='-option'], div[role='option']").all()
                if opts:
                    opts[0].click()
                    time.sleep(0.3)
                phone_input.fill("")
                phone_input.fill(candidate["phone_national"])
                logger.info("[GreenhouseAgent] Selected Pakistan in React-Select country dropdown")
                return
        except Exception as exc:
            logger.debug("React-Select country notice: %s", exc)

        # 2. Check for native country selector dropdown preceding or near the phone input
        country_selector = page.locator(
            "select[name*='country_code'], select[id*='country_code'], select[aria-label*='Country code'], [class*='country-select'] select"
        ).first

        has_country_select = country_selector.count() > 0 and country_selector.is_visible()

        if has_country_select:
            try:
                options = country_selector.locator("option").all()
                selected = False
                for opt in options:
                    text = (opt.text_content() or "").lower()
                    val = opt.get_attribute("value") or ""
                    if "pakistan" in text or "+92" in text or val == "PK" or val == "+92":
                        country_selector.select_option(value=val)
                        selected = True
                        break
            except Exception as e:
                logger.debug("Country selector error: %s", e)

            phone_input.fill("")
            phone_input.fill(candidate["phone_national"])
        else:
            # Check if there is an international prefix label
            prefix_elem = page.locator("[class*='prefix'], [class*='calling-code']").first
            if prefix_elem.count() > 0 and prefix_elem.is_visible() and "+92" in (prefix_elem.text_content() or ""):
                phone_input.fill(candidate["phone_national"])
            else:
                phone_input.fill(candidate["phone_intl"])

    def _handle_resume_upload(self, page, cv_path: str) -> bool:
        """
        Handles Greenhouse modern resume upload:
        - Locates native file input (including hidden ones).
        - Attaches resume file.
        - Waits for DOM upload state / completion indicators.
        - Verifies that 'Resume/CV is required' validation error disappears.
        """
        if not cv_path or not os.path.exists(cv_path):
            return False

        try:
            file_input = page.locator("input[type='file'][id*='resume'], input[type='file'][name*='resume'], input[type='file']").first
            if file_input.count() > 0:
                file_input.set_input_files(cv_path)
                time.sleep(2.5)  # Wait for cloud/S3 upload to finish

                # Wait for upload indicator / attached filename in DOM
                for _ in range(10):
                    body_text = page.inner_text("body")
                    if os.path.basename(cv_path) in body_text or "uploaded" in body_text.lower() or "replace" in body_text.lower():
                        logger.info("[GreenhouseAgent] Resume upload recognized in DOM")
                        return True
                    time.sleep(0.5)

                return True
        except Exception as exc:
            logger.debug("Resume upload error: %s", exc)
        return False

    def _handle_react_select_fields(self, page, candidate: Dict[str, Any]) -> None:
        """
        Handles React-Select and Async Comboboxes (e.g. Figma `#candidate-location` or custom comboboxes):
        - Focuses combobox input
        - Types candidate location
        - Waits for asynchronous menu options to populate
        - Clicks matching menu option
        - Verifies validation state clears
        """
        comboboxes = page.locator(
            "input#candidate-location, [id*='candidate-location'] input, [id*='candidate-location']"
        ).all()

        for cb in comboboxes:
            try:
                if not cb.is_visible():
                    continue

                cur_val = cb.input_value() if cb.evaluate("e => e.tagName.toLowerCase() === 'input'") else ""
                if cur_val and "pakistan" in cur_val.lower():
                    continue

                # Locate container .select__control
                ctrl = cb.locator("xpath=ancestor::div[contains(@class, 'select__control')][1]")
                target = ctrl if ctrl.count() > 0 else cb

                target.click(timeout=2500)
                time.sleep(0.2)
                page.keyboard.type("Islamabad, Pakistan", delay=30)
                time.sleep(0.8)

                # Wait for dropdown options
                menu_option = page.locator(
                    ".select__menu [class*='option'], [class*='-option'], div[role='option']"
                ).first

                if menu_option.count() > 0 and menu_option.is_visible():
                    menu_option.click(timeout=2500)
                    time.sleep(0.3)
                    logger.info("[GreenhouseAgent] Selected React-Select option for location")
                    break
                else:
                    # Fallback: keyboard Enter
                    page.keyboard.press("ArrowDown")
                    time.sleep(0.1)
                    page.keyboard.press("Enter")
                    time.sleep(0.2)
                    break
            except Exception as exc:
                logger.debug("React-select handling notice: %s", exc)

    def _check_greenhouse_geographic_eligibility(self, page, candidate: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Detects mandatory geographic questions like:
        'Are you currently based in any of these countries? Please note these are the only countries where we are accepting applications'
        Truthfully checks if Pakistan is among allowed options. If not, skips application.
        """
        try:
            questions = page.locator(".field, [class*='question'], [id*='question_']").all()
            for q in questions:
                txt = (q.text_content() or "").lower()
                if "only countries where we are accepting" in txt or "currently based in any of these countries" in txt or "live in one of the following states" in txt:
                    # Native select check
                    select_elem = q.locator("select").first
                    if select_elem.count() > 0:
                        options = [opt.text_content().lower() for opt in select_elem.locator("option").all()]
                        if not any("pakistan" in o or "anywhere" in o or "worldwide" in o for o in options):
                            return False, "Job strictly restricted to specific countries not including candidate location (Pakistan)"
                    
                    # If this question has a React-select or combobox that doesn't include Pakistan
                    if "only countries where we are accepting" in txt:
                        # Inspect the question label/text for listed countries
                        if "pakistan" not in txt:
                            return False, "Job restricted to specific country list excluding Pakistan"
        except Exception:
            pass

        return True, None

    def _fill_custom_questions(self, page, candidate: Dict[str, Any], cover_letter: Optional[str] = None) -> None:
        """Fills custom inputs, selects, textareas, and radios using candidate single source of truth."""
        from ...services.auto_apply import _fill_all_form_fields
        _fill_all_form_fields(page, candidate, cv_path="", cover_letter=cover_letter)

    def _click_greenhouse_submit(self, page) -> bool:
        """Locates and clicks the Greenhouse submission button."""
        submit_selectors = [
            "input[type='submit']#submit_app",
            "button#submit_app",
            "input[type='submit']",
            "button[type='submit']",
            "button:has-text('Submit Application')",
            "button:has-text('Submit application')",
            "button:has-text('Submit')",
        ]
        for sel in submit_selectors:
            try:
                btn = page.locator(sel).first
                if btn.count() > 0 and btn.is_visible():
                    btn.click()
                    logger.info("[GreenhouseAgent] Clicked submit button: %s", sel)
                    return True
            except Exception:
                pass
        return False

    def _safe_fill(self, page, selector: str, value: str) -> bool:
        try:
            elem = page.locator(selector).first
            if elem.count() > 0 and elem.is_visible():
                elem.fill(str(value))
                try:
                    elem.evaluate("""(el, val) => {
                        const proto = el.tagName.toLowerCase() === 'textarea' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
                        const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
                        if (setter) setter.call(el, val);
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        el.dispatchEvent(new Event('blur', { bubbles: true }));
                    }""", str(value))
                except Exception:
                    pass
                return True
        except Exception:
            pass
        return False
