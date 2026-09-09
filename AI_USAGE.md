# AI usage disclosure

I used opencode (an interactive CLI coding agent) as a pair-programming partner through the whole task. I made every final decision and ran every command myself — nothing went into a commit without me executing and reading the result first.

- Tool/model: opencode
- Purpose: I leaned on it for exploring the repo, triaging the starter bugs, drafting the troubleshooting journal, crunching the three log files, writing `validate.py` / `failure_test.py` / `backup.sh` / `restore.sh` / the CI workflow, and drafting the reports (README, decisions, security review, this file).
- Files or decisions affected: `troubleshooting.md`, `log_analysis.md`, `docker-compose.yml`, `Dockerfile`, `nginx/nginx.conf`, `validate.py`, `failure_test.py`, `backup.sh`, `restore.sh`, `.github/workflows/ci.yml`, `.env.example`, `README.md`, `decisions.md`, `security_review.md`.
- What you changed or rejected: plenty. I threw out its first instance-counting approach (it miscounted blank lines — I switched to JSON parsing). I parked the `APP_HOST` fix, hit a live 502 because of it, then unparked it. I replaced its `grep '"status": "ready"'` CI check after CI went red (Flask emits compact JSON with no space). I added `--clean --if-exists` to its backup command after a restore blew up on `relation already exists`. I moved its heredoc snippets into a runnable script after pasting kept failing.
- How you independently verified it: I ran everything with my own hands — `validate.py` 11/11, `failure_test.py` 6/6, a full backup → wipe → restore round-trip, container-recreate persistence proof, `docker compose config`, and a green CI run. I read each diff before committing.
- Related commit: all commits after the `starter-v2.0.0` baseline are mine, AI-assisted as described above.
