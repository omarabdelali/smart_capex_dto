"""Verify BAR_0196 ramp, benchmark/error columns and retrospective action context."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect

with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1100});errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto('http://127.0.0.1:3000/',wait_until='domcontentloaded')
    page.get_by_role('button',name='CBR impact',exact=True).click()
    page.locator('.cbr .search input').fill('BAR_0196')
    page.locator('.cbr .matches button').filter(has_text='1002').click(timeout=30000)
    panel=page.locator('.recipient-cbr')
    expect(panel.get_by_label('Recipient analysis event')).not_to_have_value('',timeout=120000)
    panel.get_by_label('Smooth the supported').check()
    with page.expect_response(lambda r:'/cbr/recipients/' in r.url and 'metadata=' not in r.url,timeout=240000) as pending:
        panel.get_by_role('button',name='Calculate recipient impact',exact=True).click()
    response=pending.value;assert response.status==200,response.text()
    data=response.json();assert data['query']['event_date']=='2025-09-01'
    assert data['other_site_actions']==[{'date':'2025-10-01','phase':'later','event_count':3,'event_types':['BANDWIDTH_UPGRADE'],'affected_cells':3}]
    previous=json.loads(Path('docs/verification/recipient_cbr/BAR_0196-ramp-audit.json').read_text())
    for actual,old in zip(data['scope_series'],previous['scope_series']):
        assert abs(actual['predicted']-old['predicted'])<1e-6
        assert actual['last_month_forecast']>0
        assert actual['accuracy']['absolute_percentage_error'] is not None
    expect(panel).to_contain_text('higher +1 MAE than last-month persistence')
    expect(panel.get_by_role('columnheader',name='Last-month benchmark',exact=True)).to_be_visible()
    expect(panel.get_by_role('columnheader',name='Predicted change',exact=True)).to_be_attached()
    expect(panel).to_contain_text('2025-10: 3 later action(s)')
    output=Path('docs/verification/recipient_cbr');page.screenshot(path=str(output/'BAR_0196-accuracy-ui.png'))
    page.set_viewport_size({'width':390,'height':844})
    page.wait_for_function("()=>{const el=document.querySelector('.recipient-cbr');return el.scrollWidth<=el.clientWidth+1}")
    assert not errors,errors
    result={'unchanged_forecasts':True,'benchmark_and_errors_visible':True,'later_bandwidth_actions_visible':True,
        'mobile_layout_verified':True,'page_errors':errors,'scope_errors':[{'month':p['month'],'ape':p['accuracy']['absolute_percentage_error']} for p in data['scope_series']]}
    (output/'accuracy-browser.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
    browser.close()
