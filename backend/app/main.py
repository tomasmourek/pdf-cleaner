from fastapi import FastAPI

app = FastAPI(title="PDF Cleaner API")

@app.get("/")
def root():
    return {"status": "PDF Cleaner backend running"}
