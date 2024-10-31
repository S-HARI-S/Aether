# Obsidian RAG Plugin
A simple Retrieval-Augmented Generation (RAG) plugin for Obsidian that allows you to query your vault using Google's Gemini AI.

## Features
- Real-time monitoring of markdown files in your vault
- Automatic embedding generation and updates
- Semantic search using ChromaDB
- Conversation history support
- Markdown-aware text chunking
- File change detection (create, modify, delete)

## Setting Up
1. Clone the repository into your Obsidian vault's plugins directory:
   ```bash
   cd YOUR_VAULT_PATH/.obsidian/plugins
   git clone [repository-url] rag-plugin
   ```

2. Set up the Python environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install required Python packages:
   ```bash
   pip install flask chromadb google-generativeai python-dotenv watchdog
   ```

4. Configure the environment:
   - Add your Google AI API key:
     ```
     # Configure Google AI
		genai.configure(api_key="")
     ```
   - Update `ROOT_DIR` in the code to point to your Obsidian vault path
   - ```
     Here:
     ROOT_DIR = r"C:\Users\SREEHARI\Documents\Obsidian Vault"
     ```

5. Start the Python backend server:
   ```bash
   python new.py
   ```

6. Install Node.js dependencies and start the frontend:
   ```bash
   npm install
   npm run dev
   ```

7. Enable the plugin in Obsidian:
   - Go to Settings → Community Plugins
   - Enable the plugin named "sample pluggin"

## Quick glance at Technical Details
- **Database**: Uses ChromaDB for vector storage (in-memory mode)
- **Embedding Strategy**: 
  - Chunks markdown files by sections and paragraphs
  - Maximum chunk size: 1000 characters
  - Maintains document references and metadata
- **AI Model**: Uses Gemini 1.5 Flash with configured parameters:
  - Temperature: 0.7
  - Top-p: 0.95
  - Top-k: 64
  - Max output tokens: 1000
- **File Processing**:
  - Monitors `.md` files only
  - Ignores hidden directories
  - Supports real-time updates
- **API Endpoint**: 
  - POST `/arraysum` for querying the knowledge base ( "arraysum" doesn't make sense, i will change this eventually )
  - Maintains conversation history (last 5 exchanges)

