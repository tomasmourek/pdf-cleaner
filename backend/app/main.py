from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from datetime import datetime

from app.storage import upload_file

app = FastAPI(title="PDF Cleaner API")


@app.get("/")
def root():
    return {"status": "PDF Cleaner backend running"}


@app.post("/convert")
async def convert(file: UploadFile = File(...)):
    try:
        # načtení souboru z requestu
        data = await file.read()

        if not data:
            raise HTTPException(status_code=400, detail="Soubor je prázdný.")

        # bezpečný název souboru (timestamp + původní jméno)
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_name = (file.filename or "upload.pdf").replace(" ", "_")
        object_name = f"{ts}__{safe_name}"

        # uložení do MinIO
        upload_file(
            file_bytes=data,
            filename=object_name,
            content_type=file.content_type or "application/pdf",
        )

        # odpověď API
        return JSONResponse(
            {
                "stored": True,
                "bucket": "pdf-cleaner",
                "object_name": object_name,
                "size_bytes": len(data),
                "content_type": file.content_type,
                "message": "Soubor byl uložen do MinIO.",
            }
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Chyba při ukládání do MinIO: {e}"
        )
