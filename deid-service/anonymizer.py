import pika
import json
import time
import sys
import os

# Import des moteurs d'anonymisation Microsoft
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine

# --- CONFIGURATION ---
RABBITMQ_HOST = '127.0.0.1' 
INPUT_QUEUE = 'raw_documents_queue'    # File d'entrée (venant de l'ingestor)
OUTPUT_QUEUE = 'clean_documents_queue' # File de sortie (vers l'indexeur)

# Initialisation des moteurs IA
print("Chargement du modèle IA (Presidio)...")
try:
    analyzer = AnalyzerEngine()
    anonymizer = AnonymizerEngine()
    print("Modèle chargé avec succès.")
except Exception as e:
    print(f"Erreur chargement modèle: {e}")
    print("Avez-vous lancé: python -m spacy download en_core_web_lg ?")
    sys.exit(1)

def process_text_anonymization(text):
    """Détecte et remplace les données sensibles"""
    if not text:
        return ""
        
    # 1. Analyse : Trouve les entités (Noms, Tel, Dates, etc.)
    # Note: On utilise le modèle par défaut (en) qui capte bien les entités nommées.
    # Pour un système de prod purement français, on configurerait un modèle 'fr'.
    results = analyzer.analyze(
        text=text, 
        entities=["PERSON", "PHONE_NUMBER", "EMAIL_ADDRESS", "DATE_TIME", "NRP"], # NRP = Numéro sécu/ID
        language='en'
    )
    
    # 2. Anonymisation : Remplace le texte original par les placeholders
    anonymized_result = anonymizer.anonymize(text=text, analyzer_results=results)
    
    return anonymized_result.text

def callback(ch, method, properties, body):
    """Fonction déclenchée à chaque message reçu de RabbitMQ"""
    try:
        # Décoder le message
        message = json.loads(body)
        doc_id = message.get("doc_id")
        raw_text = message.get("text", "")
        
        print(f" [->] Reçu Document ID {doc_id} ({len(raw_text)} caractères)")

        # --- CŒUR DU TRAITEMENT ---
        clean_text = process_text_anonymization(raw_text)
        # --------------------------

        # Préparer le message pour la suite du pipeline
        output_message = {
            "doc_id": doc_id,
            "original_text_masked": clean_text, # On envoie le texte propre
            "metadata": message.get("metadata", {}),
            "processed_at": time.time()
        }

        # Envoyer dans la file de sortie (pour le Service 3: Indexeur)
        ch.queue_declare(queue=OUTPUT_QUEUE, durable=True)
        ch.basic_publish(
            exchange='',
            routing_key=OUTPUT_QUEUE,
            body=json.dumps(output_message),
            properties=pika.BasicProperties(delivery_mode=2) # Message persistant
        )
        
        print(f" [<-] Document ID {doc_id} anonymisé et envoyé vers '{OUTPUT_QUEUE}'")
        print(f"      Aperçu: {clean_text[:100]}...") # Affiche le début pour vérifier

        # Confirmer le traitement à RabbitMQ (Ack)
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        print(f"ERREUR lors du traitement: {e}")
        # En cas d'erreur grave, on rejette le message sans le remettre dans la file (pour éviter une boucle infinie)
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

def start_service():
    """Boucle principale de connexion"""
    connection = None
    while True:
        try:
            print(f" [*] Connexion à RabbitMQ ({RABBITMQ_HOST})...")
            connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
            channel = connection.channel()

            # S'assurer que la queue d'entrée existe (si le Service 1 n'a jamais tourné)
            channel.queue_declare(queue=INPUT_QUEUE, durable=True)

            # QoS: On ne traite qu'un seul message à la fois pour ne pas surcharger le CPU
            channel.basic_qos(prefetch_count=1)
            
            channel.basic_consume(queue=INPUT_QUEUE, on_message_callback=callback)

            print(' [*] Service DeID en attente de documents. CTRL+C pour quitter.')
            channel.start_consuming()
            
        except pika.exceptions.AMQPConnectionError:
            print("RabbitMQ introuvable. Nouvelle tentative dans 5s...")
            time.sleep(5)
        except KeyboardInterrupt:
            print("Arrêt du service.")
            if connection: connection.close()
            break
        except Exception as e:
            print(f"Erreur inattendue: {e}")
            time.sleep(5)

if __name__ == "__main__":
    start_service()