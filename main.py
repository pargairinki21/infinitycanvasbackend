import os
import difflib
import librosa
import subprocess
import soundfile as sf
import tempfile
import re
import threading
import requests
from fastapi import FastAPI, UploadFile, File
from openai import OpenAI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, UploadFile, File, Form
from pydantic import BaseModel
from fastapi.responses import FileResponse   # 

# === CONFIG ===
FORMS_DIR = "downloaded_forms"
PRINTER_NAME = "HP_LaserJet_Professional_P1108"
EXTENSION = ".pdf"
API_KEY = os.getenv('OPENAI_API_KEY', 'your-openai-api-key-here')
client = OpenAI(api_key=API_KEY)
PERIPHERAL_API = "http://127.0.0.1:8002"

# === FastAPI app ===
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === New Chat schema ===
class ChatRequest(BaseModel):
    message: str

# === SYSTEM PROMPT ===
system_prompt = """
You are a banking + peripherals assistant. You handle:
  - Banking form requests
  - Peripheral control requests (volume, brightness, camera)
No links or external resources ever.
Your reply must always be in hindi using english text.

Rules for Banking Forms:
- If a form is requested → reply with:
    MESSAGE: <reply in hindi-english>
    PRINT FLAG: YES
    CHECKLIST: list of required docs
- If not a form → reply with:
    MESSAGE: <short polite reply>
    PRINT FLAG: NO
    CHECKLIST: <None>

Rules for Peripherals:
- Agar user ka message me "volume", "brightness", "camera" ya "mute/unmute" ka mention ho:
    MESSAGE: <acknowledge in hindi-english>
    PRINT FLAG: NO
    CHECKLIST: <None>
    PERIPHERAL: exact endpoint (e.g., /volume/up, /volume/down, /volume/mute, /brightness/up, /take_picture)
- Agar input me form nahi hai aur peripheral bhi nahi → PERIPHERAL: <None>

Rules for Off-topic:
- Reply: "so sorry, I can assist only with form-related or peripheral queries."

Important:
- Always respond in this exact format:
  MESSAGE: <reply>
  PRINT FLAG: YES/NO
  CHECKLIST: <list or <None>>
  PERIPHERAL: <endpoint or <None>>
"""
chat_history = [{"role": "system", "content": system_prompt}]

# === Helpers ===
def transcribe_audio(filename):
    y, sr = librosa.load(filename, sr=16000, mono=True)
    yt, _ = librosa.effects.trim(y)
    optimized = filename.replace('.wav', '_opt.wav')
    sf.write(optimized, yt, 16000)
    with open(optimized, 'rb') as f:
        transcript = client.audio.transcriptions.create(
            model="whisper-1", file=f, language="en"
        )
    return transcript.text

def ask_gpt(user_text):
    chat_history.append({"role": "user", "content": user_text})
    resp = client.chat.completions.create(model="gpt-4", messages=chat_history)
    reply = resp.choices[0].message.content.strip()
    chat_history.append({"role": "assistant", "content": reply})
    return reply

def parse_response(text):
    msg, flag, checklist, peripheral = "", "", "", ""
    lines = text.splitlines()
    collecting = False
    items = []
    for line in lines:
        low = line.lower()
        if "message:" in low:
            msg = line.partition(":")[2].strip()
        elif "print flag:" in low:
            flag = line.partition(":")[2].strip().upper()
        elif "checklist:" in low:
            start = line.partition(":")[2].strip()
            if start and start.lower() != "<none>":
                items.append(start)
            collecting = True
        elif "peripheral:" in low:
            peripheral = line.partition(":")[2].strip()
        elif collecting:
            if not line.strip(): continue
            if ":" in line and (line.lower().startswith("message") or line.lower().startswith("print flag") or line.lower().startswith("peripheral")):
                collecting = False
            else:
                items.append(line.strip())
    checklist = "\n".join(items) if items else "<None>"
    return msg, flag, checklist, peripheral

def get_form_list():
    return [f[:-4] for f in os.listdir(FORMS_DIR) if f.lower().endswith(EXTENSION)]

