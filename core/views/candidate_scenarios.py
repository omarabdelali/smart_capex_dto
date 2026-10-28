from rest_framework.response import Response
from rest_framework.views import APIView
from core.models import CandidateScenario
from services.candidate_scenarios import create_scenario, payload
from services.analysis_profiles import browser_actor


class CandidateScenariosView(APIView):
    def get(self,request):
        return Response([payload(row) for row in CandidateScenario.objects.order_by('-created_at')])

    def post(self,request):
        try:
            return Response(payload(create_scenario(request.data,browser_actor(request))),status=201)
        except ValueError as exc:
            return Response({'error':str(exc)},status=400)


class CandidateScenarioView(APIView):
    def get(self,request,scenario_id):
        item=CandidateScenario.objects.filter(pk=scenario_id).first()
        return Response(payload(item)) if item else Response({'error':'Candidate not found'},status=404)
