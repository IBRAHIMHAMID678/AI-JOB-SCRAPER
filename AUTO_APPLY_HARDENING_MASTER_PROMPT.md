# AUTO-APPLY ENGINE — DEEP END-TO-END HARDENING & COMPLETION PROMPT

## ROLE

You are the primary autonomous engineer responsible for completing and hardening the existing Job Scraper / JobPilot auto-apply engine.

This is an existing production/testing codebase. **Do not create a parallel toy implementation.** Work directly against the real repository, real browser automation, real ATS integrations, and existing persistence layers.

Your mission is to take the current auto-apply implementation from its present audited state to a **reliably verified, production-grade application engine**.

You must continue working until all acceptance criteria below are satisfied.

Do not stop after identifying problems.

Do not stop after making code changes.

Do not stop after one successful test.

Do not declare success because unit tests pass.

The definition of done is **verified end-to-end browser behavior + correct persistence + correct eligibility filtering + regression safety**.

---

# 1. CURRENT VERIFIED STATE

The previous audit established the following facts.

## Verified real submissions

### Figma

Role:

`Manager, Software Engineering - DevEx AI Tools`

Platform:

Greenhouse

Verified:

* 21 form fields completed
* Name
* Email
* Phone
* Resume
* LinkedIn
* Custom AI technical statements
* Submit button successfully clicked
* No blocking validation errors remained
* Status correctly recorded as `SUBMITTED`

### Palantir

Role:

`Forward Deployed Software Engineer`

Platform:

Lever

Verified:

* 57 form fields completed
* Submit action successfully completed
* Submission confirmed
* Status correctly recorded as `SUBMITTED`

These two successful applications are valuable regression fixtures.

DO NOT accidentally break their working paths while fixing other ATS behavior.

---

# 2. CRITICAL HISTORICAL BUG

The old implementation used:

`staged_application_payload`

to record applications as `SUBMITTED` even when the browser had not actually submitted the application.

That behavior has already been removed.

This must remain permanently removed.

## NON-NEGOTIABLE RULE

Never set:

`SUBMITTED`

merely because:

* fields were filled
* submit was attempted
* a button was clicked
* a network request was initiated
* a payload was constructed
* a local state transition occurred
* an exception did not occur

`SUBMITTED` requires browser-level evidence.

The engine must distinguish at minimum between:

* `DISCOVERED`
* `ELIGIBILITY_REJECTED`
* `STARTED`
* `FORM_FILLING`
* `VALIDATION_BLOCKED`
* `SUBMIT_ATTEMPTED`
* `SUBMITTED`
* `SUBMISSION_UNCONFIRMED`
* `FAILED`
* `SKIPPED`

If the application cannot prove submission, it must NOT claim submission.

---

# 3. CURRENT REAL-WORLD FAILURES

The audit found these actual browser failures.

## Greenhouse — Canonical

### Problem A — Country code / phone mismatch

Some Greenhouse forms display a country selector.

Example:

Afghanistan `+93`

The automation then enters a full phone number and the form rejects it with:

`Phone number is too long`

The engine must understand that:

* country calling code
* country selector
* national number
* international number

are related but separate pieces of form state.

Do not solve this with a blind string truncation.

Build a proper phone normalization strategy.

The automation must:

1. inspect the current selected country
2. identify the phone widget structure
3. determine whether the input expects:

   * national number
   * international number
   * number without country code
4. set the appropriate country selector
5. enter the appropriate local/national number
6. verify the resulting DOM/form value
7. verify validation state
8. only continue when the field is accepted

Do not assume every Greenhouse phone widget behaves identically.

---

# 4. GREENHOUSE — RESUME/CV UPLOAD

Newest Greenhouse layouts may contain a secondary CV/resume interaction.

A direct file assignment may leave:

`Resume/CV is required`

even though the underlying file input appears populated.

The engine must handle modern Greenhouse upload flows robustly.

Investigate the actual DOM.

Determine:

* hidden file input
* visible upload button
* drag/drop wrapper
* upload state
* asynchronous upload completion
* React state
* validation state

Implement a reusable Greenhouse resume upload handler.

It must:

1. locate the actual file input or supported upload target
2. attach the resume
3. wait for upload completion
4. verify that Greenhouse recognizes the uploaded file
5. inspect validation state
6. retry using the supported UI interaction if direct assignment does not update application state
7. never mark the form complete until the resume requirement is genuinely satisfied

Do not use arbitrary sleeps as the primary synchronization mechanism.

