"""Profile ownership, schema, revisioning and deterministic scenario defaults."""
from django.db import transaction
from django.db.models import Q
from django.core.exceptions import ValidationError
from uuid import UUID, uuid4
from django.middleware.csrf import get_token
from core.models import AnalysisProfile,AnalysisProfileDefault,AnalysisProfileRevision
from services.models.similarity.catalog import SIMILARITY_FIELDS,DISPLAY_ONLY,OPTIONAL
from services.models.similarity.gower_distance import GowerDistance
from services.models.prediction.pair_cases import PAIR_NUMERIC,PAIR_CATEGORICAL,PAIR_GROUPS

EVENTS=['ANY','SITE_ADDED','TECHNOLOGY_ADDED','FREQUENCY_BAND_ADDED','CELL_ADDED','BANDWIDTH_UPGRADE','BANDWIDTH_DOWNGRADE','COMPOUND_EVENT']
PURPOSES=['similarity','prediction','both']
PAIR_FIELDS=list(PAIR_NUMERIC+PAIR_CATEGORICAL)
SITE_FIELDS=[f for f in SIMILARITY_FIELDS if f not in DISPLAY_ONLY]


def defaults():
    return {'similarity_features':[f for f in SITE_FIELDS if f not in OPTIONAL],
        'prediction_features':PAIR_FIELDS[:],'representation':'original','pca_variance_target':.9,
        'weighting_mode':'equal_per_feature','allow_filter_relaxation':True,
        'minimum_available_weight_share':.6,'prediction_method':'pair_cbr','ramp':False,'scope':'tier1'}


def catalog():
    distance=GowerDistance()
    return {'event_types':EVENTS,'tier_schemes':['ANY','standard','extended'],'technologies':['ANY','2G','3G','4G'],
        'purposes':PURPOSES,'defaults':defaults(),'schema_version':'analysis-profile-v1',
        'similarity_features':[{'key':f,'label':f.replace('_',' '),'group':distance._get_feature_group(f),
            'type':'numeric' if f in distance.NUMERIC_FEATURES else 'categorical'} for f in SITE_FIELDS],
        'prediction_features':[{'key':f,'label':f.replace('_',' '),'group':PAIR_GROUPS[f],
            'type':'numeric' if f in PAIR_NUMERIC else 'categorical'} for f in PAIR_FIELDS],
        'constraints':['Event type and tier scheme are mandatory; identifiers never score.',
            'Profile scoring uses only selected fields. Missing values remain NULL.',
            'PCA profiles store original source fields, not query-specific PC numbers.',
            'Site fields apply to similarity/legacy CBR; pair fields apply to recipient prediction.']}


def authenticated(actor):
    return actor is not None


def browser_actor(request):
    """Server-owned persistent browser identity; never accept an owner from input."""
    value=request.session.get('analysis_browser')
    if not value:
        value=str(uuid4())
        request.session['analysis_browser']=value
        request.session.set_expiry(365*24*3600)
    return UUID(value)


def workspace_context(request):
    actor=browser_actor(request)
    seed_profiles(actor)
    return {**profile_list(actor),'csrf_token':get_token(request),
        'ownership_note':'Shared templates are workspace configuration. Personal presets belong to this browser session; clearing cookies removes access. No account administration.'}


def visible(actor):
    return AnalysisProfile.objects.filter(Q(is_shared=True)|Q(browser_owner=actor) if authenticated(actor) else Q(is_shared=True))


def editable(profile,actor):
    return authenticated(actor) and (profile.browser_owner==actor or profile.is_shared)


def snapshot(profile):
    return {k:getattr(profile,k) for k in ('name','description','purpose','event_type','tier_scheme','technology','is_shared','is_active','settings','revision','schema_version')}


def public(profile,actor=None):
    return {'id':str(profile.pk),'owner':'Shared workspace' if profile.is_shared else 'This browser','can_edit':editable(profile,actor),
        'updated_at':profile.updated_at.isoformat(),**snapshot(profile)}


def scenario(profile):
    return '|'.join([profile.event_type,profile.tier_scheme,profile.technology])


