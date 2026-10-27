"""Thin transport for workspace configuration and browser presets."""
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework.views import APIView
from rest_framework.response import Response
from services.analysis_profiles import browser_actor,workspace_context,save_profile,assign_default,remove_default


@method_decorator(csrf_protect,name='dispatch')
class AnalysisProfilesView(APIView):
    def get(self,request):
        return Response(workspace_context(request))

    def post(self,request):
        payload,code=save_profile(browser_actor(request),request.data)
        return Response(payload,status=code)


@method_decorator(csrf_protect,name='dispatch')
class AnalysisProfileView(APIView):
    def put(self,request,profile_id):
        payload,code=save_profile(browser_actor(request),request.data,profile_id)
        return Response(payload,status=code)


@method_decorator(csrf_protect,name='dispatch')
class AnalysisProfileDefaultsView(APIView):
    def post(self,request):
        payload,code=assign_default(browser_actor(request),request.data)
        return Response(payload,status=code)

    def delete(self,request,default_id):
        payload,code=remove_default(browser_actor(request),default_id)
        return Response(payload,status=code)
