pipeline {
    agent any

    environment {
        // Configuration for SonarQube
        // Ensure 'Local SonarQube' matches the name in Jenkins > Manage Jenkins > System > SonarQube servers
        SONARQUBE = 'Local SonarQube' 
        SONAR_TOKEN = credentials('sonar-token')
        
        PROJECT_KEY = 'DocQa'
        PROJECT_NAME = 'DocQa'
        PROJECT_VERSION = '1.0'
    }

    stages {
        stage('Checkout') {
            steps {
                // Checkout the current repository
                checkout scm
            }
        }

        stage('Setup Python Environment') {
            steps {
                script {
                    echo 'Initializing Virtual Environment...'
                    // Create venv if it doesn't exist
                    bat 'python -m venv venv'
                    
                    // Upgrade pip
                    bat 'venv\\Scripts\\python -m pip install --upgrade pip'
                    
                    // Install test dependencies
                    echo 'Installing test dependencies...'
                    bat 'venv\\Scripts\\pip install pytest pytest-cov'
                    
                    // Install dependencies for each microservice
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
                        // We use call logic to continue even if one fails? No, we should fail build.
                        bat "venv\\Scripts\\pip install -r ${service}\\requirements.txt"
                    }
                }
            }
        }

        stage('Run Tests') {
            steps {
                script {
                    echo 'Running Unit Tests...'
                    // Run pytest looking for tests in all subdirectories
                    // Generates JUnit XML for Jenkins to display
                    // Generates coverage XML for SonarQube
                    bat 'venv\\Scripts\\pytest --junitxml=test-results.xml --cov=. --cov-report=xml'
                }
            }
        }

        stage('SonarQube Analysis') {
            steps {
                // 'Local SonarQube' must match your Jenkins Global Configuration
                withSonarQubeEnv('Local SonarQube') {
                    // Start the scanner
                    // We reuse the local properties but ensure key params are passed
                    bat """
                        sonar-scanner ^
                        -Dsonar.projectKey=%PROJECT_KEY% ^
                        -Dsonar.projectName=%PROJECT_NAME% ^
                        -Dsonar.projectVersion=%PROJECT_VERSION% ^
                        -Dsonar.sources=. ^
                        -Dsonar.python.coverage.reportPaths=coverage.xml ^
                        -Dsonar.host.url=http://localhost:9000 ^
                        -Dsonar.login=%SONAR_TOKEN%
                    """
                }
            }
        }

        stage('Quality Gate') {
            steps {
                timeout(time: 1, unit: 'HOURS') {
                    // Stop pipeline if Quality Gate fails
                    waitForQualityGate abortPipeline: true
                }
            }
        }
    }

    post {
        always {
            // Publish test results to Jenkins
            junit 'test-results.xml'
            cleanWs()
        }
    }
}
