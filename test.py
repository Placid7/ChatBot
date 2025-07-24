import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
import requests
import json
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles  # ✅ Add this line
import os
import httpx

load_dotenv()

app = FastAPI()
router = APIRouter()
app.include_router(router)

# Add this block to allow CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or ["http://127.0.0.1:8000"] for more security
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GROQ_API_KEY = os.getenv("OPENROUTER_API_KEY_GROAK")
MODEL_NAME = os.getenv("GROQ_MODEL")






# === Load & Clean Excel ===
df = pd.read_excel("data/a.xlsx", skiprows=7)

# Step 2: Strip whitespace from column names
df.columns = df.columns.str.strip()

for col in df.columns:
    if df[col].dtype == 'object' or not pd.api.types.is_numeric_dtype(df[col]):
        df[col] = df[col].astype(str).str.strip()


# Step 3: Drop "Mobile No" column if it exists
if "Mobile No" in df.columns:
    df.drop(columns=["Mobile No"], inplace=True)

# Step 4: Drop fully empty columns (e.g., after unmerging)
df.dropna(axis=1, how='all', inplace=True)

# Step 5: Create new 'CLASS' column from 'Class' field like "XI - Arts / Humanities"
def extract_class(value):
    if pd.isna(value):
        return None
    return value.split('-')[0].strip()  # Extracts 'XI' from 'XI - Science with...'
def extract_class_subsection(value):
    if pd.isna(value):
        return None
    k=value.split('-')
    if len(k)>1:
        return value.split('-')[1].strip()  # Extracts 'XI' from 'XI - Science with...'
    else:
        return ""
     
def map_subsection_info(subsection):
    if pd.isna(subsection):
        return pd.Series([None, None, None])

    subsection = str(subsection).strip().lower()

    # Determine Stream
    if 'science' in subsection:
        stream = 'Science'
    elif 'arts' in subsection or 'humanities' in subsection:
        stream = 'Arts'
    elif 'commerce' in subsection:
        stream = 'Commerce'
    else:
        stream = None

    # Determine SubjectType (check 'without' first to avoid confusion)
    if 'without' in subsection:
        subject_type = 'without'
    elif 'with' in subsection:
        subject_type = 'with'
    else:
        subject_type = None

    # Determine Final Subjects
    if 'computer sc./i.p.' in subsection or 'computer science/ip' in subsection:
        optional_subject = 'computer science'
    elif 'computer science' in subsection:
        optional_subject = 'computer science'
    elif 'i.p. electives' in subsection or 'i.p.' in subsection:
        optional_subject = 'ip'
    else:
        optional_subject = None

    return pd.Series([subject_type, optional_subject, stream])




if 'Class' in df.columns:
    df['subsection'] = df['Class'].apply(extract_class_subsection)

if 'Class' in df.columns:
    df['Class'] = df['Class'].apply(extract_class)

# Apply to your DataFrame
df[['SubjectType', 'OptionalSubjects', 'Stream']] = df['subsection'].apply(map_subsection_info)


df.columns = [col.strip().lower().replace(" ", "_") for col in df.columns]
 
# Drop the original Subsection column
df.drop(columns=['subsection'], inplace=True)
# Step 6: Save cleaned DataFrame to temp.xlsx in the same folder
df.to_excel("data/temp.xlsx", index=False)
# Convert to JSON

