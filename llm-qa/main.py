import os
import pickle
import faiss
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# --- CHANGEMENT CLÉ : On importe ChatOllama au lieu de ChatOpenAI ---
from langchain_community.chat_models import ChatOllama 

from langchain.chains import RetrievalQA
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain.prompts import PromptTemplate
from langchain_community.docstore.in_memory import InMemoryDocstore
from langchain_community.docstore.document import Document

app = FastAPI(title="Health LLM Assistant (Local Version)")

# Chemins vers les fichiers créés par l'indexeur
FAISS_PATH = "../semantic-indexer/vector_store.faiss"
META_PATH = "../semantic-indexer/metadata_store.pkl"

print("1. Chargement du modèle d'embedding...")
# On garde le même modèle d'embedding que l'indexeur (HuggingFace)
embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

print("2. Reconstruction de la base vectorielle...")
vector_store = None

try:
    if not os.path.exists(FAISS_PATH):
        raise FileNotFoundError(f"Fichier introuvable: {FAISS_PATH}")
    
    # Lecture manuelle des fichiers de l'indexeur
    raw_index = faiss.read_index(FAISS_PATH)
    
    with open(META_PATH, "rb") as f:
        metadata_store = pickle.load(f)
    
    # Reconstruction du lien Index <-> Texte pour LangChain
    docstore = InMemoryDocstore({})
    index_to_docstore_id = {}
    
    for i, meta in enumerate(metadata_store):
        doc_id = str(i)
        doc = Document(
            page_content=meta["text_content"],
            metadata={"source": meta["source"], "original_id": meta["doc_id"]}
        )
        docstore.add({doc_id: doc})
        index_to_docstore_id[i] = doc_id
        
    vector_store = FAISS(
        embedding_function=embeddings,
        index=raw_index,
        docstore=docstore,
        index_to_docstore_id=index_to_docstore_id
    )
    print(f"✅ Base locale chargée avec succès ! ({raw_index.ntotal} documents)")

except Exception as e:
    print(f"❌ ERREUR : Impossible de charger l'index. Détails: {e}")

# --- CHANGEMENT MAJEUR ICI ---
# On utilise Ollama (Mistral) qui tourne sur votre PC
print("3. Connexion au LLM Local (Ollama)...")
llm = ChatOllama(model="mistral", temperature=0)

# Le Prompt (Consignes données à l'IA)
template = """
Tu es un assistant médical expert.
Utilise UNIQUEMENT le contexte suivant pour répondre à la question.
Si la réponse n'est pas dans le texte, dis "Je ne trouve pas cette information".

Contexte :
{context}

Question : 
{question}

Réponse :
"""
QA_CHAIN_PROMPT = PromptTemplate(input_variables=["context", "question"], template=template)

# Création de la chaîne RAG
if vector_store:
    qa_chain = RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=vector_store.as_retriever(search_kwargs={"k": 3}),
        return_source_documents=True,
        chain_type_kwargs={"prompt": QA_CHAIN_PROMPT}
    )
else:
    qa_chain = None

class Query(BaseModel):
    question: str

@app.post("/ask/")
async def ask_question(query: Query):
    if not qa_chain:
        raise HTTPException(status_code=503, detail="Index non chargé.")
    
    # L'appel peut prendre quelques secondes en local
    result = qa_chain.invoke({"query": query.question})
    
    return {
        "answer": result["result"],
        "sources": [doc.metadata.get("source") for doc in result["source_documents"]]
    }

@app.get("/health")
def health():
    return {"status": "ok", "service": "llm-qa"}
