from concurrent.futures import process
import os
import json
import faiss
import numpy as np
import gradio as gr
from google import genai
from sentence_transformers import SentenceTransformer
from google.genai import types

# ==========================================
# ส่วนเตรียมความพร้อม
# ==========================================

# 1. ตั้งค่า Gemini API ด้วย Client ตัวใหม่
gemini_client = genai.Client(api_key= process.env.genaikey)

# 2. โหลด Embedding Model 
embedding_model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')

# 3. โหลด Vector Database (FAISS) และ Metadata
index = faiss.read_index("movie_vectors.index")
with open("metadata.json", "r", encoding="utf-8") as f:
    chunk_records = json.load(f)

# ==========================================
# ONLINE PIPELINE: 12-Step RAG Chatbot
# ==========================================

def generate_rag_response(message, history):
    # --- STEP 7: Receive Query, Contextualize & Translate ---
    query_text = message.strip()
    if not query_text:
        return "กรุณาพิมพ์คำถามก่อนค่ะ"
    
    # จัดเตรียมประวัติการสนทนา (ดักจับ Gradio ทั้งเวอร์ชันเก่าและใหม่)
    history_context = "ไม่มีประวัติการสนทนา (นี่คือคำถามแรก)"
    if len(history) > 0:
        try:
            if isinstance(history[-1], dict) or hasattr(history[-1], 'content'):
                # สำหรับ Gradio เวอร์ชันใหม่ล่าสุด (เก็บแบบแยก Role)
                if len(history) >= 2:
                    # ดึงข้อความจาก dictionary หรือ object โดยตรง
                    last_q = history[-2]['content'] if isinstance(history[-2], dict) else history[-2].content
                    last_a = history[-1]['content'] if isinstance(history[-1], dict) else history[-1].content
                    history_context = f"ผู้ใช้: {last_q}\nบอท: {last_a}"
            else:
                # สำหรับ Gradio เวอร์ชันเก่า (เก็บแบบ List คู่)
                last_q = history[-1][0]
                last_a = history[-1][1]
                history_context = f"ผู้ใช้: {last_q}\nบอท: {last_a}"
        except Exception as e:
            print(f"History parsing error: {e}") # ป้องกันแอปพังถ้าอ่านประวัติไม่ได้
        
    rewrite_prompt = f"""
    คุณคือผู้ช่วยเตรียมคำค้นหา (Search Query) สำหรับระบบฐานข้อมูลภาพยนตร์ภาษาอังกฤษ

    ประวัติการสนทนาล่าสุด:
    {history_context}
    
    คำถามใหม่ของผู้ใช้: {query_text}

    งานของคุณ:
    1. ทำความเข้าใจความต้องการของผู้ใช้จากคำถามใหม่ (โดยดูประวัติการสนทนาประกอบหากเป็นการถามต่อเนื่อง)
    
    """
    
    try:
        # ให้ Gemini ทั้งวิเคราะห์ความต่อเนื่อง และแปลภาษาในรอบเดียว
        rewrite_response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=rewrite_prompt
        )
        search_query = rewrite_response.text.strip()
        print(f"Original Query: {query_text} | English Search Query: {search_query}") # เช็กการทำงานหลังบ้านได้
    except Exception as e:
        search_query = "Thai movie" # กันเหนียวกรณี API ขัดข้อง

    # --- STEP 8: Embed Query ---
    # นำคำถามภาษาอังกฤษที่สมบูรณ์แล้วไปแปลงเป็น Vector เพื่อให้ FAISS ค้นหา
    query_embedding = embedding_model.encode([search_query], convert_to_numpy=True)
    
    # --- STEP 9: Retrieve Chunks ---
    top_k = 10
    distances, indices = index.search(query_embedding.astype("float32"), top_k)
    retrieved_chunks = [chunk_records[idx] for idx in indices[0]]
    
    # --- STEP 10: Assemble Context ---
    context = "\n\n".join([
        f"[Source: {chunk['filename']}]\n{chunk['text']}" 
        for chunk in retrieved_chunks
    ])
    sources_used = list(set([chunk['filename'] for chunk in retrieved_chunks]))

    # --- STEP 11: Build Master Prompt ---
    prompt = f"""
    คุณคือ "น้องฟิล์ม" ผู้ช่วย AI สุดเป็นกันเอง ที่เชี่ยวชาญด้านภาพยนตร์ไทยเป็นพิเศษ 
    คุณกำลังคุยกับผู้ใช้งานที่แวะมาขอคำแนะนำเรื่องหนัง

    ประวัติการพูดคุยที่ผ่านมาของเรา:
    <history>
    {history_context}
    </history>

    นี่คือข้อมูลรีวิวภาพยนตร์ที่ค้นหามาได้ล่าสุด:
    <context>
    {context}
    </context>

    คำถาม/ข้อความจากผู้ใช้: "{query_text}"

    กฎในการตอบคำถามของคุณ (สำคัญมาก):
    1. ทักทายให้เป็นธรรมชาติ: หากผู้ใช้ทักทายทั่วไป ให้ทักทายกลับอย่างเป็นมิตร (แต่ถ้าใน <history> มีการทักทายกันไปแล้ว "ห้ามสวัสดีซ้ำ" ให้เข้าเรื่องทันที)
    2. สรรพนาม: ห้ามเรียกผู้ใช้ว่า "ลูกค้า" เด็ดขาด ให้ใช้คำว่า "คุณ" หรือคุยแบบเพื่อนที่กำลังป้ายยาหนังให้เพื่อนฟัง
    3. รูปแบบการแนะนำหนัง (สำคัญมาก): 
       - หากผู้ใช้ถามให้แนะนำหนังแนวต่างๆ แบบกว้างๆ (เช่น แนะนำหนังผีหน่อย, มีหนังตลกไหม) ให้คุณคัดเลือกหนังจาก <context> มา "จัดเป็นลิสต์ข้อๆ (List) อย่างน้อย 3-5 เรื่องเสมอ" เพื่อให้ผู้ใช้มีตัวเลือก
       - แต่ถ้าผู้ใช้ถามเจาะจงเฉพาะเรื่อง (เช่น ขอรีวิวเรื่อง Shutter เพิ่มหน่อย) ให้ตอบแค่เรื่องนั้นเรื่องเดียวแบบเจาะลึก
    4. ห้ามแนะนำซ้ำ: หากผู้ใช้ถามว่า "มีเรื่องอื่นอีกไหม" ให้ดูใน <history> ว่าเคยแนะนำเรื่องอะไรไปแล้ว และให้เลือกจาก <context> "เฉพาะเรื่องใหม่ที่ไม่ซ้ำเดิม" มาแนะนำ (จัดเป็นลิสต์เช่นกัน)
    5. กรณีหมดสต็อก: หากใน <context> ไม่มีหนังแนวที่ถาม หรือซ้ำกับที่เคยแนะนำไปหมดแล้ว ห้ามตอบว่า 'ไม่พบข้อมูล' ทื่อๆ แต่ให้ตอบอย่างสุภาพว่า "ตอนนี้น้องฟิล์มหมดสต็อกสำหรับแนวนี้แล้วค่ะ" และเสนอแนวอื่นที่ใกล้เคียงแทน
    6. การจัดหน้าตา: สรุปจุดเด่นของหนังให้น่าสนใจ ใช้ **ตัวหนา** เน้นชื่อหนังเสมอ และใส่อีโมจิให้ดูมีชีวิตชีวา ห้ามแต่งเนื้อเรื่องหรือชื่อหนังขึ้นมาเองเด็ดขาด ถ้าไม่รู้ให้ยอมรับตรงๆ อย่างน่ารัก


    จงตอบเป็นภาษาไทยด้วยน้ำเสียงที่เป็นธรรมชาติ เหมือนเพื่อนแนะนำหนังให้เพื่อนฟัง:
    """
    
    # ใช้คำสั่งของไลบรารีตัวใหม่ในการเรียกใช้โมเดล
    # --- STEP 12: Generate Answer + Citation (Smart & Safe) ---
    try:
        # 1. เรียกใช้งาน Gemini พร้อมพยายามปลดล็อกเซ็นเซอร์
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                safety_settings=[
                    types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
                    types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
                    types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
                    types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE")
                ]
            )
        )
        
        # 2. ดึงข้อความคำตอบ
        answer_text = response.text
        
        # 3. 🛡️ DEFENSIVE PROGRAMMING: ดักจับกรณี API ดรอปข้อความทิ้ง (ส่งค่าว่างมา)
        # ถ้า answer_text เป็น None หรือเป็นสติงก์ว่าง โค้ดจะหยุดทำงานตรงนี้และตอบผู้ใช้ทันที
        if not answer_text:
            return "⚠️ น้องฟิล์มขออภัยค่ะ! ดูเหมือนรีวิวหนังแนวนี้บางเรื่องจะมีเนื้อหาที่ระบบเซ็นเซอร์ขั้นสูงสุดของ Google บล็อกเอาไว้ (เช่น รีวิวที่มีคำบรรยายโหดร้ายหรือรุนแรงเกินไป) ลองถามหาแนวอื่นแทนนะคะ 😅"
        
        # 4. แก้ปัญหา \n โผล่เป็นตัวหนังสือ ให้กลายเป็นการขึ้นบรรทัดใหม่จริงๆ
        if answer_text:
            answer_text = answer_text.replace('\\n', '\n')

        # 5. Logic ตรวจสอบการอ้างอิงแบบฉลาด (Smart Citation)
        actual_sources_used = [source for source in sources_used if source in answer_text]
        
        if "หมดสต็อกสำหรับแนวนี้แล้วค่ะ" in answer_text:
            return answer_text
            
        elif actual_sources_used:
            citation_text = "\n\n**🎬 อ้างอิงจากรีวิวเรื่อง:** " + ", ".join(actual_sources_used)
            return answer_text + citation_text
        else:
            return answer_text

    except Exception as e:
        # 6. ดักจับ Error กรณีคนแย่งกันใช้จนโควตาฟรีเต็ม
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            return "⏳ ตอนนี้มีคนพิมพ์ถามเยอะเกินไป (โควตา API เต็มชั่วคราว) รบกวนรอประมาณ 1 นาทีแล้วลองทักมาใหม่นะคะ น้องฟิล์มรอตอบอยู่ค่ะ! 🎬"
        else:
            return f"❌ ขออภัยค่ะ ระบบหลังบ้านขัดข้องชั่วคราว: {e}"

# ==========================================
# ส่วน UI (Gradio)
# ==========================================
demo = gr.ChatInterface(
    fn=generate_rag_response,
    title="🎬 AI แนะนำหนังไทยจากรีวิว IMDb",
    description="ระบบแชทบอท RAG สำหรับแนะนำภาพยนตร์ไทย พัฒนาโดยใช้ FAISS และ Gemini API",
    examples=["อยากดูหนังผีหักมุม", "แนะนำหนังตลกคลายเครียดหน่อย", "ขอหนังรักวัยรุ่นซึ้งๆ"],
    cache_examples=False,
    fill_height=True
)

if __name__ == "__main__":
    demo.launch()