"""Population overlay endpoint."""
from django.http import HttpResponse, JsonResponse
from django.views.decorators.cache import cache_page
from services.models.features.population import population_tile


@cache_page(60 * 60)
def tile(request, z, x, y):
    if not 0 <= z <= 18 or not (0 <= x < 2**z and 0 <= y < 2**z):
        return JsonResponse({'error': 'Invalid tile coordinates'}, status=400)
    try:
        return HttpResponse(population_tile(z, x, y), content_type='image/png')
    except OSError:
        return JsonResponse({'error': 'Population raster unavailable'}, status=503)
