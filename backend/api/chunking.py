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

def chunk_code(code: str, file_type: str, chunk_size: int = 2000) -> List[str]:
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
                chunks.append(chunk)
    if not chunks:
        return [code[i:i+chunk_size] for i in range(0, len(code), chunk_size)]
    return chunks

def chunk_text(text: str, chunk_size: int = 2000) -> List[str]:
    """Chunk text by paragraphs or fixed size."""
    paragraphs = [p for p in text.split('\n\n') if p.strip()]
    chunks = []
    for para in paragraphs:
        if len(para) > chunk_size:
            for i in range(0, len(para), chunk_size):
                chunks.append(para[i:i+chunk_size])
        else:
            chunks.append(para)
    return chunks

def embed_texts(texts: List[str], model: str = "text-embedding-3-small") -> List[np.ndarray]:
    """Embed a list of texts using OpenAI and return a list of np.ndarray."""
    results = []
    for text in texts:
        text = text.replace("\n", " ")
        response = openai_client.embeddings.create(input=[text], model=model)
        embedding = np.array(response.data[0].embedding, dtype=np.float32)
        results.append(embedding)
    return results

def generate_project_summary(all_contents: List[str], model: str = "gpt-4o") -> str:
    """Generate a project summary using OpenAI's chat completion API."""
    # Concatenate all content, truncate if too long for context window
    joined_content = "\n\n".join(all_contents)
    max_tokens = 4096  # adjust as needed for model context
    if len(joined_content) > 16000:
        joined_content = joined_content[:16000]  # crude truncation for safety
    system_prompt = (
        "You are an expert software engineer. Given the following project content (code, README, user ramble, etc.), "
        "write a detailed, technology-rich summary of the project. Highlight the main technologies, architecture, "
        "notable features, and what makes the project interesting."
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
    return response.choices[0].message.content.strip() 