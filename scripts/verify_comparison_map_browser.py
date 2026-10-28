"""Verify side-by-side map interaction with fixture rankings and live map data."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect

field='n_sites_1km'
def case(key,name,score):
    return {'site_id':key,'site_name':name,'similarity':score,'distance':1-score,'weight':.5,'profile_months_available':3,
        'profile_completeness':1,'used_features':[field],'feature_weights':{field:1},'cluster_id':-1,
        'event_date':'2025-09-01','event_type':'TECHNOLOGY_ADDED','profile':{},'similarity_features':{field:2}}
cases=[case('1534','BIZ_0033',.9),case('6306','TAT_0055',.8)]
ranking={'query':{**case('1002','BAR_0196',1),'as_of_date':'2025-09-01'},'cases':cases,'selected_features':[field],
    'active_features':[field],'excluded_features':{},'candidate_pool_size':2,'total_detected_event_sites':2,
    'filter_explanation':'UI fixture ranking; map features and links use the live API.','weighting_method':'equal_per_feature',
    'representation':'original','allow_filter_relaxation':True}
with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1500,'height':1050});errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.route('**/api/similarity/features/**',lambda r:r.fulfill(json={'site_id':'1002','features':[{'key':field,'label':'Sites within 1 km','group':'spatial','available':True,'default_selected':True,'value':2}]}))
    page.route('**/api/similarity/search/**',lambda r:r.fulfill(json=ranking))
    page.route('**/api/sites/clusters/**',lambda r:r.continue_() if 'site_ids=' in r.request.url else r.fulfill(json={'type':'FeatureCollection','features':[]}))
    page.goto('http://127.0.0.1:3000/',wait_until='domcontentloaded')
    page.get_by_role('button',name='Similarity',exact=True).click()
    page.locator('#site-search').fill('BAR_0196')
    page.get_by_role('option',name='BAR_0196 1002',exact=True).click(timeout=30000)
    page.get_by_role('button',name='Find similar sites',exact=True).click()
    page.locator('.case-card').nth(1).get_by_role('button',name='Compare this site on map',exact=True).click()
    comparison=page.get_by_role('region',name='Side by side site comparison')
    expect(comparison.locator('.leaflet-container')).to_have_count(2)
    expect(page.get_by_label('Similar site to compare',exact=True)).to_have_value('6306')
    left=page.get_by_role('region',name='Query site map');right=page.get_by_role('region',name='Similar site map')
    expect(left.locator('.map-link-status')).to_contain_text('Current',timeout=120000)
    expect(right.locator('.map-link-status')).to_contain_text('Current',timeout=120000)
    expect(left.locator('.site-marker-selected')).to_have_count(1)
    expect(right.locator('.site-marker-selected')).to_have_count(1)
    assert left.bounding_box()['x']<right.bounding_box()['x']
    page.get_by_label('Similar site to compare',exact=True).select_option('1534')
    expect(right.locator('.map-link-status')).to_contain_text('Current',timeout=120000)
    right.get_by_role('button',name='Site details',exact=True).click()
    expect(right.get_by_label('Selected site details')).to_contain_text('BIZ_0033',timeout=120000)
    expect(left.get_by_label('Selected site details')).to_have_count(0)
    right.get_by_role('button',name='Close site details',exact=True).click()
    # IDs and Leaflet instances are unique; source pane remains selected.
    assert comparison.evaluate('el=>{const ids=[...el.querySelectorAll("[id]")].map(e=>e.id);return ids.length===new Set(ids).size}')
    output=Path('docs/verification/comparison_map');output.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(output/'desktop.png'))
    page.set_viewport_size({'width':390,'height':844})
    expect(comparison).to_be_visible()
    assert page.evaluate('()=>document.documentElement.scrollWidth<=window.innerWidth+1')
    assert left.bounding_box()['y']<right.bounding_box()['y']
    left.get_by_role('button',name='Map controls',exact=True).click()
    expect(left.locator('.site-marker-selected')).to_have_count(1)
    expect(left.locator('.map-link-status')).to_contain_text('Current')
    left.get_by_role('button',name='Hide controls',exact=True).click()
    page.get_by_role('button',name='Back to similarity',exact=True).click()
    expect(page.locator('.case-card')).to_have_count(2)
    page.locator('.case-card').first.get_by_role('button',name='Compare this site on map').click()
    expect(page.locator('.map-comparison .leaflet-container')).to_have_count(2)
    assert not errors,errors
    report={'fixture_rankings':True,'live_map_and_neighborhood_data':True,'two_independent_maps':True,
        'clicked_case_on_right':True,'switch_case':True,'independent_details':True,'mobile_stack':True,'return_and_remount':True,'page_errors':errors}
    (output/'browser.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
    browser.close()
