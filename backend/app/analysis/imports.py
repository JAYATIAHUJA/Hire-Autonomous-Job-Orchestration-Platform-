import posixpath
import re
from typing import Iterable, Optional

JS_PATTERNS = [
    re.compile(r"""(?:^|\s)from\s+['"]([^'"]+)['"]"""),
    re.compile(r"""^\s*import\s+['"]([^'"]+)['"]"""),
    re.compile(r"""\brequire\(\s*['"]([^'"]+)['"]\s*\)"""),
    re.compile(r"""\bimport\(\s*['"]([^'"]+)['"]\s*\)"""),
]
PY_IMPORT = re.compile(r"^\s*import\s+([\w.]+(?:\s+as\s+\w+)?(?:\s*,\s*[\w.]+(?:\s+as\s+\w+)?)*)")
PY_FROM = re.compile(r"^\s*from\s+([\w.]+)\s+import\b")
GO_IMPORT = re.compile(r"""^\s*(?:import\s+)?(?:[\w.]+\s+)?"([\w.\-/]+)"\s*$""")
JAVA_IMPORT = re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+)")
RUST_USE = re.compile(r"^\s*(?:pub\s+)?use\s+(\w+)::")
RUBY_REQUIRE = re.compile(r"""^\s*require\s+['"]([^'"]+)['"]""")
PHP_USE = re.compile(r"^\s*use\s+([\w\\]+)")
CSHARP_USING = re.compile(r"^\s*using\s+([\w.]+)\s*;")
DART_IMPORT = re.compile(r"""^\s*import\s+['"]package:([\w]+)/""")

JS_LANGUAGES = {"JavaScript", "TypeScript", "Vue", "Svelte"}


def added_lines(patch: Optional[str]) -> Iterable[str]:
    for line in (patch or "").splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            yield line[1:]


def _normalize_js(spec: str) -> Optional[str]:
    if spec.startswith((".", "/", "@/", "~/", "#")):
        return None
    if spec.startswith("node:"):
        return "node"
    parts = spec.split("/")
    return "/".join(parts[:2]) if spec.startswith("@") else parts[0]


def extract_added_imports(language: Optional[str], patch: Optional[str]) -> set[str]:
    """Packages/modules imported on lines this change added (not the whole file)."""
    found: set[str] = set()
    for line in added_lines(patch):
        if language == "Jupyter Notebook":
            line = re.sub(r'\\n",?\s*$', "", re.sub(r'^\s*"', "", line))
        if language in JS_LANGUAGES:
            for pattern in JS_PATTERNS:
                for spec in pattern.findall(line):
                    if name := _normalize_js(spec):
                        found.add(name)
        elif language in {"Python", "Jupyter Notebook"}:
            if m := PY_FROM.match(line):
                if not m.group(1).startswith("."):
                    found.add(m.group(1).split(".")[0])
            elif m := PY_IMPORT.match(line):
                for part in m.group(1).split(","):
                    found.add(part.strip().split()[0].split(".")[0])
        elif language == "Go":
            if m := GO_IMPORT.match(line):
                path = m.group(1)
                parts = path.split("/")
                found.add("/".join(parts[:3]) if "." in parts[0] else path)
        elif language in {"Java", "Kotlin", "Scala"}:
            if m := JAVA_IMPORT.match(line):
                found.add(m.group(1))
        elif language == "Rust":
            if (m := RUST_USE.match(line)) and m.group(1) not in {"std", "core", "crate", "self", "super"}:
                found.add(m.group(1))
        elif language == "Ruby":
            if m := RUBY_REQUIRE.match(line):
                found.add(m.group(1).split("/")[0])
        elif language == "PHP":
            if m := PHP_USE.match(line):
                found.add(m.group(1).lstrip("\\"))
        elif language == "C#":
            if m := CSHARP_USING.match(line):
                found.add(m.group(1))
        elif language == "Dart":
            if m := DART_IMPORT.match(line):
                found.add(m.group(1))
    return found


NPM_DEP = re.compile(r"""^\s*"(@?[\w.\-]+(?:/[\w.\-]+)?)"\s*:\s*"(?:[\^~>=<]*\d[^"]*|\*|latest|workspace:[^"]*)"\s*,?\s*$""")
REQUIREMENT = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9_.\-]*)\s*(?:\[[^\]]*\])?\s*(?:[=<>!~;@].*)?$")
PYPROJECT_LIST_DEP = re.compile(r"""^\s*["']([A-Za-z0-9][A-Za-z0-9_.\-]*)(?:\[[^\]]*\])?\s*(?:[=<>!~;][^"']*)?["']\s*,?\s*$""")
TOML_KEY_DEP = re.compile(r"""^\s*([A-Za-z0-9][A-Za-z0-9_.\-]*)\s*=\s*(?:["'][\^~>=<*\d]|\{)""")
GO_REQUIRE = re.compile(r"^\s*(?:require\s+)?([\w.\-]+\.[a-z]+/[\w.\-/]+)\s+v\d")
GEM = re.compile(r"""^\s*gem\s+['"]([^'"]+)['"]""")
MAVEN_ARTIFACT = re.compile(r"^\s*<artifactId>([^<]+)</artifactId>")
GRADLE_DEP = re.compile(r"""(?:implementation|api|compile|runtimeOnly|testImplementation)\s*\(?\s*['"]([\w.\-]+):([\w.\-]+)""")
NON_DEPENDENCY_KEYS = {"name", "version", "description", "python", "readme", "license", "authors", "edition",
                       "requires-python", "homepage", "repository", "node", "npm"}


def extract_added_dependencies(path: str, patch: Optional[str]) -> set[str]:
    name = posixpath.basename(path.replace("\\", "/").lower())
    deps: set[str] = set()
    for line in added_lines(patch):
        if line.strip().startswith(("#", "//", "-r", "-e", "--")):
            continue
        if name in {"package.json", "composer.json"}:
            m = NPM_DEP.match(line)
        elif name.startswith("requirements") and name.endswith(".txt"):
            m = REQUIREMENT.match(line)
        elif name in {"pyproject.toml", "pipfile", "cargo.toml"}:
            m = PYPROJECT_LIST_DEP.match(line) or TOML_KEY_DEP.match(line)
        elif name == "go.mod":
            m = GO_REQUIRE.match(line)
        elif name == "gemfile":
            m = GEM.match(line)
        elif name == "pom.xml":
            m = MAVEN_ARTIFACT.match(line)
        elif name.startswith("build.gradle"):
            if g := GRADLE_DEP.search(line):
                deps.add(f"{g.group(1)}:{g.group(2)}".lower())
            continue
        else:
            m = None
        if m and m.group(1).lower() not in NON_DEPENDENCY_KEYS:
            deps.add(m.group(1).lower())
    return deps
