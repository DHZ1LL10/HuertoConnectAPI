"""Lossless HTTP response compression; request image bytes remain untouched."""
from starlette.middleware.gzip import GZipMiddleware


def install_low_data(app):
    app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=5)
