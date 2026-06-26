import json
import time
import os
from playwright.sync_api import sync_playwright
import re

# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------
INPUT_FILE = "thai_movies_data.json"
OUTPUT_ENRICHED = "thai_movies_with_reviews.json"
CHECKPOINT_EVERY = 10  # เซฟไฟล์ทุกๆ 10 เรื่อง
MAX_LOAD_MORE = 10      # กด 'Load More' กี่ครั้งต่อเรื่อง (1 ครั้ง ~ 25 รีวิว)
WAIT_TIME = 2000

# ---------------------------------------------------------
# AUTO SCRAPER FUNCTION
# ---------------------------------------------------------
def scrape_reviews_ultimate(movies):
    enriched_data = []
    
    # โหลดข้อมูลเดิมที่เคยเซฟไว้ (ถ้ามี) เพื่อรันต่อจากจุดเดิมได้
    if os.path.exists(OUTPUT_ENRICHED):
        with open(OUTPUT_ENRICHED, "r", encoding="utf-8") as f:
            enriched_data = json.load(f)
        print(f"♻️  พบไฟล์เดิม! จะเริ่มดึงต่อจากเรื่องที่ {len(enriched_data) + 1}")

    # ดึงรายชื่อ ID ที่ทำเสร็จแล้วเพื่อป้องกันการดึงซ้ำ
    completed_ids = {m.get('imdb_id') for m in enriched_data if m.get('imdb_id')}

    print(f"🚀 เริ่มกระบวนการอัตโนมัติสำหรับหนังที่เหลือ...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False) # ดูหน้าจอด้วยเพื่อความมั่นใจ
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            for index, m in enumerate(movies):
                if m is None or not isinstance(m, dict): continue
                
                m_id = m.get('imdb_id')
                if not m_id or m_id in completed_ids or m_id == "N/A":
                    continue

                url = f"https://www.imdb.com/title/{m_id}/reviews"
                print(f"\n[{len(enriched_data) + 1}/{len(movies)}] 🎬 กำลังจัดการ: {m['title']}")

                try:
                    # 1. เข้าหน้าเว็บ
                    page.goto(url, timeout=60000, wait_until="load")
                    page.wait_for_timeout(3000)

                    # --- 🛠️ 1. โหมด "โหลดจนกว่าจะพอ" (LOAD MORE) ---
                    # ผมตั้งไว้ 15 รอบ (รอบละ ~25 เรื่อง) เพื่อให้ได้รีวิวระดับ 300+
                    for i in range(15): 
                        current_reviews = page.locator(".ipc-html-content-inner-div, .text.show-more__control")
                        count_before = current_reviews.count()
                        
                        # ไถหน้าจอลงไปที่ปุ่ม
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        load_more = page.locator("button:has-text('more')").last
                        
                        if load_more.is_visible():
                            load_more.click()
                            print(f"   ⏳ กำลังโหลดชุดที่ {i+1} (หน้าจอมี {count_before} รีวิว)...", end="\r")
                            
                            # สำคัญ: รอจนกว่าจำนวนรีวิวจะเพิ่มขึ้น (ให้เวลาโหลดสูงสุด 6 วินาที)
                            success = False
                            for _ in range(12): 
                                page.wait_for_timeout(500)
                                if current_reviews.count() > count_before:
                                    success = True
                                    break
                            if not success: break # ถ้าผ่านไป 6 วิแล้วไม่เพิ่ม แสดงว่าเน็ตค้างหรือหมดจริง
                        else:
                            break

                    # --- 🔓 2. บังคับกาง See all และ Spoilers (ไม้ตายเดิมที่เริ่มเวิร์ก) ---
                    print(f"\n   🔓 กำลังขยายรีวิวทั้งหมด ({current_reviews.count()} อัน)...")
                    page.evaluate("""() => {
                        const buttons = document.querySelectorAll('.ipc-overflowText-overlay, .ipc-overflowText-expand-item, .ipl-expander__control');
                        buttons.forEach(el => el.click());
                        const hidden = document.querySelectorAll('.ipc-overflowText--truncated, .ipc-html-content--is-truncated');
                        hidden.forEach(el => { el.style.display = 'block'; el.style.maxHeight = 'none'; });
                    }""")
                    page.wait_for_timeout(2000)

                    # --- 📦 3. สกัดข้อมูล ---
                    all_text = page.locator(".ipc-html-content-inner-div, .text.show-more__control").all_text_contents()
                    
                    # Clean ข้อมูล: ลบตัวซ้ำและตัวสั้น
                    clean_reviews = []
                    for r in all_text:
                        t = r.strip()
                        if len(t) > 40 and t not in clean_reviews and "Helpful" not in t[:10]:
                            clean_reviews.append(t)
                    
                    m['reviews'] = clean_reviews
                    print(f"   ✅ สำเร็จ! สกัดรวมมาได้ {len(m['reviews'])} รีวิว")

                except Exception as e:
                    print(f"   ⚠️ เรื่อง {m['title']} มีปัญหา: {e}")
                    m['reviews'] = []
                
                enriched_data.append(m)

                # --- 4. CHECKPOINT SAVE (ทุกๆ 10 เรื่อง) ---
                if len(enriched_data) % CHECKPOINT_EVERY == 0:
                    with open(OUTPUT_ENRICHED, "w", encoding="utf-8") as f:
                        json.dump(enriched_data, f, ensure_ascii=False, indent=4)
                    print(f"💾 Checkpoint: บันทึกข้อมูลสะสมแล้ว {len(enriched_data)} เรื่อง")

                time.sleep(1) # พักเบรกเล็กน้อย

        except KeyboardInterrupt:
            print("\n🛑 คุณสั่งหยุดสคริปต์ด้วยมือ!")
        finally:
            # บันทึกข้อมูลครั้งสุดท้ายก่อนปิด
            with open(OUTPUT_ENRICHED, "w", encoding="utf-8") as f:
                json.dump(enriched_data, f, ensure_ascii=False, indent=4)
            print(f"✅ ปิดกระบวนการและบันทึกข้อมูลรวมทั้งสิ้น {len(enriched_data)} เรื่อง")
            browser.close()

    return enriched_data

# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------
if __name__ == "__main__":
    if not os.path.exists(INPUT_FILE):
        print(f"❌ ไม่พบไฟล์ {INPUT_FILE}")
    else:
        with open(INPUT_FILE, "r", encoding="utf-8") as f:
            raw_movies = json.load(f)
        
        # รันสคริปต์อัตโนมัติ
        scrape_reviews_ultimate(raw_movies)