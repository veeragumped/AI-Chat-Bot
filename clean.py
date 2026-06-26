import json
import re
import os

# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------
INPUT_FILE = "thai_movies_with_reviews.json"
OUTPUT_CLEANED = "thai_movies_final_cleaned.json"

def deep_clean_text(text):
    if not text: return ""
    # 1. ลบ escaped quotes (\") ให้กลายเป็นเครื่องหมาย ' แทน
    text = text.replace('\\"', "'").replace('"', "'")
    # 2. ลบสัญลักษณ์ตกแต่ง (=======, -------)
    text = re.sub(r'[-=_*]{2,}', '', text)
    # 3. เปลี่ยน \n เป็นช่องว่าง
    text = text.replace('\n', ' ')
    # 4. ลบช่องว่างซ้ำซ้อน
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def process_and_filter():
    if not os.path.exists(INPUT_FILE):
        print(f"❌ ไม่พบไฟล์ {INPUT_FILE}!")
        return

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        movies = json.load(f)

    final_movies = []
    
    print(f"🧹 เริ่มการทำความสะอาด (แบบมี Note) สำหรับหนัง {len(movies)} เรื่อง...\n")

    for m in movies:
        imdb_rating = m.get('imdb_rating', 'N/A')
        synopsis = m.get('synopsis', 'No plot available.')
        
        # --- [จุดที่แก้]: ถ้าไม่มีรีวิว ให้ใส่ Note ไว้หน้า Synopsis ---
        if not m.get('reviews') or len(m['reviews']) == 0:
            # เราใส่แค่เนื้อหา เดี๋ยว Loop ข้างล่างจะเติม Rating ให้เองอัตโนมัติ
            m['reviews'] = [f"(Note: No user reviews yet) Synopsis: {synopsis}"]

        cleaned_reviews = []
        for rev in m['reviews']:
            t = deep_clean_text(rev)
            if len(t) < 20: continue
            
            # เช็กว่ามีเรตติ้งเดิมติดมาในข้อความไหม
            rating_match = re.search(r'(\d*\.?\d+/10)', t)
            
            if rating_match:
                found_val = rating_match.group(1)
                # ล้างฟอร์แมตซ้ำซ้อน
                pure_text = t.replace(found_val, "").replace("Rating:", "").replace("|", "").strip()
                final_format = f"Rating: {found_val} | {pure_text}"
            else:
                # ถ้าไม่มีเรตติ้ง (เช่น ในกรณีที่เป็น Fallback Synopsis) ให้ใช้ imdb_rating ของหนัง
                final_format = f"Rating: {imdb_rating}/10 | {t}"
            
            cleaned_reviews.append(final_format)
        
        m['reviews'] = cleaned_reviews
        final_movies.append(m)

    with open(OUTPUT_CLEANED, "w", encoding="utf-8") as f:
        json.dump(final_movies, f, ensure_ascii=False, indent=4)

    print(f"✅ เรียบร้อย! ข้อมูลมี Note แยกชัดเจนในไฟล์: {OUTPUT_CLEANED}")

if __name__ == "__main__":
    process_and_filter()