def validate_settings(settings):
    result=defaults()
    if not isinstance(settings,dict) or set(settings)-set(result):
        raise ValueError('Unknown or invalid profile settings.')
    result.update(settings)
    for name,allowed in [('similarity_features',SITE_FIELDS),('prediction_features',PAIR_FIELDS)]:
        values=result[name]
        if not isinstance(values,list) or any(not isinstance(f,str) or f not in allowed for f in values):
            raise ValueError(f'{name} contains unsupported features or identifiers.')
        result[name]=list(dict.fromkeys(values))
        if not result[name]:
            raise ValueError(f'Select at least one {name} field.')
    if result['representation'] not in ('original','pca') or result['weighting_mode'] not in ('equal_per_feature','equal_per_group'):
        raise ValueError('Unsupported representation or weighting mode.')
    if type(result['allow_filter_relaxation']) is not bool or type(result['ramp']) is not bool:
        raise ValueError('Relaxation and ramp must be boolean values.')
    if type(result['pca_variance_target']) not in (float,int) or not .5<=result['pca_variance_target']<=.99:
        raise ValueError('PCA variance target must be 0.5 to 0.99.')
    if type(result['minimum_available_weight_share']) not in (float,int) or not .6<=result['minimum_available_weight_share']<=1:
        raise ValueError('Profile available-weight share must be 0.6 to 1.')
    if result['prediction_method'] not in ('pair_cbr','control_adjusted','local_linear','did_local_linear'):
        raise ValueError('Unsupported prediction method.')
    if result['scope'] not in ('tier1','tier2','cluster','virtual_cluster','distance_0_2','distance_2_5','distance_5_10'):
        raise ValueError('Unsupported prediction scope.')
    if result['representation']=='pca' and len(set(result['similarity_features'])&set(GowerDistance.NUMERIC_FEATURES))<2:
        raise ValueError('PCA needs at least two selected original numeric features.')
    return result


def save_profile(actor,body,profile_id=None):
    if not authenticated(actor):
        return {'error':'Browser profile session is required.'},403
    if not isinstance(body,dict):
        return {'error':'Profile must be a JSON object.'},400
    try:
        with transaction.atomic():
            profile=visible(actor).select_for_update().filter(pk=profile_id).first() if profile_id else AnalysisProfile(browser_owner=actor)
            if profile is None:
                return {'error':'Profile not found.'},404
            if profile_id and not editable(profile,actor):
                return {'error':'This profile is read-only. Save a personal copy.'},403
            if profile_id and body.get('revision')!=profile.revision:
                return {'error':'Profile changed. Reload before saving.'},409
            unknown=set(body)-{'name','description','purpose','event_type','tier_scheme','technology','is_shared','is_active','settings','revision'}
            if unknown:
                raise ValueError('Unknown profile fields: '+', '.join(sorted(unknown)))
            previous_scenario=scenario(profile)
            for key in ('name','description','purpose','event_type','tier_scheme','technology','is_shared','is_active'):
                if key in body:
                    setattr(profile,key,body[key])
            if not isinstance(profile.name,str) or not profile.name.strip() or len(profile.name)>120:
                raise ValueError('A profile name of 1 to 120 characters is required.')
            profile.name=profile.name.strip()
            if not isinstance(profile.description,str) or len(profile.description)>5000:
                raise ValueError('Description must have at most 5000 characters.')
            if profile.purpose not in PURPOSES or profile.event_type not in EVENTS or profile.tier_scheme not in ('ANY','standard','extended') or profile.technology not in ('ANY','2G','3G','4G'):
                raise ValueError('Unsupported profile purpose or scenario.')
            if type(profile.is_shared) is not bool or type(profile.is_active) is not bool:
                raise ValueError('Sharing and activity must be boolean values.')
            if profile_id and profile.is_shared!=AnalysisProfile.objects.get(pk=profile.pk).is_shared:
                raise ValueError('Use Save as new to change between shared and personal visibility.')
            if profile_id and previous_scenario!=scenario(profile) and profile.default_assignments.exists():
                raise ValueError('Remove default assignments before changing this profile scenario.')
            if profile_id and profile.purpose!=AnalysisProfile.objects.get(pk=profile.pk).purpose and profile.default_assignments.exists():
                raise ValueError('Remove default assignments before changing profile purpose.')
            profile.settings=validate_settings(body.get('settings',profile.settings))
            if profile_id:
                profile.revision+=1
            profile.save()
            AnalysisProfileRevision.objects.create(profile=profile,revision=profile.revision,snapshot=snapshot(profile),browser_actor=actor)
            return public(profile,actor),200 if profile_id else 201
    except (ValueError,ValidationError) as error:
        return {'error':str(error)},400


