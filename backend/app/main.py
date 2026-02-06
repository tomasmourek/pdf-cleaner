from fastapi import FastAPI

app = FastAPI(title="PDF Cleaner API")

@app.get("/")
def root():
    return {"status": "PDF Cleaner backend running"}
    
from fastapi import UploadFile, File
from fastapi.responses import JSONResponse

@app.post("/convert")
async def convert(file: UploadFile = File(...)):
    return JSONResponse(
        {
            "filename": file.filename,
            "content_type": file.content_type,
            "message": "Upload OK (zatím jen test endpoint, bez konverze).",
        }
    )
    
