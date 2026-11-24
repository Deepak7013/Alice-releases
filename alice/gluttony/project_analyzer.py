"""Bounded static project-manifest analysis for untrusted DEVOUR inputs."""
from __future__ import annotations

import configparser
import json
import re
import struct
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    import tomllib
except ImportError:  # Python 3.10 deployments may not ship tomllib.
    tomllib = None


class ProjectManifestAnalyzer:
    MAX_MANIFESTS = 60
    MAX_MANIFEST_BYTES = 512_000
    MAX_CLASSFILE_BYTES = 2_000_000
    SECRET_RE = re.compile(
        r'''(?im)(["']?(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password|passwd|secret|credential)["']?\s*[:=]\s*["']?)[^"'\r\n,;}\s]+'''
    )
    URL_CREDENTIAL_RE = re.compile(r"(?i)(https?://[^:/@\s]+:)[^@/\s]+@")

    @classmethod
    def _sanitize(cls, value, limit=500):
        text = str(value or "")
        text = cls.SECRET_RE.sub(r"\1[REDACTED]", text)
        text = cls.URL_CREDENTIAL_RE.sub(r"\1[REDACTED]@", text)
        return text[:limit]

    @staticmethod
    def _add_dependency(rows, ecosystem, name, specification="", scope="runtime", source=""):
        name = str(name or "").strip()
        if not name:
            return
        rows.append({
            "ecosystem": ecosystem,
            "name": name[:200],
            "specification": ProjectManifestAnalyzer._sanitize(specification, 300),
            "scope": scope[:40],
            "source": source[:300],
        })

    @classmethod
    def inspect_java_classfile(cls, path):
        """Read JVM class names, fields, and method signatures without loading code."""
        path = Path(path)
        if path.stat().st_size > cls.MAX_CLASSFILE_BYTES:
            return {"status": "metadata_only_size_limit", "class_name": "", "fields": [], "methods": []}
        data = path.read_bytes()
        if len(data) < 10 or data[:4] != b"\xca\xfe\xba\xbe":
            return {"status": "unsupported_classfile", "class_name": "", "fields": [], "methods": []}
        offset = 8

        def take(size):
            nonlocal offset
            end = offset + size
            if size < 0 or end > len(data):
                raise ValueError("truncated_classfile")
            value = data[offset:end]
            offset = end
            return value

        def u1(): return take(1)[0]
        def u2(): return struct.unpack(">H", take(2))[0]
        def u4(): return struct.unpack(">I", take(4))[0]

        try:
            cp_count = u2()
            if cp_count < 1 or cp_count > 65535:
                raise ValueError("invalid_constant_pool")
            cp = [None] * cp_count
            index = 1
            while index < cp_count:
                tag = u1()
                if tag == 1:
                    length = u2()
                    cp[index] = (tag, take(length).decode("utf-8", errors="replace"))
                elif tag in {3, 4}:
                    take(4); cp[index] = (tag, None)
                elif tag in {5, 6}:
                    take(8); cp[index] = (tag, None); index += 1
                elif tag in {7, 8, 16, 19, 20}:
                    cp[index] = (tag, u2())
                elif tag in {9, 10, 11, 12, 17, 18}:
                    cp[index] = (tag, u2(), u2())
                elif tag == 15:
                    cp[index] = (tag, u1(), u2())
                else:
                    raise ValueError("unknown_constant_pool_tag")
                index += 1

            def utf8(constant_index):
                row = cp[constant_index] if 0 < constant_index < len(cp) else None
                if not row or row[0] != 1:
                    raise ValueError("invalid_utf8_reference")
                return row[1]

            def class_name(constant_index):
                row = cp[constant_index] if 0 < constant_index < len(cp) else None
                if not row or row[0] != 7:
                    raise ValueError("invalid_class_reference")
                return utf8(row[1]).replace("/", ".")

            def skip_attributes():
                for _ in range(u2()):
                    utf8(u2())
                    length = u4()
                    if length > cls.MAX_CLASSFILE_BYTES:
                        raise ValueError("oversized_class_attribute")
                    take(length)

            access_flags = u2()
            name = class_name(u2())
            super_index = u2()
            superclass = class_name(super_index) if super_index else ""
            interface_count = u2()
            if interface_count > 4096:
                raise ValueError("too_many_interfaces")
            interfaces = [class_name(u2()) for _ in range(interface_count)]

            fields = []
            field_count = u2()
            if field_count > 8192:
                raise ValueError("too_many_fields")
            for _ in range(field_count):
                flags, name_index, descriptor_index = u2(), u2(), u2()
                fields.append({"name": utf8(name_index), "descriptor": utf8(descriptor_index),
                               "visibility": "public" if flags & 1 else "protected" if flags & 4 else "private" if flags & 2 else "package"})
                skip_attributes()

            methods = []
            method_count = u2()
            if method_count > 8192:
                raise ValueError("too_many_methods")
            for _ in range(method_count):
                flags, name_index, descriptor_index = u2(), u2(), u2()
                methods.append({"name": utf8(name_index), "descriptor": utf8(descriptor_index),
                                "visibility": "public" if flags & 1 else "protected" if flags & 4 else "private" if flags & 2 else "package",
                                "static": bool(flags & 8), "native": bool(flags & 0x100),
                                "abstract": bool(flags & 0x400)})
                skip_attributes()
            skip_attributes()
            if offset != len(data):
                raise ValueError("trailing_classfile_data")
            return {"status": "parsed", "class_name": name, "superclass": superclass,
                    "interfaces": interfaces, "visibility": "public" if access_flags & 1 else "package",
                    "fields": fields[:500], "methods": methods[:1000]}
        except (IndexError, struct.error, ValueError):
            return {"status": "parse_error", "class_name": "", "fields": [], "methods": []}

    def _python_requirements(self, path, text):
        rows = []
        for raw in text.splitlines()[:10000]:
            line = raw.strip()
            if not line or line.startswith(("#", "-")):
                continue
            match = re.match(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)(.*)$", line)
            if match:
                self._add_dependency(rows, "python", match.group(1), match.group(2), source=path)
        return rows

    def _parse(self, relative, path):
        text = path.read_text(encoding="utf-8", errors="replace")
        name = path.name.casefold()
        dependencies = []
        scripts = []
        build_system = ""
        project = {}
        if name in {"pyproject.toml", "cargo.toml"}:
            if tomllib is None:
                return {"path": relative, "status": "unsupported_parser", "build_system": "TOML"}
            data = tomllib.loads(text)
            if name == "pyproject.toml":
                section = data.get("project", {})
                project = {key: section[key] for key in ("name", "version", "requires-python") if key in section}
                for item in section.get("dependencies", []):
                    dependencies.extend(self._python_requirements(relative, str(item)))
                optional = section.get("optional-dependencies", {})
                if isinstance(optional, dict):
                    for group, values in optional.items():
                        for item in values if isinstance(values, list) else []:
                            for row in self._python_requirements(relative, str(item)):
                                row["scope"] = f"optional:{str(group)[:32]}"
                                dependencies.append(row)
                build = data.get("build-system", {})
                for item in build.get("requires", []):
                    for row in self._python_requirements(relative, str(item)):
                        row["scope"] = "build"
                        dependencies.append(row)
                for key, command in (section.get("scripts", {}) or {}).items():
                    scripts.append({"name": str(key)[:120], "command": self._sanitize(command), "source": relative})
                build_system = "Python / PEP 517"
            else:
                section = data.get("package", {})
                project = {key: section[key] for key in ("name", "version", "edition") if key in section}
                for scope, key in (("runtime", "dependencies"), ("development", "dev-dependencies"), ("build", "build-dependencies")):
                    values = data.get(key, {})
                    if isinstance(values, dict):
                        for dep, spec in values.items():
                            spec = spec if isinstance(spec, str) else json.dumps(spec, sort_keys=True)
                            self._add_dependency(dependencies, "rust", dep, spec, scope, relative)
                build_system = "Cargo"
        elif name == "requirements.txt":
            dependencies = self._python_requirements(relative, text)
            build_system = "Python requirements"
        elif name == "package.json":
            data = json.loads(text)
            project = {key: data[key] for key in ("name", "version") if key in data}
            for scope, key in (("runtime", "dependencies"), ("development", "devDependencies"), ("optional", "optionalDependencies")):
                values = data.get(key, {})
                if isinstance(values, dict):
                    for dep, spec in values.items():
                        self._add_dependency(dependencies, "npm", dep, spec, scope, relative)
            for key, command in (data.get("scripts", {}) or {}).items():
                scripts.append({"name": str(key)[:120], "command": self._sanitize(command), "source": relative})
            build_system = "Node.js / npm"
        elif name == "go.mod":
            module = re.search(r"(?m)^\s*module\s+(\S+)", text)
            if module:
                project["module"] = module.group(1)[:300]
            for match in re.finditer(r"(?m)^\s*require\s+([^\s()]+)\s+(v[^\s]+)", text):
                self._add_dependency(dependencies, "go", match.group(1), match.group(2), source=relative)
            for block in re.finditer(r"(?ms)^\s*require\s*\((.*?)\)", text):
                for row in re.finditer(r"(?m)^\s*([^\s()]+)\s+(v[^\s]+)", block.group(1)):
                    self._add_dependency(dependencies, "go", row.group(1), row.group(2), source=relative)
            build_system = "Go Modules"
        elif name == "composer.json":
            data = json.loads(text)
            project = {key: data[key] for key in ("name", "type") if key in data}
            for scope, key in (("runtime", "require"), ("development", "require-dev")):
                values = data.get(key, {})
                if isinstance(values, dict):
                    for dep, spec in values.items():
                        self._add_dependency(dependencies, "composer", dep, spec, scope, relative)
            build_system = "Composer"
        elif name.endswith(".csproj"):
            if "<!doctype" in text.casefold() or "<!entity" in text.casefold():
                raise ValueError("XML declarations are not accepted in project manifests")
            root = ET.fromstring(text)
            for element in root.iter():
                if element.tag.rsplit("}", 1)[-1] == "PackageReference":
                    self._add_dependency(dependencies, "nuget", element.attrib.get("Include") or element.attrib.get("Update"), element.attrib.get("Version", ""), source=relative)
            build_system = ".NET SDK"
        elif name == "pom.xml":
            if "<!doctype" in text.casefold() or "<!entity" in text.casefold():
                raise ValueError("XML declarations are not accepted in project manifests")
            root = ET.fromstring(text)
            project = {
                key: (next((node.text for node in root.iter() if node.tag.rsplit("}", 1)[-1] == key), "") or "")[:300]
                for key in ("groupId", "artifactId", "version")
            }
            for dependency in root.iter():
                if dependency.tag.rsplit("}", 1)[-1] != "dependency":
                    continue
                fields = {node.tag.rsplit("}", 1)[-1]: (node.text or "").strip() for node in dependency}
                if fields.get("artifactId"):
                    coordinate = ":".join(filter(None, (fields.get("groupId", ""), fields["artifactId"])))
                    self._add_dependency(dependencies, "maven", coordinate, fields.get("version", ""), fields.get("scope", "runtime"), relative)
            build_system = "Maven"
        elif name == "setup.cfg":
            parser = configparser.ConfigParser(interpolation=None)
            parser.read_string(text)
            if parser.has_option("metadata", "name"):
                project["name"] = parser.get("metadata", "name")[:200]
            if parser.has_option("options", "install_requires"):
                dependencies = self._python_requirements(relative, parser.get("options", "install_requires"))
            build_system = "Python / setuptools"
        else:
            return None
        return {
            "path": relative,
            "status": "parsed",
            "build_system": build_system,
            "project": project,
            "dependencies": dependencies[:5000],
            "declared_scripts": scripts[:500],
        }

    def analyze(self, source, inventory, test_paths):
        manifests = []
        errors = []
        dependencies = []
        scripts = []
        systems = set()
        for item in inventory.get("files", []):
            if len(manifests) >= self.MAX_MANIFESTS:
                break
            path = Path(item["path"])
            name = path.name.casefold()
            if name not in {"pyproject.toml", "cargo.toml", "requirements.txt", "package.json",
                            "go.mod", "composer.json", "pom.xml", "setup.cfg"} and not name.endswith(".csproj"):
                continue
            if item.get("size", 0) > self.MAX_MANIFEST_BYTES:
                manifests.append({"path": item["path"], "status": "too_large"})
                continue
            try:
                parsed = self._parse(item["path"], Path(source) / item["path"])
                if parsed is None:
                    continue
                manifests.append(parsed)
                systems.add(parsed.get("build_system", ""))
                dependencies.extend(parsed.get("dependencies", []))
                scripts.extend(parsed.get("declared_scripts", []))
            except Exception as exc:
                errors.append({"path": item["path"], "error": type(exc).__name__})
                manifests.append({"path": item["path"], "status": "parse_error"})
        unique = {}
        for row in dependencies:
            key = (row["ecosystem"].casefold(), row["name"].casefold(), row["scope"].casefold(), row["specification"])
            unique[key] = row
        directories = sorted({item["path"].split("/", 1)[0] for item in inventory.get("files", [])
                              if "/" in item["path"]})[:200]
        return {
            "top_level_directories": directories,
            "manifests": manifests,
            "build_systems": sorted(x for x in systems if x),
            "dependencies": list(unique.values())[:5000],
            "declared_scripts": scripts[:1000],
            "test_files": list(test_paths)[:1000],
            "execution_policy": "manifest commands and tests are catalogued only; untrusted candidate code is not run",
            "parse_errors": errors[:100],
        }
