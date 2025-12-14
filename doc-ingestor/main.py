from fastapi import FastAPI, UploadFile, File, Depends, Form
from sqlalchemy.orm import Session
import shutil
import os

from database import engine, Base, get_db
import models
from processing import extract_text_from_file, publish_to_queue

# Création des tables dans la BDD
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="DocIngestor Service")

# Dossier temporaire pour stocker les fichiers uploadés avant traitement
UPLOAD_DIR = "temp_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.post("/ingest/")
async def ingest_document(
    file: UploadFile = File(...), 
    doc_type: str = Form(...), # ex: "CR_HOSPITALISATION"
    db: Session = Depends(get_db)
):
    # 1. Sauvegarder métadonnées en BDD (Status: PENDING)
    new_doc = models.DocumentMetadata(
        filename=file.filename,
        status="PENDING",
        doc_type=doc_type
    )
    db.add(new_doc)
    db.commit()
    db.refresh(new_doc)
    
    # 2. Sauvegarder le fichier physiquement (temporaire)
    file_path = f"{UPLOAD_DIR}/{new_doc.id}_{file.filename}"
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # 3. Extraire le texte via Tika
    extracted_text = extract_text_from_file(file_path)
    
    if not extracted_text:
        new_doc.status = "ERROR_EXTRACTION"
        db.commit()
        return {"error": "Impossible d'extraire le texte"}
    
    # 4. Envoyer dans RabbitMQ
    try:
        payload_meta = {"filename": file.filename, "type": doc_type}
        publish_to_queue(new_doc.id, extracted_text, payload_meta)
        
        # 5. Mise à jour statut (Status: PROCESSED)
        new_doc.status = "PROCESSED"
        db.commit()
        
        # Nettoyage (optionnel : supprimer le fichier temp)
        # os.remove(file_path)
        
        return {"message": "Ingestion réussie", "doc_id": new_doc.id}
        
    except Exception as e:
        new_doc.status = "ERROR_QUEUE"
        db.commit()
        return {"error": str(e)}

@app.get("/documents/")
def list_documents(db: Session = Depends(get_db)):
    return db.query(models.DocumentMetadata).all()


@app.get("/health")
def health():
    return {"status": "ok", "service": "doc-ingestor"}
