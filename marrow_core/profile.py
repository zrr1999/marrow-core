"""Profile validation and setup utilities.

Validates and prepares profile directories for use with marrow-core.
Profile directories typically contain ``roles/``, ``context.d/``, and
``.opencode/`` subdirectories managed by external tooling such as role-forge.
"""

from __future__ import annotations

import re
import shutil
import stat
from pathlib import Path


def validate_context_providers(profile_dir: Path) -> list[str]:
    """Validate ``context.d/`` directory structure.

    Checks that the directory exists and that every ``.py`` file inside it
    compiles without syntax errors.

    Returns a list of human-readable issue strings (empty == pass).
    """
    issues: list[str] = []
    context_dir = profile_dir / "context.d"

    if not context_dir.is_dir():
        issues.append(f"missing context provider directory: {context_dir}")
        return issues

    providers = sorted(p for p in context_dir.iterdir() if p.is_file() and p.suffix == ".py")

    if not providers:
        issues.append("context.d/ contains no Python providers")
        return issues

    for provider in providers:
        try:
            compile(provider.read_text(encoding="utf-8"), str(provider), "exec")
        except SyntaxError as exc:
            issues.append(f"syntax error in {provider.name}: {exc}")

    return issues


def validate_role_references(profile_dir: Path) -> list[str]:
    """Validate role markdown cross-references under ``roles/``.

    Scans every ``.md`` file for references of the form ``<subdir>/<name>``
    where ``<subdir>`` is a top-level directory under ``roles/``, and reports
    any that do not correspond to an existing role file.

    Returns a list of human-readable issue strings (empty == pass).
    """
    issues: list[str] = []
    roles_dir = profile_dir / "roles"

    if not roles_dir.is_dir():
        return issues

    # Build set of valid role references from existing files.
    valid_refs: set[str] = set()
    for path in roles_dir.rglob("*.md"):
        rel = path.relative_to(roles_dir).with_suffix("")
        if len(rel.parts) == 1:
            valid_refs.add(rel.parts[0])
        elif len(rel.parts) == 2:
            valid_refs.add(f"{rel.parts[0]}/{rel.parts[1]}")

    # Discover top-level subdirectories to build the reference pattern.
    subdirs = sorted(
        d.name for d in roles_dir.iterdir() if d.is_dir() and not d.name.startswith(".")
    )
    if not subdirs:
        return issues

    subdir_alt = "|".join(re.escape(d) for d in subdirs)
    pattern = re.compile(rf"(?:{subdir_alt})/[a-z0-9][-a-z0-9]*")

    missing_refs: dict[str, list[str]] = {}
    for path in sorted(roles_dir.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        refs = sorted({m.group(0) for m in pattern.finditer(text)})
        missing = [ref for ref in refs if ref not in valid_refs]
        if missing:
            rel_path = str(path.relative_to(profile_dir))
            missing_refs[rel_path] = missing

    for rel_path, refs in missing_refs.items():
        issues.append(f"{rel_path}: unresolved references: {', '.join(refs)}")

    return issues


def prepare_home(
    profile_dir: Path,
    home: Path,
) -> None:
    """Set up bot home directory with symlinks and context providers.

    * Creates *home* and ``home/context.d/`` if they do not exist.
    * Symlinks ``profile_dir/.opencode`` → ``home/.opencode``.
    * Copies every ``.py`` provider from ``profile_dir/context.d/`` into
      ``home/context.d/`` with the executable bit set.
    """
    home.mkdir(parents=True, exist_ok=True)

    # Symlink .opencode configuration
    opencode_src = profile_dir / ".opencode"
    opencode_dst = home / ".opencode"
    if opencode_src.exists():
        if opencode_dst.is_symlink() or opencode_dst.exists():
            opencode_dst.unlink()
        opencode_dst.symlink_to(opencode_src)

    # Copy context providers
    src_context = profile_dir / "context.d"
    dst_context = home / "context.d"
    dst_context.mkdir(parents=True, exist_ok=True)

    if src_context.is_dir():
        for src in sorted(src_context.iterdir()):
            if not src.is_file() or src.suffix != ".py":
                continue
            dst = dst_context / src.name
            shutil.copy2(src, dst)
            dst.chmod(dst.stat().st_mode | stat.S_IXUSR)
