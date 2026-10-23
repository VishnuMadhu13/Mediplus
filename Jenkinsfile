pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }

    parameters {
        booleanParam(name: 'ENFORCE_SCANS', defaultValue: false,
                     description: 'Fail the build on Trivy HIGH/CRITICAL findings')
    }

    environment {
        APP_NAME        = 'takecare'
        DOCKERHUB_USER  = 'vishnumadhu13'
        IMAGE           = "${DOCKERHUB_USER}/${APP_NAME}"
        TAG             = "${BUILD_NUMBER}"
        REPO_HOST_PATH  = 'github.com/VishnuMadhu13/takecare.git'
        SONAR_HOST_URL  = 'http://3.25.190.60:9000'      // adjust to your SonarQube container/service name
        DOCKER_NETWORK  = 'ubuntu_default'             // docker network shared by Jenkins + SonarQube
        GIT_CRED        = 'github-jenkins'
        DOCKERHUB_CRED  = 'docker-cred'      // adjust to your Docker Hub credential id
        SONAR_CRED      = 'sonar-token'                // Secret text credential with SonarQube token
        PYTHONDONTWRITEBYTECODE = '1'
    }

    stages {

        stage('Checkout') {
            steps {
                checkout scm
                sh 'git log -1 --pretty=oneline'
                sh 'git clean -ffdx'
            }
        }

        stage('Unit Tests') {
            agent { docker { image 'python:3.10-slim-bookworm'; args '-u root'; reuseNode true } }
            steps {
                sh '''
                    apt-get update -qq
                    apt-get install -y -qq --no-install-recommends build-essential pkg-config default-libmysqlclient-dev
                    pip install --no-cache-dir -r requirements.txt
                    export DB_ENGINE=sqlite
                    python manage.py check
                    python manage.py test --noinput
                    chmod -R a+rwX "$WORKSPACE" || true
                '''
            }
        }

        stage('SAST') {
            parallel {
                stage('SonarQube') {
                    agent { docker { image 'sonarsource/sonar-scanner-cli:latest'
                                     args "-u root --entrypoint='' --network ${DOCKER_NETWORK}"
                                     reuseNode true } }
                    steps {
                        withCredentials([string(credentialsId: "${SONAR_CRED}", variable: 'SONAR_TOKEN')]) {
                            sh 'sonar-scanner -Dsonar.qualitygate.wait=true -Dsonar.qualitygate.timeout=300'
                        }
                    }
                }
                stage('Bandit') {
                    agent { docker { image 'python:3.10-slim-bookworm'; args '-u root'; reuseNode true } }
                    steps {
                        sh '''
                            pip install --no-cache-dir bandit
                            bandit -r . -x ./venv,./.venv,./static,./staticfiles,./media \
                                   -f json -o bandit-report.json || true
                            chmod -R a+rwX "$WORKSPACE" || true
                        '''
                    }
                    post { always { archiveArtifacts artifacts: 'bandit-report.json', allowEmptyArchive: true } }
                }
            }
        }

        stage('Dependency Scan') {
            agent { docker { image 'python:3.10-slim-bookworm'; args '-u root'; reuseNode true } }
            steps {
                // --no-deps + --disable-pip: audits the pinned list without building mysqlclient
                sh '''
                    pip install --no-cache-dir pip-audit
                    pip-audit -r requirements.txt --no-deps --disable-pip -f json -o pip-audit.json || true
                    pip-audit -r requirements.txt --no-deps --disable-pip || true
                    chmod -R a+rwX "$WORKSPACE" || true
                '''
            }
            post { always { archiveArtifacts artifacts: 'pip-audit.json', allowEmptyArchive: true } }
        }

        stage('Docker Build') {
            steps {
                sh 'docker build -t $IMAGE:$TAG -t $IMAGE:latest .'
            }
        }

        stage('Trivy Image Scan') {
            steps {
                script {
                    def exitCode = params.ENFORCE_SCANS ? 1 : 0
                    sh """
                        docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v trivy-cache:/root/.cache/ \
                            aquasec/trivy:latest image --severity HIGH,CRITICAL --exit-code 0 --no-progress --quiet \
                            --format json ${IMAGE}:${TAG} > trivy-report.json
                        RC=0
                        docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v trivy-cache:/root/.cache/ \
                            aquasec/trivy:latest image --severity HIGH,CRITICAL --exit-code ${exitCode} --no-progress --quiet \
                            ${IMAGE}:${TAG} > trivy-report.txt || RC=\$?
                        cat trivy-report.txt
                        exit \$RC
                    """
                }
            }
            post { always { archiveArtifacts artifacts: 'trivy-report.*', allowEmptyArchive: true } }
        }

        stage('DAST (OWASP ZAP)') {
            steps {
                sh '''
                    NET=dast-net-${BUILD_NUMBER}
                    APP=takecare-dast-${BUILD_NUMBER}
                    ZAP=zap-${BUILD_NUMBER}
                    VOL=zap-wrk-${BUILD_NUMBER}
                    cleanup() {
                        docker rm -f $APP $ZAP >/dev/null 2>&1 || true
                        docker network rm $NET >/dev/null 2>&1 || true
                        docker volume rm $VOL >/dev/null 2>&1 || true
                    }
                    trap cleanup EXIT

                    docker network create $NET
                    docker volume create $VOL
                    docker run --rm -u root -v $VOL:/zap/wrk ghcr.io/zaproxy/zaproxy:stable chmod 777 /zap/wrk

                    docker run -d --name $APP --network $NET \
                        -e DB_ENGINE=sqlite -e DEBUG=False -e ALLOWED_HOSTS='*' -e RUN_MIGRATIONS=1 \
                        $IMAGE:$TAG

                    for i in $(seq 1 30); do
                        docker exec $APP python -c "import socket; socket.create_connection(('localhost',8000),2)" && break
                        sleep 2
                    done

                    docker run --name $ZAP --network $NET -v $VOL:/zap/wrk -t ghcr.io/zaproxy/zaproxy:stable \
                        zap-baseline.py -t http://$APP:8000 -r zap-report.html -J zap-report.json -I || true
                    docker cp $ZAP:/zap/wrk/zap-report.html ./zap-report.html
                    docker cp $ZAP:/zap/wrk/zap-report.json ./zap-report.json
                    test -s zap-report.html
                '''
            }
            post { always { archiveArtifacts artifacts: 'zap-report.*', allowEmptyArchive: true } }
        }

        stage('Consolidated Security Report') {
            agent { docker { image 'python:3.10-slim-bookworm'
                            args "--network ${DOCKER_NETWORK}"
                            reuseNode true } }
            steps {
                withCredentials([string(credentialsId: "${SONAR_CRED}", variable: 'SONAR_TOKEN')]) {
                    sh '''python scripts/generate_security_report.py \
                            --build "$BUILD_NUMBER" --image "$IMAGE:$TAG" \
                            --sonar-host "$SONAR_HOST_URL" --sonar-project takecare \
                            --sonar-url "http://3.107.90.61:9000/dashboard?id=takecare"'''
                }
            }
            post { always { archiveArtifacts artifacts: 'security-report.html', allowEmptyArchive: true } }
        }

        stage('Push Image') {
            steps {
                withCredentials([usernamePassword(credentialsId: "${DOCKERHUB_CRED}",
                                                  usernameVariable: 'DH_USER', passwordVariable: 'DH_PASS')]) {
                    sh '''
                        echo "$DH_PASS" | docker login -u "$DH_USER" --password-stdin
                        docker push $IMAGE:$TAG
                        docker push $IMAGE:latest
                        docker logout
                    '''
                }
            }
        }

        stage('Update Manifest (GitOps)') {
            steps {
                withCredentials([usernamePassword(credentialsId: "${GIT_CRED}",
                                                  usernameVariable: 'GIT_USER', passwordVariable: 'GIT_PASS')]) {
                    sh '''
                        git config user.email "jenkins@takecare.local"
                        git config user.name  "jenkins"
                        git fetch https://${GIT_USER}:${GIT_PASS}@${REPO_HOST_PATH} main
                        git checkout -B main FETCH_HEAD

                        sed -i "s|image: ${IMAGE}:.*|image: ${IMAGE}:${TAG}|" k8s/deployments.yaml
                        grep "image: ${IMAGE}" k8s/deployments.yaml

                        git add k8s/deployments.yaml
                        git diff --cached --quiet || git commit -m "ci: deploy ${IMAGE}:${TAG} [skip ci]"
                        git push https://${GIT_USER}:${GIT_PASS}@${REPO_HOST_PATH} main
                    '''
                }
            }
        }
    }

    post {
        always {
            sh 'docker image prune -f || true'
        }
        success { echo "Pushed ${IMAGE}:${TAG}; ArgoCD will sync k8s/ to Minikube." }
        failure { echo 'Pipeline failed - check the stage logs above.' }
    }
}