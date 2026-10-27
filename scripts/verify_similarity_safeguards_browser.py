"""Live checks for hard hierarchy, frozen ranges, coverage reporting and strict PCA."""
import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright,expect

with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:3000/',wait_until='domcontentloaded')
    page.get_by_role('button',name='Similarity',exact=True).click()
    page.locator('#site-search').fill('GAB_0033')
    page.get_by_role('option').filter(has=page.locator('span',has_text=re.compile('^105784$'))).click(timeout=30000)
    expect(page.locator('[data-feature-key]')).to_have_count(95,timeout=120000)
    outcomes=[]
    for strict in (False,True):
        checkbox=page.get_by_label('Allow technology/band relaxation for small pools')
        checkbox.set_checked(not strict)
        with page.expect_response(lambda r:'/similarity/search/' in r.url,timeout=240000) as pending:
            page.get_by_role('button',name=re.compile('^(Find similar sites|Update similarity)$')).click()
        response=pending.value;assert response.status==200,response.text()
        data=response.json()
        assert data['reference']['kind']=='frozen_global_training_reference'
        assert data['minimum_available_weight_share']==.6
        assert data['allow_filter_relaxation']==(not strict)
        for case in data['cases']:
            assert case['event_type']==data['query']['event_type']
            assert case['tier_scheme']==data['query']['tier_scheme']
            assert case['available_weight_share']>=.6-1e-12
        expect(page.locator('.ranking-summary')).to_contain_text(re.compile(r'Minimum shared weight: 60(?:\.0)?%'))
        outcomes.append({'strict':strict,'cases':len(data['cases']),'rejected':len(data['rejected_cases']),'reference':data['reference']})
    # Strict PCA availability and ranking must use the same hierarchy/fit ID.
    page.locator('#representation').select_option('pca')
    expect(page.locator('[data-feature-key="PC1"]')).to_be_visible(timeout=240000)
    with page.expect_response(lambda r:'/similarity/search/' in r.url,timeout=240000) as pending:
        page.get_by_role('button',name=re.compile('^(Find similar sites|Update similarity)$')).click()
    response=pending.value;assert response.status==200,response.text()
    pca=response.json();assert pca['representation']=='pca' and not pca['allow_filter_relaxation']
    assert all(c['available_weight_share']>=.6-1e-12 for c in pca['cases'])
    assert not errors,errors
    output=Path('docs/verification/pair_cbr');output.mkdir(parents=True,exist_ok=True)
    (output/'browser.json').write_text(json.dumps({'original':outcomes,'strict_pca_cases':len(pca['cases']),'page_errors':errors},indent=2),encoding='utf-8')
    page.screenshot(path=str(output/'similarity-safeguards.png'))
    print((output/'browser.json').read_text(encoding='utf-8'))
    browser.close()
