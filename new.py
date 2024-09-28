import os
import re
import time
import json
import chromadb
import google.generativeai as genai
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from dotenv import load_dotenv
from flask import Flask, request, jsonify

load_dotenv()

app = Flask(__name__)

chroma_client = chromadb.Client()
collection_name = 'file-embeddings'
collection = chroma_client.get_or_create_collection(name=collection_name)

# Configure Google AI
genai.configure(api_key="")
generation_config = {
    "temperature": 0.7,
    "top_p": 0.95,
    "top_k": 64,
    "max_output_tokens": 1000,
}
model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    generation_config=generation_config,
)

ROOT_DIR = r"C:\Users\SREEHARI\Documents\Obsidian Vault"

conversation_history = []

def chunk_markdown(md_text, max_chunk_size=1000):
    sections = re.split(r'(?=^#)', md_text, flags=re.MULTILINE)
    chunks = []
    for section in sections:
        paragraphs = section.strip().split('\n\n')
        current_chunk = ''
        for paragraph in paragraphs:
            if len(current_chunk) + len(paragraph) + 1 > max_chunk_size:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ''
            current_chunk += paragraph + '\n\n'
        if current_chunk:
            chunks.append(current_chunk.strip())
    return chunks

def process_file(file_path):
    try:
        with open(file_path, "r", encoding='utf-8') as file:
            text = file.read()
        
        chunks = chunk_markdown(text)
        ids = [f"{os.path.relpath(file_path, ROOT_DIR)}_{i}" for i in range(len(chunks))]
        metadatas = [{"file_path": os.path.relpath(file_path, ROOT_DIR)} for _ in chunks]
        
        collection.upsert(
            documents=chunks,
            ids=ids,
            metadatas=metadatas
        )
        print(f"Processed and upserted {file_path}")
    except Exception as e:
        print(f"Error processing {file_path}: {str(e)}")

def remove_file_embeddings(file_path):
    try:
        rel_path = os.path.relpath(file_path, ROOT_DIR)
        collection.delete(where={"file_path": rel_path})
        print(f"Removed embeddings for {file_path}")
    except Exception as e:
        print(f"Error removing embeddings for {file_path}: {str(e)}")

def query_and_generate(query_text):
    results = collection.query(
        query_texts=[query_text],
        n_results=5
    )
    
    distances = results["distances"][0]
    
    distance_threshold = 1.5
    
    relevant_docs = [doc for i, doc in enumerate(results["documents"][0]) if distances[i] < distance_threshold]
    relevant_meta = [meta for i, meta in enumerate(results["metadatas"][0]) if distances[i] < distance_threshold]
    
    unique_sources = []
    for meta in relevant_meta:
        if meta['file_path'] not in unique_sources:
            unique_sources.append(meta['file_path'])
    
    if not relevant_docs:
        context = "The query does not closely match any specific file content."
    else:
        context = "\n\n".join(relevant_docs)
    
    history_text = "\n".join([f"Human: {turn['human']}\nAssistant: {turn['assistant']}" for turn in conversation_history])
    
    prompt = f"""
    You are a highly knowledgeable AI assistant with access to a personal knowledge base. 
    Your task is to provide a concise, accurate, and informative response to the user's question based on the given context and conversation history. 
    Follow these guidelines:

    1. Be descriptive but concise, focusing on the most relevant information.
    2. Use a confident and friendly authoritative tone.
    3. Use proper Markdown formatting for enhanced readability.
    4. Include relevant facts, figures, or brief examples if they enhance the answer.
    5. If the context doesn't contain relevant information to answer the question, state that clearly.
    6. Start your response immediately without any prefix or formatting.
    7. IMPORTANT: DO NOT start your answer with ```. Only use ``` for inline code snippets if absolutely necessary.
    8. Maintain continuity with the conversation history, referencing previous exchanges when relevant.

    Conversation History:
    {history_text}

    Human: {query_text}

    Context from knowledge base:
    {context}

    Assistant:
    """
    
    try:
        response = model.generate_content(prompt)

        # Update conversation history
        conversation_history.append({"human": query_text, "assistant": response.text})

        # Keep only the last 5 exchanges to manage context length
        if len(conversation_history) > 5:
            conversation_history.pop(0)

        return {
            "query": query_text,
            "answer": response.text,
            "sources": unique_sources
        }
    except Exception as e:
        return {
            "query": query_text,
            "error": str(e),
            "sources": unique_sources
        }

class MyEventHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith('.md'):
            print(f"File {event.src_path} has been created")
            process_file(event.src_path)

    def on_modified(self, event):
        if not event.is_directory and event.src_path.endswith('.md'):
            print(f"File {event.src_path} has been modified")
            process_file(event.src_path)

    def on_deleted(self, event):
        if not event.is_directory and event.src_path.endswith('.md'):
            print(f"File {event.src_path} has been deleted")
            remove_file_embeddings(event.src_path)

def is_valid_directory(path):
    return not any(part.startswith('.') for part in path.split(os.sep))

def process_existing_files():
    for root, dirs, files in os.walk(ROOT_DIR):
        # Skip hidden directories
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        
        if is_valid_directory(root):
            for file in files:
                if file.endswith('.md'):
                    process_file(os.path.join(root, file))

@app.route('/arraysum', methods=['POST'])
def array_sum():
    data = request.json
    query_text = data.get('query')
    
    if not query_text:
        return jsonify({"error": "No query provided"}), 400
    
    result = query_and_generate(query_text)
    return jsonify(result)

def main():
    process_existing_files()

    # Set up the observer
    event_handler = MyEventHandler()
    observer = Observer()
    observer.schedule(event_handler, ROOT_DIR, recursive=True)
    observer.start()

    try:
        app.run(debug=True)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()

if __name__ == "__main__":
    main()