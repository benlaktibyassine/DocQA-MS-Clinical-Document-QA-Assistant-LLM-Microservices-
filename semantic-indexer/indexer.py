import pika
import json
import os
import numpy as np
import pickle # Pour sauvegarder les métadonnées simplement
from sentence_transformers import SentenceTransformer
import faiss

# --- CONFIGURATION ---
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
INPUT_QUEUE = 'clean_documents_queue'

# Fichiers de stockage (Base de données locale)
INDEX_FILE = "vector_store.faiss"
METADATA_FILE = "metadata_store.pkl"

# --- INITIALISATION ---
print("Chargement du modèle d'embedding (HuggingFace)...")
# On utilise un petit modèle performant et gratuit
model = SentenceTransformer('all-MiniLM-L6-v2') 
dimension = 384 # Taille des vecteurs de ce modèle

# Chargement ou création de l'index FAISS
if os.path.exists(INDEX_FILE):
    print("Chargement de l'index existant...")
    index = faiss.read_index(INDEX_FILE)
    with open(METADATA_FILE, 'rb') as f:
        metadata_store = pickle.load(f)
else:
    print("Création d'un nouvel index...")
    index = faiss.IndexFlatL2(dimension)
    metadata_store = [] # Liste pour stocker le texte associé aux vecteurs

print(f"Index prêt. Contient {index.ntotal} vecteurs.")

def save_state():
    """Sauvegarde l'index et les textes sur le disque"""
    faiss.write_index(index, INDEX_FILE)
    with open(METADATA_FILE, 'wb') as f:
        pickle.dump(metadata_store, f)
    print(" -> Index sauvegardé sur disque.")

def chunk_text(text, chunk_size=500):
    """Découpe le texte en morceaux de 500 caractères environ"""
    # Dans la vraie vie, on utilise des "RecursiveCharacterTextSplitter" plus malins
    # Ici, on fait simple pour comprendre le principe.
    chunks = []
    for i in range(0, len(text), chunk_size):
        chunks.append(text[i:i+chunk_size])
    return chunks

def callback(ch, method, properties, body):
    try:
        message = json.loads(body)
        doc_id = message.get("doc_id")
        text = message.get("original_text_masked") # Le texte anonymisé
        
        print(f" [->] Reçu Doc ID {doc_id}. Traitement...")

        # 1. Découpage (Chunking)
        chunks = chunk_text(text)
        print(f"      Découpé en {len(chunks)} morceaux.")

        if not chunks:
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        # 2. Vectorisation (Embedding)
        embeddings = model.encode(chunks) # Transforme le texte en chiffres

        # 3. Ajout dans FAISS
        # FAISS attend des float32
        index.add(np.array(embeddings).astype('float32'))

        # 4. Stockage des métadonnées (pour retrouver le texte plus tard)
        # On doit se souvenir que le vecteur N correspond au texte "..." du document Y
        for chunk in chunks:
            metadata_store.append({
                "doc_id": doc_id,
                "text_content": chunk,
                "source": message.get("metadata", {}).get("filename", "unknown")
            })

        # 5. Sauvegarde
        save_state()
        
        print(f" [OK] Doc ID {doc_id} indexé avec succès.")
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        print(f"Erreur: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

def start_consuming():
    connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
    channel = connection.channel()
    channel.queue_declare(queue=INPUT_QUEUE, durable=True)
    channel.basic_qos(prefetch_count=1)
    
    # --- LA CORRECTION EST ICI ---
    # On dit à RabbitMQ d'envoyer les messages vers notre fonction 'callback'
    channel.basic_consume(queue=INPUT_QUEUE, on_message_callback=callback)
    # -----------------------------
    
    print(' [*] Indexeur Sémantique en attente...')
    channel.start_consuming()

if __name__ == "__main__":
    try:
        start_consuming()
    except KeyboardInterrupt:
        print("Arrêt.")