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
    assert len(values["ML_SERVICE_API_KEY"] or "") == 64
    assert values["MlInference__ApiKey"] == values["ML_SERVICE_API_KEY"]
    assert values["POSTGRES_PASSWORD"] != values["MINIO_ROOT_PASSWORD"]
    assert values["ML_SERVICE_API_KEY"] not in {
        values["POSTGRES_PASSWORD"],
        values["MINIO_ROOT_PASSWORD"],
    }
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
        assert service["mem_limit"]
        assert service["cpus"]
        assert service["pids_limit"]
        assert service["logging"]["driver"] == "local"
    assert "ports" not in services["postgres"]
    assert "ports" not in services["ml-inference"]
    assert services["postgres"]["networks"] == ["backend-internal"]
    assert services["ml-inference"]["networks"] == ["backend-internal"]
    assert services["backend"]["networks"] == ["frontend", "backend-internal"]
    assert compose["networks"]["backend-internal"]["internal"] is True
    assert "POSTGRES_PASSWORD" not in services["ml-inference"]["environment"]
    assert "MINIO_ROOT_PASSWORD" not in services["ml-inference"]["environment"]
    assert services["ml-inference"]["environment"]["ML_SERVICE_API_KEY"].startswith(
        "${ML_SERVICE_API_KEY:"
    )
    assert services["backend"]["environment"]["MlInference__ApiKey"].startswith(
        "${ML_SERVICE_API_KEY:"
    )
    assert services["ml-inference"]["volumes"] == [
        "./artifacts/models:/models:ro",
        "inference-data:/data/objects",
    ]


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
    assert {".env", ".env.*", "data", "artifacts", "backups", ".git"} <= set(ignored)


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
    assert "docker compose exec -T backend curl" in commands
    assert "curl --fail http://127.0.0.1:8000" not in commands


def test_real_performance_benchmark_is_manual_controlled_and_requires_pass():
    workflow = yaml.load(
        (ROOT / ".github/workflows/research-benchmark.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    assert set(workflow["on"]) == {"workflow_dispatch"}
    job = workflow["jobs"]["benchmark"]
    assert "brainseg-research-cpu" in job["runs-on"]
    assert job["environment"] == "research-controlled"
    commands = "\n".join(step.get("run", "") for step in job["steps"])
    assert "--allow-persistent-results" in commands
    assert "['status'] == 'Pass'" in commands
    assert "BRAINSEG_BENCHMARK_API_KEY" in job["env"]


def test_model_and_http_contract_settings_are_versioned():
    settings = json.loads((ROOT / "services/ml-inference/logging.json").read_text(encoding="utf-8"))
    assert settings["formatters"]["json"]["()"] == "brainseg_inference.logging.JsonFormatter"
    values = dotenv_values(ROOT / ".env.example")
    assert values["ML_MODEL_MANIFEST_PATH"] == "/models/model-manifest.yaml"
    assert values["ML_MAX_INFERENCE_BATCH_SIZE"] == "16"
    assert values["POSTGRES_PASSWORD"] == ""
    assert values["MINIO_ROOT_PASSWORD"] == ""
    assert values["ML_SERVICE_API_KEY"] == ""


def test_host_development_port_overrides_are_loopback_only():
    compose = yaml.safe_load((ROOT / "compose.dev.yaml").read_text(encoding="utf-8"))
    assert set(compose["services"]) == {"postgres", "ml-inference"}
    for service in compose["services"].values():
        assert all(port.startswith("127.0.0.1:") for port in service["ports"])


def test_readmes_and_stage_reports_have_research_disclaimers():
    paths = (
        "README.md",
        "ml/training/README.md",
        "apps/web/src/app/proxy/README.md",
        "docs/adr/0001-skeleton.md",
        "docs/test-reports/0001-skeleton.md",
        "docs/deployment.md",
        "docs/reproducibility.md",
        "docs/test-reports/0009-deployment-documentation.md",
    )
    for relative in paths:
        content = (ROOT / relative).read_text(encoding="utf-8")
        assert "不用于临床诊断" in content or "Not for clinical diagnosis" in content
