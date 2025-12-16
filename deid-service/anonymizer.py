import pika
import json
import time
import sys
import os
import logging # <--- AMÉLIORATION 1

# Import Presidio
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine

# --- CONFIGURATION LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("DeID-Service")

# --- CONFIGURATION ENVIRONNEMENT ---
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
INPUT_QUEUE = os.getenv("INPUT_QUEUE", "raw_documents_queue")
OUTPUT_QUEUE = os.getenv("OUTPUT_QUEUE", "clean_documents_queue")
# Choix du modèle de langue (fr recommandé pour la France)
NLP_LANG = os.getenv("NLP_LANG", "en") 

# Initialisation
logger.info(f"Chargement du modèle IA (Presidio) en langue '{NLP_LANG}'...")
try:
    analyzer = AnalyzerEngine()
    anonymizer = AnonymizerEngine()
    logger.info("Modèle chargé avec succès.")
except Exception as e:
    logger.critical(f"Erreur chargement modèle: {e}")
    logger.critical(f"Avez-vous installé le modèle Spacy ? (python -m spacy download {NLP_LANG}_core_web_lg)")
    sys.exit(1)

def process_text_anonymization(text):
    if not text: return ""
    
    # AMÉLIORATION 2 : Utilisation de la variable de langue
    results = analyzer.analyze(
        text=text, 
        entities=["PERSON", "PHONE_NUMBER", "EMAIL_ADDRESS", "DATE_TIME", "NRP", "LOCATION"],
        language=NLP_LANG
    )
    
    anonymized_result = anonymizer.anonymize(text=text, analyzer_results=results)
    return anonymized_result.text

def callback(ch, method, properties, body):
    try:
        message = json.loads(body)
        doc_id = message.get("doc_id", "UNKNOWN")
        raw_text = message.get("text", "")
        
        logger.info(f"[->] Reçu Doc ID {doc_id} ({len(raw_text)} chars)")

        # Traitement
        clean_text = process_text_anonymization(raw_text)

        output_message = {
            "doc_id": doc_id,
            "original_text_masked": clean_text,
            "metadata": message.get("metadata", {}),
            "processed_at": time.time()
        }

        # AMÉLIORATION 3 : Déclaration de la queue de sortie ici aussi par sécurité
        ch.queue_declare(queue=OUTPUT_QUEUE, durable=True)
        
        ch.basic_publish(
            exchange='',
            routing_key=OUTPUT_QUEUE,
            body=json.dumps(output_message),
            properties=pika.BasicProperties(delivery_mode=2)
        )
        
        logger.info(f"[<-] Doc ID {doc_id} anonymisé -> '{OUTPUT_QUEUE}'")
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except json.JSONDecodeError:
        logger.error("Message reçu invalide (pas un JSON)")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    except Exception as e:
        logger.error(f"Erreur traitement: {e}")
        # En prod, on pourrait mettre requeue=True avec un compteur d'essais
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

def start_service():
    while True:
        try:
            logger.info(f"Connexion à RabbitMQ ({RABBITMQ_HOST})...")
            connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
            channel = connection.channel()

            channel.queue_declare(queue=INPUT_QUEUE, durable=True)
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue=INPUT_QUEUE, on_message_callback=callback)

            logger.info('Service DeID démarré. En attente de documents...')
            channel.start_consuming()
            
        except pika.exceptions.AMQPConnectionError:
            logger.warning("RabbitMQ indisponible. Retentative dans 5s...")
            time.sleep(5)
        except KeyboardInterrupt:
            logger.info("Arrêt du service.")
            try: connection.close()
            except: pass
            break

if __name__ == "__main__":
    start_service()