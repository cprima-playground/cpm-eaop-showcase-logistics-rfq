"""Session-scoped MaritimeGraph fixture -- load_graph() calls
ocean_astar.landmask.register_clear_zone() for every node (D2's hard
load-order rule: it raises if called after the blocked mask is already
cached). Loading the graph exactly ONCE per test session, shared by every
test that needs it, avoids that race entirely -- no test in this
automated suite exercises the real coastline-aware A* pass (that's slow,
minutes-class on a cold cache, and belongs to a live/manual smoke test,
same convention as tms-mcp's test_capacity_checkpoint.py), so nothing
here ever caches the blocked mask in the first place."""

import pytest

from geo_api import routing


@pytest.fixture(scope="session")
def graph() -> routing.MaritimeGraph:
    return routing.load_graph()