Prefer:

* DOM state
* mutation/state changes
* upload indicators
* network completion where appropriate
* validation state
* explicit UI state

---

# 5. GREENHOUSE — VERCEL GEOGRAPHIC ELIGIBILITY

Some Greenhouse forms contain mandatory custom questions such as:

"Are you currently based in any of these countries? Please note these are the only countries where we are accepting applications"

This must be treated as an actual eligibility gate.

Do NOT blindly choose an answer just to make the form submit.

The engine must:

1. detect geographic eligibility questions
2. understand the candidate's configured work/location eligibility
3. determine whether the candidate genuinely qualifies
4. select the correct allowed option only when justified
5. reject/skip the job when the candidate is not eligible
6. persist the rejection reason

The system must never falsify:

* location
* residency
* work authorization
* citizenship
* visa status
* employment eligibility

If the job requires a country that does not match the candidate profile, skip it.

---

# 6. GREENHOUSE — FIGMA REACT-SELECT LOCATION

Figma uses a dynamic:

`#candidate-location`

React-Select-style asynchronous combobox.

Typing alone is insufficient.

The engine must:

1. focus the actual combobox
2. type the location
3. wait for async options
4. detect the popup/listbox
5. choose the appropriate option
6. verify the selected value exists in the control
7. verify validation errors disappear

Do not simply set:

`input.value`

for React-controlled components.

The reusable strategy should support React Select / custom async comboboxes generally.

---

# 7. LEVER — CONDITIONAL QUESTIONS

Lever forms can contain conditional and multi-page questions.

Example:

Palantir Japan produced many fields and eventually exposed strict country/residency/work-authorization requirements.

The engine must correctly handle:

* conditional questions
* dynamically appearing fields
* dependent dropdowns
* multi-page forms
* fields that appear only after another answer
* validation appearing after interaction
* country/residency questions
* work authorization questions

The automation must re-scan the form after meaningful state-changing interactions.

Do not assume:

`find fields once → fill fields once → submit`

is sufficient.

The correct mental model is:

`observe → interact → DOM changes → re-observe → interact → validate → continue`

---

# 8. EXPERIENCE & SENIORITY GATEKEEPER

The existing implementation is in:

`jobpilot/services/auto_apply.py`

It already contains a strict Experience & Seniority Gatekeeper.

Preserve and strengthen it.

Current requirements:

## Experience

Skip jobs explicitly requiring:

`>3 years`

Examples:

* 4+ years
* 5+ years
* 5-7 years
* 4 years minimum
* minimum 4 years
* at least 4 years

The parser must handle wording variations rather than relying only on one regex.

Be careful with:

* "3+ years"
* "2-4 years"
* "3 years preferred"
* "3 years experience required"
* "experience with..."
* "up to 3 years"

Do not incorrectly reject a job merely because the description mentions someone else having many years of experience.

Distinguish:

* required experience
* preferred experience
* team/company background
* unrelated contextual text

## Seniority

Reject titles indicating seniority beyond the target profile, including:

* Manager
* Director
* Lead
* Principal
* Staff
* VP
* Head of
* PhD

But do not rely only on title matching.

Inspect title + description when necessary.

Avoid false positives.

Example:

"Engineering Manager tools used by our team"

is not necessarily the candidate's role.

The gatekeeper should classify the actual job seniority.

---

# 9. IMPORTANT — DO NOT TRUST INGESTION COUNT

Previous audit:

`352` ingested jobs

`90` direct ATS roles matched candidate criteria.

Do not treat this ratio as proof that the gatekeeper is correct.

Build a proper audit.

For every rejected job, capture:

* job ID
* title
* company
* source
* matched rule
* evidence text
* decision
* timestamp

For every accepted job, capture:

* job ID
* title
* company
* source
* experience interpretation
* seniority interpretation
* eligibility result
* final decision

Create tests covering false positives and false negatives.

---

# 10. CANDIDATE PROFILE MUST BE A SINGLE SOURCE OF TRUTH

Find the current candidate profile/resume/application configuration in the repository.

Do not duplicate candidate information across random files.

Determine the authoritative source for:

* name
* email
* phone
* location
* LinkedIn
* GitHub
* resume path
* skills
* education
* experience
* work authorization
* geographic eligibility
* desired seniority
* years of experience

If the architecture currently has duplicated values, consolidate or create a clear canonical application profile abstraction.

ATS adapters should consume the canonical profile.

They should not independently invent candidate data.

