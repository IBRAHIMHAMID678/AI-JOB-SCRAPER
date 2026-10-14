"""
Stealth Browser Configuration & Automated Bot-Mitigation Helpers.
Hardens Playwright contexts against headless detection and anti-automation tripwires
without requiring human intervention.
"""
from __future__ import annotations

import random
import time
from typing import Any, Dict, Optional

STEALTH_LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--window-position=0,0",
    "--ignore-certificate-errors",
    "--ignore-ssl-errors",
]

STEALTH_INIT_SCRIPT = """
// 1. Evade navigator.webdriver detection
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined
});

// 2. Mock Chrome runtime
window.chrome = {
    app: { isInstalled: false, InstallState: { DISABLED: 'disabled' }, RunningState: { CANNOT_RUN: 'cannot_run' } },
    runtime: { OnInstalledReason: {}, OnRestartRequiredReason: {}, PlatformArch: {}, PlatformNaclArch: {}, PlatformOs: {}, RequestUpdateCheckStatus: {} },
    loadTimes: () => {},
    csi: () => {}
};

// 3. Mock languages and plugins
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en']
});

Object.defineProperty(navigator, 'plugins', {
    get: () => [
        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
        { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }
    ]
});

// 4. Overwrite permissions query
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
);
"""


def apply_stealth_to_context(context: Any) -> None:
    """Injects stealth init scripts and overrides into the browser context."""
    try:
        context.add_init_script(STEALTH_INIT_SCRIPT)
    except Exception:
        pass


def human_type(locator: Any, text: str, min_delay: float = 0.02, max_delay: float = 0.06) -> None:
    """
    Types text into a field with randomized human-like keystroke latencies
    to avoid tripping automated rapid-fill bot walls.
    """
    try:
        locator.focus()
        time.sleep(random.uniform(0.1, 0.25))
        for char in text:
            locator.type(char, delay=random.uniform(min_delay * 1000, max_delay * 1000))
        time.sleep(random.uniform(0.1, 0.2))
    except Exception:
        # Fallback to direct fill if typing fails
        locator.fill(text)
