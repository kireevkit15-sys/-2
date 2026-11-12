"""Browser coordinates regression; requires Playwright. Adds a small test series."""
import sys
URL=sys.argv[1] if len(sys.argv)>1 else "http://127.0.0.1:8000"
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
 b=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox']);page=b.new_page(viewport={'width':1440,'height':1100});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(URL);before=page.request.get(URL+'/api/samples').json();page.locator('#newBatch').click();f=page.locator('#batchForm')
 for key,value in dict(site='Участок с координатами',profiles='2',per_profile='2',start_profile='5',start_point='10').items():f.locator('[name="'+key+'"]').fill(value)
 f.locator('[name="coordinates_text"]').fill('60,1; 59,1\n60,2\t59,2\n60.3 59.3')
 f.get_by_role('button',name='Создать серию',exact=True).click();assert page.locator('#batchDialog .form-error').is_visible()
 assert len(page.request.get(URL+'/api/samples').json())==len(before)
 f.locator('[name="coordinates_text"]').fill('60,1; 59,1\n60,2\t59,2\n60.3 59.3\n-12.5 45.5')
 assert 'ПР-06' in page.locator('#coordinatePreview').inner_text()
 # Preview matches the mapping used by the backend.
 f.get_by_role('button',name='Создать серию',exact=True).click();page.wait_for_function("document.querySelector('#batchFilter').value!==''")
 bid=int(page.locator('#batchFilter').input_value());rows=sorted([r for r in page.request.get(URL+'/api/samples').json() if r['batch_id']==bid],key=lambda r:r['id'])
 assert [(r['latitude'],r['longitude']) for r in rows]==[(60.1,59.1),(60.2,59.2),(60.3,59.3),(-12.5,45.5)]
 assert [(r['profile'],r['point']) for r in rows]==[('ПР-05','Т-010'),('ПР-05','Т-011'),('ПР-06','Т-010'),('ПР-06','Т-011')]
 page.locator('#rows [data-open]').first.click();page.wait_for_selector('#detailDialog[open]');assert '-12.5, 45.5' in page.locator('#detail').inner_text();page.locator('#detailDialog .close').click()
 page.locator('#fieldbook').click();page.get_by_role('button',name='Сформировать предпросмотр').click();page.wait_for_function("!document.querySelector('#printBook').disabled")
 assert '60.1, 59.1' in page.frame_locator('#bookPreview').locator('body').inner_text()
 assert '-12.5, 45.5' in page.frame_locator('#bookPreview').locator('body').inner_text()
 assert not errors,errors
 b.close();print('PASS: validation, Excel paste, decimal comma, profile/point mapping, stored coordinates, sample card and fieldbook')
