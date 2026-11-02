# Windows development with WSL2

Project Forge defaults Windows development to WSL2 when the Project does not require native Windows execution.

Recommended shape:

- Windows hosts desktop applications such as VS Code, browsers, and Docker Desktop.
- WSL2 (Ubuntu by default) hosts Git repositories, shells, language runtimes, package managers, Project Forge tooling, build/test commands, and the Docker CLI.
- Repositories live in the WSL Linux filesystem, normally `~/projects/<repository>`, rather than under `/mnt/c/...`.
- Docker Desktop uses its WSL2 backend with WSL integration enabled for the selected distro. Do not install a second Docker Engine inside WSL just to make Docker commands work there.

Native Windows remains supported when a material Project requirement demands it, such as Windows-specific applications/drivers, Windows containers, or a required native-Windows toolchain.

## Setup and migrate existing Windows checkouts

Run the migration utility from PowerShell on Windows.

Preview/setup checks only:

```powershell
.\tools\windows\project-forge-wsl2.ps1 -InstallMissing
```

Setup plus repository migration from a folder containing one or more Git repositories:

```powershell
.\tools\windows\project-forge-wsl2.ps1 `
  -InstallMissing `
  -MigrateRepositories `
  -SourceRoot "C:\path\to\projects"
```

The default destination is `~/projects` inside Ubuntu. Override it with `-DestinationRoot` or choose another installed distro with `-Distro`.

The utility intentionally does **not** delete the Windows source checkout. For each repository it requires a clean source working tree by default, creates a Linux-native checkout in WSL, restores the original `origin`, and verifies the destination HEAD and working-tree state. Dirty repositories and existing destinations are skipped instead of guessed through.

If WSL or Ubuntu must be installed, Windows may require a restart or Ubuntu first-run initialization. In that case, complete the OS/distro step and rerun the same command.

Docker Desktop installation can be requested with `-InstallMissing`, but Docker Desktop must be running and WSL integration must be enabled for the selected distro before the Docker-in-WSL readiness check can pass.

After migration, open the repository from inside WSL:

```bash
cd ~/projects/<repository>
code .
```

Then run the Project's normal Project Forge/project setup and readiness checks from WSL.

## Rollback

Migration is non-destructive. Until you explicitly remove the old checkout, rollback simply means stop using the WSL checkout and return to the original Windows repository. Do not delete the Windows copy until the migrated Project has passed its normal development, build/test, and Docker readiness checks.
