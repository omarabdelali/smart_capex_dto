"""Exercise live population and similarity UI with locally installed Edge.

Run backend on :8000 and Vite on :3000, then use the project virtualenv.
Requires the optional Playwright development package and installed Edge.
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def verify():
    artifacts = Path(__file__).resolve().parents[1] / 'docs/verification/population'
    artifacts.mkdir(parents=True, exist_ok=True)
    report = {'checks': [], 'page_errors': [], 'population_tile_failures': []}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='msedge', headless=True)
        context = browser.new_context(viewport={'width': 1440, 'height': 1000})
        page = context.new_page()
        page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
        page.on('response', lambda response: report['population_tile_failures'].append(
            {'url': response.url, 'status': response.status}
        ) if '/population/tiles/' in response.url and response.status != 200 else None)
        page.goto('http://127.0.0.1:3000/', wait_until='domcontentloaded')
        page.wait_for_function("() => document.querySelectorAll('.leaflet-interactive').length > 100", timeout=60000)
        expect(page.locator('.loading')).to_have_count(0, timeout=60000)
        toggle = page.get_by_label('Tunisia population density', exact=True)
        expect(toggle).not_to_be_checked()
        with page.expect_response(lambda response: '/population/tiles/' in response.url and response.status == 200):
            toggle.check()
        expect(page.locator('.cluster-map-container').get_by_text('GHSL 2025 estimate', exact=False)).to_be_visible()
        page.wait_for_function("""() => [...document.querySelectorAll('img.leaflet-tile')]
            .some(img => img.src.includes('/population/tiles/') && img.complete && img.naturalWidth === 256)""")
        report['checks'].append('Desktop toggle loads native-resolution population tiles')
        slider = page.locator('.dem-controls').filter(has=page.locator('h4', has_text='Population')).locator('input[type=range]')
        slider.fill('30')
        expect(page.get_by_text('Opacity: 30%', exact=False)).to_be_visible()
        page.wait_for_function("""() => [...document.querySelectorAll('.leaflet-tile-container')]
            .some(el => el.querySelector('img[src*="/population/tiles/"]') && el.parentElement.style.opacity === '0.3')""")
        report['checks'].append('Population opacity changes independently')
        page.locator('.leaflet-control-zoom-in').click()
        page.wait_for_function("() => !document.querySelector('.leaflet-zoom-anim')")
        page.wait_for_function("() => [...document.querySelectorAll('img.leaflet-tile')].some(img => img.src.includes('/population/tiles/') && img.complete && img.naturalWidth === 256)")
        page.locator('.cluster-map-container').get_by_text('GHSL 2025 estimate', exact=False).scroll_into_view_if_needed()
        page.screenshot(path=str(artifacts / 'desktop-map.png'))
        toggle.uncheck()
        expect(page.locator('img[src*="/population/tiles/"]')).to_have_count(0)
        report['checks'].append('Zoom works and population toggle removes overlay')

        page.get_by_role('button', name='Similarity', exact=True).click()
        page.locator('#site-search').fill('NAB_0041')
        page.locator('.suggestions button').first.click(timeout=30000)
        fieldset = page.locator('fieldset').filter(has=page.locator('legend', has_text='Population'))
        expect(fieldset).to_be_visible(timeout=30000)
        expect(fieldset.locator('input')).to_have_count(3)
        expect(fieldset.locator('input').first).to_be_checked()
        expect(fieldset.locator('input').first).to_be_enabled()
        expect(fieldset).to_contain_text('Tier 1 population (0–2 km)')
        expect(fieldset).to_contain_text('Tier 2 population (2–5 km)')
        page.get_by_role('button', name='Find similar sites', exact=True).click()
        expect(page.locator('.case-card').first).to_be_visible(timeout=180000)
        page.locator('.case-card').first.locator('summary').click()
        row = page.locator('.case-card').first.locator('tr').filter(has=page.get_by_role('rowheader', name='Population density (1 km) · people/km²', exact=True))
        expect(row).to_contain_text('Used')
        expect(row).not_to_contain_text('Unavailable')
        expect(page.locator('.case-card').first.get_by_role('rowheader', name='Tier 1 population (0–2 km) · people', exact=True)).to_be_visible()
        expect(page.locator('.case-card').first.get_by_role('rowheader', name='Tier 2 population (2–5 km) · people', exact=True)).to_be_visible()
        report['checks'].append('Population is available, selected by default, and used in case comparison')
        report['checks'].append('Tier 1 and separate Tier 2 population fields appear in picker and comparison table')
        page.screenshot(path=str(artifacts / 'desktop-similarity.png'))

        page.get_by_role('button', name='CBR impact', exact=True).click()
        page.get_by_label('CBR prediction engine').select_option('legacy')
        page.locator('.cbr .search input').fill('NAB_0041')
        page.locator('.cbr .matches button').first.click(timeout=30000)
        page.get_by_role('button', name='Predict impact', exact=True).click()
        expect(page.locator('.cbr aside')).to_be_visible(timeout=180000)
        expect(page.locator('.cbr')).to_contain_text('Tier 1 population (0–2 km)')
        expect(page.locator('.cbr')).to_contain_text('Tier 2 population (2–5 km)')
        expect(page.locator('.cbr')).to_contain_text('prediction cutoff (2026-07-01)')
        report['checks'].append('CBR shows tier population and historical prediction cutoff')
        page.screenshot(path=str(artifacts / 'desktop-cbr.png'))
        page.get_by_role('button', name='Similarity', exact=True).click()

        page.set_viewport_size({'width': 390, 'height': 844})
        expect(fieldset).to_be_visible()
        page.get_by_role('button', name='Site map', exact=True).click()
        page.wait_for_function("() => document.querySelectorAll('.leaflet-interactive').length > 100", timeout=60000)
        page.get_by_role('button', name='Map controls', exact=True).click()
        toggle = page.get_by_label('Tunisia population density', exact=True)
        toggle.check()
        expect(page.locator('.cluster-map-container').get_by_text('GHSL 2025 estimate', exact=False)).to_be_visible()
        page.locator('.cluster-map-container').get_by_text('GHSL 2025 estimate', exact=False).scroll_into_view_if_needed()
        page.screenshot(path=str(artifacts / 'mobile-map.png'))
        report['checks'].append('Population controls remain usable at 390 px width')
        assert not report['page_errors'], report['page_errors']
        assert not report['population_tile_failures'], report['population_tile_failures']
        browser.close()
    (artifacts / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    verify()
