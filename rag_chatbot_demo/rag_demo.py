from multiprocessing import process
import os
import faiss
import numpy as np
import json
from sentence_transformers import SentenceTransformer
import google.generativeai as genai

os.environ['HUGGINGFACE_HUB_TOKEN']= process.env.hf_tokenHUGGINGFACE_HUB_TOKEN

# -----------------------------
# CONFIG
# -----------------------------
DOCS_DIR = "docs"
#CHUNK_OVERLAP = 100
TOP_K = 10

# ใส่ API Key ของตนเอง
genai.configure(api_key= process.env.genaikey)

# ใช้ embedding model แบบง่าย
embedding_model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')

# -----------------------------
# STEP 1: LOAD DOCUMENTS
# -----------------------------
def load_documents(folder_path):
    file_path = os.path.join(folder_path, "thai_movies_final_cleaned.json")

    if not os.path.exists(file_path):
        return[]
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
    except Exception as e:
        return []
    
# -----------------------------
# STEP 2: SIMPLE CHUNKING
# -----------------------------
def chunk_text(json_file):
    with open(json_file,'r',encoding='utf-8') as f:
        movies = json.load(f)


# -----------------------------
# STEP 3: PREPARE CHUNKS + METADATA
# -----------------------------
def prepare_chunks(documents):
    chunk_records = []
    for doc in documents:
        title = doc.get('title', 'Unknown')
        imdb_id = doc.get('imdb_id', 'N/A')
        imdb_rating = doc.get('imdb_rating', 'N/A')
        release_year = doc.get('release_year', 'N/A')
        runtime = doc.get('runtime','N/A')
        synopsis = doc.get('synopsis', 'No plot available.')
        reviews = doc.get('reviews') or doc.get('Reviews') or []

        for i, rev in enumerate(reviews):
            context_text = f"Movie: {title} ({release_year}) {runtime}| Official Rating: {imdb_rating}/10 | {rev}"

            chunk_records.append({
                "chunk_id": f"{imdb_id}_{i}",
                "filename": title,
                "text": context_text,
                "metadata": {
                    "imdb_id": imdb_id,
                    "imdb_rating": imdb_rating,
                    "release_year": release_year,
                    "synopsis": synopsis
                }
            })
            
    return chunk_records


# -----------------------------
# STEP 4: CREATE EMBEDDINGS
# -----------------------------
def create_embeddings(chunk_records):
    texts = [c["text"] for c in chunk_records]
    embeddings = embedding_model.encode(texts, show_progress_bar=True, convert_to_numpy=True)
    return embeddings

# -----------------------------
# STEP 5: BUILD FAISS INDEX
# -----------------------------

def build_faiss_index(embeddings):
    dim = embeddings.shape[1]
    index = faiss.IndexFlatL2(dim)
    index.add(embeddings.astype("float32"))
    return index


# -----------------------------
# STEP 6: RETRIEVE RELEVANT CHUNKS
# -----------------------------
def retrieve(query, index, chunk_records, top_k=3):
    query_embedding = embedding_model.encode([query], convert_to_numpy=True)
    distances, indices = index.search(query_embedding.astype("float32"), top_k)
    
    results = [chunk_records[idx] for idx in indices[0]]
    return results

def save_vector_db(index, chunk_records, index_file="movie_vectors.index", metadata_file="metadata.json"):
    faiss.write_index(index, index_file)
    
    with open(metadata_file, 'w', encoding='utf-8') as f:
        json.dump(chunk_records, f, ensure_ascii=False, indent=4)

# -----------------------------
# MAIN
# -----------------------------
def main():

    print("Loading documents...")
    documents = load_documents(DOCS_DIR)

    print("Preparing chunks...")
    chunk_records = prepare_chunks(documents)

    print("Creating embeddings...")
    embeddings = create_embeddings(chunk_records)

    print("Building index...")
    index = build_faiss_index(embeddings)

    save_vector_db(index, chunk_records)


if __name__ == "__main__":
    main()