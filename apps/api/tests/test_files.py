import pytest

from app.analysis.files import classify_file


@pytest.mark.parametrize(
    "path, language, category",
    [
        ("src/App.tsx", "TypeScript", "source"),
        ("backend/app/main.py", "Python", "source"),
        ("tests/test_api.py", "Python", "test"),
        ("src/components/Button.test.tsx", "TypeScript", "test"),
        ("pkg/server/handler_test.go", "Go", "test"),
        ("src/test/java/com/x/UserServiceTest.java", "Java", "test"),
        ("README.md", None, "docs"),
        ("docs/setup.txt", None, "docs"),
        (".github/workflows/ci.yml", None, "ci"),
        ("Dockerfile", None, "infra"),
        ("deploy/k8s/deployment.yaml", None, "infra"),
        ("main.tf", None, "infra"),
        ("package.json", None, "manifest"),
        ("requirements-dev.txt", None, "manifest"),
        ("package-lock.json", None, "lockfile"),
        ("frontend/yarn.lock", None, "lockfile"),
        ("node_modules/react/index.js", "JavaScript", "generated"),
        ("static/app.min.js", "JavaScript", "generated"),
        ("tsconfig.json", None, "config"),
        ("styles/main.scss", "HTML/CSS", "source"),
        ("assets/logo.png", None, "other"),
    ],
)
def test_classify_file(path, language, category):
    info = classify_file(path)
    assert (info.language, info.category) == (language, category)
