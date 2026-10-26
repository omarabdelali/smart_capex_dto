"""HTTP adapters for read-only exploration services."""
from rest_framework.response import Response
from rest_framework.views import APIView
from services.data_explorer import metadata, explore


class DataExplorerMetadataView(APIView):
    def get(self, request):
        return Response(metadata())


class DataExplorerView(APIView):
    def get(self, request):
        payload, status = explore(request.query_params)
        return Response(payload, status=status)
