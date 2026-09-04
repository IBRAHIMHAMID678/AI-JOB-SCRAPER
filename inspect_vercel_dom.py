from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('https://job-boards.greenhouse.io/vercel/jobs/6102343004', wait_until='networkidle')
    page.wait_for_timeout(2000)
    
    # Check phone elements
    phone = page.locator('input#phone, input[name*="phone"]').first
    print('Phone input count:', phone.count())
    if phone.count() > 0:
        parent_html = phone.evaluate('el => el.parentElement.parentElement.innerHTML')
        print('Phone container html snippet:', parent_html[:400])

    # Check custom questions
    custom = page.locator('[id*="question_"]').all()
    print('Custom question elements count:', len(custom))
    for q in custom[:8]:
        tag = q.evaluate('el => el.tagName')
        qid = q.get_attribute('id')
        name = q.get_attribute('name')
        label = q.evaluate('el => el.closest("label")?.innerText || document.querySelector(`label[for="${el.id}"]`)?.innerText || el.parentElement?.innerText || ""')
        print(f' - ID: {qid} | Tag: {tag} | Name: {name} | Label: {label[:60].strip()}')
        
    browser.close()
