from alice.gluttony.assimilation import AssimilationEngine


def test_project_analyzer_extracts_build_dependency_and_test_metadata(tmp_path):
    source = tmp_path / "candidate"
    source.mkdir()
    (source / "pyproject.toml").write_text(
        '[project]\nname="sample-agent"\nversion="1.2.0"\n'
        'requires-python=">=3.11"\ndependencies=["requests>=2.31"]\n'
        '[project.optional-dependencies]\ntest=["pytest>=8"]\n'
        '[project.scripts]\nsample="sample:main"\n'
        '[build-system]\nrequires=["setuptools>=68"]\n',
        encoding="utf-8",
    )
    (source / "package.json").write_text(
        '{"name":"frontend","scripts":{"test":"vitest run"},'
        '"dependencies":{"react":"^19"},"devDependencies":{"vitest":"^3"}}',
        encoding="utf-8",
    )
    (source / "Cargo.toml").write_text(
        '[package]\nname="native-agent"\nversion="0.2.0"\nedition="2021"\n'
        '[dependencies]\nserde={version="1",features=["derive"]}\n',
        encoding="utf-8",
    )
    (source / "go.mod").write_text(
        'module example.org/agent\n\ngo 1.23\n\nrequire example.org/lib v1.4.0\n',
        encoding="utf-8",
    )
    (source / "tests").mkdir()
    (source / "tests" / "test_agent.py").write_text("def test_run(): pass\n", encoding="utf-8")

    engine = AssimilationEngine(tmp_path)
    inventory = engine._inventory(source)
    profile = engine.project_analyzer.analyze(source, inventory, ["tests/test_agent.py"])

    assert set(profile["build_systems"]) == {"Python / PEP 517", "Node.js / npm", "Cargo", "Go Modules"}
    assert {row["name"] for row in profile["dependencies"]} >= {
        "requests", "pytest", "setuptools", "react", "vitest", "serde", "example.org/lib",
    }
    assert {row["scope"] for row in profile["dependencies"]} >= {"runtime", "development", "optional:test", "build"}
    assert any(row["name"] == "test" and row["command"] == "vitest run" for row in profile["declared_scripts"])
    assert profile["test_files"] == ["tests/test_agent.py"]
    assert "are catalogued only" in profile["execution_policy"]


def test_project_analyzer_records_parse_error_without_aborting_digest(tmp_path):
    source = tmp_path / "candidate"
    source.mkdir()
    (source / "package.json").write_text("{broken", encoding="utf-8")
    engine = AssimilationEngine(tmp_path)
    profile = engine.project_analyzer.analyze(source, engine._inventory(source), [])
    assert profile["manifests"] == [{"path": "package.json", "status": "parse_error"}]
    assert profile["parse_errors"][0]["error"] == "JSONDecodeError"


def test_manifest_dependency_urls_do_not_copy_embedded_passwords_into_report(tmp_path):
    source = tmp_path / "candidate"
    source.mkdir()
    (source / "requirements.txt").write_text(
        "private-lib @ https://alice:private-password@packages.example/lib.whl\n",
        encoding="utf-8",
    )
    engine = AssimilationEngine(tmp_path)
    profile = engine.project_analyzer.analyze(source, engine._inventory(source), [])
    spec = profile["dependencies"][0]["specification"]
    assert "private-password" not in spec
    assert "[REDACTED]" in spec


def test_static_rust_import_scan_recognizes_external_crates(tmp_path):
    source = tmp_path / "candidate"
    source.mkdir()
    (source / "Cargo.toml").write_text(
        '[package]\nname="native-agent"\nversion="0.1.0"\n'
        '[dependencies]\nserde = "1"\ntokio = "1"\n',
        encoding="utf-8",
    )
    (source / "lib.rs").write_text(
        "use serde::Serialize;\nuse tokio::runtime;\nuse std::io;\n"
        "pub fn run() {}\n",
        encoding="utf-8",
    )
    engine = AssimilationEngine(tmp_path)

    analysis = engine._analyze(source, engine._inventory(source))

    assert {"serde", "tokio"}.issubset(set(analysis["dependencies"]))
    assert "std" not in analysis["dependencies"]
