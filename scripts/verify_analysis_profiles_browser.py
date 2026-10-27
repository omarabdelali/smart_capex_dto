"""Exercise configuration, browser defaults and actual scoring through the UI."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect

with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    context=browser.new_context(viewport={'width':1440,'height':1100})
    page=context.new_page();errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto('http://127.0.0.1:3000/',wait_until='domcontentloaded')
    page.get_by_role('button',name='Administration',exact=True).click()
    config=page.locator('.configuration')
    expect(config.get_by_label('Name',exact=True)).to_be_visible(timeout=30000)
    config.get_by_label('Name',exact=True).fill('Browser verification preset')
    config.get_by_label('Shared workspace template',exact=True).uncheck()
    # Select two site fields and one pair field through the scroll lists.
    for column in config.locator('.feature-columns section').all():
        for checkbox in column.locator('input[type=checkbox]').all():
            checkbox.uncheck()
    config.locator('.feature-columns section').nth(0).get_by_text('n sites 1km',exact=False).first.locator('input').check()
    config.locator('.feature-columns section').nth(0).get_by_text('n sites 2km',exact=False).first.locator('input').check()
    config.locator('.feature-columns section').nth(1).get_by_text('distance m',exact=False).first.locator('input').check()
    with page.expect_response(lambda r:'/analysis/profiles/' in r.url and r.request.method=='POST') as pending:
        config.get_by_role('button',name='Create template',exact=True).click()
    response=pending.value;assert response.status==201,response.text()
    profile=response.json();profile_id=profile['id']
    expect(config.get_by_role('button',name='My similarity default',exact=True)).to_be_visible()
    config.get_by_role('button',name='My similarity default',exact=True).click()
    expect(config).to_contain_text('Default saved.')
    page.get_by_role('button',name='Similarity',exact=True).click()
    page.locator('#site-search').fill('GAB_0033')
    page.get_by_role('option',name='GAB_0033 105784',exact=True).click(timeout=30000)
    expect(page.locator('.similarity-page .profile-picker')).to_contain_text('Applied: Browser verification preset',timeout=240000)
    with page.expect_response(lambda r:'/similarity/search/' in r.url,timeout=300000) as pending:
        page.get_by_role('button',name='Find similar sites',exact=True).click()
    response=pending.value;assert response.status==200,response.text()
    ranked=response.json()
    assert ranked['analysis_profile']['id']==profile_id
    assert set(ranked['selected_features'])=={'n_sites_1km','n_sites_2km'}
    assert ranked['cases']
    for case in ranked['cases']:
        assert set(case['feature_weights'])<={'n_sites_1km','n_sites_2km'}
        assert abs(sum(case['feature_weights'].values())-1)<1e-8
    # A saved template is available in the prediction picker too.
    page.get_by_role('button',name='CBR impact',exact=True).click()
    page.locator('.cbr .search input').fill('BAR_0196')
    page.locator('.cbr .matches button').filter(has_text='1002').click(timeout=30000)
    panel=page.locator('.recipient-cbr')
    expect(panel.get_by_label('Recipient analysis event')).not_to_have_value('',timeout=240000)
    panel.get_by_label('Configuration profile',exact=True).select_option(profile_id)
    expect(panel.locator('.pair-features input:checked')).to_have_count(1)
    assert panel.locator('.pair-features input:checked').input_value()=='distance_m'
    with page.expect_response(lambda r:'/cbr/recipients/' in r.url and 'metadata=' not in r.url,timeout=240000) as pending:
        panel.get_by_role('button',name='Calculate recipient impact',exact=True).click()
    response=pending.value;assert response.status==200,response.text()
    predicted=response.json()
    assert predicted['analysis_profile']['id']==profile_id
    assert predicted['scoring_settings']['selected_features']==['distance_m']
    expect(panel).to_contain_text('Scoring: distance_m')
    with page.expect_response(lambda r:'/cbr/recipients/' in r.url and 'metadata=true' in r.url and 'analysis_unit=episode' in r.url,timeout=120000) as pending:
        panel.get_by_label('Recipient analysis unit',exact=True).select_option('episode')
    metadata=pending.value.json()
    assert len(metadata['events'])==2
    october=next(e for e in metadata['events'] if e['date']=='2025-10-01')
    assert len(october['actions'])==3
    panel.get_by_label('Recipient analysis event',exact=True).select_option(october['event_key'])
    panel.get_by_text('Episode actions and original event dates',exact=True).click()
    expect(panel).to_contain_text('One analysis per physical site/month')
    with page.expect_response(lambda r:'/cbr/recipients/' in r.url and 'metadata=' not in r.url,timeout=240000) as pending:
        panel.get_by_role('button',name='Calculate recipient impact',exact=True).click()
    response=pending.value;assert response.status==200,response.text()
    episode=response.json();assert episode['query']['analysis_unit']=='episode'
    assert len(episode['query']['raw_event_keys'])==3
    assert episode['reference']['reference_id']=='6318d2c850865098d0788c86'
    page.set_viewport_size({'width':390,'height':844})
    page.get_by_role('button',name='Administration',exact=True).click()
    config=page.locator('.configuration')
    expect(config.get_by_label('Template',exact=True)).to_be_visible()
    config.get_by_label('Template',exact=True).select_option(profile_id)
    config.get_by_label('Description',exact=True).fill('Verified browser round trip')
    config.get_by_role('button',name='Save revision',exact=True).click()
    expect(config.get_by_label('Template',exact=True).locator('option:checked')).to_contain_text('v2')
    expect(config).to_contain_text('This browser')
    config.get_by_label('Active',exact=True).uncheck()
    config.get_by_role('button',name='Save revision',exact=True).click()
    expect(config.get_by_label('Template',exact=True).locator('option:checked')).to_contain_text('archived')
    assert not errors,errors
    result={'profile_id':profile_id,'browser_configuration_revision_and_archive':True,'personal_scenario_default':True,
        'similarity_selected_fields':ranked['selected_features'],'similarity_cases':len(ranked['cases']),
        'prediction_selected_fields':predicted['scoring_settings']['selected_features'],'episode_raw_actions':len(episode['query']['raw_event_keys']),'episode_forecast_status':episode['status'],'page_errors':errors}
    output=Path('docs/verification/analysis_profiles');output.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(output/'configuration-mobile.png'),full_page=True)
    (output/'browser.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2));browser.close()
