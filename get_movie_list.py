from bs4 import BeautifulSoup
import json
import re

file_path = "rag_chatbot_demo/docs/Movie,Thai.html"

try:
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    soup = BeautifulSoup(content, "html.parser")
    movie_items = soup.select(".ipc-metadata-list-summary-item")
    
    scraped_data = []

    for item in movie_items:
        # 1. Title & ID
        title_tag = item.select_one(".ipc-title__text")
        link_tag = item.select_one(".ipc-title-link-wrapper")
        
        if title_tag and link_tag:
            full_title = title_tag.get_text(strip=True)
            clean_title = full_title.split(". ", 1)[-1]
            
            href = link_tag.get("href", "")
            id_match = re.search(r"tt\d+", href)
            movie_id = id_match.group() if id_match else "N/A"

            # 2. Metadata Row (Year, Runtime)
            metadata_items = item.select(".dli-title-metadata-item")
            metadata_list = [m.get_text(strip=True) for m in metadata_items]
            release_year = metadata_list[0] if len(metadata_list) > 0 else "N/A"
            runtime = metadata_list[1] if len(metadata_list) > 1 else "N/A"

            # 3. IMDb Rating
            rating_tag = item.select_one('span[aria-label^="IMDb rating"]')
            final_rating = "N/A"
            if rating_tag:
                rating_score = re.search(r"\d+\.\d+", rating_tag.get_text())
                final_rating = rating_score.group() if rating_score else "N/A"

            # 4. Synopsis (เรื่องย่อ) *** เพิ่มตรงนี้ ***
            # ในหน้าลิสต์ IMDb มักจะใช้คลาสนี้เก็บคำบรรยายสั้นๆ
            synopsis_tag = item.select_one(".ipc-html-content-inner-div")
            synopsis = synopsis_tag.get_text(strip=True) if synopsis_tag else "No synopsis available."

            scraped_data.append({
                "title": clean_title,
                "imdb_id": movie_id,
                "release_year": release_year,
                "runtime": runtime,
                "imdb_rating": final_rating,
                "synopsis": synopsis # เก็บเรื่องย่อลงไปใน JSON
            })

    # บันทึกเป็น JSON
    with open("thai_movies_data.json", "w", encoding="utf-8") as f:
        json.dump(scraped_data, f, ensure_ascii=False, indent=4)

    print(f"✅ สกัดข้อมูลสำเร็จ {len(scraped_data)} เรื่อง พร้อม 'เรื่องย่อ' และ Metadata!")

except Exception as e:
    print(f"❌ เกิดข้อผิดพลาด: {e}")