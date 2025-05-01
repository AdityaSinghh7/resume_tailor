# Tailor your project section

## Problem Statement
Early-career software engineers rely heavily on their projects to get the foot in the door, they have several projects however, while tailoring their resumes, they often missing key details or resorting to guesswork that can introduce errors or exaggerations. This platform solves this by automatically ingesting user's real project code, READMEs, from GitHub and optionally adding rich “ramble” write-ups; structuring all content in a relational store with vector embeddings for semantic retrieval; and then, on demand, running a Retrieval-Augmented Generation pipeline that rewrites the user’s LaTeX resume's project section to match a given job description while guaranteeing every bullet is traceable to their authenticated record. The system returns both a polished, job-targeted PDF and an objective 0–100 alignment score, giving users a fast, transparent, and fabrication-free path to application-ready materials.


## Tech Stack
- **NextJS** + **React** for frontend
- **Python FastAPI** for data retrieval/ingestion + auth 
- **Weaviate** for vector storage
- **OpenAI embeddings** to embed the data for storage
- **LlamaIndex** for RAG pipeline
- **TreeSitter** for code-parsing