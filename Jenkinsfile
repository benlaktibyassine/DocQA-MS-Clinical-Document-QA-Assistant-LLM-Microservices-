pipeline {
    agent any

    environment {
        // Configuration SonarQube
        // 1. Crée un credential 'Secret text' ID: sonar-token
        SONAR_TOKEN = credentials('sonar-token')
        
        // 2. Assure-toi que ce nom correspond à ta config dans: Manage Jenkins > System > SonarQube servers
        SONAR_SERVER_NAME = 'Local SonarQube' 
        
        // Configuration du projet
        PROJECT_KEY = 'DocQa'
        PROJECT_NAME = 'DocQa'
        PROJECT_VERSION = '1.0'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Setup Python Environment') {
            steps {
                script {
                    echo 'Initializing Virtual Environment...'
                    // Crée le venv s'il n'existe pas
                    bat 'python -m venv venv'
                    
                    // Met à jour pip
                    bat 'venv\\Scripts\\python -m pip install --upgrade pip'
                    
                    // Installe les dépendances de test
                    echo 'Installing test dependencies...'
                    bat 'venv\\Scripts\\pip install pytest pytest-cov'
                    
                    // Installe les dépendances des microservices
                    def services = [
                        'deid-service', 
                        'doc-ingestor', 
                        'semantic-indexer', 
                        'synthese-comparative', 
                        'llm-qa', 
                        'clinical-ui'
                    ]
                    
                    for (service in services) {
                        echo "Installing dependencies for ${service}..."
                        // On utilise try/catch ou on laisse planter si un requirements.txt manque ? 
                        // Ici, on suppose que tous les fichiers existent.
                        bat "venv\\Scripts\\pip install -r ${service}\\requirements.txt"
                    }
                }
            }
        }

        stage('Run Tests') {
            steps {
                script {
                    echo 'Running Unit Tests...'
                    // Lance pytest et génère les rapports XML pour Jenkins et SonarQube
                    // --ignore=venv évite de scanner les fichiers de la librairie
                    bat 'venv\\Scripts\\pytest --junitxml=test-results.xml --cov=. --cov-report=xml --ignore=venv'
                }
            }
        }

        stage('SonarQube Analysis') {
            steps {
                script {
                    // RÉCUPÉRATION DE L'OUTIL SONAR SCANNER
                    // Assure-toi d'avoir configuré l'outil "SonarScanner" dans:
                    // Manage Jenkins > Global Tool Configuration > SonarQube Scanner
                    def scannerHome = tool 'SonarScanner' 
                    
                    withSonarQubeEnv(SONAR_SERVER_NAME) {
                        // Utilisation de scannerHome pour gérer les espaces dans les chemins (Alpha Electronics)
                        bat """
                            "${scannerHome}\\bin\\sonar-scanner" ^
                            -Dsonar.projectKey=%PROJECT_KEY% ^
                            -Dsonar.projectName=%PROJECT_NAME% ^
                            -Dsonar.projectVersion=%PROJECT_VERSION% ^
                            -Dsonar.sources=. ^
                            -Dsonar.exclusions=venv/**/*,**/__pycache__/**,**/*.xml ^
                            -Dsonar.python.coverage.reportPaths=coverage.xml ^
                            -Dsonar.login=%SONAR_TOKEN%
                        """
                    }
                }
            }
        }

        stage('Quality Gate') {
            steps {
                timeout(time: 1, unit: 'HOURS') {
                    // Attend la réponse du Webhook de SonarQube
                    waitForQualityGate abortPipeline: true
                }
            }
        }
    }

    post {
        always {
            // Publie les résultats des tests JUnit (visible dans l'onglet "Tests" du build)
            junit 'test-results.xml'
            
            // Nettoie l'espace de travail pour économiser de la place
            cleanWs()
        }
    }
}
