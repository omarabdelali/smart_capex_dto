"""Verify rendered Leaflet links match backend neighborhood membership."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect


with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto('http://127.0.0.1:3000/',wait_until='domcontentloaded')
    results=[]
    for site_id,scope in [('106008','virtual_cluster'),('105784','tiers')]:
        page.locator('#site-search-input').fill(site_id)
        with page.expect_response(lambda response:f'/sites/{site_id}/map-links/' in response.url,timeout=120000) as pending:
            page.locator('.site-search button[type=submit]').click()
        response=pending.value
        assert response.status==200
        data=response.json();assert data['link_scope']==scope
        expect(page.locator('.map-link-status')).to_contain_text(f": {len(data['members'])}.",timeout=30000)
        for tier in ['tier1','tier2']:
            expect(page.locator(f'path.neighborhood-link.{tier}')).to_have_count(sum(m['tier']==tier for m in data['members']))
        if scope=='virtual_cluster':
            assert len(data['members'])<=12 and data['cluster_id']==-1
            assert any(m['distance_m']>=5000 for m in data['members'])
        results.append({'site_id':site_id,'scope':scope,'links':len(data['members']),'tier_scheme':data['tier_scheme']})
    page.get_by_role('button',name='Close site details',exact=True).click()
    expect(page.locator('path.neighborhood-link')).to_have_count(0)
    assert not errors,errors
    output=Path('docs/verification/noise_virtual_clusters/map-links-browser.json')
    output.write_text(json.dumps({'checks':results,'close_clears_links':True,'page_errors':errors},indent=2),encoding='utf-8')
    print(output.read_text(encoding='utf-8'))
    browser.close()
