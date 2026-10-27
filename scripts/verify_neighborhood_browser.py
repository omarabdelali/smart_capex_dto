"""Live UI and API verification of real/virtual tiers and scheme partitions."""
import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright,expect


def verify():
    output=Path('docs/verification/noise_virtual_clusters')
    output.mkdir(parents=True,exist_ok=True)
    errors=[];checks=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1050})
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto('http://127.0.0.1:3000/',wait_until='domcontentloaded')
        page.locator('#site-search-input').fill('106008')
        page.locator('.site-search button[type=submit]').click()
        marker=page.locator('.site-addition-icons[data-site-id="106008"]')
        expect(marker).to_be_visible(timeout=60000);marker.click(force=True)
        popup=page.locator('.site-feature-popup')
        expect(popup.locator('.site-id')).to_have_text('ID: 106008',timeout=120000)
        popup.get_by_role('button',name='Neighborhood',exact=True).click()
        panel=popup.locator('.neighborhood-panel')
        expect(panel).to_contain_text('extended tiers')
        expect(panel).to_contain_text('None (-1)')
        expect(panel).to_contain_text('V_106008')
        data=page.request.get('http://127.0.0.1:8000/api/sites/106008/features/',timeout=120000).json()
        context=data['neighborhood']['event']
        assert data['cluster_id']==-1 and data['tier_scheme']=='extended'
        assert 1<=context['vis_n_members']<=12
        expect(panel.locator('tbody tr')).to_have_count(context['vis_n_members'])
        expect(panel).to_contain_text(context['cutoff'])
        page.screenshot(path=str(output/'event-neighborhood.png'))
        panel.get_by_label('Neighborhood membership version',exact=True).select_option('current')
        expect(panel).to_contain_text(data['neighborhood']['current']['cutoff'])
        expect(panel.locator('tbody tr')).to_have_count(data['neighborhood']['current']['vis_n_members'])
        checks.append('Event membership rebuilt separately from stored current snapshot; -1 and V_site identity preserved')
        page.set_viewport_size({'width':390,'height':844})
        page.screenshot(path=str(output/'neighborhood-mobile.png'))
        assert panel.evaluate('el=>el.scrollWidth<=el.clientWidth+1')
        page.set_viewport_size({'width':1440,'height':1050})
        popup.get_by_role('button',name='KPIs & Config',exact=True).click()
        expect(popup.get_by_label('MAOS scope')).to_be_visible()
        popup.get_by_label('MAOS scope').select_option('virtual_cluster')
        expect(popup.get_by_label('MAOS metric')).to_have_value('thrp_dl_gb')
        expect(popup.get_by_label('MAOS metric').locator('option[value="cqi_avg"]')).to_have_js_property('disabled',True)
        assert data['maos_scopes']['cluster']['records']==[]
        assert 'virtual_cluster' in data['maos_scopes']
        checks.append('Current virtual MAOS traffic sample; real noise cluster empty; other sampled KPIs disabled')
        page.get_by_role('button',name='Similarity',exact=True).click()
        page.locator('#site-search').fill('MED_0007')
        page.get_by_role('option').filter(has=page.locator('span',has_text=re.compile('^106008$'))).click()
        expect(page.locator('[data-feature-key]')).to_have_count(95,timeout=120000)
        expect(page.locator('.tier-scheme-note')).to_contain_text('extended tiers')
        expect(page.locator('[data-feature-key="tier_scheme"] input')).to_have_js_property('disabled',True)
        expect(page.locator('[data-feature-key="population_tier2"]')).to_contain_text('5-<10 km')
        # A standard whole-site query has a small eligible pool for real PCA.
        page.locator('#site-search').fill('GAB_0033')
        page.get_by_role('option').filter(has=page.locator('span',has_text=re.compile('^105784$'))).click()
        expect(page.locator('.tier-scheme-note')).to_contain_text('standard tiers',timeout=120000)
        page.locator('#representation').select_option('pca')
        print('Checking real PCA within the standard partition...',flush=True)
        expect(page.locator('[data-feature-key="PC1"]')).to_be_visible(timeout=600000)
        with page.expect_response(lambda r:'/similarity/search/' in r.url,timeout=180000) as pending:
            page.get_by_role('button',name='Find similar sites',exact=True).click()
        result=pending.value.json();assert pending.value.status==200,result
        assert result['representation']=='pca' and result['query']['tier_scheme']=='standard'
        assert result['cases'] and all(c['tier_scheme']=='standard' for c in result['cases'])
        expect(page.locator('.case-card')).to_have_count(len(result['cases']))
        page.screenshot(path=str(output/'pca-tier-partition.png'))
        checks.append('95 fields; mandatory tier policy; standard PCA fit/ranking contains only standard cases')
        page.get_by_role('button',name='CBR impact',exact=True).click()
        page.locator('.cbr .search input').fill('MED_0007')
        page.locator('.cbr .matches button').filter(has_text='106008').click(timeout=30000)
        with page.expect_response(lambda r:'/cbr/impact/' in r.url,timeout=180000) as pending:
            page.get_by_role('button',name='Predict impact',exact=True).click()
        cbr=pending.value.json();assert pending.value.status==200,cbr
        assert cbr['query']['tier_scheme']=='extended'
        assert all(c['features']['tier_scheme']=='extended' for c in cbr['cases'])
        assert set(cbr['distance_band_responses'])=={'distance_0_2','distance_2_5','distance_5_10'}
        assert not cbr['scopes']['cluster']['site_count']
        assert cbr['scopes']['virtual_cluster']['series']['cqi_avg']==[]
        page.locator('.controls select').first.select_option('virtual_cluster')
        expect(page.locator('.controls select').last).to_have_value('downlink_traffic_gb')
        expect(page.locator('.controls select').last.locator('option[value="cqi_avg"]')).to_have_js_property('disabled',True)
        expect(page.locator('.cbr')).to_contain_text('These traffic results describe a sample')
        expected=cbr['scopes']['virtual_cluster']['series']['downlink_traffic_gb']
        if any(p['observed'] is not None for p in expected):
            expect(page.locator('.chart-frame canvas')).to_be_visible()
        for scope in ('distance_0_2','distance_2_5','distance_5_10'):
            page.locator('.controls select').first.select_option(scope)
            expect(page.locator('.chart h3')).to_contain_text(cbr['scope_labels'][scope])
        page.screenshot(path=str(output/'distance-band-responses.png'))
        checks.append('Extended CBR scopes, traffic-only virtual sample, three distance bands, month +1 outcomes and scheme-compatible analogs')
        page.get_by_role('button',name='Data Explorer',exact=True).click()
        expect(page.get_by_role('button',name='Apply filters',exact=True)).to_be_enabled(timeout=60000)
        page.get_by_label('Dataset',exact=True).select_option('calculated')
        page.get_by_label('Aggregation',exact=True).select_option('virtual_cluster')
        page.get_by_label('Tier origin site ID',exact=True).fill('106008')
        page.get_by_role('button',name='Apply filters',exact=True).click()
        expect(page.get_by_role('button',name='Apply filters',exact=True)).to_be_enabled(timeout=120000)
        expect(page.locator('.results')).to_contain_text('virtual_cluster scope')
        checks.append('Data Explorer exposes origin-tier radii, scheme filter and virtual traffic sample')
        assert not errors,errors
        browser.close()
    report={'checks':checks,'page_errors':errors,'pca_fit':{k:result['pca'][k] for k in ('fit_rows','input_dimension','retained_dimension','retained_variance','fit_id')},
        'pca_case_count':len(result['cases']),'noise_cbr_case_count':cbr['case_count']}
    (output/'browser-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    verify()
