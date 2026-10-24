"""Detect cell additions from complete monthly MAOS KPI histories."""

from collections import defaultdict
from typing import Dict

from django.db import transaction
from django.db.models import Min

from core.models import Cell, MAOSMonthlyKPI, Site


KPI_FIELDS = (
    'traffic_user_avg', 'thrp_bits_dl', 'thrp_bits_ul', 'prb_util_dl_pct',
    'prb_util_ul_pct', 'rrc_conn_avg', 'active_users_avg', 'cqi_avg', 'rsrp_avg_dbm',
)


def _active(kpis) -> bool:
    """A recorded nonzero KPI means the cell had service/activity."""
    return any(value not in (None, 0) for value in kpis)


class MAOSLaunchDetector:
    """Detect cells whose KPIs were all zero/absent before their launch month."""

    def detect_and_save(self) -> Dict[str, int]:
        data_start = MAOSMonthlyKPI.objects.aggregate(first_month=Min('month_date'))['first_month']
        if data_start is None:
            return {
                'cells_evaluated': 0, 'detected_cells': 0, 'detected_sites': 0,
                'detected_site_technologies': 0, 'data_start': None,
            }

        # Stream each cell's history and retain its first month with any nonzero KPI.
        first_activity = {}
        current_cell = None
        cell_event = None
        rows = MAOSMonthlyKPI.objects.order_by('cell_id', 'month_date').values_list(
            'cell_id', 'month_date', *KPI_FIELDS
        )
        for row in rows.iterator(chunk_size=10_000):
            cell_id, month, *kpis = row
            if cell_id != current_cell:
                if current_cell is not None and cell_event is not None:
                    first_activity[current_cell] = cell_event
                current_cell, cell_event = cell_id, None
            if cell_event is None and _active(kpis):
                cell_event = month
        if current_cell is not None and cell_event is not None:
            first_activity[current_cell] = cell_event

        # Keep per-cell additions so a new sector is detected even when its
        # technology already serves the site.
        cell_launches = {pk: date for pk, date in first_activity.items() if date > data_start}
        cells = Cell.objects.in_bulk(cell_launches.keys())
        additions_by_site = defaultdict(list)
        cells_to_update = []
        for cell_pk, launch_date in cell_launches.items():
            cell = cells.get(cell_pk)
            if cell is None:
                continue
            additions_by_site[cell.site_id].append(launch_date)
            if not cell.is_launched or cell.launch_date != launch_date:
                cell.is_launched = True
                cell.launch_date = launch_date
                cells_to_update.append(cell)

        # A whole site is added only when every technology at that site first
        # has nonzero KPI in the same month. Otherwise only qualifying cells
        # are additions, even if the site/technology was already active.
        first_by_site_technology = {}
        first_cells = Cell.objects.filter(pk__in=first_activity.keys()).values_list(
            'site_id', 'technology', 'pk'
        )
        for site_id, technology, cell_pk in first_cells.iterator(chunk_size=10_000):
            month = first_activity[cell_pk]
            key = (site_id, technology)
            first_by_site_technology[key] = min(first_by_site_technology.get(key, month), month)

        all_site_technologies = defaultdict(set)
        for site_id, technology in Cell.objects.values_list('site_id', 'technology').iterator(chunk_size=10_000):
            all_site_technologies[site_id].add(technology)
        site_launches = {}
        for site_id, technologies in all_site_technologies.items():
            dates = [first_by_site_technology.get((site_id, technology)) for technology in technologies]
            if dates and all(date is not None and date > data_start for date in dates) and len(set(dates)) == 1:
                site_launches[site_id] = dates[0]

        sites = Site.objects.in_bulk(set(additions_by_site) | set(site_launches))
        sites_to_update = []
        for site_pk, launch_date in site_launches.items():
            site = sites.get(site_pk)
            if site is None:
                continue
            if not site.is_launched or site.launch_date != launch_date:
                site.is_launched = True
                site.launch_date = launch_date
                sites_to_update.append(site)

        with transaction.atomic():
            Cell.objects.filter(is_launched=True).exclude(pk__in=cell_launches.keys()).update(
                is_launched=False, launch_date=None
            )
            Site.objects.filter(is_launched=True).exclude(pk__in=site_launches.keys()).update(
                is_launched=False, launch_date=None
            )
            if cells_to_update:
                Cell.objects.bulk_update(cells_to_update, ['is_launched', 'launch_date'], batch_size=1_000)
            if sites_to_update:
                Site.objects.bulk_update(sites_to_update, ['is_launched', 'launch_date'], batch_size=1_000)

        return {
            'cells_evaluated': Cell.objects.filter(monthly_kpis__isnull=False).distinct().count(),
            'detected_cells': len(cell_launches),
            'detected_sites': len(site_launches),
            'detected_site_technologies': len(first_by_site_technology),
            'data_start': data_start,
        }
