"""The three goal models (architecture section 8.2) and the grid engine they share.

Models are implemented in-house with numpy and scipy (ADR-019). A model that fails to converge or
fails its sanity checks is reported as ``failed``; it is never silently replaced.
"""
