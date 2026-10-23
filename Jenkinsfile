pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }

    environment {
        APP_NAME       = 'mediplus'
        IMAGE          = 'vishnumadhu13/mediplus'
        IMAGE_TAG      = "${env.BUILD_NUMBER}"
        REPO_URL       = 'https://github.com/VishnuMadhu13/mediplus.git'
        SONAR_HOST_URL  = 'http://3.25.190.60:9000'
        GIT_BRANCH_CI  = 'main'
        // Jenkins credential IDs - change to match your Jenkins
        GITHUB_CREDS   = 'github-jenkins'
        DOCKERHUB_CREDS = 'docker-cred'
        SONAR_TOKEN_ID = 'sonar-token'      // "Secret text" credential holding the Sonar token
        // CI-only values for unit tests / DAST container (not used in production)
        DJANGO_SETTINGS_MODULE = 'mediplus.settings_container'
        CI_SECRET_KEY  = 'ci-only-not-a-real-secret'
    }

    stages {
        stage('Checkout') {
            steps {
                git branch: "${GIT_BRANCH_CI}", credentialsId: "${GITHUB_CREDS}", url: "${REPO_URL}"
                sh 'mkdir -p reports/zap'
            }
        }

        stage('Unit Tests') {
            agent { docker { image 'python:3.12-slim'; reuseNode true; args '-e HOME=/tmp -e PYTHONUSERBASE=/tmp/pyuser' } }
            environment { DJANGO_SECRET_KEY = "${CI_SECRET_KEY}"; SQLITE_PATH = '/tmp/test.sqlite3' }
            steps {
                sh '''
                    export PATH="$PATH:/tmp/pyuser/bin"
                    pip install --user -q -r requirements.txt
                    python manage.py check
                    python manage.py test
                '''
            }
        }

        stage('SAST') {
            parallel {
                stage('SonarQube') {
                    steps {
                        script { scannerHome = tool 'SonarScanner' }
                        withSonarQubeEnv("${SONAR_SERVER}") {
                            sh "${scannerHome}/bin/sonar-scanner -Dsonar.projectKey=mediplus"
                        }
                        timeout(time: 10, unit: 'MINUTES') {
                            waitForQualityGate abortPipeline: true
                        }
                    }
                }
                stage('Bandit') {
                    agent { docker { image 'python:3.12-slim'; reuseNode true; args '-e HOME=/tmp -e PYTHONUSERBASE=/tmp/pyuser' } }
                    steps {
                        catchError(buildResult: 'UNSTABLE', stageResult: 'UNSTABLE') {
                            sh '''
                                export PATH="$PATH:/tmp/pyuser/bin"
                                pip install --user -q bandit
                                bandit -r . -x ./.vscode,./reports,./staticfiles,./k8s \
                                    -f json -o reports/bandit.json || BANDIT_RC=$?
                                bandit -r . -x ./.vscode,./reports,./staticfiles,./k8s \
                                    -f txt -o reports/bandit.txt || true
                                test -s reports/bandit.json
                                exit ${BANDIT_RC:-0}
                            '''
                        }
                    }
                }
            }
        }

        stage('Dependency Scan') {
            agent { docker { image 'python:3.12-slim'; reuseNode true; args '-e HOME=/tmp -e PYTHONUSERBASE=/tmp/pyuser' } }
            steps {
                catchError(buildResult: 'UNSTABLE', stageResult: 'UNSTABLE') {
                    sh '''
                        export PATH="$PATH:/tmp/pyuser/bin"
                        pip install --user -q pip-audit
                        pip-audit -r requirements.txt --no-deps --disable-pip \
                            -f json -o reports/pip-audit.json || AUDIT_RC=$?
                        test -s reports/pip-audit.json
                        exit ${AUDIT_RC:-0}
                    '''
                }
            }
        }

        stage('Docker Build') {
            steps {
                sh 'docker build -t ${IMAGE}:${IMAGE_TAG} -t ${IMAGE}:latest .'
            }
        }

        stage('Trivy Image Scan') {
            steps {
                catchError(buildResult: 'UNSTABLE', stageResult: 'UNSTABLE') {
                    // stdout redirect (no bind mount) so it works when Jenkins itself runs in a container
                    sh '''
                        docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
                            aquasec/trivy:latest image --quiet --format json \
                            --severity CRITICAL,HIGH,MEDIUM --ignore-unfixed \
                            ${IMAGE}:${IMAGE_TAG} > reports/trivy-image.json
                        test -s reports/trivy-image.json
                    '''
                }
            }
        }

        stage('DAST (OWASP ZAP)') {
            steps {
                sh '''
                    NET=mediplus-dast-${BUILD_NUMBER}
                    APP=mediplus-app-${BUILD_NUMBER}
                    ZAP=mediplus-zap-${BUILD_NUMBER}
                    docker network create $NET

                    docker run -d --name $APP --network $NET --network-alias mediplus-app \
                        -e DJANGO_SECRET_KEY=${CI_SECRET_KEY} \
                        -e DJANGO_ALLOWED_HOSTS=mediplus-app,localhost \
                        ${IMAGE}:${IMAGE_TAG}

                    ok=0
                    for i in $(seq 1 30); do
                        if docker run --rm --network $NET curlimages/curl:8.10.1 -fsS -o /dev/null http://mediplus-app:8000/index; then ok=1; break; fi
                        sleep 3
                    done
                    if [ "$ok" != 1 ]; then echo "App did not become ready"; docker logs $APP; exit 1; fi

                    # Named volume + docker cp (a bind mount of $WORKSPACE breaks when Jenkins runs in a container)
                    docker run --name $ZAP --network $NET -u 0 -v zap-wrk-${BUILD_NUMBER}:/zap/wrk \
                        ghcr.io/zaproxy/zaproxy:stable \
                        zap-baseline.py -t http://mediplus-app:8000/index \
                        -r zap-report.html -J zap-report.json -w zap-report.md -I || true

                    docker cp $ZAP:/zap/wrk/. reports/zap/
                    # Fail loudly instead of staying green with no report
                    test -s reports/zap/zap-report.json
                '''
            }
            post {
                always {
                    sh '''
                        docker rm -f mediplus-app-${BUILD_NUMBER} mediplus-zap-${BUILD_NUMBER} 2>/dev/null || true
                        docker network rm mediplus-dast-${BUILD_NUMBER} 2>/dev/null || true
                        docker volume rm zap-wrk-${BUILD_NUMBER} 2>/dev/null || true
                    '''
                }
            }
        }

        stage('Consolidated Security Report') {
            agent { docker { image 'python:3.12-slim'; reuseNode true; args '-e HOME=/tmp' } }
            steps {
                withSonarQubeEnv("${SONAR_SERVER}") {
                    withCredentials([string(credentialsId: "${SONAR_TOKEN_ID}", variable: 'SONAR_TOKEN')]) {
                        sh 'python scripts/consolidate_reports.py --dir reports --project ${APP_NAME} --build ${BUILD_NUMBER}'
                    }
                }
            }
            post {
                always {
                    archiveArtifacts artifacts: 'reports/**', allowEmptyArchive: true
                }
            }
        }

        stage('Push Image') {
            steps {
                withCredentials([usernamePassword(credentialsId: "${DOCKERHUB_CREDS}", usernameVariable: 'DH_USER', passwordVariable: 'DH_PASS')]) {
                    sh '''
                        echo "$DH_PASS" | docker login -u "$DH_USER" --password-stdin
                        docker push ${IMAGE}:${IMAGE_TAG}
                        docker push ${IMAGE}:latest
                        docker logout
                    '''
                }
            }
        }

        stage('Update Manifest (GitOps)') {
            steps {
                withCredentials([usernamePassword(credentialsId: "${GITHUB_CREDS}", usernameVariable: 'GH_USER', passwordVariable: 'GH_TOKEN')]) {
                    sh '''
                        AUTH="AUTHORIZATION: basic $(printf '%s:%s' "$GH_USER" "$GH_TOKEN" | base64 | tr -d '\\n')"
                        git config user.email "jenkins@mediplus.local"
                        git config user.name  "jenkins"
                        git -c http.extraheader="$AUTH" fetch origin ${GIT_BRANCH_CI}
                        git checkout -B ${GIT_BRANCH_CI} origin/${GIT_BRANCH_CI}

                        sed -i "s|image: ${IMAGE}:.*|image: ${IMAGE}:${IMAGE_TAG}|" k8s/deployments.yaml
                        grep "image: ${IMAGE}:${IMAGE_TAG}" k8s/deployments.yaml

                        git add k8s/deployments.yaml
                        git commit -m "ci: deploy ${IMAGE}:${IMAGE_TAG} [skip ci]" || { echo "nothing to commit"; exit 0; }
                        git -c http.extraheader="$AUTH" push origin ${GIT_BRANCH_CI}
                    '''
                }
            }
        }
    }

    post {
        always { sh 'docker image prune -f || true' }
    }
}
