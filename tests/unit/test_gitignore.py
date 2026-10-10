"""T065: the real .env and drafts are never committed (FR-031, SC-009).

A leaked API token is the most expensive failure this feature could cause, and
the only thing standing between a filled-in .env and a public repository is one
line in this file.

T094/T095 corrected how the last two tests prove that. They asserted that `.env`
and draft files were **absent** from the working tree, which is the opposite of
the design: creating `.env` is the documented first-time setup (SC-009) and
writing into `drafts/` is what `prepare` exists to do (FR-012). Doing either
turned the suite red, so the gate the constitution requires to be green only
passed on a checkout nobody had used. What must never happen is those files
being *tracked*, so that is what is asserted now.
"""

import fnmatch
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GITIGNORE = ROOT / ".gitignore"


def _lines() -> list[str]:
    return [
        line.strip()
        for line in GITIGNORE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def test_gitignore_exists():
    assert GITIGNORE.is_file()


def test_the_real_env_file_is_ignored():
    assert ".env" in _lines()


def test_the_example_env_file_is_not_ignored():
    # `.env` must not be written as a pattern that also catches `.env.example`,
    # or a first-time user clones a repo with no example to copy.
    lines = _lines()
    assert ".env*" not in lines
    assert ".env.example" not in lines


def test_drafts_contents_are_ignored():
    lines = _lines()
    assert any(entry in lines for entry in ("drafts/", "drafts/*"))


def test_the_drafts_placeholder_is_kept():
    # The directory should survive a clone even though its contents do not.
    assert "!drafts/.gitkeep" in _lines()
    assert (ROOT / "drafts" / ".gitkeep").is_file()


def test_python_build_artifacts_are_ignored():
    lines = _lines()
    for pattern in ("__pycache__/", "*.egg-info/"):
        assert pattern in lines


# --- is a given path actually excluded? ---------------------------------
#
# Asserting a pattern appears somewhere in .gitignore does not prove it covers
# the file that matters. These evaluate the rule against a concrete path: via
# git when the checkout is a repository, and otherwise by applying the patterns
# directly, so the check still means something before `git init`.


def _git(*args: str) -> subprocess.CompletedProcess | None:
    """Run git at the repo root, or None when git cannot be invoked."""
    try:
        return subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _in_git_repo() -> bool:
    result = _git("rev-parse", "--git-dir")
    return result is not None and result.returncode == 0


def _is_tracked(relpath: str) -> bool:
    result = _git("ls-files", "--error-unmatch", "--", relpath)
    return result is not None and result.returncode == 0


def _ignored_by_patterns(relpath: str) -> bool:
    """Apply .gitignore to one path, for the subset of syntax this file uses.

    Later patterns win, and a leading "!" re-includes -- the two rules needed to
    get `drafts/*` plus `!drafts/.gitkeep` right.
    """
    name = relpath.rsplit("/", 1)[-1]
    verdict = False
    for pattern in _lines():
        negated = pattern.startswith("!")
        candidate = pattern[1:] if negated else pattern
        as_directory = candidate.rstrip("/") + "/" if candidate.endswith("/") else None
        if (
            fnmatch.fnmatch(relpath, candidate)
            or fnmatch.fnmatch(name, candidate)
            or (as_directory is not None and relpath.startswith(as_directory))
        ):
            verdict = not negated
    return verdict


def test_a_real_env_file_is_excluded_rather_than_absent():
    """T094: a filled-in .env is correct setup; being tracked is the failure."""
    assert _ignored_by_patterns(".env"), (
        ".gitignore does not exclude .env, so a filled-in token could be committed"
    )
    if not _in_git_repo():
        return
    ignored = _git("check-ignore", "-q", "--", ".env")
    assert ignored is not None and ignored.returncode == 0, (
        "git does not treat .env as ignored"
    )
    assert not _is_tracked(".env"), (
        ".env is tracked by git; assume the API token was committed and rotate it"
    )


def test_draft_files_are_excluded_rather_than_absent():
    """T095: `prepare` writes into drafts/; those files must not be tracked."""
    drafts = ROOT / "drafts"
    present = (
        sorted(p.name for p in drafts.iterdir() if p.is_file() and p.name != ".gitkeep")
        if drafts.is_dir()
        else []
    )

    # Check whatever is there now, plus a representative name so the rule is
    # still exercised on a checkout where nothing has been drafted yet.
    for name in [*present, "PROJ-123.yaml"]:
        relpath = f"drafts/{name}"
        assert _ignored_by_patterns(relpath), f".gitignore does not exclude {relpath}"
        if _in_git_repo():
            assert not _is_tracked(relpath), f"{relpath} is tracked by git"

    # The negation has to survive: the placeholder is the one file in drafts/
    # that must stay trackable, or the directory vanishes from a clone.
    assert not _ignored_by_patterns("drafts/.gitkeep")
