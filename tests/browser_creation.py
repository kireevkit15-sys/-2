"""Browser regression against a running disposable GeoTrace instance.
Usage: python tests/browser_creation.py http://127.0.0.1:8000
Requires Playwright and Chromium for development only. Adds test samples.
"""
import os
import sys
from playwright.sync_api import sync_playwright

url=sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8000'
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH','/usr/bin/chromium'),headless=True,args=['--no-sandbox'])
    page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.add_init_script("Storage.prototype.getItem=function(){throw new DOMException('Storage disabled','SecurityError')};Storage.prototype.setItem=function(){throw new DOMException('Storage disabled','SecurityError')}")
    page.goto(url);page.wait_for_function("document.querySelector('#pageInfo').textContent.length>0")
    page.locator('#newSample').click()
    form=page.locator('#createForm')
    for field,value in dict(site='Проверка хранилища',profile='ПР-01',point='Т-001').items():form.locator(f'[name="{field}"]').fill(value)
    form.get_by_role('button',name='Создать пробу',exact=True).click();page.wait_for_selector('#detailDialog[open]')
    first_code=page.locator('#detail h2').first.inner_text()
    assert first_code.startswith('GC-')
    page.locator('#detailDialog .close').click()
    # Invalid QR configuration must not invalidate a successfully created sample.
    page.locator('#baseUrl').fill('wrong-url');page.locator('#baseUrl').press('Tab')
    page.locator('#newSample').click()
    for field,value in dict(site='Проверка адреса QR',profile='ПР-02',point='Т-001').items():form.locator(f'[name="{field}"]').fill(value)
    form.get_by_role('button',name='Создать пробу',exact=True).click();page.wait_for_selector('#detailDialog[open]')
    assert 'Проба сохранена' in page.locator('#detail').inner_text()
    page.locator('#detailDialog .close').click()
    page.locator('#baseUrl').fill(url);page.locator('#baseUrl').press('Tab')
    page.locator('#newBatch').click();batch=page.locator('#batchForm');batch.locator('[name="site"]').fill('Серия при запрещённом хранилище');batch.locator('[name="per_profile"]').fill('5')
    batch.get_by_role('button',name='Создать серию',exact=True).click();page.wait_for_function("document.querySelector('#batchFilter').value!==''")
    assert page.locator('#rows tr').count()==5
    # A newly created individual sample must be visible outside the old series filter.
    page.locator('#newSample').click()
    for field,value in dict(site='После серии',profile='ПР-03',point='Т-001').items():form.locator(f'[name="{field}"]').fill(value)
    form.get_by_role('button',name='Создать пробу',exact=True).click();page.wait_for_selector('#detailDialog[open]')
    assert page.locator('#batchFilter').input_value()==''
    page.locator('#detailDialog .close').click();page.reload();page.wait_for_selector('#rows tr')
    assert page.locator('#rows').inner_text().find(first_code)>=0
    # Server errors must be visible IN the modal, not behind it.
    page.route('**/api/samples',lambda route:route.fulfill(status=503,content_type='application/json',body='{"error":"База занята — тест"}') if route.request.method=='POST' else route.continue_())
    page.locator('#newSample').click()
    for field,value in dict(site='Ошибка',profile='1',point='1').items():form.locator(f'[name="{field}"]').fill(value)
    form.get_by_role('button',name='Создать пробу',exact=True).click();page.locator('#createDialog .form-error').wait_for(state='visible')
    assert 'База занята' in page.locator('#createDialog .form-error').inner_text()
    assert not form.get_by_role('button',name='Создать пробу',exact=True).is_disabled()
    page.locator('#createDialog .close').first.click();page.unroute('**/api/samples')
    # An old server must be diagnosed before submitting any write.
    page.route('**/api/health',lambda route:route.fulfill(status=404,content_type='application/json',body='{"error":"not found"}'))
    writes=[];page.on('request',lambda r:writes.append(r.url) if r.method=='POST' else None)
    page.locator('#newBatch').click();batch.locator('[name="site"]').fill('Старый сервер');batch.get_by_role('button',name='Создать серию',exact=True).click()
    page.locator('#batchDialog .form-error').wait_for(state='visible');assert 'другая версия' in page.locator('#batchDialog .form-error').inner_text();assert not writes
    assert not errors,errors
    browser.close()
print('PASS: storage denied, single creation, batch creation, invalid QR address, filter reset, reload, visible DB errors, stale server blocked')
