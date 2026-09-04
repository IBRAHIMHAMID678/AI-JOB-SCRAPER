from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('https://job-boards.greenhouse.io/vercel/jobs/6102343004', wait_until='networkidle')
    page.wait_for_timeout(2000)
    
    phone = page.locator('input#phone').first
    phone.scroll_into_view_if_needed()
    page.wait_for_timeout(500)
    
    iti_btn = page.locator('button.iti__selected-country').first
    print('iti_btn visible after scroll:', iti_btn.is_visible())
    
    style = iti_btn.evaluate("el => window.getComputedStyle(el).display + ' / ' + window.getComputedStyle(el).visibility + ' / opacity:' + window.getComputedStyle(el).opacity")
    print('Computed style:', style)
    print('Bounding box:', iti_btn.bounding_box())
    
    # Try selecting Pakistan via JS or direct click
    res = page.evaluate("""() => {
        const li = document.querySelector("li[data-country-code='pk']");
        if (li) {
            li.click();
            return 'clicked pk li';
        }
        return 'no pk li';
    }""")
    print('JS select pk result:', res)
    
    # Also check if intlTelInput instance exists on phone input
    iti_instance = page.evaluate("""() => {
        const input = document.querySelector('#phone');
        if (window.intlTelInputGlobals) {
            const iti = window.intlTelInputGlobals.getInstance(input);
            if (iti) {
                iti.setCountry('pk');
                iti.setNumber('3180584128');
                return 'setCountry pk via intlTelInputGlobals success';
            }
        }
        return 'no globals';
    }""")
    print('iti_instance result:', iti_instance)
    
    browser.close()
