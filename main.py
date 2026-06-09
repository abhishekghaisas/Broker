from dotenv import load_dotenv
load_dotenv()

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from broker.router import router as broker_router

#Initialize non-blocking Python backend
app = FastAPI(title="Broker")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

#Mount modularized broker router
app.include_router(broker_router)

if __name__ == "__main__":
    #Run broker locally
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)