def match_form_name(user_input, available_forms):
    import itertools
    def tok(t): return re.findall(r'[a-z0-9]+', t.lower())
    in_toks = tok(user_input)
    scores = []
    for form in available_forms:
        f_toks = tok(form)
        s = 0
        for t in in_toks:
            if t in f_toks:
                s += 3
            else:
                for ft in f_toks:
                    r = difflib.SequenceMatcher(None, t, ft).ratio()
                    if r > 0.85:
                        s += 2; break
                    elif r > 0.7:
                        s += 1
        for phrase in itertools.combinations(in_toks, 2):
            if " ".join(phrase) in form.lower():
                s += 2
        if any(t in form.replace(" ", "").lower() for t in in_toks):
            s += 2
        scores.append((form, s))
    best, score = max(scores, key=lambda x: x[1]) if scores else (None, 0)
    return best if score >= 4 else None

# === MODIFIED ===
def get_form_path(filename):
    url = f"http://127.0.0.1:8001/pdf/{filename}"
    print(f"✅ PDF available at: {url}")
    return url

def call_peripheral_api(endpoint: str):
    try:
        if endpoint and endpoint != "<None>":
            print(f"🔗 Calling peripheral API: {PERIPHERAL_API}{endpoint}")
            response = requests.post(f"{PERIPHERAL_API}{endpoint}", timeout=5)
            print(f"✅ Peripheral API response: {response.status_code}")
            return response.json()
    except requests.exceptions.ConnectionError as e:
        print(f"❌ Connection error to port 8002: {e}")
        return {"error": f"Cannot connect to peripheral server: {e}"}
    except Exception as e:
        print(f"❌ General error: {e}")
        return {"error": str(e)}
    return None

# === SHARED HANDLER FUNCTION ===
def handle_user_text(user_text):
    gpt_output = ask_gpt(user_text)
    print("🟢 GPT OUTPUT:", gpt_output)   # 👈 add this
    message, print_flag, checklist, peripheral = parse_response(gpt_output)
    print("🔎 Parsed Peripheral:", peripheral)  # 👈 add this


    peripheral_result = None
    if peripheral and peripheral != "<None>":
        peripheral_result = call_peripheral_api(peripheral)

    pdf_path = None
    if print_flag == "YES":
        if checklist and checklist != "<None>":
            message = f"Yeh hai aapka checklist:\n{checklist}"

        forms = get_form_list()
        selected = match_form_name(user_text, forms)
        if selected:
            path = os.path.join(FORMS_DIR, selected + EXTENSION)
            if os.path.exists(path):
                pdf_path = get_form_path(selected + EXTENSION)
                message += f"\n📄 Aapka form ready hai: {pdf_path}"
            else:
                message += f"\n❌ File '{path}' not found."
        else:
            message += "\n❌ Could not confidently match form. Try again."

    return {
        "user_text": user_text,
        "gpt_output": gpt_output,
        "message": message,
        "print_flag": print_flag,
        "checklist": checklist,
        "peripheral": peripheral,
        "peripheral_result": peripheral_result,
        "pdf_path": pdf_path
    }

# === API ENDPOINTS ===
@app.post("/process_audio")
async def process_audio(file: UploadFile = File(...)):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        audio_path = tmp.name
        content = await file.read()
        tmp.write(content)

    user_text = transcribe_audio(audio_path).strip()
    return handle_user_text(user_text)

@app.post("/chat")
async def chat(req: ChatRequest):
    user_text = req.message.strip()
    return handle_user_text(user_text)

# === NEW PDF ENDPOINT ===
# === NEW PDF ENDPOINT ===
@app.get("/pdf/{filename}")
async def get_pdf(filename: str):
    filepath = os.path.join(FORMS_DIR, filename)
    if not os.path.exists(filepath):
        return {"error": "File not found"}
    
    # Add headers to allow iframe embedding
    from fastapi import Response
    
    with open(filepath, "rb") as f:
        pdf_content = f.read()
    
    headers = {
        "X-Frame-Options": "ALLOWALL",  # Allow iframe embedding
        "Content-Security-Policy": "frame-ancestors *",  # Allow from any origin
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "*",
        "Cache-Control": "no-cache",
        "Content-Disposition": "inline"  # Display inline, not download
    }
    
    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers=headers
    )