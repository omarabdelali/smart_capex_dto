import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def verify():
    output=Path('docs/verification/approved_context')
    output.mkdir(parents=True,exist_ok=True)
    errors=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1050})
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto('http://127.0.0.1:3000/',wait_until='domcontentloaded')
        page.get_by_role('button',name='Similarity',exact=True).click()
        page.locator('#site-search').fill('TAT_0055')
        page.get_by_role('option').filter(has=page.locator('span',has_text=re.compile('^6306$'))).click()
        expect(page.locator('.feature-profile-date')).to_contain_text('2023-12-01',timeout=60000)
        data=page.request.get('http://127.0.0.1:8000/api/similarity/features/?site_id=6306').json()
        rows={row['key']:row for row in data['features']}
        for key in ('sector_count_after','antenna_height_m','total_prb_available','z_antenna_m',
                    'neighbor_avg_antenna_height_m','dominant_clutter','terrain_relief_class',
                    'population_tier1','population_tier2','avg_users','avg_prb_util_pct'):
            assert rows[key]['available'],(key,rows[key])
            expect(page.locator(f'[data-feature-key="{key}"] input')).to_be_enabled()
        assert rows['sector_count_after']['value']==4
        assert abs(rows['total_prb_available']['value']-572.6143)<1e-7
        assert abs(rows['avg_users']['value']-75.4926)<1e-7
        assert rows['total_prb_available']['unit']=='PRBs'
        assert rows['total_bw_after_mhz']['value'] is None
        assert rows['total_bw_after_mhz']['code']=='prb_bandwidth_unmapped'
        expect(page.locator('[data-feature-key="total_bw_after_mhz"] input')).to_be_disabled()
        assert rows['cluster_id']['value']==81 and rows['cluster_id']['selectable'] is False
        expect(page.locator('[data-feature-key="cluster_id"] input')).to_be_disabled()
        expect(page.locator('[data-feature-key="terrain_relief_class"] input')).not_to_be_checked()
        page.screenshot(path=str(output/'static-feature-picker.png'))
        page.get_by_role('button',name='Site map',exact=True).click()
        page.locator('#site-search-input').fill('TAT_0055')
        page.locator('.site-search button[type=submit]').click()
        marker=page.locator('.site-addition-icons[data-site-id="6306"]')
        expect(marker).to_be_visible(timeout=60000)
        marker.click(force=True)
        popup=page.locator('.site-feature-popup')
        expect(popup.locator('.site-id')).to_have_text('ID: 6306',timeout=60000)
        popup.get_by_role('button',name='KPIs & Config',exact=True).click()
        expect(popup.locator('.cluster-prelaunch-panel')).to_contain_text('2023-11-01')
        expect(popup.locator('.cluster-prelaunch-panel')).to_contain_text('75.493')
        expect(popup).to_contain_text('Site LTE capacity (PRBs)')
        site=page.request.get('http://127.0.0.1:8000/api/sites/6306/features/').json()
        assert all(cell['cluster_id']==81 for cell in site['cell_plan'])
        assert abs(site['cluster_prelaunch']['avg_users']-rows['avg_users']['value'])<1e-9
        page.screenshot(path=str(output/'cluster-baseline-popup.png'))
        popup.get_by_role('button',name='Terrain',exact=True).click()
        expect(popup).to_contain_text('rolling')
        page.screenshot(path=str(output/'terrain-relief-popup.png'))
        page.set_viewport_size({'width':390,'height':844})
        page.screenshot(path=str(output/'terrain-relief-mobile.png'))
        assert not errors,errors
        browser.close()
    report={'site_id':'6306','event_date':data['event_date'],'feature_count':len(rows),
        'page_errors':errors,'features':rows,'checks':['static population and geography enabled',
        'KPI sectors and PRB capacity','strict unmapped bandwidth remains unknown',
        'cluster users summed in previous month','cluster IDs inherited and display only',
        'separate terrain relief and land-cover clutter','popup agrees with similarity',
        'desktop/mobile rendering']}
    (output/'browser-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({key:value for key,value in report.items() if key!='features'},indent=2))


if __name__=='__main__':
    verify()
