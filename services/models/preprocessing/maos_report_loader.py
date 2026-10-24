"""Import native Huawei monthly MAOS CSV reports into the KPI table."""

from pathlib import Path
from typing import Dict

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
        stats = {'rows_read': 0, 'rows_submitted': 0, 'unmatched_cells': 0, 'invalid_dates': 0}

        for chunk in pd.read_csv(
            self.csv_path,
            skiprows=self.REPORT_HEADER_ROW,
            usecols=lambda column: column.strip() in usecols,
            chunksize=self.CHUNK_SIZE,
            low_memory=False,
        ):
            chunk.columns = chunk.columns.str.strip()
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
                    chunk[column] = pd.to_numeric(chunk[column], errors='coerce').fillna(0)

            records = []
            for row in chunk.itertuples(index=False, name=None):
                values = dict(zip(chunk.columns, row))
                cqi_counts = [float(values.get(f'L.ChMeas.CQI.DL.{i}', 0) or 0) for i in range(16)]
                cqi_total = sum(cqi_counts)
                cqi_avg = sum(i * count for i, count in enumerate(cqi_counts)) / cqi_total if cqi_total else 0
                records.append(MAOSMonthlyKPI(
                    cell_id=int(values['cell_pk']),
                    month_date=values['month_date'],
                    traffic_user_avg=float(values.get('L.Traffic.User.Avg', 0) or 0),
                    thrp_bits_dl=float(values.get('L.Thrp.bits.DL(bit)', 0) or 0),
                    prb_util_dl_pct=float(values.get('L.ChMeas.PRB.DL.Used.Avg', 0) or 0),
                    active_users_avg=float(values.get('L.Traffic.ActiveUser.Avg', 0) or 0),
                    cqi_avg=cqi_avg,
                ))

            with transaction.atomic():
                MAOSMonthlyKPI.objects.bulk_create(
                    records, batch_size=2_000, ignore_conflicts=True
                )
            stats['rows_submitted'] += len(records)

        return stats
