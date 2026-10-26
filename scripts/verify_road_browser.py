"""Live Roads tab, optional picker, group weights and actual comparison checks."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def verify():
    output = Path(__file__).resolve().parents[1]/'docs/verification/roads'
    output.mkdir(parents=True,exist_ok=True)
    report = {'checks':[], 'errors':[]}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='msedge',headless=True)
        page = browser.new_page(viewport={'width':1440,'height':1050})
        page.on('pageerror',lambda error:report['errors'].append(str(error)))
        page.goto('http://127.0.0.1:3000/',wait_until='domcontentloaded')
        page.locator('#site-search-input').fill('BIZ_0033')
        page.locator('.site-search button[type=submit]').click()
        popup = page.locator('.site-feature-popup')
        expect(popup.locator('h3')).to_have_text('BIZ_0033',timeout=60000)
        popup.get_by_role('button',name='Roads',exact=True).click()
        expect(popup.get_by_text('Total road length',exact=True)).to_be_visible()
        expect(popup.locator('.road-class')).not_to_have_count(0)
        expect(popup.get_by_text('Extract date:',exact=False)).to_contain_text('2026-10-22')
        page.wait_for_function("() => document.querySelector('.site-feature-popup .tab-pane').getAnimations().every(a => a.playState !== 'running')")
        page.screenshot(path=str(output/'roads-desktop.png'))
        page.set_viewport_size({'width':390,'height':844})
        popup.get_by_text('Total road length',exact=True).scroll_into_view_if_needed()
        page.screenshot(path=str(output/'roads-mobile.png'))
        report['checks'].append('Roads is a separate inspector tab with persisted values, class-length bars, source and coverage, on desktop/mobile')
        page.set_viewport_size({'width':1440,'height':1050})
        page.get_by_role('button',name='Similarity',exact=True).click()
        page.locator('#site-search').fill('NAB_0041')
        page.locator('.suggestions button').first.click(timeout=30000)
        group = page.locator('fieldset').filter(has=page.locator('legend',has_text='Road context'))
        expect(group.locator('input')).to_have_count(7,timeout=30000)
        for checkbox in group.locator('input').all():
            expect(checkbox).not_to_be_checked()
        with page.expect_response(lambda r:'/similarity/search/' in r.url,timeout=180000) as response:
            page.get_by_role('button',name='Find similar sites',exact=True).click()
        base = response.value.json()
        assert base['cases']
        keys = [f['key'] for f in page.request.get('http://localhost:8000/api/similarity/features/?site_id=1792').json()['features'] if f['group']=='road_context']
        assert all(not set(keys).intersection(case['used_features']) for case in base['cases'])
        group.locator('label').filter(has_text='Weighted road density').locator('input').check()
        group.locator('label').filter(has_text='Estimated road junctions').locator('input').check()
        page.locator('.feature-picker select').select_option('equal_per_group')
        with page.expect_response(lambda r:'/similarity/search/' in r.url,timeout=180000) as response:
            page.get_by_role('button',name='Update similarity',exact=True).click()
        result = response.value.json()
        assert result['weighting_method']=='equal_per_group'
        road_weights = []
        for case in result['cases']:
            assert abs(sum(case['feature_weights'].values())-1)<1e-9
            weight = sum(v for f,v in case['feature_weights'].items() if f in keys)
            assert 0 < weight <= .050000001
            road_weights.append(weight)
        first = page.locator('.case-card').first
        first.locator('summary').click()
        row = first.locator('tr').filter(has=page.get_by_role('rowheader',name='Weighted road density (1 km)',exact=True))
        expect(row).to_contain_text('Used')
        expected_weight = result['cases'][0]['feature_weights']['road_density_weighted_km_km2']
        expect(row).to_contain_text(f'{expected_weight*100:.2f}%')
        page.screenshot(path=str(output/'roads-similarity.png'))
        report['checks'].append('Seven road dimensions start unselected; default search excludes them; explicit opt-in works in group mode with actual normalized weights and <=5% total road share')
        report['case_road_weight_sums'] = road_weights
        assert not report['errors'],report['errors']
        browser.close()
    (output/'browser-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    verify()
