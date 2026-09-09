# Evidence and submission index

- Repository URL:
- Final commit:
- Matching CI run:
- Continuous 12-18 minute video URL:
- Challenge receipt ID:
- Starting video commit:
- Later documentation-only commits, if any:

| Requirement | File / output | Commit | Video timestamp |
|---|---|---|---|
| Investigate (journal) | `troubleshooting.md` (10 entries) | investigate + verify commits | demo of one historical-log finding |
| Log analysis | `log_analysis.md` (Q1–Q10, tables) | docs commits | demo of one historical-log finding |
| Two Flask behind NGINX | `docker-compose.yml`, `nginx/nginx.conf` | fix commits | build/start + health |
| Endpoints `/ /health /ready /records /counter` | `validate.py` 11/11 | feat commits | endpoint tests |
| Both backends via `/instance` | `validate.py` both-backends | feat commits | repeated `/instance` |
| Stop one backend + recover | `failure_test.py` 6/6 | feat commits | stop/recover segment |
| Record survives recreate | `backup.sh`/`restore.sh`, `curl /records` | feat commits | recreate segment |
| Validation + failure scripts | `validate.py`, `failure_test.py` | feat commits | script runs |
| Backup/restore proof | `backups/*.sql` (ignored), terminal output | feat commits | backup segment |
| CI green on push/PR | `.github/workflows/ci.yml`, Actions run | ci commits | — |
| Port 8080 → 8090 live | `PUBLIC_PORT`, `docker compose ps` | video commits | port-change segment |
| Third instance live | `docker-compose.yml` app-03, `/instance` ×3 | video commits | scale segment |
| `video_challenge.sh` fault fixed live | `.assessment/challenge.json` | video commits | challenge segment |
| Architecture diagram | `architecture.png` (final: 3 instances, 8090) | docs commits | repo tour |
| Decisions / security / AI | `decisions.md`, `security_review.md`, `AI_USAGE.md` | docs commits | repo tour |

Final state to match everywhere: three instances (app-01/02/03), public port 8090.
