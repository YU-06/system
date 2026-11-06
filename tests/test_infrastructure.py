import importlib.util
import json
from pathlib import Path

import pytest
import yaml
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def environment_initializer():
    path = ROOT / "infra/scripts/init_env.py"
    spec = importlib.util.spec_from_file_location("init_env", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.initialize_environment


def test_environment_initialization_generates_secrets_without_overwriting(tmp_path: Path):
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    (tmp_path / ".env.example").write_text(example, encoding="utf-8")
    initialize = environment_initializer()
    path = initialize(tmp_path)
    values = dotenv_values(path)
    assert len(values["POSTGRES_PASSWORD"] or "") == 64
    assert len(values["MINIO_ROOT_PASSWORD"] or "") == 64
    assert values["POSTGRES_PASSWORD"] != values["MINIO_ROOT_PASSWORD"]
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        initialize(tmp_path)
    assert path.read_bytes() == original
    assert (tmp_path / ".env.example").read_text(encoding="utf-8") == example


def test_compose_has_real_dependencies_health_checks_and_no_unused_redis():
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    services = compose["services"]
    assert set(services) == {
        "postgres",
        "object-storage",
        "backend-migrate",
        "backend",
        "web",
        "ml-inference",
    }
    assert services["backend"]["environment"]["POSTGRES_HOST"] == "postgres"
    assert services["backend"]["environment"]["ObjectStorage__Provider"] == "Minio"
    assert (
        services["backend"]["depends_on"]["backend-migrate"]["condition"]
        == "service_completed_successfully"
    )
    for name, service in services.items():
        if name != "backend-migrate":
            assert service["healthcheck"]["test"]
        for port in service.get("ports", []):
            assert port.startswith("127.0.0.1:")
        assert "env_file" not in service
    assert "POSTGRES_PASSWORD" not in services["ml-inference"]["environment"]
    assert "MINIO_ROOT_PASSWORD" not in services["ml-inference"]["environment"]
    assert services["ml-inference"]["volumes"] == ["./artifacts/models:/models:ro"]


def test_all_application_images_are_non_root_and_have_health_checks():
    for relative in (
        "apps/backend/Dockerfile",
        "apps/web/Dockerfile",
        "services/ml-inference/Dockerfile",
        "infra/minio/Dockerfile",
    ):
        content = (ROOT / relative).read_text(encoding="utf-8")
        assert "HEALTHCHECK " in content
        assert "USER " in content
        assert "COPY . ." not in content
    minio = (ROOT / "infra/minio/Dockerfile").read_text(encoding="utf-8")
    assert "git rev-parse HEAD" in minio
    assert "9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a" in minio
    ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert {".env", ".env.*", "data", "artifacts", ".git"} <= set(ignored)


def test_ci_contains_all_required_executable_gates():
    config = yaml.load(
        (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader
    )
    assert set(config["jobs"]) == {"backend", "web", "python", "docker"}
    assert {"push", "pull_request", "workflow_dispatch"} <= config["on"].keys()
    commands = "\n".join(
        step.get("run", "") for job in config["jobs"].values() for step in job["steps"]
    )
    for command in (
        "dotnet restore",
        "dotnet build",
        "dotnet test",
        "npm ci",
        "npm run lint",
        "npm test",
        "npm run build",
        "ruff check",
        "pytest",
        "docker compose build",
        "docker compose up",
    ):
        assert command in commands


def test_model_and_http_contract_settings_are_versioned():
    settings = json.loads((ROOT / "services/ml-inference/logging.json").read_text(encoding="utf-8"))
    assert settings["formatters"]["json"]["()"] == "brainseg_inference.logging.JsonFormatter"
    values = dotenv_values(ROOT / ".env.example")
    assert values["ML_PREPROCESSING_VERSION"] == "flair-v1"
    assert values["ML_MODEL_SHA256"] == ""
    assert (values["POSTGRES_PASSWORD"] or "").startswith("replace-")
    assert (values["MINIO_ROOT_PASSWORD"] or "").startswith("replace-")


def test_readmes_and_stage_reports_have_research_disclaimers():
    paths = (
        "README.md",
        "ml/training/README.md",
        "apps/web/src/app/proxy/README.md",
        "docs/adr/0001-skeleton.md",
        "docs/test-reports/0001-skeleton.md",
    )
    for relative in paths:
        content = (ROOT / relative).read_text(encoding="utf-8")
        assert "不用于临床诊断" in content or "Not for clinical diagnosis" in content
