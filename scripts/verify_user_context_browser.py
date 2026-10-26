"""Verify new user ratios, scope selectors, null gaps and actual plotted data."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def verify():
    output=Path(__file__).resolve().parents[1]/'docs/verification/user_context'
    output.mkdir(parents=True,exist_ok=True)
    report={'checks':[],'page_errors':[],'chart_combinations':[]}
    with sync_playwright() as pw:
        browser=pw.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1050})
        page.on('pageerror',lambda error:report['page_errors'].append(str(error)))
        page.goto('http://127.0.0.1:3000/',wait_until='domcontentloaded')
        page.locator('#site-search-input').fill('BIZ_0033')
        page.locator('.site-search button[type=submit]').click()
        popup=page.locator('.site-feature-popup')
        expect(popup.locator('h3')).to_have_text('BIZ_0033',timeout=60000)
        popup.get_by_role('button',name='KPIs & Config',exact=True).click()
        expect(page.locator('.user-context-panel')).to_be_visible()
        expect(page.locator('.user-context-panel tbody tr')).to_have_count(3)
        expect(page.locator('.user-context-panel')).not_to_contain_text('Unavailable')
        data=page.request.get('http://localhost:8000/api/sites/1534/features/').json()
        assert data['user_context']['tier1_lowlatency_user_share']==0
        assert data['user_context']['cluster_lowlatency_user_share']>0
        report['checks'].append('BIZ_0033 shows all nine ratios, retaining real zero and nonzero low-latency shares')
        report['biz_profile']={k:v for k,v in data['user_context'].items() if k not in ('support','updated_at')}
        history=page.locator('.maos-history')
        metric=page.get_by_label('MAOS metric',exact=True)
        scope=page.get_by_label('MAOS scope',exact=True)
        expect(scope.locator('option')).to_have_count(7)
        for scope_key in ('tier1','tier2','cluster','all_scopes'):
            scope.select_option(scope_key)
            for metric_key in ('edge_user_share','edge_user_peak_ratio','lowlatency_user_share'):
                metric.select_option(metric_key)
                keys=['tier1','tier2','cluster'] if scope_key=='all_scopes' else [scope_key]
                expect(history.locator('canvas')).to_be_visible()
                plotted=page.evaluate("""async () => {
                    const resource=performance.getEntriesByType('resource').find(e=>e.name.includes('/chart__js.js?v='));
                    const {Chart}=await import(resource.name);
                    const c=Chart.getChart(document.querySelector('.maos-history canvas'));
                    return {labels:c.data.labels, data:c.data.datasets.map(d=>d.data), gaps:c.data.datasets.map(d=>d.spanGaps)};
                }""")
                assert not any(plotted['gaps'])
                for index,key in enumerate(keys):
                    rows={row['month']:row for row in data['maos_scopes'][key]['records']}
                    expected=[rows.get(month,{}).get(metric_key) for month in plotted['labels']]
                    assert plotted['data'][index]==expected,(scope_key,metric_key,key)
                report['chart_combinations'].append(f'{scope_key}/{metric_key}')
        scope.select_option('all_scopes')
        metric.select_option('edge_user_share')
        history.scroll_into_view_if_needed()
        page.screenshot(path=str(output/'monthly-scopes-desktop.png'))
        page.set_viewport_size({'width':390,'height':844})
        expect(scope).to_be_visible()
        page.screenshot(path=str(output/'monthly-scopes-mobile.png'))
        page.set_viewport_size({'width':1440,'height':1050})
        page.get_by_role('button',name='Similarity',exact=True).click()
        page.locator('#site-search').fill('NAB_0041')
        page.locator('.suggestions button').first.click(timeout=30000)
        group=page.locator('fieldset').filter(has=page.locator('legend',has_text='Pre-event edge and low-latency users'))
        expect(group.locator('input')).to_have_count(9,timeout=30000)
        for checkbox in group.locator('input').all():
            if checkbox.is_enabled():expect(checkbox).to_be_checked()
        report['checks'].append('Nine grouped similarity dimensions appear; available values selected and unavailable values disabled')
        page.screenshot(path=str(output/'similarity-user-context.png'))
        page.get_by_role('button',name='Cluster analysis',exact=True).click()
        expect(page.locator('.context-grid')).to_be_visible(timeout=60000)
        with page.expect_response(lambda r:'/cluster_analysis/' in r.url and 'cluster_id=7' in r.url,timeout=60000) as response:
            page.get_by_label('Select a cluster',exact=True).select_option('7')
        cluster=response.value.json()
        for key in ('edge_user_share','edge_user_peak_ratio','lowlatency_user_share'):
            page.get_by_label('Select cluster KPI',exact=True).select_option(key)
            expect(page.locator('.cluster-analysis canvas')).to_be_visible()
            plotted=page.evaluate("""async () => {
                const resource=performance.getEntriesByType('resource').find(e=>e.name.includes('/chart__js.js?v='));
                const {Chart}=await import(resource.name);
                const c=Chart.getChart(document.querySelector('.cluster-analysis canvas'));
                return {data:c.data.datasets[0].data,gaps:c.data.datasets[0].spanGaps};
            }""")
            assert plotted['data']==[row[key] for row in cluster['monthly_kpis']]
            assert plotted['gaps'] is False
            report['chart_combinations'].append('cluster-analysis/'+key)
        report['checks'].append('Dedicated Cluster analysis KPI selector and all three ratio chart arrays match the API')
        page.screenshot(path=str(output/'cluster-user-ratios.png'))
        assert not report['page_errors'],report['page_errors']
        browser.close()
    (output/'browser-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':verify()
