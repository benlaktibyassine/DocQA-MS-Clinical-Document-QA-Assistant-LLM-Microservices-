@echo off
TITLE Orchestrateur RAG Medical
color 0A

echo ========================================================
echo   DEMARRAGE DE L'ARCHITECTURE MICROSERVICES (HYBRIDE)
echo ========================================================
echo.

:: 1. Lancement de l'Infrastructure (Docker)
echo [1/6] Lancement de l'Infrastructure Docker (RabbitMQ, Postgres, Tika)...
docker-compose up -d postgres rabbitmq tika
echo    -> Attente de 10 secondes pour l'initialisation des bases...
timeout /t 10 /nobreak >nul

:: 2. Lancement Service 1 : Doc Ingestor
echo [2/6] Démarrage Doc Ingestor (API)...
start "Service 1: Doc Ingestor" cmd /k "cd doc-ingestor && venv\Scripts\activate &&  uvicorn main:app --reload"

:: 3. Lancement Service 2 : DeID (Anonymisation)
echo [3/6] Démarrage DeID Service...
start "Service 2: DeID Anonymizer" cmd /k "cd deid-service && venv\Scripts\activate && python anonymizer.py"

:: 4. Lancement Service 3 : Semantic Indexer
echo [4/6] Démarrage Semantic Indexer...
start "Service 3: Semantic Indexer" cmd /k "cd semantic-indexer && .venv\Scripts\activate && python indexer.py"

:: 5. Lancement Service 4 : LLM QA
echo [5/6] Démarrage LLM QA (RAG)...
:: Note: On pointe vers localhost pour Ollama
start "Service 4: LLM QA" cmd /k "cd llm-qa && venv\Scripts\activate && uvicorn main:app --reload --port 8001"

:: 6. Lancement Interface UI
echo [6/6] Démarrage Interface Clinique...
start "Service UI: Clinical App" cmd /k "cd clinical-ui && venv\Scripts\activate && streamlit run app.py"

echo.
echo ========================================================
echo   TOUT EST LANCE !
echo   - Swagger Ingestion : http://localhost:8000/docs
echo   - Swagger LLM       : http://localhost:8001/docs
echo   - Interface UI      : http://localhost:8501
echo   - RabbitMQ Admin    : http://localhost:15672
echo ========================================================
pause