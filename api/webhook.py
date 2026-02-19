from fastapi import FastAPI, Request

app = FastAPI()

@app.post("/webhook/fraud-check")
async def fraud_check(request: Request):
    data = await request.json()

    return {
        "status": "processing",
        "request_id": "FRD-001"
    }
