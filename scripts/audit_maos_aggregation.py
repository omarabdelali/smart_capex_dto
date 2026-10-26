"""Read-only raw-cell reconciliation; run through manage.py shell and runpy."""
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

from core.models import MAOSMonthlyKPI, Site
from services.models.features.maos_context import monthly_series, scope_members


site = Site.objects.get(site_id='1534')
report = {'date': date.today().isoformat(), 'site': site.site_name, 'scopes': {}}
for scope, members in {'site': [site.site_id], **scope_members(site)}.items():
    values = defaultdict(list)
    for month, value in MAOSMonthlyKPI.objects.filter(cell__site__site_id__in=members).values_list('month_date', 'active_users_avg').iterator():
        values[month.strftime('%Y-%m')].append(value)
    actual = {row['month']: row['active_users_avg'] for row in monthly_series(members)}
    for month, cells in values.items():
        valid = [value for value in cells if value is not None]
        expected = sum(valid) if valid else None
        observed = actual[month]
        assert expected == observed or (expected is not None and observed is not None and abs(expected-observed) <= 1e-8*max(1,abs(expected))), (scope,month,expected,observed)
    latest = max(actual, default=None)
    report['scopes'][scope] = {'sites':len(members), 'months_checked':len(values),
        'latest_month':latest, 'latest_active_users':actual.get(latest), 'mismatches':0}
destination = Path('docs/verification/user_context/active-users-audit.json')
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
