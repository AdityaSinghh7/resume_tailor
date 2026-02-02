import os
import numpy as np
from typing import List, Optional
from openai import OpenAI
from dotenv import load_dotenv
from tree_sitter import Parser
from tree_sitter_languages import get_language

# Load environment variables
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# TreeSitter setup
TREE_SITTER_LANGUAGES = {}
EXTENSION_LANGUAGE_MAP = {
    'py': 'python', 'js': 'javascript', 'ts': 'typescript', 'jsx': 'javascript', 'tsx': 'typescript',
    'java': 'java', 'c': 'c', 'cpp': 'cpp', 'h': 'cpp', 'hpp': 'cpp', 'go': 'go', 'rb': 'ruby',
    'php': 'php', 'rs': 'rust', 'swift': 'swift', 'kt': 'kotlin', 'dart': 'dart', 'vue': 'vue', 'svelte': 'svelte',
}

NODE_TYPES = {
    'python': ["function_definition", "class_definition"],
    'javascript': ["function_declaration", "class_declaration"],
    'typescript': ["function_declaration", "class_declaration"],
    'java': ["method_declaration", "class_declaration"],
    'c': ["function_definition"],
    'cpp': ["function_definition", "class_specifier"],
    'go': ["function_declaration", "method_declaration"],
    'ruby': ["method", "class"],
    'php': ["function_definition", "class_declaration"],
    'rust': ["function_item", "struct_item", "enum_item", "impl_item"],
    'swift': ["function_declaration", "class_declaration", "struct_declaration"],
    'kotlin': ["function_declaration", "class_declaration"],
    'dart': ["function_declaration", "class_declaration"],
    'vue': [], 'svelte': [],
}

for ext, lang_name in EXTENSION_LANGUAGE_MAP.items():
    try:
        TREE_SITTER_LANGUAGES[ext] = get_language(lang_name)
    except Exception:
        pass

DEFAULT_CHUNK_SIZE = int(os.getenv("EMBED_CHUNK_SIZE", "1000"))

def _split_large_chunk(text: str, chunk_size: int) -> List[str]:
    if len(text) <= chunk_size:
        return [text]
    return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]

def chunk_code(code: str, file_type: str, chunk_size: int = DEFAULT_CHUNK_SIZE) -> List[str]:
    """Chunk code using TreeSitter by function/class for supported languages, else by size."""
    ext = file_type.lower()
    lang = TREE_SITTER_LANGUAGES.get(ext)
    if not lang:
        return [code[i:i+chunk_size] for i in range(0, len(code), chunk_size)]
    parser = Parser()
    parser.set_language(lang)
    tree = parser.parse(bytes(code, "utf8"))
    root = tree.root_node
    lang_name = EXTENSION_LANGUAGE_MAP.get(ext, None)
    node_types = NODE_TYPES.get(lang_name, [])
    chunks = []
    if node_types:
        for node in root.children:
            if node.type in node_types:
                chunk = code[node.start_byte:node.end_byte]
                chunks.extend(_split_large_chunk(chunk, chunk_size))
    if not chunks:
        return [code[i:i+chunk_size] for i in range(0, len(code), chunk_size)]
    return chunks

def chunk_text(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE) -> List[str]:
    """Chunk text by paragraphs or fixed size."""
    paragraphs = [p for p in text.split('\n\n') if p.strip()]
    chunks = []
    for para in paragraphs:
        if len(para) > chunk_size:
            chunks.extend(_split_large_chunk(para, chunk_size))
        else:
            chunks.append(para)
    return chunks

def embed_texts(texts: List[str], model: str = "text-embedding-3-small", batch_size: int = 96) -> List[np.ndarray]:
    """Embed a list of texts using OpenAI and return a list of np.ndarray."""
    results: List[np.ndarray] = []
    if not texts:
        return results
    for start in range(0, len(texts), batch_size):
        batch = [text.replace("\n", " ") for text in texts[start:start + batch_size]]
        response = openai_client.embeddings.create(input=batch, model=model)
        for item in response.data:
            results.append(np.array(item.embedding, dtype=np.float32))
    return results

def generate_project_summary(all_contents: List[str], model: str = "gpt-4o") -> str:
    """Generate a project summary using OpenAI's chat completion API."""
    # Concatenate all content, truncate if too long for context window
    joined_content = "\n\n".join(all_contents)
    max_tokens = 4096  # adjust as needed for model context
    if len(joined_content) > 16000:
        joined_content = joined_content[:16000]  # crude truncation for safety
    system_prompt = (
        "You are an expert technical recruiter at a big tech company. Given the following project content (code, README, user ramble, etc.), "
        "parse and extract every minute and relevant technology, library, framework, API, tool, and architectural pattern used in the project, even if minor or only used in a small part. "
        "Highlight the main technologies, architecture, notable features, and what makes the project interesting from a technical recruiter's perspective. "
        "Organize your summary into clear sections: 'Technologies Used', 'Libraries/Frameworks', 'APIs', 'Architectural Patterns', 'Other Notable Details'. "
        "This summary will be used to generate technical resume entries, so include all information that could be relevant for a technical resume."
    )
    response = openai_client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": joined_content}
        ],
        max_tokens=max_tokens,
        temperature=0.3
    )
    summary = response.choices[0].message.content.strip()
    print("\n[chunking.py] ===== Project Summary Generated =====\n" + summary + "\n[chunking.py] =====================================\n")
    return summary 
