# Security scan report - mediplus

Build: local-sandbox  |  Generated: 2026-10-23 07:44 UTC

## Summary

| Stage | Tool | Status | Findings |
|---|---|---|---|
| SAST | SonarQube | NOT RUN (no SONAR_HOST_URL/SONAR_TOKEN) | - |
| SAST | Bandit | FINDINGS | LOW 1 |
| SCA (dependency scan) | pip-audit | CLEAN | none |
| Container image | Trivy | NOT RUN - no report produced | - |
| DAST | OWASP ZAP baseline | NOT RUN - no report produced | - |

## SAST - Bandit

| Severity | Test | Location | Issue |
|---|---|---|---|
| LOW | B105 | ./mediplus/settings.py:24 | Possible hardcoded password: 'django-insecure-y7l(cti5k-!+u+!wo1236^h5+2a1v2g#s596t&ya!yhfct2e!e' |

## SCA (dependency scan) - pip-audit

No findings.

## Container image - Trivy

No report was produced for this scan. Treat as NOT RUN.

## DAST - OWASP ZAP baseline

No report was produced for this scan. Treat as NOT RUN.
