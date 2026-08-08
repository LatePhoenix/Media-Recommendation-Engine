"""Service layer: thin boundaries between routers and the data/engine internals.

Phase 1 introduces CatalogService, RecommendationService, and InterestService.
ExternalLinkService and MetadataNormalizationService arrive with Phases 3/4.

Import services from their submodules (``app.services.interest`` etc.) rather than
from this package root — the engine imports the pure helpers in ``interest``, so an
eager re-export here would create an import cycle (engine → services → recommendation
→ engine).
"""