---

# 11. BUILD A GENERIC ATS FORM ENGINE

Do not hardcode every individual company's selectors.

Architecture should support reusable strategies.

At minimum:

## ATS adapters

Create or strengthen platform-specific adapters for:

### Greenhouse

Responsibilities:

* form discovery
* text inputs
* textareas
* select elements
* React Select
* async comboboxes
* country selectors
* phone fields
* resume upload
* checkboxes
* radio groups
* custom questions
* validation
* submit detection
* confirmation detection

### Lever

Responsibilities:

* form discovery
* text inputs
* textareas
* selects
* custom questions
* conditional fields
* multi-step forms
* resume upload
* validation
* submission detection
* confirmation detection

The system must have a shared abstraction above these adapters.

---

# 12. FORM FIELD CLASSIFICATION

Create/review a field classification system.

Fields should be classified into types such as:

* name
* first_name
* last_name
* email
* phone
* location
* address
* resume
* LinkedIn
* GitHub
* portfolio
* education
* degree
* school
* graduation date
* experience
* work authorization
* sponsorship
* country
* residency
* salary
* start date
* custom text question
* custom select question
* radio question
* checkbox
* unknown

Do not blindly answer unknown questions.

---

# 13. CUSTOM QUESTION SAFETY

Custom application questions require special handling.

The engine may answer questions when the answer can be truthfully derived from the canonical candidate profile or job context.

Examples:

* years of experience
* skills
* education
* location
* LinkedIn
* GitHub
* availability

Questions involving factual eligibility must use actual candidate data.

Never fabricate:

* employment history
* degree
* certification
* citizenship
* residency
* work authorization
* visa
* security clearance
* criminal record
* disability
* veteran status
* demographic information
* sponsorship eligibility

If the engine cannot determine the answer truthfully:

`DO NOT GUESS`

Instead:

* mark the field unresolved
* record the reason
* stop submission
* persist `VALIDATION_BLOCKED` / `SUBMISSION_UNCONFIRMED`
* surface the job for review if the product supports manual review

---

# 14. SUBMISSION VERIFICATION ENGINE

This is one of the most important requirements.

Create a dedicated submission verification layer.

A successful submission should require strong evidence.

Possible evidence:

1. URL transition to confirmation page
2. known confirmation heading/text
3. confirmation container
4. successful response/navigation
5. application reference where available
6. form disappearance followed by confirmation state
7. ATS-specific confirmation marker

Do NOT consider:

* button click alone
* disabled button
* lack of exception
* network request alone

to be proof.

Create an evidence object such as:

* platform
* submission_attempted_at
* confirmation_detected_at
* confirmation_type
* confirmation_text/selector identifier
* final_url
* browser/page state
* screenshot path
* validation_errors_before_submit
* validation_errors_after_submit

Persist this alongside the application record.

---

# 15. SUBMISSION STATE MACHINE

Implement an explicit state machine.

Example:

```text
DISCOVERED
    ↓
ELIGIBILITY_CHECK
    ↓
ELIGIBLE
    ↓
STARTED
    ↓
FORM_DISCOVERY
    ↓
FORM_FILLING
    ↓
VALIDATION_CHECK
    ├── blocked → VALIDATION_BLOCKED
    ↓
SUBMIT_ATTEMPTED
    ↓
CONFIRMATION_CHECK
    ├── confirmed → SUBMITTED
    └── uncertain → SUBMISSION_UNCONFIRMED
```

No code path should jump directly from:

`FORM_FILLING → SUBMITTED`

without verification.

Audit all existing status transitions.

Search the entire repository for:

* `SUBMITTED`
* `submitted`
* `application_status`
* `status`
* `staged_application_payload`
* submission persistence
* application creation/update
* success handling

Identify every possible path that can produce `SUBMITTED`.

Make sure every path is guarded.

---

# 16. PERSISTENCE

Applications currently exist in:

## MongoDB

Host:

`mongodb://localhost:27017/`

Database:

`job_scraper_db`

Collection:

`applications`

## SQLite

Path:

`d:\Job Scraper\jobpilot.db`

Table:

`applications`

The two stores must not contradict one another.

Investigate:

* which is authoritative
* synchronization logic
* duplicate application behavior
* status updates
* retries
* crash recovery

If MongoDB and SQLite are both intentional, create a clear consistency strategy.

At minimum:

* application ID
* job ID
* platform
* company
* role
* URL
* status
* timestamps
* submission evidence
* failure reason
* strategy
* screenshot paths
* eligibility decision

