# Resume Project Section Tailor

## Problem Statement
Early-career software engineers rely heavily on their projects to get the foot in the door. While they often have several projects, tailoring their resumes becomes challenging - they either miss key details or resort to guesswork that can introduce errors or exaggerations. This platform solves this by automatically ingesting user's real project code, READMEs, and documentation from GitHub, along with optional rich "STAR format" write-ups. It structures all content in a PostgreSQL database with vector embeddings for semantic retrieval, and then runs a Retrieval-Augmented Generation pipeline that rewrites the project section to match a given job description while ensuring every bullet point is traceable to authenticated source code. The system returns both polished, job-targeted project descriptions and objective alignment scores, providing a fast, transparent, and fabrication-free path to application-ready materials.

## Architecture Overview

### Authentication & Data Ingestion
- GitHub OAuth integration for secure user authentication
- Automatic repository discovery and metadata ingestion
- Smart file filtering based on extensions and size thresholds
- Structured storage of repository metadata in PostgreSQL

### Content Processing Pipeline
- Intelligent code parsing using TreeSitter for language-aware chunking
- Support for multiple programming languages including Python, JavaScript, TypeScript, Java, and more
- Semantic chunking of documentation and README files
- Optional STAR format project descriptions ("rambles") with semantic processing
- OpenAI embeddings generation for all content chunks
- LLM-powered project summarization combining code, documentation, and user descriptions
- Hybrid vector storage using pgvector for both chunk-level and project-level embeddings

### RAG-Powered Resume Generation
- Job description semantic analysis and embedding
- Two-level semantic search:
  1. Project-level matching using summary embeddings
  2. Chunk-level retrieval for detailed content
- LLM-driven resume bullet point generation
- Alignment scoring based on semantic similarity
- Technology stack extraction and relevance ranking

## Tech Stack
- **Frontend**: NextJS + React with TypeScript
- **Backend**: Python FastAPI
- **Database**: PostgreSQL with pgvector extension
- **Authentication**: GitHub OAuth
- **AI/ML**:
  - OpenAI API for embeddings and LLM
  - TreeSitter for code parsing
  - Custom RAG pipeline implementation

## Features
- 🔐 Secure GitHub integration with OAuth
- 📚 Automatic repository content ingestion
- 💡 Intelligent code and documentation parsing
- 📝 Optional STAR format project descriptions
- 🔍 Semantic search across all project content
- 🎯 Job-specific project selection
- 📊 Objective alignment scoring
- ⚡ Real-time resume section generation
- 🔄 Automatic content updates and re-processing

## Future Roadmap
1. Enhanced Project Summarization
   - Improved system prompts for quantitative metrics extraction
   - More detailed technology stack analysis
   - Better capture of project impact and outcomes

2. Performance Optimization
   - Multi-threaded/async processing pipeline
   - Optimized embedding generation
   - Caching strategies for frequent queries

3. Additional Features
   - Direct project upload via ZIP files
   - PDF export functionality
   - More granular alignment scoring
   - Custom project templates

## Getting Started

### Prerequisites
- Python 3.12+
- Node.js 18+
- PostgreSQL with pgvector extension
- GitHub OAuth application credentials
- OpenAI API key

### Installation
1. Clone the repository
2. Install backend dependencies:
   ```bash
   cd backend
   python -m venv .venv
   source .venv/bin/activate  # or .venv\Scripts\activate on Windows
   pip install -r requirements.txt
   ```
3. Install frontend dependencies:
   ```bash
   cd frontend
   npm install
   ```
4. Set up environment variables:
   
   **Backend (.env):**
   ```env
   OPENAI_API_KEY=your_openai_key
   POSTGRES_PASSWORD=your_postgres_password
   POSTGRES_USER=your_postgres_user
   POSTGRES_DB=your_postgres_db
   POSTGRES_PORT=5432
   POSTGRES_HOST=localhost
   SECRET_KEY=your_secret_key
   GITHUB_OAUTH_CALLBACK_URL=http://localhost:8000/auth/github/callback
   GITHUB_CLIENT_SECRET=your_github_client_secret
   GITHUB_CLIENT_ID=your_github_client_id
   ```
   
   **Frontend (.env):**
   ```env
   GITHUB_OAUTH_CALLBACK_URL=http://localhost:8000/auth/github/callback
   GITHUB_CLIENT_SECRET=your_github_client_secret
   NEXT_PUBLIC_GITHUB_CLIENT_ID=your_github_client_id
   ```

### Running the Application
1. Start the backend server:
   ```bash
   cd backend
   uvicorn main:app --reload
   ```
2. Start the frontend development server:
   ```bash
   cd frontend
   npm run dev
   ```

## Contributing
Contributions are welcome! Please feel free to submit a Pull Request.