# Copy the project's shared memory notes into the AI agent's memory for THIS folder.
#
#   powershell -ExecutionPolicy Bypass -File setup\seed_memory.ps1
#
# Claude Code keeps a project's memory under
#   %USERPROFILE%\.claude\projects\<folder path, every non-alphanumeric -> '-'>\memory\
# so memory written on another device does not travel with the folder.  The
# notes that matter are kept in knowledge\memory\ precisely so they do; this
# copies them where the agent looks.  Existing notes with the same name are
# overwritten; others are left alone.  CLAUDE.md already points any agent at
# knowledge\ -- this just makes "refresh your memory" work from the first turn.

$root = Split-Path -Parent $PSScriptRoot
$slug = ($root -replace '[^A-Za-z0-9]', '-')
$dest = Join-Path $env:USERPROFILE ".claude\projects\$slug\memory"
New-Item -ItemType Directory -Force -Path $dest | Out-Null

$src = Join-Path $root "knowledge\memory"
$n = 0
Get-ChildItem $src -Filter *.md | Where-Object { $_.Name -ne 'INDEX.md' } | ForEach-Object {
    Copy-Item $_.FullName (Join-Path $dest $_.Name) -Force
    $n++
}
# the index the agent loads every session: the folder first, then one line per note
$lines = @("- [START HERE]($root\START_HERE.md) - on 'refresh your memory': read START_HERE.md, then knowledge\PLAYBOOK.md; run setup\check.py")
$lines += Get-Content -Encoding UTF8 (Join-Path $src "INDEX.md") | Where-Object { $_ -like '- `[*' }
Set-Content -Path (Join-Path $dest "MEMORY.md") -Value $lines -Encoding utf8
Write-Host "memory seeded: $n notes -> $dest"