# === Clean Excel and Save Grouped JSON ===
def cleanExcel(df: pd.DataFrame, output_path: str, teacher_path: str):
    # Load student data
    # Load class teacher data
    teachers = pd.read_excel(teacher_path)

    # Normalize columns
    #df.columns = [col.strip().lower().replace(" ", "_") for col in df.columns]
    teachers.columns = [col.strip().lower().replace(" ", "_") for col in teachers.columns]

    # Rename teacher columns for clarity
    teachers = teachers.rename(columns={
        "class_teacher": "class_teacher",
        "co_class_teacher": "co_class_teacher"  # Convert to safe column name
    })

    # Group and summarize student data
    grouped = df.groupby(['class', 'section']).agg(
    total=('student_name', 'count'),
    rte=('rte', lambda x: (x.astype(str).str.strip().str.lower() == 'yes').sum()),
    bpl=('bpl', lambda x: (x.astype(str).str.strip().str.lower() == 'yes').sum()),
    sgc=('single_girl_child', lambda x: (x.astype(str).str.strip().str.lower() == 'yes').sum()),
    general=('category', lambda x: (x.astype(str).str.strip().str.lower() == 'general').sum()),
    obc=('category', lambda x: (x.astype(str).str.strip().str.lower() == 'obc').sum()),
    sc=('category', lambda x: (x.astype(str).str.strip().str.lower() == 'sc').sum()),
    st=('category', lambda x: (x.astype(str).str.strip().str.lower() == 'st').sum()),
    girl=('gender', lambda x: (x.astype(str).str.strip().str.lower() == 'girl').sum()),
    boy=('gender', lambda x: (x.astype(str).str.strip().str.lower() == 'boy').sum()),
    with_computer_science=(
        'optionalsubjects',
        lambda x: ((df.loc[x.index, 'subjecttype'] == 'with') & (x == 'computer science')).sum()
    ),
    with_ip=(
        'optionalsubjects',
        lambda x: ((df.loc[x.index, 'subjecttype'] == 'with') & (x == 'ip')).sum()
    ),

    bpl_vvn_fee_exemption=('vvn_fee_exemption', lambda x: (x.astype(str).str.strip().str.lower() == 'bpl').sum()),
    disabled_vvn_fee_exemption=('vvn_fee_exemption', lambda x: (x.astype(str).str.strip().str.lower() == 'disabled').sum()),
    No_vvn_feeexemption=('vvn_fee_exemption', lambda x: (x.astype(str).str.strip().str.lower() == 'no exemption').sum()),
    sgc_vvn_fee_exemption=('vvn_fee_exemption', lambda x: (x.astype(str).str.strip().str.lower() == 'single girl child').sum()),
    

    bpl_tuition_fee_exemption=('tuition_fee_exemption', lambda x: (x.astype(str).str.strip().str.lower() == 'bpl').sum()),
    disabled_tuition_fee_exemption=('tuition_fee_exemption', lambda x: (x.astype(str).str.strip().str.lower() == 'disabled').sum()),
    No_tuition_feeexemption=('tuition_fee_exemption', lambda x: (x.astype(str).str.strip().str.lower() == 'no exemption').sum()),
    sgc_tuition_fee_exemption=('tuition_fee_exemption', lambda x: (x.astype(str).str.strip().str.lower() == 'single girl child').sum()),

    bpl_comp_fund_exemption=('comp_fund_exemption', lambda x: (x.astype(str).str.strip().str.lower() == 'bpl').sum()),
    disabled_comp_fund_exemption=('comp_fund_exemption', lambda x: (x.astype(str).str.strip().str.lower() == 'disabled').sum()),
    No_comp_fund_exemption=('comp_fund_exemption', lambda x: (x.astype(str).str.strip().str.lower() == 'no exemption').sum()),
    sgc_comp_fund_exemption=('comp_fund_exemption', lambda x: (x.astype(str).str.strip().str.lower() == 'single girl child').sum()),


    bpl_comp_sci_fee_exemption=('comp_sci_fee_exemption', lambda x: (x.astype(str).str.strip().str.lower() == 'bpl').sum()),
    disabled_comp_sci_fee_exemption=('comp_sci_fee_exemption', lambda x: (x.astype(str).str.strip().str.lower() == 'disabled').sum()),
    No_comp_sci_fee_exemption=('comp_sci_fee_exemption', lambda x: (x.astype(str).str.strip().str.lower() == 'no exemption').sum()),
    sgc_comp_sci_fee_exemption=('comp_sci_fee_exemption', lambda x: (x.astype(str).str.strip().str.lower() == 'single girl child').sum()),  



    kvs_ward=('kvs_ward', lambda x: (x.astype(str).str.strip().str.lower() == 'yes').sum()),
    cat1=('admn_category', lambda x: (x.astype(str).str.strip() == 'I').sum()),
    cat2=('admn_category', lambda x: (x.astype(str).str.strip() == 'II').sum()),
    cat3=('admn_category', lambda x: (x.astype(str).str.strip() == 'III').sum()),
    cat4=('admn_category', lambda x: (x.astype(str).str.strip() == 'IV').sum()),
    cat5=('admn_category', lambda x: (x.astype(str).str.strip() == 'V').sum()),
    cat6=('admn_category', lambda x: (x.astype(str).str.strip() == 'VI').sum()),
    minority=('minority', lambda x: (x.astype(str).str.strip().str.lower() == 'yes').sum()),
    allstudentsname=('student_name', lambda x: '-'.join(x.dropna().astype(str)))
).reset_index()

    # Merge with class teacher data
    merged = pd.merge(grouped, teachers, on=['class', 'section'], how='left')
    json_data = merged.to_json(orient="records", force_ascii=False)

    # Save to a file
    with open("data/output1.json", "w", encoding="utf-8") as f2:
        f2.write(json_data)
    # Save final result
    merged.to_excel(output_path, index=False)    


cleanExcel(df, "data/output.xlsx", "data/classteacher.xlsx")



#############################################################################

@app.post("/chat")
async def chat(request: Request):
    body = await request.json()
    question = body.get("question", "")
    model = body.get("model", "meta-llama/llama-4-scout-17b-16e-instruct")

    # Load context from file
    try:
        with open("data/output1.json", "r", encoding="utf-8") as f:
            json_context = json.load(f)
    except Exception as e:
        return JSONResponse(content={"error": f"Failed to load context: {str(e)}"}, status_code=500)

    # Inject context into the system prompt
    messages = [
        {
            "role": "system",
            "content": f"""You are a helpful assistant for KV ONGC DEHRADUN.
Use the following knowledge base context to answer questions:
{json.dumps(json_context, indent=2)}"""
        },
        {
            "role": "user",
            "content": question
        }
    ]

    # Call Groq API
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 1024
                }
            )
            response.raise_for_status()
            data = response.json()
            return JSONResponse(content={"answer": data["choices"][0]["message"]["content"]})
        except httpx.HTTPStatusError as e:
            return JSONResponse(content={"error": str(e)}, status_code=e.response.status_code)
        except httpx.ReadTimeout:
            return JSONResponse(content={"error": "Groq API timed out"}, status_code=504)



# Serve static files from the "static" folder at root level ("/")
app.mount("/", StaticFiles(directory="static", html=True), name="static")
