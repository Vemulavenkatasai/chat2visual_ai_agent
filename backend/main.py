from fastapi import FastAPI
from pydantic import BaseModel
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from fastapi.middleware.cors import CORSMiddleware
from agent2 import chart_agent


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class Query(BaseModel):
    query: str


@app.post("/ask")
def ask(q: Query):
    return chart_agent(q.query)
