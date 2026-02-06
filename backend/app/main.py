from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse

from app.storage import upload_file

app = FastAPI(title="PDF Cleaner API")


@app.get("/")
def root():
    return {"status": "PDF Cleaner backend running"}


@app.post("/convert")
async def convert(file: UploadFile = File(...)):
    contents = await file.read()

    # upload do MinIO
    upload_file(contents, file.filename)

    return JSONResponse(
        {
            "filename": file.filename,
            "content_type": file.content_type,
            "message": "Soubor byl uložen do MinIO",
        }
    )
