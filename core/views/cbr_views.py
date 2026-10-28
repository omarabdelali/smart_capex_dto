"""Read-only CBR impact forecast API."""
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from services.analysis_profiles import browser_actor
from services.models.prediction.cbr_impact import build_cbr_impact_prediction
from services.models.prediction.recipient_cbr import recipient_request
from services.models.prediction.counterfactual_gains import gain_request


class CounterfactualGainView(APIView):
    def get(self,request):
        payload,code=gain_request(request.query_params,browser_actor(request))
        return Response(payload,status=code)


class RecipientCBRView(APIView):
    def get(self,request):
        payload,code=recipient_request(request.query_params,browser_actor(request))
        return Response(payload,status=code)


class CBRImpactPredictionView(APIView):
    """Predict the selected site's event response for neighboring sites."""

    def get(self, request):
        site_id = request.query_params.get('site_id', '').strip()
        if not site_id:
            return Response({'error': 'site_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        result = build_cbr_impact_prediction(site_id,event_key=request.query_params.get('event_key'),actor=browser_actor(request),profile_params=request.query_params)
        if result is None:
            return Response({'error': f'Site {site_id} was not found'}, status=status.HTTP_404_NOT_FOUND)
        if result.get('error'):
            return Response(result, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        return Response(result)
