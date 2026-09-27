"""
Lever Deep Application Agent & Conditional Form Engine.
Hardened according to AUTO_APPLY_HARDENING_MASTER_PROMPT specifications:
1. Multi-pass DOM scanning (observe -> interact -> DOM changes -> re-observe -> fill newly appeared fields).
2. Dynamic & Conditional question handling (e.g. Palantir conditional work-auth, residency, clearance dropdowns).
3. Multi-page form navigation (Next / Continue / Review / Submit).
4. Truthful question handling (never fabricates non-existent work authorization or clearance).
5. Affirmative submission verification using SubmissionEvidence.
"""
from __future__ import annotations

import os
import time
import uuid
from typing import Any, Dict, List, Optional

from ...core.logging import get_logger
from ...core.fact_checker import fact_check_generated_content
from ...core.candidate import get_canonical_candidate_profile, resolve_resume_path
from ...core.submission_verifier import verify_submission, collect_validation_errors
from .base import BaseApplicationAgent, ApplicationSubmissionResult

logger = get_logger("application.lever")


class LeverAgent(BaseApplicationAgent):
    agent_type = "lever"

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
        Executes hardened Lever application flow with conditional question loops.
        """
        result = ApplicationSubmissionResult()
        app_id = uuid.uuid4().hex[:8]
        logger.info("[LeverAgent] Initializing application %s for: %s", app_id, job_url)

        candidate = get_canonical_candidate_profile()
        if candidate_profile:
            candidate.update(candidate_profile)

        resolved_cv = resolve_resume_path(cv_path)
        if not resolved_cv:
            result.success = False
            result.status = "FAILED"
            result.errors.append("Resume file not found")
            return result

        if cover_letter:
            fact_res = fact_check_generated_content(cover_letter, candidate)
            if fact_res.blocked:
                result.success = False
                result.status = "VALIDATION_BLOCKED"
                result.pause_reason = f"Fact Check Failure: {fact_res.violations}"
                return result

        try:
            from playwright.sync_api import sync_playwright
            from ...services.auto_apply import _fill_all_form_fields

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 900},
                )
                page = context.new_page()

                logger.info("[LeverAgent] Navigating to %s", job_url)
                page.goto(job_url, timeout=35000, wait_until="domcontentloaded")
                time.sleep(2.0)

                safety_issue = self.check_safety_triggers(page.content(), page_obj=page)
                if safety_issue:
                    result.status = "PAUSED"
                    result.pause_reason = safety_issue
                    browser.close()
                    return result

                # Accept cookies if banner visible
                self._dismiss_cookies(page)

                # Click initial Lever 'Apply for this job' or 'Apply' button
                self._click_apply_button(page)

                # Multi-page / Conditional loop (observe -> fill -> check for newly appeared fields -> next)
                max_passes = 4
                pass_num = 0
                total_filled = 0

                while pass_num < max_passes:
                    pass_num += 1
                    filled_in_pass = _fill_all_form_fields(page, candidate, cv_path=resolved_cv, cover_letter=cover_letter)
                    total_filled += filled_in_pass
                    logger.info("[LeverAgent] Pass %d filled %d fields (total: %d)", pass_num, filled_in_pass, total_filled)

                    # Look for conditional questions that might have appeared
                    time.sleep(0.8)
                    has_more_conditional = self._check_unfilled_visible_fields(page)
                    if not has_more_conditional:
                        break

                # If multi-step (e.g. Next / Continue buttons)
                self._handle_multistep_navigation(page, candidate, resolved_cv, cover_letter)

                # Pre-submit validation scan
                errors_before = collect_validation_errors(page)
                if errors_before:
                    logger.warning("[LeverAgent] Pre-submit validation errors detected: %s", errors_before)

                if dry_run:
                    logger.info("[LeverAgent] DRY_RUN active — stopping before submit")
                    result.success = len(errors_before) == 0
                    result.status = "FORM_FILLING" if result.success else "VALIDATION_BLOCKED"
                    browser.close()
                    return result

                # Submit form
                submit_clicked = self._click_lever_submit(page)
                if not submit_clicked:
                    logger.warning("[LeverAgent] Could not click submit button on Lever page")
                    result.success = False
                    result.status = "FAILED"
                    browser.close()
                    return result

                # Affirmative submission verification
                time.sleep(3.5)
                evidence = verify_submission(page, platform="lever", application_id=app_id)
                result.screenshot_path = evidence.screenshot_path
                result.status = evidence.status
                result.success = evidence.is_confirmed

                if evidence.is_confirmed:
                    result.confirmation_message = f"Lever application verified: {evidence.confirmation_text}"
                    logger.info("[LeverAgent] Successfully submitted and verified! Ref: %s", evidence.confirmation_text)
                else:
                    result.errors.append(evidence.notes or "Lever submission unconfirmed")
                    logger.warning("[LeverAgent] Lever application unconfirmed: %s", evidence.status)

                browser.close()

        except Exception as exc:
            logger.error("[LeverAgent] Exception during Lever execution: %s", exc, exc_info=True)
            result.success = False
            result.status = "FAILED"
            result.errors.append(str(exc))

        return result

    def _dismiss_cookies(self, page) -> None:
        cookie_btn = page.locator("button:has-text('ACCEPT'), button:has-text('Accept'), a:has-text('Accept')").first
        if cookie_btn.count() > 0 and cookie_btn.is_visible():
            try:
                cookie_btn.click()
                time.sleep(0.5)
            except Exception as exc:
                logger.warning("[LeverAgent] Failed dismissing cookie banner: %s", exc)

    def _click_apply_button(self, page) -> None:
        apply_btn = page.locator(
            "a:has-text('APPLY'), a:has-text('Apply for this job'), button:has-text('Apply for this job'), a.postings-btn"
        ).first
        if apply_btn.count() > 0 and apply_btn.is_visible():
            try:
                apply_btn.click()
                time.sleep(1.5)
            except Exception as exc:
                logger.warning("[LeverAgent] Failed clicking apply button: %s", exc)

    def _check_unfilled_visible_fields(self, page) -> bool:
        """Checks if any visible input or select elements remain empty."""
        try:
            empty_inputs = page.locator("input:not([type='hidden']):not([type='submit']):not([type='button'])").all()
            for inp in empty_inputs:
                if inp.is_visible() and not inp.input_value():
                    return True
        except Exception as exc:
            logger.warning("[LeverAgent] Empty-field check failed: %s", exc)
        return False

    def _handle_multistep_navigation(self, page, candidate: Dict[str, Any], cv_path: str, cover_letter: Optional[str]) -> None:
        """Handles multi-step pages by clicking 'Next' or 'Continue' and filling subsequent sections."""
        from ...services.auto_apply import _fill_all_form_fields
        for _ in range(3):
            next_btn = page.locator(
                "button:has-text('Next'), button:has-text('Continue'), a:has-text('Next'), a:has-text('Continue')"
            ).first
            if next_btn.count() > 0 and next_btn.is_visible():
                try:
                    next_btn.click()
                    time.sleep(1.5)
                    _fill_all_form_fields(page, candidate, cv_path, cover_letter)
                except Exception as exc:
                    logger.warning("[LeverAgent] Multi-step navigation/fill failed: %s", exc)
                    break
            else:
                break

    def _click_lever_submit(self, page) -> bool:
        submit_selectors = [
            "button#btn-submit",
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Submit application')",
            "button:has-text('Submit Application')",
            "button:has-text('Submit')",
        ]
        for sel in submit_selectors:
            try:
                btn = page.locator(sel).first
                if btn.count() > 0 and btn.is_visible():
                    btn.click()
                    logger.info("[LeverAgent] Clicked Lever submit button: %s", sel)
                    return True
            except Exception as exc:
                logger.warning("[LeverAgent] Failed clicking submit selector '%s': %s", sel, exc)
        return False
