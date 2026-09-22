# Shell Setup Notes (Windows)

- Default instructions in README use `cmd.exe` syntax. Escape long lines with caret `^`.
- PowerShell users: replace `^` with backtick `` ` `` or use single-line commands.
- Use `copy .env.example .env` on Windows to create your env file.
- Prefer WSL2 for a smoother UNIX-like experience when using CLI tools.

## Reserved device names

Windows reserves names like `CON`, `PRN`, `AUX`, `NUL`, `COM1`… Avoid creating files or folders with these names. If a repository contains such an entry (e.g., `nul`), some tools may error. Options:
- Work inside WSL2 where POSIX filenames are permitted.
- Remove or rename the offending entry locally if it’s not required.

## Quick checks

- Docker Desktop must be running. Verify:
```cmd
docker version
```
- Compose V2 is included with Docker Desktop. Verify:
```cmd
docker compose version
```
- If ports are busy (8000/5601/8081/8082/8083/9005), stop the conflicting apps or adjust `docker-compose.yml` ports.
