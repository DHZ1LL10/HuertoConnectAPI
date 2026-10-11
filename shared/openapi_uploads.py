"""Keep upload schemas compatible with Swagger UI across Pydantic versions."""
def normalize_upload_schemas(value):
    if isinstance(value, dict):
        if value.get("type") == "string" and value.get("contentMediaType") == "application/octet-stream":
            value["format"] = "binary"
        for child in value.values():
            normalize_upload_schemas(child)
    elif isinstance(value, list):
        for child in value:
            normalize_upload_schemas(child)
    return value


def enable_upload_controls(app):
    original = app.openapi
    def openapi():
        return normalize_upload_schemas(original())
    app.openapi = openapi
