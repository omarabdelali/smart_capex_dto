"""Live BIZ_0033 regression: popup separation, real population and CBR charts."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def verify():
    output = Path(__file__).resolve().parents[1] / 'docs/verification/biz_0033'
    output.mkdir(parents=True, exist_ok=True)
    report = {'checks': [], 'errors': []}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1050})
        page.on('pageerror', lambda error: report['errors'].append(str(error)))
        page.goto('http://127.0.0.1:3000/', wait_until='domcontentloaded')
        page.locator('#site-search-input').fill('BIZ_0033')
        page.locator('.site-search button[type=submit]').click()
        popup = page.locator('.site-feature-popup')
        expect(popup.locator('h3')).to_have_text('BIZ_0033', timeout=60000)
        expect(popup.get_by_role('button', name='Population', exact=True)).to_be_visible()
        expect(popup.get_by_text('Tier 1 population', exact=False)).to_have_count(0)
        popup.get_by_role('button', name='Population', exact=True).click()
        expect(popup.locator('.population-panel .info-item')).to_have_count(3)
        expect(popup.locator('.population-panel')).not_to_contain_text('Unavailable')
        expect(popup.locator('.population-panel')).to_contain_text('Partial mapped estimate')
        api = page.request.get('http://localhost:8000/api/sites/1534/features/').json()['population']
        assert 27000 < api['population_tier1'] < 27200
        assert 56000 < api['population_tier2'] < 57000
        assert api['quality']['tier1']['status'] == 'incomplete_land_coverage'
        report['population'] = api
        report['checks'].append('Population is a separate tab; all three BIZ_0033 values calculated and partial coverage disclosed')
        page.screenshot(path=str(output/'population-desktop.png'))
        page.set_viewport_size({'width':390,'height':844})
        expect(popup.locator('.population-panel')).to_be_visible()
        popup.locator('.population-panel').scroll_into_view_if_needed()
        page.screenshot(path=str(output/'population-mobile.png'))
        page.set_viewport_size({'width':1440,'height':1050})

        page.get_by_role('button', name='CBR impact', exact=True).click()
        page.locator('.cbr .search input').fill('BIZ_0033')
        page.locator('.cbr .matches button').first.click(timeout=30000)
        with page.expect_response(lambda r: '/cbr/impact/' in r.url, timeout=180000) as received:
            page.get_by_role('button', name='Predict impact', exact=True).click()
        result = received.value.json()
        assert received.value.status == 200
        expect(page.locator('.cbr aside')).to_be_visible()
        expect(page.locator('.population-note')).to_be_visible()
        report['cutoff'] = result['prediction_cutoff']
        report['case_count'] = result['case_count']
        assert all(str(case['event_date']) < result['prediction_cutoff'] for case in result['cases'])
        scopes = page.locator('.controls select').first
        kpis = page.locator('.controls select').last
        tested = []
        for scope in ('tier1','tier2','cluster','site'):
            scopes.select_option(scope)
            for metric in ('downlink_traffic_gb','cqi_avg','active_users','dl_throughput_kbps','dl_packet_delay_ms'):
                kpis.select_option(metric)
                expected = result['site_predictions'][0]['series'][metric] if scope=='site' and result['site_predictions'] else result['scopes'].get(scope,{}).get('series',{}).get(metric,[])
                has_data = any(p['observed'] is not None or p['predicted'] is not None for p in expected)
                if has_data:
                    expect(page.locator('.chart-frame canvas')).to_be_visible()
                    # Chart.js instance values must agree with the actual API,
                    # including null gaps and uncertainty bounds.
                    plotted = page.evaluate("""async () => {
                        const resource=performance.getEntriesByType('resource').find(e=>e.name.includes('/chart__js.js?v='));
                        const {Chart} = await import(resource?.name || '/node_modules/.vite/deps/chart__js.js');
                        const chart=Chart.getChart(document.querySelector('.chart-frame canvas'));
                        return {data:chart.data.datasets.map(d=>d.data), gaps:chart.data.datasets.map(d=>d.spanGaps), height:chart.height};
                    }""")
                    assert plotted['data'][0] == [p['observed'] for p in expected]
                    assert plotted['data'][1] == [p['predicted'] for p in expected]
                    assert plotted['data'][2] == [p['lower_95'] for p in expected]
                    assert plotted['data'][3] == [p['upper_95'] for p in expected]
                    assert not any(plotted['gaps'])
                    assert 200 <= plotted['height'] <= 500
                tested.append(f'{scope}/{metric}')
        scopes.select_option('tier1')
        kpis.select_option('downlink_traffic_gb')
        page.locator('.series-table summary').click()
        expect(page.locator('.series-table table tbody tr')).to_have_count(10)
        page.screenshot(path=str(output/'cbr-desktop.png'))
        page.set_viewport_size({'width':390,'height':844})
        expect(page.locator('.chart-frame canvas')).to_be_visible()
        page.screenshot(path=str(output/'cbr-mobile.png'))
        report['checks'].append('CBR API and charts checked across four scopes and five KPIs; arrays, gaps, bounds and chart height match')
        report['tested_chart_combinations'] = tested
        assert not report['errors'], report['errors']
        browser.close()
    (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    verify()