must remain consistent.

---

# 17. IDEMPOTENCY / DUPLICATE PROTECTION

The engine must NEVER accidentally apply twice to the same job.

Before starting an application:

check existing records by stable identity.

Use appropriate keys such as:

* canonical job URL
* ATS job ID
* platform + job ID
* normalized company + role + URL where necessary

Handle URL tracking parameters.

Example:

same job:

`?gh_jid=123`

versus canonical URL without tracking parameters.

Do not accidentally treat the same job as two jobs.

---

# 18. RETRY SAFETY

Retries must be state-aware.

If:

`SUBMIT_ATTEMPTED`

occurred but confirmation was lost because the browser crashed:

DO NOT blindly resubmit.

Instead:

1. attempt to determine whether submission succeeded
2. inspect application state where possible
3. inspect ATS confirmation
4. mark `SUBMISSION_UNCONFIRMED` if proof is unavailable
5. require explicit safe retry logic

Never create duplicate submissions merely because the automation timed out.

---

# 19. BROWSER AUTOMATION RELIABILITY

Audit the browser layer thoroughly.

The automation must handle:

* headed Chrome
* page navigation
* redirects
* async rendering
* React components
* dynamic forms
* iframes where applicable
* stale elements
* delayed validation
* upload completion
* popups
* dropdown menus
* autocomplete
* scroll/visibility
* lazy-rendered fields

Avoid arbitrary:

```python
sleep(5)
```

as the primary mechanism.

Use deterministic waits wherever possible.

If sleeps are retained as fallback stabilization, keep them short and explain why they exist.

---

# 20. FORM OBSERVABILITY

Every application attempt should generate useful diagnostic information.

Capture:

* ATS/platform
* URL
* title/company
* detected fields
* field classifications
* fields successfully filled
* unresolved fields
* validation errors
* selector/strategy used
* upload status
* submit attempt
* confirmation result
* final state
* screenshot(s)
* failure reason

Do not dump sensitive candidate data into logs unnecessarily.

Mask:

* email
* phone
* addresses
* tokens
* credentials

where appropriate.

---

# 21. SCREENSHOT EVIDENCE

Current screenshot directory:

`d:\Job Scraper\jobpilot\screenshots\`

Preserve this system and improve it.

Capture screenshots at meaningful milestones:

1. form loaded
2. validation failure
3. before submit
4. after submit attempt
5. confirmed submission
6. fatal failure

Use deterministic names.

Example:

```text
{application_id}_{platform}_{stage}_{timestamp}.png
```

Do not overwrite evidence from previous runs.

Persist screenshot paths in the application record.

---

# 22. ERROR CLASSIFICATION

Do not store every failure as a generic:

`FAILED`

Create useful categories.

Examples:

```text
ELIGIBILITY_REJECTED
EXPERIENCE_EXCEEDED
SENIORITY_REJECTED
LOCATION_INELIGIBLE
WORK_AUTHORIZATION_UNKNOWN
SPONSORSHIP_REQUIRED
FORM_FIELD_UNRESOLVED
PHONE_VALIDATION
RESUME_UPLOAD_FAILED
REACT_SELECT_FAILED
VALIDATION_BLOCKED
ATS_UNSUPPORTED
BROWSER_NAVIGATION_ERROR
SUBMISSION_UNCONFIRMED
SUBMISSION_CONFIRMED
DUPLICATE_APPLICATION
```

This will allow later analytics.

---

# 23. TEST MATRIX

Create a comprehensive automated test suite.

## Greenhouse tests

Must cover:

* simple form
* phone field
* country selector + phone
* resume upload
* React Select
* async location dropdown
* checkbox
* radio
* textarea
* custom question
* validation error
* successful submission
* confirmation detection

## Lever tests

Must cover:

* simple form
* conditional fields
* multi-step flow
* country question
* work authorization
* resume upload
* validation
* successful submission
* confirmation detection

---

# 24. LIVE BROWSER TESTS

Do not rely exclusively on mocked DOM tests.

Run actual browser tests against safe/test/real publicly accessible ATS pages where appropriate.

Use the previously identified roles/pages as regression targets where they are still accessible.

Regression targets:

### Greenhouse

* Figma
* Canonical
* Vercel

### Lever

* Palantir

Important:

If a job has closed or materially changed, locate another real public job on the same ATS platform and use that as a substitute regression fixture.

The purpose is to verify the platform behavior, not a specific company's job.

---

# 25. DO NOT AUTOMATICALLY SUBMIT RANDOM JOBS DURING TESTING

Separate:

## FORM TEST

Fill and validate but do not submit.

from:

## REAL APPLICATION TEST

Only perform a real submission when explicitly configured/authorized by the existing project workflow.

Never accidentally turn the entire test suite into mass applications.

Create an explicit test mode.

For example:

```text
DRY_RUN
FILL_ONLY
SUBMIT_ENABLED
```

Make the default test mode safe.

---

# 26. TEST FIXTURES

Build reusable ATS fixtures.

Where possible, create local HTML fixtures reproducing:

* Greenhouse phone behavior
* Greenhouse React Select
* Greenhouse upload behavior
* Vercel eligibility dropdown
* Lever conditional questions
* validation states
* confirmation pages

These allow deterministic regression testing without hitting live ATS systems for every unit/integration test.

Then supplement with real browser tests.

---

# 27. CANDIDATE-TO-JOB MATCHING

Before application begins, verify:

```text
job eligibility
        ↓
