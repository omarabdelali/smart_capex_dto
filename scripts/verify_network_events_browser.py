"""Check six event classes in real popups, map filters and cluster rows."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def verify():
    output=Path('docs/verification/network_events')
    examples=json.loads((output/'validation.json').read_text(encoding='utf-8'))['examples']
    report={'popup_checks':[],'map_checks':[],'page_errors':[]}
    with sync_playwright() as pw:
        browser=pw.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1050})
        page.on('pageerror',lambda error:report['page_errors'].append(str(error)))
        page.goto('http://127.0.0.1:3000/',wait_until='domcontentloaded')
        event_filter=page.locator('#event-type-select')
        expect(event_filter.locator('option')).to_have_count(7,timeout=60000)
        for kind,example in examples.items():
            event_filter.select_option('ALL')
            page.locator('#site-search-input').fill(example['site_name'])
            page.locator('.site-search button[type=submit]').click()
            marker=page.locator(f'.site-addition-icons[data-site-id="{example["site_id"]}"]')
            # A 3G and a 4G site can share the same display name/coordinates.
            # Select the exact event-bearing site rather than the first name match.
            expect(marker).to_be_visible(timeout=60000)
            marker.click(force=True)
            popup=page.locator('.site-feature-popup')
            expect(popup.locator('h3')).to_have_text(example['site_name'],timeout=60000)
            expect(popup.locator('.site-id')).to_have_text(f"ID: {example['site_id']}",timeout=60000)
            popup.get_by_role('button',name='Overview',exact=True).click()
            panel=popup.locator('.radio-events')
            expect(panel).to_be_visible()
            data=page.request.get(f"http://127.0.0.1:8000/api/sites/{example['site_id']}/features/").json()
            event=next(e for e in data['network_events'] if e['event_type']==kind and e['event_date']==example['date'])
            expected_types=sorted({e['event_type'] for e in data['network_events']})
            expect(marker.locator('[data-event-type]')).to_have_count(len(expected_types))
            actual=marker.locator('[data-event-type]').evaluate_all('(els) => els.map(el => el.dataset.eventType).sort()')
            assert actual==expected_types,(example['site_name'],actual,expected_types)
            label=('/'.join(event['technologies'])+' added' if kind=='TECHNOLOGY_ADDED' else {
                'SITE_ADDED':'Site added','FREQUENCY_BAND_ADDED':'Frequency band added',
                'CELL_ADDED':'Cell added','BANDWIDTH_UPGRADE':'Bandwidth upgrade',
                'BANDWIDTH_DOWNGRADE':'Bandwidth downgrade'}[kind])
            expect(panel).to_contain_text(f"{label} · effective {event['event_date']}")
            if event['previous_bandwidth_mhz'] is not None:
                expect(panel).to_contain_text(f"{event['previous_bandwidth_mhz']:g} → {event['new_bandwidth_mhz']:g} MHz")
            else:
                assert event['event_date']==max(event['cell_activation_months'].values())
            for cell,month in event['cell_activation_months'].items():
                expect(panel).to_contain_text(f'{cell} · first positive traffic {month}')
            expect(panel).to_contain_text('Configuration date: Unknown')
            event_filter.select_option(kind)
            expect(marker.locator('[data-event-type]')).to_have_count(1)
            expect(marker.locator('[data-event-type]')).to_have_attribute('data-event-type',kind)
            absent=next((key for key in examples if key not in expected_types),None)
            if absent:
                event_filter.select_option(absent)
                expect(marker).to_have_count(0)
                event_filter.select_option(kind)
                expect(marker.locator('[data-event-type]')).to_have_count(1)
            report['map_checks'].append({'site':example['site_name'],'action_count':len(data['network_events']),
                'distinct_icons':len(expected_types),'matching_filter':kind,'absent_filter':absent})
            report['popup_checks'].append({'type':kind,'site':example['site_name'],'date':event['event_date']})
        page.screenshot(path=str(output/'radio-events-desktop.png'))
        for selector in ('.radio-events','.site-badges'):
            assert popup.locator(selector).evaluate('(el) => el.scrollWidth <= el.clientWidth + 1'), selector
        page.set_viewport_size({'width':390,'height':844})
        page.screenshot(path=str(output/'radio-events-mobile.png'))
        page.set_viewport_size({'width':1440,'height':1050})
        page.get_by_role('button',name='Cluster analysis',exact=True).click()
        expect(page.locator('.context-grid')).to_be_visible(timeout=60000)
        cluster=page.get_by_label('Select a cluster',exact=True).input_value()
        data=page.request.get(f'http://127.0.0.1:8000/api/sites/cluster_analysis/?cluster_id={cluster}').json()
        expect(page.locator('.events-table tbody tr')).to_have_count(len(data['events']))
        assert len({e['event_key'] for e in data['events']})==len(data['events'])
        report['cluster_event_rows_checked']=len(data['events'])
        page.screenshot(path=str(output/'cluster-events.png'))
        assert not report['page_errors'],report['page_errors']
        browser.close()
    (output/'browser-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    verify()
