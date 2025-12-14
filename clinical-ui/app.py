import streamlit as st
import requests
import time

# --- CONFIGURATION DES PORTS ---
# Mettez ici les URLs de vos microservices
API_INGEST_URL = "http://127.0.0.1:8000/ingest/"
API_LLM_URL = "http://127.0.0.1:8001/ask/"

# Configuration de la page
# Simple status checks for services
def check_service(url):
    try:
        r = requests.get(f"{url}/health", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


st.set_page_config(page_title="Assistant Clinique IA", page_icon="🏥", layout="wide")
with st.sidebar.expander('Services status'):
    st.write('Ingestor (8000):', '✅' if check_service('http://127.0.0.1:8000') else '❌')
    st.write('LLM (8001):', '✅' if check_service('http://127.0.0.1:8001') else '❌')
    st.write('Synthese (DeID Worker):', '🟢 Running')
    st.write('RabbitMQ (15672):', '✅' if check_service('http://127.0.0.1:15672') else '❌')


# Titre et Header
st.title("🏥 Assistant Clinique RAG (Sécurisé & Local)")
st.markdown("""
Cet assistant permet d'interroger les dossiers patients de manière sécurisée.
**Architecture :** Ingestion -> Anonymisation -> Indexation -> LLM Local (Mistral).
""")

# --- BARRE LATÉRALE : UPLOAD DE FICHIERS ---
with st.sidebar:
    st.header("📂 Dossier Patient")
    uploaded_file = st.file_uploader("Ajouter un document (PDF, Text)", type=["pdf", "txt", "docx"])
    
    if uploaded_file is not None:
        if st.button("Traiter et Ingérer"):
            with st.spinner("Envoi au Service 1 (Ingestor)..."):
                try:
                    # Préparation de l'envoi
                    files = {"file": (uploaded_file.name, uploaded_file, uploaded_file.type)}
                    data = {"doc_type": "compte-rendu"}
                    
                    # Appel API Service 1
                    response = requests.post(API_INGEST_URL, files=files, data=data)
                    
                    if response.status_code == 200:
                        st.success("✅ Document transmis !")
                        st.info("Le pipeline asynchrone (DeID -> Indexer) est en cours...")
                        # Petit délai pour laisser le temps aux services de fond de bosser
                        progress_bar = st.progress(0)
                        for i in range(100):
                            time.sleep(0.05) # Simulation d'attente 5s
                            progress_bar.progress(i + 1)
                        st.success("Document prêt pour interrogation !")
                    else:
                        st.error(f"Erreur Ingestion : {response.text}")
                        
                except Exception as e:
                    st.error(f"Impossible de joindre le Service 1 : {e}")

    st.divider()
    st.caption("Statut des Services :")
    st.caption("🟢 Ingestor (8000)")
    st.caption("🟢 DeID (RabbitMQ)")
    st.caption("🟢 Indexer (RabbitMQ)")
    st.caption("🟢 LLM Mistral (8001)")

# --- ZONE PRINCIPALE : CHAT ---

# Initialisation de l'historique de chat dans la session
if "messages" not in st.session_state:
    st.session_state.messages = []

# Affichage de l'historique
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Zone de saisie utilisateur
if prompt := st.chat_input("Posez votre question sur le dossier patient..."):
    # 1. Afficher la question utilisateur
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # 2. Interroger le Service 4 (LLM)
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        message_placeholder.markdown("⏳ *Analyse du dossier en cours...*")
        
        try:
            # Appel API Service 4
            payload = {"question": prompt}
            response = requests.post(API_LLM_URL, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                answer = data.get("answer", "Pas de réponse.")
                sources = data.get("sources", [])
                
                # Formatage de la réponse avec les sources
                full_response = f"{answer}\n\n"
                if sources:
                    full_response += "---\n**Sources :** " + ", ".join(sources)
                
                message_placeholder.markdown(full_response)
                st.session_state.messages.append({"role": "assistant", "content": full_response})
            else:
                error_msg = f"Erreur LLM ({response.status_code}) : {response.text}"
                message_placeholder.error(error_msg)
                
        except Exception as e:
            message_placeholder.error(f"Erreur de connexion au Service LLM : {e}")
            st.error("Vérifiez que le service 'llm-qa' tourne bien sur le port 8001.")