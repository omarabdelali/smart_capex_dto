"""Import native Huawei monthly MAOS CSV reports into the KPI table."""

from pathlib import Path
from typing import Dict
import calendar
import math

import pandas as pd
from django.db import transaction

from core.models import Cell, MAOSMonthlyKPI


class MAOSReportLoader:
    """Stream the report export and attach monthly counters by exact cell name."""

    REPORT_HEADER_ROW = 6
    CHUNK_SIZE = 50_000
    REQUIRED_COLUMNS = {'Date', 'Cell Name'}
    COUNTER_COLUMNS = {
        'L.Traffic.User.Avg',
        'L.Thrp.bits.DL(bit)',
        'L.ChMeas.PRB.DL.Used.Avg',
        'L.Traffic.ActiveUser.Avg',
        'L.Cell.Unavail.Dur.Sys(s)',
        'L.ChMeas.PRB.DL.Avail',
        'L.Thrp.Time.DL.RmvLastTTI(ms)',
        'L.Thrp.bits.DL.LastTTI(bit)',
        'L.Traffic.DL.PktDelay.Time(ms)',
        'L.Traffic.DL.PktDelay.Num(packet)',
        *{f'L.ChMeas.CQI.DL.{i}' for i in range(16)},
    }

    def __init__(self, csv_path: str):
        self.csv_path = Path(csv_path)
        if not self.csv_path.is_file():
            raise FileNotFoundError(f'MAOS monthly CSV not found: {self.csv_path}')

    @classmethod
    def discover_monthly_csv(cls, data_dir: str = 'data/maos') -> Path:
        paths = sorted(Path(data_dir).glob('**/*monthly*.csv'))
        if len(paths) != 1:
            raise FileNotFoundError(
                f'Expected one monthly MAOS CSV under {data_dir}, found {len(paths)}'
            )
        return paths[0]

    def import_to_database(self) -> Dict[str, int]:
        cell_ids = dict(
            Cell.objects.values_list('cell_name', 'pk')
        )
        usecols = self.REQUIRED_COLUMNS | self.COUNTER_COLUMNS
        stats = {'rows_read': 0, 'rows_submitted': 0, 'unmatched_cells': 0, 'invalid_dates': 0,
                 'available_counters': [], 'missing_counters': []}

        for chunk in pd.read_csv(
            self.csv_path,
            skiprows=self.REPORT_HEADER_ROW,
            usecols=lambda column: column.strip() in usecols,
            chunksize=self.CHUNK_SIZE,
            low_memory=False,
        ):
            chunk.columns = chunk.columns.str.strip()
            stats['available_counters'] = sorted(set(chunk.columns) & self.COUNTER_COLUMNS)
            stats['rows_read'] += len(chunk)
            chunk['month_date'] = pd.to_datetime(
                chunk['Date'].astype(str).str.strip(), format='%m-%Y', errors='coerce'
            ).dt.date
            chunk['cell_pk'] = chunk['Cell Name'].astype(str).str.strip().map(cell_ids)
            stats['invalid_dates'] += int(chunk['month_date'].isna().sum())
            stats['unmatched_cells'] += int(chunk['cell_pk'].isna().sum())
            chunk = chunk.dropna(subset=['month_date', 'cell_pk'])
            if chunk.empty:
                continue

            numeric_columns = list(self.COUNTER_COLUMNS)
            for column in numeric_columns:
                if column in chunk:
                    chunk[column] = pd.to_numeric(chunk[column], errors='coerce')

            def number(values, key):
                value = values.get(key)
                if value is None or pd.isna(value):
                    return None
                try:
                    result = float(value)
                    return result if math.isfinite(result) else None
                except (TypeError, ValueError):
                    return None

            records = []
            for row in chunk.itertuples(index=False, name=None):
                values = dict(zip(chunk.columns, row))
                cqi_values = [number(values, f'L.ChMeas.CQI.DL.{i}') for i in range(16)]
                cqi_present = any(value is not None for value in cqi_values)
                cqi_counts = [value if value is not None else 0 for value in cqi_values]
                cqi_total = sum(cqi_counts) if cqi_present else None
                cqi_weighted_sum = sum(i * count for i, count in enumerate(cqi_counts)) if cqi_present else None
                cqi_avg = cqi_weighted_sum / cqi_total if cqi_total else None
                dl_bits = number(values, 'L.Thrp.bits.DL(bit)')
                dl_last_tti_bits = number(values, 'L.Thrp.bits.DL.LastTTI(bit)')
                dl_time_ms = number(values, 'L.Thrp.Time.DL.RmvLastTTI(ms)')
                prb_used = number(values, 'L.ChMeas.PRB.DL.Used.Avg')
                prb_available = number(values, 'L.ChMeas.PRB.DL.Avail')
                delay_time_ms = number(values, 'L.Traffic.DL.PktDelay.Time(ms)')
                delay_packets = number(values, 'L.Traffic.DL.PktDelay.Num(packet)')
                unavailable_s = number(values, 'L.Cell.Unavail.Dur.Sys(s)')
                month_date = values['month_date']
                observation_s = calendar.monthrange(month_date.year, month_date.month)[1] * 86400
                prb_pct = (prb_used / prb_available * 100) if prb_used is not None and prb_available and prb_available > 0 else None
                throughput_bits = dl_bits - dl_last_tti_bits if dl_bits is not None and dl_last_tti_bits is not None and dl_bits >= dl_last_tti_bits else None
                throughput_kbps = throughput_bits / dl_time_ms if throughput_bits is not None and dl_time_ms is not None and dl_time_ms > 0 else None
                delay_ms = delay_time_ms / delay_packets if delay_time_ms is not None and delay_packets is not None and delay_packets > 0 else None
                availability_pct = 100 * (1 - min(max(unavailable_s, 0), observation_s) / observation_s) if unavailable_s is not None else None
                records.append(MAOSMonthlyKPI(
                    cell_id=int(values['cell_pk']),
                    month_date=month_date,
                    traffic_user_avg=number(values, 'L.Traffic.User.Avg'),
                    thrp_bits_dl=dl_bits,
                    thrp_bits_ul=None,
                    prb_util_dl_pct=prb_pct,
                    prb_util_ul_pct=None,
                    rrc_conn_avg=None,
                    active_users_avg=number(values, 'L.Traffic.ActiveUser.Avg'),
                    cqi_avg=cqi_avg,
                    rsrp_avg_dbm=None,
                    prb_dl_used_avg=prb_used,
                    prb_dl_available=prb_available,
                    thrp_time_dl_ms=dl_time_ms,
                    thrp_bits_dl_last_tti=dl_last_tti_bits,
                    dl_packet_delay_time_ms=delay_time_ms,
                    dl_packet_delay_packets=delay_packets,
                    dl_throughput_kbps=throughput_kbps,
                    dl_packet_delay_ms=delay_ms,
                    cell_unavail_duration_s=unavailable_s,
                    observation_duration_s=observation_s if unavailable_s is not None else None,
                    cell_availability_pct=availability_pct,
                    cqi_weighted_sum=cqi_weighted_sum,
                    cqi_sample_count=cqi_total,
                ))

            with transaction.atomic():
                MAOSMonthlyKPI.objects.bulk_create(
                    records,
                    batch_size=2_000,
                    update_conflicts=True,
                    update_fields=[
                        'traffic_user_avg', 'thrp_bits_dl', 'thrp_bits_ul', 'prb_util_dl_pct',
                        'prb_util_ul_pct', 'rrc_conn_avg', 'active_users_avg', 'cqi_avg', 'rsrp_avg_dbm',
                        'prb_dl_used_avg', 'prb_dl_available', 'thrp_time_dl_ms', 'thrp_bits_dl_last_tti',
                        'dl_packet_delay_time_ms', 'dl_packet_delay_packets', 'dl_throughput_kbps',
                        'dl_packet_delay_ms', 'cell_unavail_duration_s', 'observation_duration_s',
                        'cell_availability_pct', 'cqi_weighted_sum', 'cqi_sample_count',
                    ],
                    unique_fields=['cell', 'month_date'],
                )
            stats['rows_submitted'] += len(records)

        stats['missing_counters'] = sorted(self.COUNTER_COLUMNS - set(stats['available_counters']))

        return stats