experience gate
        ↓
seniority gate
        ↓
location eligibility
        ↓
work authorization
        ↓
required qualifications
        ↓
application feasibility
        ↓
apply
```

The engine must not spend browser resources on jobs that should have been rejected earlier.

---

# 28. DO NOT APPLY TO OBVIOUSLY INELIGIBLE JOBS

Build a hard preflight gate.

Examples:

* explicitly requires 5 years experience → reject
* explicitly Senior/Staff/Principal → reject
* explicitly requires PhD → reject
* explicitly requires residency in an unsupported country → reject
* explicitly requires authorization the candidate does not have → reject
* explicitly says no remote eligibility where candidate requires remote → reject

Persist every rejection.

---

# 29. UNKNOWN ≠ ACCEPT

This is critical.

If a requirement cannot be determined:

Do not automatically accept.

Use:

```text
UNKNOWN
```

and route it according to the product's safe policy.

Especially for:

* work authorization
* sponsorship
* residency
* citizenship
* security clearance
* degree requirements
* experience requirements

---

# 30. APPLICATION PROFILE VALIDATION

Before launching the browser:

validate the candidate profile.

Ensure:

* required fields exist
* resume exists
* resume path is valid
* email valid
* phone valid
* URLs valid
* candidate experience is known
* location is known

Fail fast before opening ATS pages if the profile is incomplete.

---

# 31. RESUME VALIDATION

Verify the configured resume:

* exists
* readable
* correct extension
* non-zero size
* supported by ATS upload
* not corrupted

Do not repeatedly open a browser only to discover that the resume path is invalid.

---

# 32. FIELD STRATEGY PRIORITY

For each field, use this strategy:

```text
1. semantic/accessibility metadata
2. stable ID
3. stable name
4. associated label
5. platform-specific selector
6. controlled-component interaction
7. carefully bounded fallback
```

Do NOT build a giant fragile CSS selector list.

Avoid selectors based on:

* random generated classes
* DOM position
* nth-child where unnecessary
* visual coordinates

---

# 33. CONTROLLED REACT INPUTS

React-controlled inputs must be interacted with in a way that updates application state.

Do not simply mutate:

```javascript
element.value = ...
```

unless followed by a correct event sequence and verified state update.

For:

* React Select
* controlled inputs
* autocomplete
* custom comboboxes

use actual user-like interactions whenever practical.

Then verify the UI state.

---

# 34. VALIDATION ENGINE

Before submit:

scan the page for:

* required field errors
* invalid input messages
* red validation states
* aria-invalid
* error containers
* visible error text
* upload errors

Do not click submit repeatedly while validation errors remain.

Create:

```text
collect_validation_errors()
```

or equivalent.

Return structured errors.

Example:

```json
{
  "field": "candidate-location",
  "type": "required",
  "message": "Location is required"
}
```

---

# 35. SELF-HEALING FORM STRATEGY

When a field fails:

Do not immediately abort.

Try a bounded strategy sequence.

Example:

```text
strategy A
→ verify

if failed:
strategy B
→ verify

if failed:
strategy C
→ verify

if failed:
record precise failure
```

Do not retry indefinitely.

Maximum attempts must be bounded.

---

# 36. STRATEGY TELEMETRY

Persist which strategy succeeded.

Example:

```text
phone:
  strategy = greenhouse_country_then_local_number

location:
  strategy = react_select_type_select

