# ==============================
# 🔥 IMPORTS
# ==============================
import sqlite3
import pandas as pd
import requests
import faiss
import numpy as np
import json
import os
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from prophet import Prophet

# ==============================
# 🔥 LOAD ENV (NO HARDCODE)
# ==============================
load_dotenv()  #1

GEMINI_KEY = os.getenv("GEMINI_KEY")
CUSTOMER_FILE_ID = os.getenv("CUSTOMER_FILE_ID")
LOAN_GITHUB_URL = os.getenv("LOAN_GITHUB_URL")
DB_NAME = os.getenv("DB_NAME", "data.db")
TOP_K = int(os.getenv("TOP_K", 2))
FORECAST_STEPS = int(os.getenv("FORECAST_STEPS", 3))

# ==============================
# 🔥 DATA INGESTION
# ==============================
def load_csv_from_drive(file_id, filename):  #2.1
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    res = requests.get(url)
    with open(filename, "wb") as f:
        f.write(res.content)
    return pd.read_csv(filename)

def load_csv_from_github(url):   #2.2
    return pd.read_csv(url)

def store_to_db():
    if os.path.exists(DB_NAME):
        print("DB exists ✅")
        return

    print("Running ingestion...")

    customer_df = load_csv_from_drive(CUSTOMER_FILE_ID, "customers.csv")
    loan_df = load_csv_from_github(LOAN_GITHUB_URL)

    conn = sqlite3.connect(DB_NAME)
    customer_df.to_sql("customers", conn, if_exists="replace", index=False)
    loan_df.to_sql("loans", conn, if_exists="replace", index=False)
    conn.commit()
    conn.close()

store_to_db()        #3    here calling db function to crecerte db.file

conn = sqlite3.connect(DB_NAME, check_same_thread=False)

# ==============================
# 🔥 SCHEMA + RAG
# ==============================
def get_schema():
    tables = pd.read_sql(
        "SELECT name FROM sqlite_master WHERE type='table';", conn
    )["name"].tolist()

    schema = []
    for table in tables:
        cols = pd.read_sql(f"PRAGMA table_info({table});", conn)
        schema.append(f"{table} columns: {', '.join(cols['name'].tolist())}")  
    return schema

documents = get_schema()     #     "customers columns: id, name, age",
                             #    "loans columns: loan_amount, loan_year"



model = SentenceTransformer("all-MiniLM-L6-v2")    #import model for emdedding generation
embeddings = model.encode(documents)               #   [0.12, -0.45, 0.67, ..., 0.89],   # customers
                                                     # [0.34, -0.22, 0.11, ..., 0.56]    # loans



index = faiss.IndexFlatL2(embeddings.shape[1])  #348 is the dimension of the embedding vector
index.add(np.array(embeddings))          # adding the embeddings to the index for similarity search

def retrieve_context(query):
    q = model.encode([query])   # encoding the user query into an embedding vector
    _, idx = index.search(np.array(q), TOP_K)  # searching the index for the most similar schema descriptions based on the query embedding
    return [documents[i] for i in idx[0]] # returning the most relevant schema descriptions as context for the LLM  covet aagain to string format and pass to llm

# ==============================
# 🔥 GEMINI
# ==============================
def call_llm(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={GEMINI_KEY}"

    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    res = requests.post(url, json=payload)
    data = res.json()

    if "error" in data:
        print("Gemini Error:", data["error"])
        return ""

    if "candidates" in data:
        return data["candidates"][0]["content"]["parts"][0]["text"]

    return ""

def clean_json(res):
    start = res.find("{")
    end = res.rfind("}")
    return res[start:end+1]

# ==============================
# 🔥 META GENERATION
# ==============================
def generate_meta(query, context):
    prompt = f"""
Database schema:                                                                  
{context}                                 

User Query:
{query}

Return JSON:
type, sql, chart, x_column, y_column, title
"""
    res = call_llm(prompt)
    cleaned = clean_json(res)

    try:
        meta = json.loads(cleaned)
        meta["sql"] = meta["sql"].replace(";", "")
        return meta
    except:
        return {"error": "Invalid JSON", "raw": cleaned}

# ==============================
# 🔥 SQL EXECUTION
# ==============================
def run_sql(sql):
    try:
        df = pd.read_sql(sql, conn)
        if df.empty:
            return {"error": "No data"}
        return df
    except Exception as e:
        return {"error": str(e)}

# ==============================
# 🔮 PROPHET FORECAST
# ==============================
def prophet_forecast(df, x_col, y_col):
    try:
        df_p = df[[x_col, y_col]].copy()
        df_p.columns = ["ds", "y"]

        df_p["ds"] = pd.to_datetime(df_p["ds"], errors="coerce")

        model = Prophet()
        model.fit(df_p)

        future = model.make_future_dataframe(periods=FORECAST_STEPS, freq='Y')
        forecast = model.predict(future)

        f = forecast.tail(FORECAST_STEPS)

        return (
            f["ds"].dt.year.tolist(),
            f["yhat"].round(2).tolist()
        )
    except Exception as e:
        print("Prophet Error:", e)
        return [], []

# ==============================
# 🔥 FINAL CHART
# ==============================
def to_chart(df, meta):
    if isinstance(df, dict):
        return df

    x = meta["x_column"]
    y = meta["y_column"]

    df = df.sort_values(by=x)

    labels = df[x].tolist()
    values = df[y].tolist()

    if meta.get("type") == "prediction":
        fx, fy = prophet_forecast(df, x, y)
        if fx:
            labels += fx
            values += fy
            meta["title"] += " (prediction)"

    return {
        "chart": meta["chart"].lower(),
        "labels": labels,
        "values": [round(v, 2) for v in values],
        "title": meta["title"]
    }

# ==============================
# 🔥 MAIN AGENT
# ==============================
def chart_agent(query):
    context = retrieve_context(query)

    meta = generate_meta(query, context)
    if "error" in meta:
        return meta

    df = run_sql(meta["sql"])
    return to_chart(df, meta)

# ==============================
# 🔥 TEST
# ==============================
if __name__ == "__main__":
    print(chart_agent("Show loan amount by loan_year"))
    print(chart_agent("Predict loan trends for next 3 years"))