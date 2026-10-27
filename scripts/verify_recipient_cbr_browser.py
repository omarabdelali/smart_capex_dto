"""Live recipient CBR, control, ramp and sampled-noise UI checks."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect

with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1050})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:3000/',wait_until='domcontentloaded')
    page.get_by_role('button',name='CBR impact',exact=True).click()
    expect(page.get_by_label('CBR prediction engine')).to_have_value('recipient')
    page.locator('.cbr .search input').fill('GAB_0033')
    page.locator('.cbr .matches button').filter(has_text='105784').click(timeout=30000)
    panel=page.locator('.recipient-cbr')
    expect(panel.get_by_label('Recipient analysis event')).not_to_have_value('',timeout=120000)
    results=[]
    for method,ramp in [('pair_cbr',False),('pair_cbr',True),('control_adjusted',False)]:
        panel.get_by_label('Recipient CBR method').select_option(method)
        panel.get_by_label('Smooth the supported').set_checked(ramp)
        with page.expect_response(lambda r:'/cbr/recipients/' in r.url and 'metadata=' not in r.url,timeout=300000) as pending:
            panel.get_by_role('button',name='Calculate recipient impact',exact=True).click()
        response=pending.value;assert response.status==200,response.text()
        result=response.json();assert result['method']==method and result['ramp_requested']==ramp
        assert result['bootstrap_draws']==500 and result['reference']['reference_id']
        points=[p for r in result['recipients'] for p in r['points']]
        available=[p for p in points if p['predicted'] is not None]
        assert all(p['horizon']>=1 for p in points)
        assert all(p['support']['n_event_sites']>=3 and p['support']['effective_event_n']>=2 for p in available)
        if method=='control_adjusted':
            assert result['baseline_kind'].startswith('mean')
            assert all(r['controls']['exclusion_m']==10000 for r in result['recipients'])
        else:
            assert result['baseline_kind'].startswith('median')
        expect(panel).to_contain_text('not prediction intervals')
        if method=='pair_cbr' and not ramp:
            output=Path('docs/verification/recipient_cbr');output.mkdir(parents=True,exist_ok=True)
            page.screenshot(path=str(output/'raw-recipient-ui.png'))
        results.append({'method':method,'ramp':ramp,'recipients':len(result['recipients']),'supported_points':len(available),'status':result['status']})
    if result['recipients']:
        panel.get_by_label('Recipient result').select_option(result['recipients'][0]['site_id'])
        expect(panel.get_by_text('Matched controls and pre-trend diagnostics',exact=True)).to_be_visible()
        panel.get_by_label('Recipient interval type').select_option('prediction')
        expect(panel).to_contain_text('mean intervals are not substituted')
    output=Path('docs/verification/recipient_cbr');output.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(output/'matched-control-ui.png'))
    page.set_viewport_size({'width':390,'height':844})
    try:
        page.wait_for_function("()=>{const el=document.querySelector('.recipient-cbr');return el.scrollWidth<=el.clientWidth+1}",timeout=15000)
    except Exception:
        page.screenshot(path=str(output/'mobile-overflow-debug.png'))
        print(panel.evaluate("el=>({width:el.clientWidth,scroll:el.scrollWidth,items:[...el.querySelectorAll('*')].filter(x=>x.getBoundingClientRect().right>el.getBoundingClientRect().right+1).slice(0,12).map(x=>({tag:x.tagName,cls:x.className,width:x.clientWidth,scroll:x.scrollWidth,text:x.textContent.slice(0,70)}))})"))
        raise
    page.screenshot(path=str(output/'recipient-mobile.png'))
    page.set_viewport_size({'width':1440,'height':1050})
    page.locator('.cbr .search input').fill('MED_0007')
    page.locator('.cbr .matches button').filter(has_text='106008').click(timeout=30000)
    expect(panel.get_by_label('Recipient analysis event')).not_to_have_value('',timeout=120000)
    panel.get_by_label('Recipient CBR scope').select_option('virtual_cluster')
    expect(panel.get_by_label('Recipient CBR KPI')).to_have_value('downlink_traffic_gb')
    expect(panel.get_by_label('Recipient CBR KPI').locator('option[value="cqi_avg"]')).to_have_js_property('disabled',True)
    assert not errors,errors
    (output/'browser.json').write_text(json.dumps({'checks':results,'noise_virtual_traffic_only':True,'mobile_layout_verified':True,'page_errors':errors},indent=2),encoding='utf-8')
    print((output/'browser.json').read_text(encoding='utf-8'))
    browser.close()
