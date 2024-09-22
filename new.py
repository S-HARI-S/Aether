import os
import time
import json
import hashlib
import chromadb
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from huggingface_hub import InferenceClient
from filelock import FileLock
from sentence_transformers import SentenceTransformer
import numpy as np
import google.generativeai as genai


chroma_client = chromadb.Client()


collection_name = 'file-embeddings'
collection = chroma_client.get_or_create_collection(name=collection_name)


file_hashes = {}


EXCLUDED_FOLDERS = {'.obsidian'}

PLUGIN_FOLDER = ''
VAULT_ROOT = ''


sentence_model = SentenceTransformer('all-MiniLM-L6-v2')

def embed_text(text):
    return sentence_model.encode(text)

def calculate_file_hash(file_path):

    hasher = hashlib.md5()
    with open(file_path, 'rb') as file:
        buf = file.read()
        hasher.update(buf)
    return hasher.hexdigest()

def should_process_file(file_path):

    if any(part.startswith('.') for part in file_path.split(os.sep)):
        return False
    
    if any(folder in file_path.split(os.sep) for folder in EXCLUDED_FOLDERS):
        return False

    try:
        current_hash = calculate_file_hash(file_path)
        if file_path not in file_hashes or file_hashes[file_path] != current_hash:
            file_hashes[file_path] = current_hash
            return True
    except OSError as e:
        print(f"Error accessing file {file_path}: {e}")
    return False

def process_file(file_path):

    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            file_content = file.read()

        file_name = os.path.basename(file_path)
        relative_path = os.path.relpath(file_path, VAULT_ROOT)
        

        combined_content = f"File Name: {file_name}\nRelative Path: {relative_path}\nContent: {file_content}"


        embedding = embed_text(combined_content)


        collection.upsert(
            documents=[combined_content],
            embeddings=[embedding.tolist()],
            ids=[file_name],
            metadatas=[{
                "file_path": file_path,
                "relative_path": relative_path,
                "file_name": file_name
            }]
        )

        print(f'Processed file: {file_name}')

    except Exception as e:
        print(f'Error processing file {file_path}: {e}')

def on_modified(event):

    if event.event_type in ['modified', 'created'] and event.src_path:
        if os.path.isfile(event.src_path) and should_process_file(event.src_path):
            process_file(event.src_path)

class FileEventHandler(FileSystemEventHandler):

    def on_modified(self, event):
        on_modified(event)

    def on_created(self, event):
        on_modified(event)

def process_existing_files(directory):

    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in EXCLUDED_FOLDERS]
        
        for file in files:
            file_path = os.path.join(root, file)
            if should_process_file(file_path):
                process_file(file_path)

def find_similar_files(query, n=10):

    query_embedding = embed_text(query)
    results = collection.query(
        query_embeddings=[query_embedding.tolist()],
        n_results=n,
        include=["metadatas", "distances", "documents"]
    )

    similar_files = []
    if results['ids']:
        for i, (file_id, metadata, document, distance) in enumerate(zip(results['ids'][0], results['metadatas'][0], results['documents'][0], results['distances'][0]), 1):
            similar_files.append({
                "file_id": file_id,
                "file_path": metadata['file_path'],
                "relative_path": metadata['relative_path'],
                "file_name": metadata['file_name'],
                "similarity": distance,
                "content": document
            })
    return similar_files

def extract_relevant_snippets(similar_files, query, max_chars=3000):

    query_embedding = embed_text(query)
    snippets = []
    for file in similar_files:
        content = file['content']
        sentences = content.split('.')
        sentence_embeddings = embed_text(sentences)
        
      
        similarities = np.dot(sentence_embeddings, query_embedding) / (np.linalg.norm(sentence_embeddings, axis=1) * np.linalg.norm(query_embedding))
        
  
        sorted_indices = np.argsort(similarities)[::-1]
        
        relevant_snippets = []
        char_count = 0
        for idx in sorted_indices:
            sentence = sentences[idx].strip()
            if char_count + len(sentence) <= max_chars:
                relevant_snippets.append(sentence)
                char_count += len(sentence)
            else:
                break
        

        file_info = f"File: {file['file_name']} (Path: {file['relative_path']})"
        snippet_text = f"{file_info}\n{' '.join(relevant_snippets)}"
        snippets.append(snippet_text)
    
    return "\n\n".join(snippets)

def generate_answer(question, context_snippets):
 
    
 
    genai.configure(api_key="you aint getting that son")


    generation_config = {
        "temperature": 0.7,
        "top_p": 0.95,
        "top_k": 64,
        "max_output_tokens": 500,
        "response_mime_type": "text/plain",
    }
    
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        generation_config=generation_config,
    )

    prompt = f"""
You are a highly knowledgeable AI assistant with access to a personal knowledge base. Your task is to provide a concise, accurate, and informative response to the user's question based on the given context. Follow these guidelines:

1. Be descriptive but concise, focusing on the most relevant information.
2. Use a confident and authoritative tone.
3. Use proper Markdown formatting for enhanced readability.
4. Include relevant facts, figures, or brief examples if they enhance the answer.
5. If the context doesn't contain relevant information to answer the question, state that clearly.
6. Reference the source files when providing information, using the format [File Name].
7. Start your response immediately without any prefix or formatting.
8. IMPORTANT: DO NOT start your answer with ```. Only use ``` for inline code snippets if absolutely necessary.

Question: {question}

Context:
{context_snippets}

Response:
"""


    chat_session = model.start_chat(history=[])
    response = chat_session.send_message(prompt)


    cleaned_response = response.text.strip()
    if cleaned_response.startswith("```"):
        cleaned_response = cleaned_response.split("\n", 1)[-1].strip()
        if cleaned_response.endswith("```"):
            cleaned_response = cleaned_response[:-3].strip()

    return cleaned_response

def generate_file_name(question):

    clean_question = ''.join(e for e in question if e.isalnum() or e.isspace())
    truncated_question = clean_question[:50].strip()
    return f"{truncated_question}.md"

def interactive_search():

    question_file = os.path.join(PLUGIN_FOLDER, 'rag_question.json')
    results_file = os.path.join(PLUGIN_FOLDER, 'rag_results.json')

    
    question_lock = FileLock(question_file + '.lock')
    results_lock = FileLock(results_file + '.lock')

    try:
 
        with question_lock:
            with open(question_file, 'r') as f:
                data = json.load(f)
                question = data.get('question')

                if not question: 
                    print("No question found.")
                    return

        with question_lock:
            os.remove(question_file)


        similar_files = find_similar_files(question, n=10)
        
        
        context_snippets = extract_relevant_snippets(similar_files, question, max_chars=3000)


        answer = generate_answer(question, context_snippets)

        sources = [file['file_path'] for file in similar_files]

 
        with results_lock:
            with open(results_file, 'w') as f:
                json.dump({"question": question, "answer": answer, "sources": sources}, f, indent=2)
        
        print("Results saved to rag_results.json")
    except Exception as e:
        print(f"Error in interactive search: {e}")

def watch_and_process_all_files(directory):

    print(f'Processing existing files in: {directory}')
    process_existing_files(directory)

    print(f'Monitoring directory for changes: {directory}')
    event_handler = FileEventHandler()
    observer = Observer()
    observer.schedule(event_handler, path=directory, recursive=True)
    observer.start()

    try:
        while True:

            question_file = os.path.join(PLUGIN_FOLDER, 'rag_question.json')
            if os.path.exists(question_file) and os.path.getsize(question_file) > 0:
                interactive_search()

            time.sleep(1) 
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    watch_and_process_all_files(VAULT_ROOT)