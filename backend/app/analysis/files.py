import posixpath
import re
from dataclasses import dataclass
from typing import Optional

EXTENSION_LANGUAGES = {
    ".py": "Python", ".ipynb": "Jupyter Notebook",
    ".js": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".mts": "TypeScript", ".tsx": "TypeScript",
    ".vue": "Vue", ".svelte": "Svelte",
    ".go": "Go", ".java": "Java", ".kt": "Kotlin", ".kts": "Kotlin", ".scala": "Scala",
    ".rs": "Rust", ".rb": "Ruby", ".php": "PHP", ".cs": "C#",
    ".cpp": "C++", ".cc": "C++", ".cxx": "C++", ".hpp": "C++", ".hh": "C++",
    ".c": "C", ".h": "C", ".swift": "Swift", ".m": "Objective-C", ".dart": "Dart",
    ".sql": "SQL", ".html": "HTML/CSS", ".htm": "HTML/CSS",
    ".css": "HTML/CSS", ".scss": "HTML/CSS", ".sass": "HTML/CSS", ".less": "HTML/CSS",
    ".sh": "Shell Scripting", ".bash": "Shell Scripting", ".zsh": "Shell Scripting", ".ps1": "Shell Scripting",
    ".r": "R", ".lua": "Lua", ".ex": "Elixir", ".exs": "Elixir", ".hs": "Haskell", ".sol": "Solidity",
}

GENERATED_DIRS = {"node_modules", "vendor", "dist", "build", ".next", "target", "__pycache__", "venv", ".venv",
                  "site-packages", "coverage", "out"}
GENERATED_SUFFIXES = (".min.js", ".min.css", ".map", ".pb.go", "_pb2.py", ".snap", ".lock")
LOCKFILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "pipfile.lock", "go.sum",
             "cargo.lock", "gemfile.lock", "composer.lock", "uv.lock", "bun.lockb"}
MANIFESTS = {"package.json", "pyproject.toml", "pipfile", "go.mod", "pom.xml", "build.gradle", "build.gradle.kts",
             "cargo.toml", "gemfile", "composer.json", "pubspec.yaml"}
CI_DIRS = (".github/workflows/", ".circleci/", ".gitlab/")
CI_FILES = {".gitlab-ci.yml", "jenkinsfile", "azure-pipelines.yml", ".travis.yml"}
INFRA_DIRS = ("k8s/", "kubernetes/", "helm/", "terraform/", "deploy/", "infra/")
DOC_EXTENSIONS = {".md", ".mdx", ".rst", ".txt", ".adoc"}
CONFIG_EXTENSIONS = {".json", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".xml", ".env", ".conf"}
TEST_DIRS = {"test", "tests", "__tests__", "spec", "specs", "e2e"}
TEST_NAME = re.compile(
    r"(^test_.*\.py$|_test\.(py|go)$|\.(test|spec)\.(js|jsx|ts|tsx|mjs)$|Tests?\.(java|kt|cs)$)"
)

# Lines in these categories count as the user's own engineering work.
MEANINGFUL_CATEGORIES = {"source", "test", "infra", "ci"}
IGNORED_CATEGORIES = {"generated", "lockfile"}


@dataclass(frozen=True)
class FileInfo:
    path: str
    language: Optional[str]
    category: str


def classify_file(path: str) -> FileInfo:
    normalized = path.replace("\\", "/")
    lower = normalized.lower()
    name = posixpath.basename(lower)
    ext = posixpath.splitext(name)[1]
    segments = set(lower.split("/")[:-1])
    language = EXTENSION_LANGUAGES.get(ext)

    if segments & GENERATED_DIRS or name.endswith(GENERATED_SUFFIXES) and name not in LOCKFILES:
        category = "generated"
    elif name in LOCKFILES:
        category = "lockfile"
    elif name in MANIFESTS or (name.startswith("requirements") and ext == ".txt"):
        category = "manifest"
    elif lower.startswith(CI_DIRS) or name in CI_FILES:
        category = "ci"
    elif (name.startswith("dockerfile") or name.endswith(".dockerfile") or name.startswith("docker-compose")
          or name in {"compose.yaml", "compose.yml"} or ext in {".tf", ".tfvars"}
          or any(f"/{d}" in f"/{lower}" for d in INFRA_DIRS)):
        category = "infra"
    elif ext in DOC_EXTENSIONS or "docs" in segments or name.startswith(("license", "changelog")):
        category = "docs"
    elif language and (segments & TEST_DIRS or TEST_NAME.search(posixpath.basename(normalized))):
        category = "test"
    elif language:
        category = "source"
    elif ext in CONFIG_EXTENSIONS or name.startswith("."):
        category = "config"
    else:
        category = "other"

    return FileInfo(path=normalized, language=language, category=category)
