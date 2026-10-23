# mediplus - CI/CD file set

Copy these into the repo root (keeps the same layout):

| File | Purpose |
|---|---|
| `Jenkinsfile` | Checkout, Unit Tests, SAST (SonarQube + Bandit), pip-audit, Docker build, Trivy, DAST (ZAP), consolidated report, push, GitOps update |
| `scripts/consolidate_reports.py` | Merges every scan into `reports/SECURITY_SCAN_REPORT.md` |
| `Dockerfile`, `docker-entrypoint.sh`, `.dockerignore` | Image (gunicorn + WhiteNoise, non-root) |
| `requirements.txt` | Pinned deps (repo had none) |
| `mediplus/settings_container.py` | Env-driven overrides; `settings.py` is untouched |
| `mediplus/tests.py` | Smoke tests for the Unit Tests stage |
| `sonar-project.properties` | SonarQube project config (key `mediplus`) |
| `k8s/deployments.yaml`, `k8s/service.yaml` | App manifests (Jenkins rewrites the image tag) |
| `argocd/application.yaml` | ArgoCD app watching `k8s/` on `main` |

## Must fix in the app first (found while testing)
1. `admin_app/views.py` has no `userdelete`, but `admin_app/urls.py` routes to it -> Django cannot start.
   ```python
   def userdelete(request, id):
       data = user_details.objects.get(pk=id)
       data.delete()
       return redirect(userview)
   ```
2. There is no `login` view/route anywhere (header links to `login`, `redirect(login)` is used, `session['uid']` is never set).
3. `mediplus` app has no `migrations/` folder (entrypoint uses `--run-syncdb`; better: `python manage.py makemigrations mediplus` and commit).

## Jenkins placeholders to match your setup
`GITHUB_CREDS` (github-jenkins), `DOCKERHUB_CREDS` (dockerhub-credentials), `SONAR_SERVER` (sonarqube),
`SONAR_TOKEN_ID` (sonar-token), tool name `SonarScanner`, repo `https://github.com/VishnuMadhu13/mediplus.git`.

## Minikube / ArgoCD
```bash
kubectl create namespace mediplus
kubectl -n mediplus create secret generic mediplus-secret \
  --from-literal=DJANGO_SECRET_KEY="$(openssl rand -base64 48)"
kubectl apply -f argocd/application.yaml
minikube service mediplus -n mediplus
```