resume:
  strategy = native_file_input_then_upload_verification
```

This lets future runs become more reliable.

---

# 37. APPLICATION AUDIT DASHBOARD / REPORT

If the existing project has a UI/dashboard, expose:

* total jobs
* eligible jobs
* rejected jobs
* started
* validation blocked
* submitted
* submission unconfirmed
* failed
* duplicate prevented

Break down by:

* ATS
* company
* reason
* date
* strategy

Do not fabricate statistics.

All numbers must come from persistence.

---

# 38. DATABASE AUDIT

Inspect both:

MongoDB:

`job_scraper_db.applications`

and:

SQLite:

`d:\Job Scraper\jobpilot.db`

Look for:

* false SUBMITTED records
* duplicate applications
* inconsistent status
* missing timestamps
* missing failure reasons
* missing evidence
* records created by old staged fallback logic

Do not silently delete historical evidence.

If old records are invalidly marked `SUBMITTED`, determine a safe migration strategy.

Potentially introduce:

```text
LEGACY_UNVERIFIED
```

rather than rewriting history without evidence.

---

# 39. MIGRATION / BACKWARD COMPATIBILITY

If schema changes are needed:

* add migrations
* preserve old records
* preserve IDs
* preserve screenshots
* maintain compatibility with existing UI/API consumers
* update serializers/types
* update MongoDB documents
* update SQLite schema safely

Do not break existing consumers.

---

# 40. SEARCH THE ENTIRE REPOSITORY

Before implementation, perform repository-wide searches for:

```text
SUBMITTED
staged_application_payload
application_status
applications
auto_apply
greenhouse
lever
resume
phone
candidate-location
react-select
submit
confirmation
screenshot
experience
seniority
Manager
Director
Principal
Staff
Lead
PhD
```

Map:

* call graph
* state transitions
* browser layer
* persistence
* UI
* tests
* CLI/API
* worker/background execution

Do not assume the files mentioned in this report are the only files involved.

---

# 41. USE PARALLEL SUB-AGENTS

Use as many read-only/review/testing sub-agents as practical.

Recommended roles:

### Agent 1

Audit application state machine.

### Agent 2

Audit Greenhouse adapter.

### Agent 3

Audit Lever adapter.

### Agent 4

Audit phone/resume handling.

### Agent 5

Audit experience/seniority gate.

### Agent 6

Audit MongoDB/SQLite persistence.

### Agent 7

Audit browser synchronization and selectors.

### Agent 8

Audit existing tests and identify coverage gaps.

### Agent 9

Run independent security/safety review of candidate-question handling.

### Agent 10

Perform final regression/audit.

Agents should primarily investigate/review/test independently.

Avoid conflicting writes.

Use isolated worktrees/branches if the environment supports them.

One integration owner should merge changes.

---

# 42. IMPLEMENTATION ORDER

Do not randomly patch issues.

Use this order:

## Phase 0 — Repository reconnaissance

Map architecture and existing behavior.

Deliver:

* files involved
* state flow
* database flow
* ATS adapters
* tests
* current failures

Do not make speculative changes before understanding the flow.

---

## Phase 1 — Submission truth model

Fix/verify:

* state machine
* submission confirmation
* false SUBMITTED prevention
* evidence persistence
* retry safety

This is foundational.

---

## Phase 2 — Candidate profile + eligibility

Fix:

* canonical profile
* experience gate
* seniority gate
* geographic eligibility
* authorization handling
* unknown handling

---

## Phase 3 — Greenhouse reliability

Implement:

* phone normalization
* country selector
* resume upload
* React Select
* async dropdowns
* validation scanning
* confirmation detection

---

## Phase 4 — Lever reliability

Implement:

* dynamic fields
* conditional questions
* multi-page behavior
* country/work authorization questions
* resume
* validation
* confirmation

---

## Phase 5 — Generic form abstraction

Extract reusable strategies.

Avoid company-specific hacks.

---

## Phase 6 — Persistence integrity

Verify:

* MongoDB
* SQLite
* synchronization
* idempotency
* evidence
* migrations

---

## Phase 7 — Testing

Run:

* unit tests
* integration tests
* fixture browser tests
* live ATS browser tests
* regression suite

---

## Phase 8 — Final live audit

Use real browser execution.

Verify:

1. eligible job
2. form discovery
3. form fill
4. validation
5. submit
6. confirmation
7. persistence
8. screenshot evidence

Then test an intentionally blocked/ineligible case.

Verify it does NOT submit.

---

# 43. TEST THE KNOWN FAILURE CASES

Do not merely test generic success.

Explicitly reproduce the previously observed failures.

## Test A

Greenhouse phone:

wrong country code initially selected.

Expected:

engine detects mismatch and corrects country/number representation.

Result:

no "Phone number is too long".

---

## Test B

Greenhouse resume:

direct file assignment.

Expected:

engine verifies actual upload state and performs fallback UI interaction if required.

Result:

no "Resume/CV is required".

---

## Test C

Greenhouse geographic question.

Expected:

engine correctly evaluates eligibility.

If eligible:

select truthful allowed answer.

If not eligible:

reject before submission.

---

## Test D

Figma React Select.

Expected:

type → async options → select → verify.

Result:

validation error clears.

---

## Test E

Lever conditional question.

Expected:

answer causes dependent field to appear → engine rescans → fills new field → validates.

---

# 44. NEGATIVE TESTS

Create explicit negative tests.

Examples:

### Experience

Job:

`Senior Software Engineer — 5+ years required`

Expected:

`EXPERIENCE_EXCEEDED`

No browser application.

### Seniority

Job:

`Staff Software Engineer`

Expected:

`SENIORITY_REJECTED`

### Location

Job:

`Must currently reside in Country X`

Candidate not in Country X.

Expected:

`LOCATION_INELIGIBLE`

### Authorization

Job requires authorization unavailable to candidate.

Expected:

`WORK_AUTHORIZATION_UNKNOWN` or `ELIGIBILITY_REJECTED`

depending on evidence.

### Unknown custom question

Expected:

application does not submit.

---

# 45. REGRESSION REQUIREMENT

The final test suite must prove that the fixes do not break the previously successful:

* Figma Greenhouse path
* Palantir Lever path

If those jobs are unavailable, reproduce their form characteristics with equivalent fixtures/live roles.

---

# 46. PERFORMANCE

Do not make the engine dramatically slower through unnecessary waits.

Measure:

* time to form discovery
* time to fill
* validation time
* upload time
* submission verification time

Use event-driven waits.

Reuse browser sessions only when safe.

Do not trade correctness for speed.

Correctness comes first.

---

# 47. LOGGING

Logs must clearly explain decisions.

Example:

```text
[ELIGIBILITY] REJECTED
job=...
reason=EXPERIENCE_EXCEEDED
evidence="4+ years required"
```

Example:

```text
[FORM] greenhouse
field=candidate-location
strategy=react_select_type_select
result=SUCCESS
```

Example:

```text
[SUBMISSION]
attempted=true
confirmation=true
confirmation_type=greenhouse_confirmation_page
status=SUBMITTED
```

Example:

```text
[SUBMISSION]
attempted=true
confirmation=false
status=SUBMISSION_UNCONFIRMED
reason=confirmation_not_detected
```

---

# 48. NO SILENT FALLBACKS

Every fallback must be explicit.

Never have code that silently turns:

```text
unknown
```

into:

```text
accepted
```

or:

```text
submit attempted
```

into:

```text
submitted
```

or:

```text
field missing
```

into:

```text
field guessed
```

---

# 49. SECURITY

Review:

* secrets
* environment variables
* database credentials
* browser cookies
* application logs
* screenshots

Do not leak:

* passwords
* API keys
* session cookies
* authentication headers

Screenshots containing sensitive candidate information should be stored only where intended.

---

# 50. FINAL DATA QUALITY AUDIT

After implementation, perform a complete audit of application records.

Report:

```text
Total application records:
Confirmed SUBMITTED:
Submission unconfirmed:
Validation blocked:
Failed:
Eligibility rejected:
Duplicates prevented:
```

Then verify:

```text
Every SUBMITTED record has submission evidence.
```

This is mandatory.

If even one record violates that rule:

DO NOT DECLARE COMPLETE.

Fix it and rerun the audit.

---

# 51. FINAL 30-APPLICATION AUDIT

Run a 30-application quality audit across the resulting application set where enough eligible test/application records exist.

For each record inspect:

* correct job
* correct company
* correct ATS
* correct eligibility
* correct candidate information
* correct fields
* correct resume
* no fabricated answers
* correct status
* submission evidence
* screenshot evidence
* persistence consistency

Score each record.

Target:

**30/30 valid records**

If any fail:

1. identify root cause
2. fix
3. rerun affected tests
4. rerun regression
5. repeat the 30-record audit

Do not stop at 29/30.

---

# 52. FINAL REGRESSION LOOP

You are explicitly instructed to work in this loop:

```text
INSPECT
↓
PLAN
↓
IMPLEMENT
↓
UNIT TEST
↓
INTEGRATION TEST
↓
BROWSER TEST
↓
AUDIT RESULTS
↓
IDENTIFY FAILURES
↓
FIX ROOT CAUSE
↓
RERUN FAILED TESTS
↓
RERUN REGRESSION
↓
RE-AUDIT
↓
REPEAT
```

Continue until there are no known failures relevant to this scope.

---

# 53. DEFINITION OF DONE

The task is complete only when ALL are true.

## Submission truth

* [ ] No fake/staged submission fallback exists.
* [ ] Every `SUBMITTED` record has browser confirmation evidence.
* [ ] Submission state machine is explicit.
* [ ] Unconfirmed submissions cannot become `SUBMITTED`.
* [ ] Retry cannot blindly duplicate an uncertain application.

## Eligibility

* [ ] >3 year explicit requirements are rejected.
* [ ] Senior/leadership roles are rejected according to policy.
* [ ] Geographic restrictions are evaluated truthfully.
* [ ] Work authorization is handled safely.
* [ ] Unknown eligibility is never silently accepted.

## Greenhouse

* [ ] Phone country-code issue solved.
* [ ] Resume upload issue solved.
* [ ] React Select solved.
* [ ] Async location selection solved.
* [ ] Validation detection works.
* [ ] Confirmation detection works.

## Lever

* [ ] Conditional fields solved.
* [ ] Multi-page behavior solved.
* [ ] Country/work authorization questions handled.
* [ ] Validation detection works.
* [ ] Confirmation detection works.

## Persistence

* [ ] MongoDB records correct.
* [ ] SQLite records correct.
* [ ] Statuses synchronized.
* [ ] Evidence persisted.
* [ ] Failure reasons persisted.
* [ ] Duplicate protection works.

## Testing

* [ ] Unit tests pass.
* [ ] Integration tests pass.
* [ ] Fixture browser tests pass.
* [ ] Live ATS tests pass where safely possible.
* [ ] Figma/Greenhouse regression passes.
* [ ] Palantir/Lever regression passes.
* [ ] Known failure reproductions pass.
* [ ] Negative tests pass.
* [ ] Full regression passes.

## Quality

* [ ] 30-record audit passes.
* [ ] No unexplained `SUBMITTED` records.
* [ ] No known false-positive applications.
* [ ] No fabricated candidate answers.
* [ ] No duplicate submissions.
* [ ] Screenshots/evidence are persisted.
* [ ] Logs are useful and safe.

---

# 54. FINAL REPORT FORMAT

When everything is actually complete, report:

## Implementation

List every file changed and why.

## Architecture

Explain:

* state machine
* ATS adapter architecture
* form strategy architecture
* eligibility pipeline
* submission verification

## Greenhouse

Report each fixed issue and how it was verified.

## Lever

Report each fixed issue and how it was verified.

## Persistence

Report MongoDB + SQLite behavior.

## Tests

Provide:

```text
Unit:
Integration:
Browser fixtures:
Live ATS:
Full regression:
```

Include exact counts.

## Application Audit

Provide:

```text
Confirmed submissions:
Unconfirmed:
Blocked:
Rejected:
Failed:
Duplicates prevented:
```

## Evidence

For confirmed submissions, provide:

* application ID
* company
* role
* ATS
* confirmation evidence
* screenshot evidence
* database persistence confirmation

## Remaining Issues

Only list genuine unresolved issues.

If none:

`NONE`

Do not hide failures behind a green summary.

---

# 55. ABSOLUTE FINAL INSTRUCTION

Do not optimize for making the report look successful.

Optimize for making the **system actually correct**.

If a test fails, investigate the root cause.

If a live ATS behaves differently from the fixture, update the abstraction.

If a selector is fragile, replace it.

If the state model allows false submission, fix the state model.

If persistence can disagree, fix persistence.

If a job is ineligible, do not apply.

If an answer is unknown, do not fabricate it.

If submission cannot be verified, do not call it submitted.

If regression breaks an earlier successful path, fix the regression before proceeding.

**Do not stop because the implementation "looks good."**

Continue the inspect → implement → test → audit → fix → regression loop until the complete definition of done is satisfied.

At the end, provide the exact evidence proving each acceptance criterion.

# END MASTER PROMPT
