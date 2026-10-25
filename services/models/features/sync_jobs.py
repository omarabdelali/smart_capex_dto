"""Background orchestration for full feature re-synchronization."""
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from django.db import close_old_connections, transaction
from django.utils import timezone

from core.models import FeatureSyncJob

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='feature-sync')
_start_lock = Lock()


def _job_payload(job):
    return {
        'id': job.pk, 'mode': job.mode, 'status': job.status, 'stage': job.stage,
        'processed': job.processed, 'total': job.total,
        'current_site': job.current_site or None, 'result': job.result,
        'error': job.error or None,
        'created_at': job.created_at.isoformat() if job.created_at else None,
        'started_at': job.started_at.isoformat() if job.started_at else None,
        'finished_at': job.finished_at.isoformat() if job.finished_at else None,
    }


def latest_job():
    job = FeatureSyncJob.objects.first()
    return _job_payload(job) if job else None


def start_job(mode):
    with _start_lock, transaction.atomic():
        active = FeatureSyncJob.objects.filter(status__in=['queued', 'running']).first()
        if active:
            return _job_payload(active), False
        job = FeatureSyncJob.objects.create(mode=mode, status='queued', stage='queued')
        transaction.on_commit(lambda job_id=job.pk: _executor.submit(_run_job, job_id))
        return _job_payload(job), True


def _run_job(job_id):
    close_old_connections()
    job = FeatureSyncJob.objects.get(pk=job_id)
    job.status, job.stage, job.started_at = 'running', 'starting', timezone.now()
    job.save(update_fields=['status', 'stage', 'started_at'])
    try:
        if job.mode == 'full':
            job.stage = 'detecting_additions'
            job.save(update_fields=['stage'])
            from services.models.preprocessing.maos_launch_detector import MAOSLaunchDetector
            detection = MAOSLaunchDetector().detect_and_save()
            if detection.get('data_start'):
                detection['data_start'] = detection['data_start'].isoformat()
            job.result = {'detection': detection}
            job.save(update_fields=['result'])

        from services.models.features.pipeline import FeatureExtractionPipeline

        def report(progress):
            FeatureSyncJob.objects.filter(pk=job_id, status='running').update(
                stage=progress['stage'], processed=progress['processed'],
                total=progress['total'], current_site=progress.get('current_site') or '',
            )

        stats = FeatureExtractionPipeline().extract_and_save_features(
            skip_existing=False, progress_callback=report
        )
        current = FeatureSyncJob.objects.get(pk=job_id)
        result = current.result or {}
        result['features'] = stats
        current.result = result
        current.status, current.stage, current.finished_at = 'succeeded', 'complete', timezone.now()
        current.save(update_fields=['result', 'status', 'stage', 'finished_at'])
    except Exception as exc:
        FeatureSyncJob.objects.filter(pk=job_id).update(
            status='failed', stage='failed', error=f'{type(exc).__name__}: {exc}',
            finished_at=timezone.now(),
        )
    finally:
        close_old_connections()
