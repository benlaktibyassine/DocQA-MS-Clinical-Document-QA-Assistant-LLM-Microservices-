import pika
import json
import os
import glob
import csv
import numpy as np
import pickle
from sentence_transformers import SentenceTransformer
import faiss

# --- CONFIGURATION ---
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
INPUT_QUEUE = 'clean_documents_queue'
DEFAULT_DATA_DIR = "default_data"

# Fichiers de stockage
INDEX_FILE = "vector_store.faiss"
METADATA_FILE = "metadata_store.pkl"

print("Chargement du modèle d'embedding...")
model = SentenceTransformer('all-MiniLM-L6-v2') 
dimension = 384
index = None
metadata_store = []

def save_state():
    faiss.write_index(index, INDEX_FILE)
    with open(METADATA_FILE, 'wb') as f:
        pickle.dump(metadata_store, f)
    print(" -> Index sauvegardé.")

def add_to_index(text, source_name, doc_type="knowledge_base"):
    """Ajoute un texte vectorisé à l'index"""
    global index
    if not text.strip(): return

    embeddings = model.encode([text])
    if index is None:
        index = faiss.IndexFlatL2(dimension)
    
    index.add(np.array(embeddings).astype('float32'))
    
    metadata_store.append({
        "doc_id": "KB_MTC",
        "text_content": text,
        "source": source_name,
        "type": doc_type
    })

def ingest_csv_data():
    """Traite intelligemment vos CSV MTC"""
    if not os.path.exists(DEFAULT_DATA_DIR): return

    csv_files = glob.glob(os.path.join(DEFAULT_DATA_DIR, "*.csv"))
    
    for file_path in csv_files:
        filename = os.path.basename(file_path)
        print(f"🚀 Traitement structuré de : {filename}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                count = 0
                
                for row in reader:
                    # CAS 1 : Matrice de Ranking (Scores)
                    if "matrice" in filename or "ranking" in filename:
                        # On crée une phrase que le LLM comprendra parfaitement
                        # Ex: "Pour le syndrome Vide de Qi, la plante Ginseng a un score de 10."
                        text = (
                            f"ANALYSE SCORE MTC : Syndrome '{row.get('nom_syndrome', '')}'. "
                            f"Plante recommandée : {row.get('nom_latin', '')} ({row.get('nom_chinois', '')}). "
                            f"Score de pertinence : {row.get('score_role', '0')}."
                        )
                        add_to_index(text, filename)
                        count += 1

                    # CAS 2 : Base de Connaissance (Détails)
                    elif "base" in filename or "connaissance" in filename:
                        # Ex: "Dans la formule X, la plante Y est Empereur..."
                        text = (
                            f"DÉTAIL CLINIQUE : Syndrome '{row.get('nom_syndrome', '')}'. "
                            f"Formule '{row.get('nom_formule', '')}'. "
                            f"Plante : {row.get('nom_latin', '')}. "
                            f"Rôle : {row.get('role_formule', 'Inconnu')} (Score {row.get('score_role', '')}). "
                            f"Description : {row.get('description', '')}"
                        )
                        add_to_index(text, filename)
                        count += 1
                        
                print(f"   -> {count} entrées indexées pour {filename}")

        except Exception as e:
            print(f"⚠️ Erreur lecture CSV {filename}: {e}")

# --- DÉMARRAGE ---
if os.path.exists(INDEX_FILE) and os.path.exists(METADATA_FILE):
    print("Chargement de l'index existant...")
    index = faiss.read_index(INDEX_FILE)
    with open(METADATA_FILE, 'rb') as f:
        metadata_store = pickle.load(f)
else:
    print("Création d'un nouvel index MTC...")
    index = faiss.IndexFlatL2(dimension)
    metadata_store = []
    ingest_csv_data() # Scan et ingestion des CSV
    save_state()

print(f"Index prêt ({index.ntotal} vecteurs). En attente RabbitMQ...")

# --- PARTIE RABBITMQ (Ne change pas) ---
def callback(ch, method, properties, body):
    try:
        message = json.loads(body)
        doc_id = message.get("doc_id")
        text = message.get("original_text_masked")
        print(f" [->] Reçu Doc Patient {doc_id}")
        
        # Découpage simple pour le texte patient
        chunks = [text[i:i+500] for i in range(0, len(text), 500)]
        
        for chunk in chunks:
            add_to_index(chunk, f"Dossier Patient {doc_id}", "patient_file")
            
        save_state()
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        print(f"Erreur: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

def start_consuming():
    connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
    channel = connection.channel()
    channel.queue_declare(queue=INPUT_QUEUE, durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=INPUT_QUEUE, on_message_callback=callback)
    channel.start_consuming()

if __name__ == "__main__":
    try:
        start_consuming()
    except KeyboardInterrupt:
        print("Arrêt.")