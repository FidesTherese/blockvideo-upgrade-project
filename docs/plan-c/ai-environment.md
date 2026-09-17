# AI Development Environment

- Baseline: `main` / `00ae7cb3333d226bee97c742c7aa1db1dd81203c`
- OS: Windows 11
- Python: 3.12.12; project requires >=3.12
- uv: 0.12.15, invoked as `python -m uv`
- Node: 24.11.1; project requires >=20
- pnpm: 10.18.3, invoked through `npx`
- FFmpeg/FFprobe: 9.0.1
- Development model: current Pi session model; no product model is used in units 01–10
- External API/data budget: zero. Use synthetic data and fake providers only.
- Allowed: repository reads/writes, tests, builds, local servers, Git inspection.
- Approval required: paid API calls, publishing, deployment, push, production/user data, or secrets.
- Secrets: `.env` and API keys stay local and ignored. No final evaluation data is present.
- Backup: Git baseline and remote `origin`; generated storage is disposable and ignored.
