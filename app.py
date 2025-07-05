# Wrapper for Render
# ------------------
# Many PaaS platforms (including Render) default to running
#     gunicorn app:app
# which expects a module named ``app`` that exposes the Flask
# application instance named ``app``.
#
# Our real application lives in ``render_crawler.py`` and the
# Flask instance is also called ``app``.  This tiny shim simply
# re-exports it so that both
#     gunicorn app:app
# and
#     gunicorn render_crawler:app
# work interchangeably.

from render_crawler import app  # noqa: F401 