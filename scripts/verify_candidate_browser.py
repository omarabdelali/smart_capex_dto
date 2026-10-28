"""Exercise the candidate map with fixture data and no persistent writes."""
from playwright.sync_api import sync_playwright, expect

item={'id':'fixture','name':'Test candidate','status':'complete','inputs':{'name':'Test candidate','latitude':35.0,
    'longitude':9.0,'technology':'4G','band':'L1800','sector_count':3,'event_month':'2026-10-01'},
    'features':{'cluster_id':-1,'tier_scheme':'extended','avg_users':None,'virtual_cluster_context':{'vis_n_members':2}},
    'result':{'assignment':{'kind':'virtual','members':[{'site_id':'2','site_name':'Member','latitude':35.02,'longitude':9.02}]},
        'similarity':{'pool_size':1,'profile':{'name':'Test profile','revision':2},'filter_explanation':'Fixture','cases':[{'site_id':'1','site_name':'Example site','cluster_id':-1,
        'latitude':35.01,'longitude':9.01,'similarity':.8,'event_date':'2024-01-01'}]}}}
saved=[]
with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1400,'height':900});errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    def candidates(route):
        if route.request.method=='POST':
            body=route.request.post_data_json
            assert body['technologies'][0]['bands']=='L1800; L800'
            assert len(body['technologies'])==2 and body['profile_id']=='profile-1'
            saved.append(item);route.fulfill(status=201,json=item)
        else: route.fulfill(json=saved)
    page.route('**/api/candidates/',candidates)
    page.route('**/api/analysis/profiles/',lambda r:r.fulfill(json={'csrf_token':'fixture','profiles':[{'id':'profile-1','name':'Test profile','revision':2,'is_active':True,'purpose':'similarity'}]}))
    def sites(route):
        features=[{'type':'Feature','geometry':{'type':'Point','coordinates':[9,35]},'properties':{'site_id':'99','site_name':'Existing'}}] if 'search=' in route.request.url else []
        route.fulfill(json={'type':'FeatureCollection','features':features})
    page.route('**/api/sites/clusters/**',sites)
    page.route('**/api/sites/1/map-links/',lambda r:r.fulfill(json={'members':[{'site_id':'3','site_name':'Neighbor','latitude':35.03,'longitude':9.03}]}))
    page.route('**/api/sites/1/features/**',lambda r:r.fulfill(status=404,json={'error':'fixture unavailable'}))
    page.goto('http://127.0.0.1:3000/',wait_until='domcontentloaded')
    page.get_by_role('button',name='Candidate site',exact=True).click()
    expect(page.locator('.leaflet-container')).to_be_visible()
    page.get_by_label('Planning scenario').select_option('existing')
    page.locator('.search input').fill('Existing')
    page.locator('.search').get_by_role('button',name='Search').click()
    page.get_by_role('button',name='Select Existing · 99').click()
    expect(page.get_by_text('Existing',exact=True)).to_be_visible()
    page.get_by_label('Planning scenario').select_option('new')
    page.get_by_label('Candidate name').fill('Test candidate')
    page.get_by_label('Latitude').fill('35')
    page.get_by_label('Longitude').fill('9')
    page.get_by_label('Frequency bands').first.fill('L1800; L800')
    page.get_by_role('button',name='Add another technology').click()
    page.get_by_label('Frequency bands').nth(1).fill('U900')
    page.get_by_label('Feature template').select_option('profile-1')
    page.get_by_role('button',name='Calculate and save').click()
    expect(page.get_by_text('Virtual / noise')).to_be_visible()
    expect(page.get_by_text('Example site',exact=True)).to_be_visible()
    expect(page.get_by_text('Low support:',exact=False)).to_be_visible()
    expect(page.locator('.candidate-icon').first).to_be_visible()
    page.locator('.candidate-icon').last.click()
    page.get_by_role('button',name='Example site').click()
    expect(page.get_by_role('button',name='Close site details')).to_be_visible()
    page.get_by_text('Calculated features and unavailable values').click()
    expect(page.get_by_text('Unavailable',exact=True).first).to_be_visible()
    assert not errors,errors
    print('Candidate form, saved exercise, distinct map marker, low support and missing values verified with fixture API.')
    browser.close()
