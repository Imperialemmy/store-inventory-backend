class ApiNoCacheMiddleware:
    """Mark API responses as non-cacheable.

    Without an explicit Cache-Control header some browsers (notably Safari)
    may serve a cached copy of GET endpoints, so a list page can show stale
    data right after a write until the user hard-reloads.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith("/api/") and "Cache-Control" not in response:
            response["Cache-Control"] = "no-store"
        return response
