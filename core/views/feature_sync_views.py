from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from services.models.features.sync_jobs import latest_job, start_job


class FeatureSyncView(APIView):
    """Read job status or start one full feature synchronization run."""

    def get(self, request):
        return Response({'job': latest_job()})

    def post(self, request):
        mode = request.data.get('mode')
        if mode not in {'features', 'full'}:
            return Response({'error': "mode must be 'features' or 'full'"}, status=status.HTTP_400_BAD_REQUEST)
        job, created = start_job(mode)
        return Response({'job': job, 'started': created}, status=status.HTTP_202_ACCEPTED if created else status.HTTP_409_CONFLICT)
