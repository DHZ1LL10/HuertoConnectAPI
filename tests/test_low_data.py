import hashlib
import httpx
from fastapi import FastAPI, File, UploadFile
from shared.low_data import install_low_data


async def test_compression_preserves_uploaded_image_and_response():
    app = FastAPI()
    install_low_data(app)
    @app.post("/foto")
    async def upload(imagen: UploadFile = File(...)):
        data = await imagen.read()
        return {"hash": hashlib.sha256(data).hexdigest(), "bytes": len(data), "historial": ["diagnostico"] * 500}
    original = b"original-image-data" * 1000
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        files = {"imagen": ("original.png", original, "image/png")}
        compressed = await client.post("/foto", files=files, headers={"Accept-Encoding": "gzip"})
        plain = await client.post("/foto", files=files, headers={"Accept-Encoding": "identity"})
        assert compressed.json() == plain.json()
        assert compressed.json()["hash"] == hashlib.sha256(original).hexdigest()
        assert compressed.json()["bytes"] == len(original)
        assert compressed.headers["content-encoding"] == "gzip"
        assert "accept-encoding" in compressed.headers["vary"].lower()
        assert int(compressed.headers["content-length"]) < len(plain.content)
        docs = await client.get("/docs")
        assert "createImageBitmap" not in docs.text and "toBlob" not in docs.text