def profile_list(actor):
    assignments=AnalysisProfileDefault.objects.filter(profile__in=visible(actor),scope_key__in=['system',f'browser:{actor}' if authenticated(actor) else 'system'])
    return {'profiles':[public(p,actor) for p in visible(actor)],
        'defaults':[{'id':d.pk,'profile_id':str(d.profile_id),'purpose':d.purpose,'scope':d.scope_key,'scenario_key':d.scenario_key} for d in assignments],
        'catalog':catalog()}


def assign_default(actor,body):
    if not authenticated(actor):
        return {'error':'Browser profile session is required.'},403
    purpose=body.get('purpose');system=body.get('scope')=='system'
    if purpose not in ('similarity','prediction') or body.get('scope') not in ('system','personal'):
        return {'error':'Choose similarity/prediction and personal/system scope.'},400
    try:
        profile=visible(actor).get(pk=body.get('profile_id'),is_active=True)
    except (AnalysisProfile.DoesNotExist,ValidationError):
        return {'error':'Active profile not found.'},404
    if profile.purpose not in (purpose,'both') or system and not profile.is_shared:
        return {'error':'The default must support its purpose; system defaults must be shared.'},400
    with transaction.atomic():
        d,_=AnalysisProfileDefault.objects.update_or_create(scope_key='system' if system else f'browser:{actor}',
            purpose=purpose,scenario_key=scenario(profile),defaults={'profile':profile,'user':None})
    return {'id':d.pk,'profile_id':str(profile.pk),'purpose':purpose,'scope':d.scope_key},200


def remove_default(actor,default_id):
    if not authenticated(actor):
        return {'error':'Browser profile session is required.'},403
    row=AnalysisProfileDefault.objects.filter(pk=default_id).first()
    if row is None:
        return {'error':'Default not found.'},404
    if row.scope_key not in (f'browser:{actor}','system'):
        return {'error':'You cannot change this default.'},403
    row.delete()
    return {'removed':True},200


def resolve_profile(actor,purpose,params,context):
    explicit=params.get('profile_id')
    if explicit=='manual':
        return None,{'mode':'manual'},None
    pool=visible(actor).filter(is_active=True,purpose__in=[purpose,'both'])
    if explicit:
        try:
            selected=pool.filter(pk=explicit).first()
        except ValidationError:
            return None,None,({'error':'Invalid profile ID.'},400)
        if selected is None:
            return None,None,({'error':'Profile unavailable or not owned/shared for this purpose.'},404)
        candidates=[(selected,'explicit')]
    else:
        rows=AnalysisProfileDefault.objects.filter(profile__in=pool,purpose=purpose,scope_key__in=['system',f'browser:{actor}' if authenticated(actor) else 'system']).select_related('profile')
        rows=sorted(rows,key=lambda d:(d.scope_key!='system',sum(v!='ANY' for v in d.scenario_key.split('|')),d.updated_at,str(d.profile_id)),reverse=True)
        candidates=[(d.profile,d.scope_key) for d in rows]
    for profile,source in candidates:
        technologies=set(str(context.get('technology') or '').split('/'))
        matches=(profile.event_type in ('ANY',context.get('event_type')) and profile.tier_scheme in ('ANY',context.get('tier_scheme'))
                 and (profile.technology=='ANY' or profile.technology in technologies))
        if not matches:
            if explicit:
                return None,None,({'error':'This profile does not match the event type, tier scheme or technology.'},422)
            continue
        try:
            settings=validate_settings(profile.settings)
        except ValueError as error:
            return None,None,({'error':'Profile schema needs review: '+str(error)},422)
        return settings,{'id':str(profile.pk),'name':profile.name,'revision':profile.revision,'schema_version':profile.schema_version,
            'source':source,'settings':settings,'strict_feature_selection':True},None
    return None,{'mode':'built_in'},None


def seed_profiles(actor):
    from core.models import AnalysisSetup
    if actor is None:
        return
    with transaction.atomic():
        marker,_=AnalysisSetup.objects.select_for_update().get_or_create(pk=1)
        if marker.completed:
            return
        if not AnalysisProfile.objects.filter(is_shared=True).exists():
            payload,code=save_profile(actor,{'name':'Balanced default','purpose':'both','is_shared':True,'settings':defaults()})
            if code==201:
                for purpose in ('similarity','prediction'):
                    assign_default(actor,{'profile_id':payload['id'],'purpose':purpose,'scope':'system'})
        marker.completed=True
        marker.save(update_fields=['completed'])
