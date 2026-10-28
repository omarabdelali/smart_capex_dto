"""Verify live origin counterfactual identities, cumulative support and UI states."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect

with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1480,'height':1080});errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    # Avoid loading the whole network before navigating; forecast APIs are live.
    page.route('**/api/sites/clusters/**',lambda r:r.fulfill(json={'type':'FeatureCollection','features':[]}))
    page.goto('http://127.0.0.1:3000/',wait_until='domcontentloaded')
    page.get_by_role('button',name='CBR impact',exact=True).click()
    page.get_by_label('CBR prediction engine',exact=True).select_option('gain')
    page.locator('.cbr .search input').fill('MAN_0069')
    page.locator('.cbr .matches button').filter(has_text='1320').click(timeout=30000)
    panel=page.locator('.gain-panel')
    expect(panel.get_by_label('Gain episode')).not_to_have_value('',timeout=120000)
    panel.get_by_label('Gain episode').select_option('f22dab1a5d965eb2afa0e14452df2093eaeaa71a802b16b02f1600f3fda4a33f')
    panel.get_by_label('Gain scope').select_option('origin')
    panel.get_by_label('Gain horizon').select_option('3')
    with page.expect_response(lambda r:'/cbr/gains/' in r.url and 'metadata=' not in r.url,timeout=300000) as pending:
        panel.get_by_role('button',name='Calculate counterfactual gains',exact=True).click()
    response=pending.value;assert response.status==200,response.text()
    data=response.json()
    assert data['model_version']=='counterfactual-gain-v1'
    assert data['query']['analysis_unit']=='episode'
    assert data['recipients'][0]['recipient_role']=='origin'
    assert len(data['recipients'])==1
    supported=[p for p in data['scope_series'] if p['monthly_gain'] is not None]
    assert supported
    for point in supported:
        assert abs(point['monthly_gain']-(point['with_event_forecast']-point['no_event_forecast']))<1e-7
        assert point['prediction_interval_95'] is None
    selected=data['scope_series'][:3]
    if all(p['monthly_gain'] is not None for p in selected):
        assert abs(data['cumulative']['gain']-sum(p['monthly_gain'] for p in selected))<1e-7
    else:
        assert data['cumulative']['gain'] is None
    expect(panel.get_by_role('columnheader',name='No-event forecast',exact=True)).to_be_visible()
    expect(panel.get_by_role('columnheader',name='Monthly gain',exact=True)).to_be_attached()
    expect(panel).to_contain_text('Cumulative scope gain over 3 months')
    expect(panel.locator('tbody tr')).to_have_count(3)
    output=Path('docs/verification/counterfactual_gains');output.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(output/'origin-gain-desktop.png'))
    panel.get_by_label('Gain horizon').select_option('2')
    with page.expect_response(lambda r:'/cbr/gains/' in r.url and 'metadata=' not in r.url,timeout=300000) as pending:
        panel.get_by_role('button',name='Calculate counterfactual gains',exact=True).click()
    response=pending.value;assert response.status==200,response.text()
    two_month=response.json()
    assert two_month['cumulative']['gain'] is not None
    assert abs(two_month['cumulative']['gain']-sum(p['monthly_gain'] for p in two_month['scope_series'][:2]))<1e-7
    expect(panel).to_contain_text('Cumulative scope gain over 2 months')
    # Newly launched origin prehistory is unknown; expose NULL, never zero gain.
    page.locator('.cbr .search input').fill('BAR_0196')
    page.locator('.cbr .matches button').filter(has_text='1002').click(timeout=30000)
    panel=page.locator('.gain-panel')
    expect(panel.get_by_label('Gain episode')).not_to_have_value('',timeout=120000)
    panel.get_by_label('Gain scope').select_option('origin')
    with page.expect_response(lambda r:'/cbr/gains/' in r.url and 'metadata=' not in r.url,timeout=300000) as pending:
        panel.get_by_role('button',name='Calculate counterfactual gains',exact=True).click()
    response=pending.value;assert response.status==200,response.text()
    missing=response.json()
    assert missing['query']['event_date']=='2025-09-01'
    assert missing['cumulative']['gain'] is None
    assert all(p['monthly_gain'] is None for p in missing['scope_series'])
    expect(panel).to_contain_text('Unavailable')
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('()=>document.documentElement.scrollWidth<=window.innerWidth+1')
    assert not errors,errors
    report={'live_origin_forecast':'MAN_0069','supported_months':len(supported),'horizon':3,
        'two_month_cumulative_gain':two_month['cumulative']['gain'],'scenario_identity':True,'cumulative_complete_prefix':True,'no_calibrated_prediction_claim':True,
        'missing_origin_baseline_remains_null':'BAR_0196 2025-09','mobile_layout':True,'page_errors':errors}
    (output/'browser.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    (output/'MAN_0069-origin.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2));browser.close()
