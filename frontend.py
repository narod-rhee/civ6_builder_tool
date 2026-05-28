from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.parser import BytesParser
from email.policy import default as email_policy
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

from PIL import Image

from cropper import (
    CropperError,
    MODE_PRESETS,
    OutputDimension,
    apply_mode_defaults,
    place_subject_on_target_canvas,
    process_recipe,
    remove_background_from_corners,
    validate_recipe,
)
from xml_profile_extractor import (
    ExtractorError,
    extract_path as extract_xml_profile,
    load_profile as load_xml_profile,
    profile_to_copilot_prefill,
    summarize_profile as summarize_xml_profile,
    write_json as write_xml_json,
)


ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"
RUN_ROOT = ROOT / "frontend_runs"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
TEMPLATE_ROOT = ROOT / "Template"
DEFAULT_TEMPLATE_OUTPUT = ROOT / "output" / "template_copilot"
TEMPLATE_EXTENSIONS = {".xml", ".sql", ".artdef"}
GENERIC_TEMPLATE_KEYS = {"Template", "Template Leader", "Template Faith"}
MAX_AI_TEXT_REPLACEMENT_OCCURRENCES = 20
LOCAL_CONFIG = {
    "OPENAI_API_KEY": "",
    "AGENT_WORKFLOW_ID": "",
    "AGENT_WORKFLOW_VERSION": "",
    "CHATKIT_USER": "",
    "WORKSPACE_PATH": "",
    "INITIAL_PROMPT": "Use this workspace context to help me with local project work.",
    "OPENAI_TEXT_MODEL": "",
    "OPENAI_IMAGE_MODEL": "",
}

NOVELAI_ASSET_PRESETS: dict[str, dict[str, Any]] = {
    "civilization_icon": {
        "label": "Civilization Icon (OpenAI)",
        "prompt_engine": "openai",
        "resolution": "1024x1024",
        "sampler": "k_euler_ancestral",
        "steps": 26,
        "prompt_guidance": 5.0,
        "quality_tags": "best quality, amazing quality, very aesthetic, absurdres",
        "composition": "centered Civilization-style emblem, readable silhouette, clean crest design, faction symbols, simple background, icon-ready square composition",
        "undesired": "lowres, cluttered emblem, unreadable symbol, tiny details, text, logo, watermark, blurry, jpeg artifacts",
        "openai_size": "1024x1024",
        "openai_enabled": True,
    },
    "unit_theme": {
        "label": "Unit Theme (NovelAI)",
        "prompt_engine": "novelai",
        "resolution": "1024x1024",
        "sampler": "k_euler_ancestral",
        "steps": 28,
        "prompt_guidance": 5.2,
        "quality_tags": "best quality, amazing quality, very aesthetic, absurdres, clean game concept art",
        "composition": "Civilization-style unit asset concept, full readable silhouette, clear weapon or equipment identity, faction colors, simple background, icon-crop friendly pose",
        "undesired": "lowres, cluttered background, unreadable silhouette, cropped weapon, extra limbs, bad hands, text, logo, watermark, blurry, jpeg artifacts",
        "openai_size": "1024x1024",
        "openai_enabled": False,
    },
    "diplomacy_background": {
        "label": "Diplomacy Background (NovelAI)",
        "prompt_engine": "novelai",
        "resolution": "1920x960",
        "sampler": "k_euler_ancestral",
        "steps": 32,
        "prompt_guidance": 5.4,
        "quality_tags": "best quality, amazing quality, very aesthetic, absurdres, cinematic background art",
        "composition": "Civilization-style diplomacy background, 2:1 wide composition, environment or throne-room scene, readable central negative space, faction atmosphere, no character closeup, no text",
        "undesired": "lowres, portrait closeup, cropped face, text, logo, watermark, blurry, jpeg artifacts, cluttered foreground, distorted architecture",
        "openai_size": "1024x1024",
        "openai_enabled": False,
    },
    "moment_picture": {
        "label": "Moment Picture (NovelAI)",
        "prompt_engine": "novelai",
        "resolution": "1024x1024",
        "sampler": "k_euler_ancestral",
        "steps": 30,
        "prompt_guidance": 5.2,
        "quality_tags": "best quality, amazing quality, very aesthetic, polished scene art",
        "composition": "Civilization-style square moment picture, 1:1 composition, readable central event, faction atmosphere, cinematic lighting, no UI text",
        "undesired": "lowres, text, logo, watermark, blurry, jpeg artifacts, extreme crop, messy foreground, distorted faces",
        "openai_size": "1024x1024",
        "openai_enabled": False,
    },
}
DEFAULT_IGNORE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "frontend_runs",
}


class FrontendError(Exception):
    pass


@dataclass
class UploadedFile:
    filename: str
    data: bytes


@dataclass
class FormData:
    values: dict[str, str]
    files: dict[str, UploadedFile]


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value

    return values


def config_value(name: str, dotenv: dict[str, str], fallback: str = "") -> str:
    pasted = LOCAL_CONFIG.get(name, "").strip()
    if pasted:
        return pasted
    if name in dotenv and dotenv[name].strip():
        return dotenv[name].strip()
    if os.environ.get(name):
        return os.environ[name]
    return fallback


def load_settings(args: argparse.Namespace) -> dict[str, Any]:
    dotenv = parse_env_file(ROOT / ".env")
    workspace = Path(
        args.workspace
        or config_value("WORKSPACE_PATH", dotenv, str(ROOT))
    ).expanduser().resolve()

    return {
        "api_key": args.api_key or config_value("OPENAI_API_KEY", dotenv),
        "workflow_id": args.workflow_id or config_value("AGENT_WORKFLOW_ID", dotenv),
        "workflow_version": args.workflow_version or config_value("AGENT_WORKFLOW_VERSION", dotenv),
        "user": args.user
        or config_value("CHATKIT_USER", dotenv, os.environ.get("USERNAME", "local-user")),
        "workspace": workspace,
        "prompt": args.prompt
        or config_value(
            "INITIAL_PROMPT",
            dotenv,
            "Use this workspace context to help me with local project work.",
        ),
        "text_model": args.text_model or config_value("OPENAI_TEXT_MODEL", dotenv, "gpt-4.1-mini"),
        "image_model": args.image_model or config_value("OPENAI_IMAGE_MODEL", dotenv, "gpt-image-2"),
        "file_limit": args.file_limit,
    }


def build_state(settings: dict[str, Any]) -> dict[str, str]:
    root = settings["workspace"]
    files = workspace_files(root, settings["file_limit"])
    return {
        "workspace_name": root.name,
        "workspace_path": str(root),
        "workspace_files_json": json.dumps(files),
        "initial_prompt": settings["prompt"],
    }


def create_chatkit_session(settings: dict[str, Any]) -> dict[str, Any]:
    if not settings["api_key"]:
        raise ValueError("Missing OPENAI_API_KEY. Add it to .env or pass --api-key.")
    if not settings["workflow_id"]:
        raise ValueError("Missing AGENT_WORKFLOW_ID. Add it to .env or pass --workflow-id.")
    if not settings["workspace"].is_dir():
        raise ValueError(f"Workspace does not exist: {settings['workspace']}")

    workflow: dict[str, Any] = {
        "id": settings["workflow_id"],
        "state_variables": build_state(settings),
    }
    if settings["workflow_version"]:
        workflow["version"] = settings["workflow_version"]

    body = {
        "user": settings["user"],
        "workflow": workflow,
        "chatkit_configuration": {
            "automatic_thread_titling": {"enabled": True},
            "file_upload": {"enabled": True, "max_files": 10, "max_file_size": 512},
            "history": {"enabled": True},
        },
    }

    request = urllib.request.Request(
        "https://api.openai.com/v1/chatkit/sessions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings['api_key']}",
            "Content-Type": "application/json",
            "OpenAI-Beta": "chatkit_beta=v1",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API returned {exc.code}: {details}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach OpenAI ChatKit Sessions API: {exc.reason}") from exc


def public_config(settings: dict[str, Any]) -> dict[str, Any]:
    files = workspace_files(settings["workspace"], settings["file_limit"])
    return {
        "workflow_id": settings["workflow_id"],
        "workflow_version": settings["workflow_version"] or "latest",
        "user": settings["user"],
        "workspace_name": settings["workspace"].name,
        "workspace_path": str(settings["workspace"]),
        "file_count": len(files),
        "files": files[:80],
        "prompt": settings["prompt"],
        "has_api_key": bool(settings["api_key"]),
    }


class CropperFrontendHandler(BaseHTTPRequestHandler):
    server_version = "CropperFrontend/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.send_static_file(WEB_ROOT / "index.html")
            return
        if parsed.path.startswith("/static/"):
            self.send_static_file(WEB_ROOT / parsed.path.removeprefix("/static/"))
            return
        if parsed.path == "/api/profiles":
            self.send_json(profile_payload())
            return
        if parsed.path == "/api/workspace":
            self.send_json(workspace_payload())
            return
        if parsed.path == "/api/config":
            self.send_json(public_config(self.server.settings))
            return
        if parsed.path == "/api/server-pool":
            self.send_json(server_pool_payload(self.server))
            return
        if parsed.path == "/api/templates":
            self.send_json(template_inventory_payload())
            return
        if parsed.path == "/api/asset-presets":
            self.send_json(asset_presets_payload())
            return
        if parsed.path == "/api/file":
            params = parse_qs(parsed.query)
            file_value = params.get("path", [""])[0]
            self.send_workspace_file(Path(unquote(file_value)))
            return
        self.send_error(404, "Not found")

    def do_POST(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/api/generate":
                self.handle_generate()
                return
            if parsed.path == "/api/raw256":
                self.handle_raw256()
                return
            if parsed.path == "/api/remove-background":
                self.handle_remove_background()
                return
            if parsed.path == "/api/chatkit/session":
                self.send_json(create_chatkit_session(self.server.settings))
                return
            if parsed.path == "/api/template-copilot":
                self.handle_template_copilot()
                return
            if parsed.path == "/api/xml-extractor/extract":
                self.handle_xml_extractor_extract()
                return
            if parsed.path == "/api/xml-extractor/summarize":
                self.handle_xml_extractor_summarize()
                return
            if parsed.path == "/api/xml-extractor/copilot":
                self.handle_xml_extractor_copilot()
                return
            if parsed.path == "/api/novelai-prompt":
                self.handle_novelai_prompt()
                return
            if parsed.path == "/api/openai-image":
                self.handle_openai_image()
                return
            if parsed.path == "/api/server-pool/start":
                self.handle_server_pool_start()
                return
            if parsed.path == "/api/server-pool/stop":
                self.handle_server_pool_stop()
                return
            self.send_error(404, "Not found")
        except (CropperError, ExtractorError, FrontendError, OSError, RuntimeError, ValueError) as exc:
            self.send_json({"status": "error", "message": str(exc)}, status=400)

    def handle_generate(self) -> None:
        form = self.read_form()
        image_path = save_upload(form, "image")
        mode = form_value(form, "mode", "civilization_icons")
        base_name = sanitize_base_name(form_value(form, "base_name", "ICON_CUSTOM"), preserve_case=mode == "unit_icons")
        output_dir = resolve_output_dir(form_value(form, "output_dir", f"output/{base_name.lower()}"))

        recipe_data = build_recipe_from_form(form, image_path, output_dir, base_name, mode)
        recipe = validate_recipe(recipe_data, ROOT / "frontend.generated.json")
        manifest = process_recipe(recipe)
        self.send_json(with_file_urls(manifest))

    def handle_raw256(self) -> None:
        form = self.read_form()
        image_path = save_upload(form, "image")
        base_name = sanitize_base_name(form_value(form, "base_name", "ICON_RAW"))
        output_dir = resolve_output_dir(form_value(form, "output_dir", f"output/{base_name.lower()}"))

        recipe_data = build_recipe_from_form(form, image_path, output_dir, base_name, "raw_256")
        recipe = validate_recipe(recipe_data, ROOT / "frontend.raw256.json")
        manifest = process_recipe(recipe)
        self.send_json(with_file_urls(manifest))

    def handle_remove_background(self) -> None:
        form = self.read_form()
        image_path = save_upload(form, "image")
        output_dir = resolve_output_dir(form_value(form, "output_dir", "output/background_removed"))
        output_dir.mkdir(parents=True, exist_ok=True)

        tolerance = form_int(form, "tolerance", 35)
        feather = form_float(form, "feather", 2)
        despill = form_bool(form, "despill", True)
        method = form_value(form, "background_method", "advanced")
        image = Image.open(image_path).convert("RGBA")
        cleaned = remove_background_from_corners(image, tolerance, feather, despill, method)
        if form_bool(form, "clean_to_256", False):
            cleaned = place_subject_on_target_canvas(
                cleaned,
                OutputDimension(256, 256),
                form_float(form, "subject_scale_percent", 100),
                form_float(form, "horizontal_offset_percent", 0),
                form_float(form, "vertical_offset_percent", 0),
            )
        output_path = output_dir / f"{image_path.stem}_background_removed.png"
        cleaned.save(output_path, "PNG")
        self.send_json(
            {
                "status": "success",
                "generated_files": [
                    {
                        "path": str(output_path),
                        "width": cleaned.width,
                        "height": cleaned.height,
                        "url": file_url(output_path),
                    }
                ],
                "warnings": [],
            }
        )

    def handle_template_copilot(self) -> None:
        request = self.read_json_body()
        payload = generate_template_copilot_files(request, self.server.settings)
        self.send_json(payload)

    def handle_xml_extractor_extract(self) -> None:
        request = self.read_json_body()
        source_path = resolve_input_path(str(request.get("path") or ""))
        out_path = resolve_json_output_path(
            str(request.get("out") or "output/xml_extractor/extracted_profile.json"),
            "extracted_profile.json",
        )
        profile = extract_xml_profile(source_path, out_path)
        self.send_json(
            {
                "status": "success",
                "output_path": str(out_path),
                "output_url": file_url(out_path),
                "summary": profile.get("summary") or summarize_xml_profile(profile, print_output=False),
                "warnings": profile.get("warnings", []),
                "file_count": len(profile.get("files", [])),
            }
        )

    def handle_xml_extractor_summarize(self) -> None:
        request = self.read_json_body()
        profile_path = resolve_input_path(str(request.get("profile") or ""))
        profile = load_xml_profile(profile_path)
        self.send_json(
            {
                "status": "success",
                "profile_path": str(profile_path),
                "summary": summarize_xml_profile(profile, print_output=False),
                "warnings": profile.get("warnings", []),
            }
        )

    def handle_xml_extractor_copilot(self) -> None:
        request = self.read_json_body()
        profile_path = resolve_input_path(str(request.get("profile") or ""))
        out_path = resolve_json_output_path(
            str(request.get("out") or "output/xml_extractor/copilot_prefill.json"),
            "copilot_prefill.json",
        )
        profile = load_xml_profile(profile_path)
        prefill = profile_to_copilot_prefill(profile)
        write_xml_json(out_path, prefill)
        self.send_json(
            {
                "status": "success",
                "output_path": str(out_path),
                "output_url": file_url(out_path),
                "prefill": prefill,
                "summary": {
                    "civilizations": prefill.get("civilization_names", []),
                    "leaders": prefill.get("leader_names", []),
                    "units": prefill.get("unit_names", []),
                    "buildings": prefill.get("building_names", []),
                    "districts": prefill.get("district_names", []),
                    "improvements": prefill.get("improvement_names", []),
                    "localized_text_count": len(prefill.get("localization_keys", [])),
                    "warnings": prefill.get("warnings", []),
                },
            }
        )

    def handle_novelai_prompt(self) -> None:
        request = self.read_json_body()
        payload = generate_novelai_prompt_payload(request, self.server.settings)
        self.send_json(payload)

    def handle_openai_image(self) -> None:
        request = self.read_json_body()
        payload = create_openai_image_asset(request, self.server.settings)
        self.send_json(payload)

    def handle_server_pool_start(self) -> None:
        request = self.read_json_body()
        count = int(request.get("count") or 2)
        start_port = int(request.get("start_port") or (self.server.server_address[1] + 1))
        self.send_json(start_server_pool(self.server, count, start_port))

    def handle_server_pool_stop(self) -> None:
        request = self.read_json_body()
        port = int(request.get("port") or 0)
        self.send_json(stop_server_pool_member(self.server, port))

    def read_json_body(self) -> dict[str, Any]:
        content_type = self.headers.get("Content-Type", "")
        if "application/json" not in content_type:
            raise FrontendError("Expected application/json.")
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            raise FrontendError("Missing JSON body.")
        try:
            data = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise FrontendError(f"Invalid JSON: {exc.msg}") from exc
        if not isinstance(data, dict):
            raise FrontendError("JSON body must be an object.")
        return data

    def read_form(self) -> FormData:
        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            raise FrontendError("Expected multipart/form-data.")
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            raise FrontendError("Missing form body.")

        body = self.rfile.read(content_length)
        message = BytesParser(policy=email_policy).parsebytes(
            b"Content-Type: " + content_type.encode("utf-8") + b"\r\n"
            b"MIME-Version: 1.0\r\n\r\n"
            + body
        )

        values: dict[str, str] = {}
        files: dict[str, UploadedFile] = {}
        for part in message.iter_parts():
            if part.get_content_disposition() != "form-data":
                continue
            name = part.get_param("name", header="content-disposition")
            if not name:
                continue
            filename = part.get_filename()
            payload = part.get_payload(decode=True) or b""
            if filename:
                files[name] = UploadedFile(filename=filename, data=payload)
            else:
                charset = part.get_content_charset() or "utf-8"
                values[name] = payload.decode(charset, errors="replace")

        return FormData(values=values, files=files)

    def send_static_file(self, path: Path) -> None:
        path = path.resolve()
        if not path.is_file() or WEB_ROOT not in path.parents:
            self.send_error(404, "Not found")
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(path.stat().st_size))
        self.end_headers()
        with path.open("rb") as file:
            shutil.copyfileobj(file, self.wfile)

    def send_workspace_file(self, path: Path) -> None:
        path = path.resolve()
        if not path.is_file() or not is_allowed_file_path(path):
            self.send_error(404, "Not found")
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(path.stat().st_size))
        self.end_headers()
        with path.open("rb") as file:
            shutil.copyfileobj(file, self.wfile)

    def send_json(self, payload: dict, status: int = 200) -> None:
        encoded = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def is_allowed_file_path(path: Path) -> bool:
    allowed_roots = [ROOT, ROOT.parent, RUN_ROOT, DEFAULT_TEMPLATE_OUTPUT]
    for allowed_root in allowed_roots:
        try:
            path.relative_to(allowed_root.resolve())
            return True
        except ValueError:
            continue
    return False


def build_recipe_from_form(
    form: FormData,
    image_path: Path,
    output_dir: Path,
    base_name: str,
    mode: str,
) -> dict:
    recipe = {
        "source": str(image_path),
        "output_dir": str(output_dir),
        "base_name": base_name,
        "mode": mode,
        "overwrite": True,
        "background_remove": {
            "enabled": form_bool(form, "remove_background", False),
            "sample": "corners",
            "method": form_value(form, "background_method", "advanced"),
            "tolerance": form_int(form, "tolerance", 35),
            "feather": form_float(form, "feather", 2),
            "despill": form_bool(form, "despill", True),
        },
        "subject_scale_percent": form_float(form, "subject_scale_percent", 100),
        "vertical_offset_percent": form_float(form, "vertical_offset_percent", 0),
        "horizontal_offset_percent": form_float(form, "horizontal_offset_percent", 0),
        "unit_right_scale_percent": form_float(
            form,
            "unit_right_scale_percent",
            form_float(form, "subject_scale_percent", 100),
        ),
    }

    if mode in {"leader_icons", "leader_circle"} or form_bool(form, "circle_enabled", False):
        recipe["circle"] = {
            "enabled": True,
            "crop_to_circle": True,
            "background": {
                "enabled": True,
                "color": parse_hex_color(form_value(form, "circle_color", "#121212")),
            },
        }

    return recipe


def save_upload(form: FormData, field_name: str) -> Path:
    field = form.files.get(field_name)
    if field is None or not field.filename:
        raise FrontendError("Choose an image file first.")

    uploads_dir = RUN_ROOT / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    safe_name = sanitize_filename(Path(field.filename).name)
    output_path = uploads_dir / f"{int(time.time() * 1000)}_{safe_name}"
    with output_path.open("wb") as output_file:
        output_file.write(field.data)
    return output_path


def profile_payload() -> dict:
    profiles = {}
    for mode in sorted(MODE_PRESETS):
        preset = apply_mode_defaults({"mode": mode})
        sizes = preset.get("sizes", [])
        dimensions = preset.get("dimensions", [])
        shape = preset.get("shape", "square")
        profiles[mode] = {
            "label": mode.replace("_", " ").title(),
            "shape": shape,
            "sizes": sizes,
            "dimensions": dimensions,
            "notes": profile_notes(mode),
        }
    profiles["background_removal"] = {
        "label": "Remove Background",
        "shape": "image",
        "sizes": [256],
        "dimensions": [],
        "notes": "Background remover: advanced edge matte with optional clean 256 canvas output.",
    }
    return {"status": "success", "profiles": profiles}


def workspace_payload() -> dict:
    files = workspace_files(ROOT, 160)
    return {
        "status": "success",
        "workspace_name": ROOT.name,
        "workspace_path": str(ROOT),
        "file_count": len(files),
        "files": files,
    }


def server_pool_payload(server: "CropperFrontendServer") -> dict:
    cleanup_server_pool(server)
    members = [
        {
            "port": port,
            "pid": process.pid,
            "url": f"http://{server.server_address[0]}:{port}",
            "status": "running",
        }
        for port, process in sorted(server.server_pool.items())
    ]
    return {
        "status": "success",
        "current": {
            "port": server.server_address[1],
            "url": f"http://{server.server_address[0]}:{server.server_address[1]}",
        },
        "members": members,
    }


def start_server_pool(server: "CropperFrontendServer", count: int, start_port: int) -> dict:
    if count < 1 or count > 8:
        raise FrontendError("Server count must be between 1 and 8.")
    cleanup_server_pool(server)

    launched = []
    port = max(1, start_port)
    while len(launched) < count:
        port = next_free_port(server.server_address[0], port, {server.server_address[1], *server.server_pool.keys()})
        log_path = server_pool_log_path(port)
        log_file = log_path.open("ab")
        command = [
            sys.executable,
            str(ROOT / "frontend.py"),
            "--host",
            str(server.server_address[0]),
            "--port",
            str(port),
        ]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process = subprocess.Popen(
            command,
            cwd=str(ROOT),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        server.server_pool[port] = process
        launched.append(
            {
                "port": port,
                "pid": process.pid,
                "url": f"http://{server.server_address[0]}:{port}",
                "log": str(log_path),
            }
        )
        port += 1

    return {"status": "success", "launched": launched, "pool": server_pool_payload(server)}


def stop_server_pool_member(server: "CropperFrontendServer", port: int) -> dict:
    process = server.server_pool.get(port)
    if process is None:
        raise FrontendError(f"No tracked server is running on port {port}.")
    process.terminate()
    try:
        process.wait(timeout=4)
    except subprocess.TimeoutExpired:
        process.kill()
    server.server_pool.pop(port, None)
    return {"status": "success", "stopped": port, "pool": server_pool_payload(server)}


def cleanup_server_pool(server: "CropperFrontendServer") -> None:
    dead_ports = [port for port, process in server.server_pool.items() if process.poll() is not None]
    for port in dead_ports:
        server.server_pool.pop(port, None)


def next_free_port(host: str, start_port: int, blocked_ports: set[int]) -> int:
    port = start_port
    while port <= 65535:
        if port not in blocked_ports and port_is_free(host, port):
            return port
        port += 1
    raise FrontendError("No free port found for a new server.")


def port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) != 0


def server_pool_log_path(port: int) -> Path:
    log_dir = RUN_ROOT / "server_pool"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / f"server_{port}.log"


def template_inventory_payload() -> dict:
    templates = []
    for path in template_files():
        relative = path.relative_to(TEMPLATE_ROOT)
        text = read_text_preview(path)
        placeholders = extract_template_placeholders(text)
        templates.append(
            {
                "path": str(relative).replace("\\", "/"),
                "name": path.name,
                "folder": str(relative.parent).replace("\\", "/") if relative.parent != Path(".") else "",
                "kind": path.suffix.lower().lstrip("."),
                "placeholder_count": len(placeholders),
                "placeholders": placeholders[:24],
            }
        )
    return {
        "status": "success",
        "template_root": str(TEMPLATE_ROOT),
        "default_output_dir": str(DEFAULT_TEMPLATE_OUTPUT),
        "templates": templates,
    }


def asset_presets_payload() -> dict:
    return {
        "status": "success",
        "presets": NOVELAI_ASSET_PRESETS,
        "openai": {
            "default_model": "gpt-image-2",
            "models": ["gpt-image-2", "gpt-image-1.5", "gpt-image-1", "gpt-image-1-mini"],
            "sizes": ["1024x1024"],
            "qualities": ["auto", "low", "medium", "high"],
            "backgrounds": ["auto", "transparent", "opaque"],
            "formats": ["png", "webp", "jpeg"],
        },
    }


def generate_novelai_prompt_payload(request: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    asset_type = str(request.get("asset_type") or "civilization_icon")
    preset = NOVELAI_ASSET_PRESETS.get(asset_type)
    if not preset:
        raise FrontendError(f"Unknown asset type: {asset_type}")
    if not settings["api_key"]:
        raise ValueError("Missing OPENAI_API_KEY. Add it to .env before using the prompt generator.")

    prompt_engine = str(preset.get("prompt_engine") or "novelai")
    prompt_request = {
        "task": "Create a practical image prompt package for a Civilization mod asset.",
        "rules": [
            "Return only valid JSON.",
            "If prompt_engine is openai, write the OpenAI image prompt and leave positive_prompt and undesired_content empty.",
            "If prompt_engine is novelai, write a positive prompt and undesired_content compatible with NovelAI tag-style prompting and leave openai_prompt empty.",
            "Use comma-separated tags and short natural-language fragments for NovelAI prompts.",
            "Avoid mentioning copyrighted character names unless the user explicitly supplied them.",
            "Civilization icons belong to OpenAI in this tool because they need clean symbolic accuracy and strong instruction following.",
            "ARX is handled by the Cropper ARX profile, not by NovelAI prompting.",
            "Keep the output useful only for Civilization icons, Civilization unit-theme assets, diplomacy backgrounds, or moment pictures.",
            "For unit_theme, focus on NovelAI generation and unit readability rather than OpenAI image creation.",
            "For diplomacy_background, use a wide 1920x960 NovelAI composition with no UI text and no portrait closeup.",
            "For moment_picture, use a square scene composition that will crop cleanly to 375x375.",
            "For civilization_icon, describe a centered emblem or crest with no text, clean geometry, readable silhouette, and transparent/flat background readiness.",
            "Keep tone and visual language consistent with user-supplied civilization, leader, and faction notes instead of improvising a new style.",
            "Respect the preset settings unless the user asks for different framing.",
        ],
        "required_json_shape": {
            "positive_prompt": "string",
            "undesired_content": "string",
            "settings": {
                "resolution": "string",
                "sampler": "string",
                "steps": 28,
                "prompt_guidance": 5.5,
                "seed": "random",
            },
            "openai_prompt": "string",
            "notes": ["string"],
        },
        "preset": preset,
        "prompt_engine": prompt_engine,
        "user_inputs": {
            "asset_type": asset_type,
            "subject": request.get("subject", ""),
            "civilization": request.get("civilization", ""),
            "visual_brief": request.get("visual_brief", ""),
            "style_tags": request.get("style_tags", ""),
            "must_include": request.get("must_include", ""),
            "avoid": request.get("avoid", ""),
        },
    }
    body = {
        "model": settings.get("text_model") or "gpt-4.1-mini",
        "input": [
            {
                "role": "system",
                "content": "You generate practical image prompts for Civilization mod assets. Civilization icons use OpenAI prompts; NovelAI is for units, diplomacy backgrounds, and moment pictures; ARX is handled by cropper sizing.",
            },
            {
                "role": "user",
                "content": json.dumps(prompt_request, ensure_ascii=False),
            },
        ],
        "text": {"format": {"type": "json_object"}},
    }
    response = call_openai_responses_api(body, settings["api_key"])
    text = extract_openai_text(response)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"OpenAI returned invalid JSON: {text[:500]}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("OpenAI returned JSON, but not an object.")
    if prompt_engine == "openai":
        payload["positive_prompt"] = ""
        payload["undesired_content"] = ""
    else:
        payload["openai_prompt"] = ""
    payload["status"] = "success"
    payload["asset_type"] = asset_type
    return payload


def create_openai_image_asset(request: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    if not settings["api_key"]:
        raise ValueError("Missing OPENAI_API_KEY. Add it to .env before creating images.")
    asset_type = str(request.get("asset_type") or "civilization_icon")
    preset = NOVELAI_ASSET_PRESETS.get(asset_type)
    if not preset or asset_type != "civilization_icon" or not preset.get("openai_enabled", False):
        raise FrontendError("OpenAI Image Creator is only enabled for Civilization Icon assets.")
    prompt = str(request.get("prompt") or "").strip()
    if not prompt:
        raise FrontendError("OpenAI image prompt is required.")

    output_dir = resolve_template_output_dir(str(request.get("output_dir") or (ROOT / "output" / "openai_assets")))
    output_dir.mkdir(parents=True, exist_ok=True)
    output_format = str(request.get("output_format") or "png")
    if output_format not in {"png", "webp", "jpeg"}:
        raise FrontendError("output_format must be png, webp, or jpeg.")
    size = str(request.get("size") or "1024x1024")
    if size != "1024x1024":
        raise FrontendError("OpenAI Image Creator is restricted to 1024x1024 Civilization icon drafts.")

    body = {
        "model": str(request.get("model") or settings.get("image_model") or "gpt-image-2"),
        "prompt": (
            f"Create only a {preset['label']} for a Civilization-style mod asset. "
            "Do not create portraits, ARX crops, moment art, unit art, maps, UI mockups, or unrelated assets. "
            f"{prompt}"
        ),
        "size": size,
        "quality": str(request.get("quality") or "auto"),
        "background": str(request.get("background") or "auto"),
        "output_format": output_format,
        "n": 1,
    }
    response = call_openai_images_api(body, settings["api_key"])
    image_data = response.get("data", [{}])[0]
    b64_json = image_data.get("b64_json")
    if not isinstance(b64_json, str):
        raise RuntimeError("OpenAI image response did not include b64_json.")

    safe_name = sanitize_filename(str(request.get("filename") or "openai_asset"))
    suffix = "jpg" if output_format == "jpeg" else output_format
    output_path = output_dir / f"{safe_name}_{int(time.time() * 1000)}.{suffix}"
    output_path.write_bytes(base64.b64decode(b64_json))
    return {
        "status": "success",
        "generated_files": [
            {
                "path": str(output_path),
                "url": file_url(output_path),
                "width": None,
                "height": None,
            }
        ],
        "revised_prompt": image_data.get("revised_prompt"),
        "model": body["model"],
        "size": body["size"],
        "quality": body["quality"],
    }


def call_openai_images_api(body: dict[str, Any], api_key: str) -> dict[str, Any]:
    request = urllib.request.Request(
        "https://api.openai.com/v1/images/generations",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI Images API returned {exc.code}: {details}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach OpenAI Images API: {exc.reason}") from exc


def template_files() -> list[Path]:
    if not TEMPLATE_ROOT.exists():
        return []
    return sorted(path for path in TEMPLATE_ROOT.rglob("*") if path.is_file() and path.suffix.lower() in TEMPLATE_EXTENSIONS)


def read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def read_text_preview(path: Path, max_chars: int = 500_000) -> str:
    try:
        with path.open("r", encoding="utf-8-sig", errors="replace") as file:
            return file.read(max_chars)
    except UnicodeError:
        with path.open("r", encoding="utf-8", errors="replace") as file:
            return file.read(max_chars)


def extract_template_placeholders(text: str) -> list[str]:
    placeholders = set(re.findall(r"\b[A-Z][A-Z0-9_]*TEMPLATE[A-Z0-9_]*\b", text))
    text_values = set(re.findall(r"<Text>([^<]*Template[^<]*)</Text>", text))
    placeholders.update(value.strip() for value in text_values if value.strip())
    return sorted(placeholders, key=lambda value: (value.count("_"), len(value), value), reverse=True)


def generate_template_copilot_files(request: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    selected_files = request.get("files")
    uploaded_templates = request.get("uploaded_templates", [])
    if not isinstance(selected_files, list):
        selected_files = []
    if not isinstance(uploaded_templates, list):
        uploaded_templates = []
    if not selected_files and not uploaded_templates:
        raise FrontendError("Select at least one XML, SQL, or ArtDef template file.")

    selected_paths = resolve_template_selection(selected_files)
    selected_paths.extend(save_uploaded_templates(uploaded_templates))
    output_dir = resolve_template_output_dir(str(request.get("output_dir") or DEFAULT_TEMPLATE_OUTPUT))
    output_dir.mkdir(parents=True, exist_ok=True)

    use_api = bool(request.get("use_api", True))
    brief = str(request.get("brief") or "").strip()
    if use_api and not brief:
        raise FrontendError("Describe what the template should become.")

    manual_replacements = request.get("manual_replacements", {})
    if manual_replacements is None:
        manual_replacements = {}
    if not isinstance(manual_replacements, dict):
        raise FrontendError("manual_replacements must be an object when provided.")

    context = build_template_context(selected_paths, request)
    output_strategy = str(request.get("output_strategy") or "merge")
    if output_strategy not in {"merge", "separate"}:
        raise FrontendError("output_strategy must be 'merge' or 'separate'.")

    if use_api:
        ai_payload = create_template_replacement_plan(brief, context, settings)
    else:
        ai_payload = {
            "file_prefix": filename_prefix_from_identifier(identifier_from_name(str(context.get("fields", {}).get("mod_code") or "GeneratedCiv"))),
            "replacements": {},
            "variants": [],
            "notes": ["OpenAI API disabled; generated deterministic IDs, manual replacements, and Template ID JSON only."],
        }
    ai_variants = normalize_template_variants(ai_payload, output_strategy)
    variants = combine_ai_and_entity_variants(ai_payload, ai_variants, context, request)

    generated_files = []
    all_replacements: dict[str, dict[str, str]] = {}
    safety_notes: list[str] = []
    for variant in variants:
        variant_name = sanitize_filename(str(variant.get("name") or "merged"))
        variant_prefix = sanitize_filename(str(variant.get("file_prefix") or ai_payload.get("file_prefix") or request.get("file_prefix") or "GeneratedCiv"))
        replacements = variant.get("replacements", {})
        if not isinstance(replacements, dict):
            raise FrontendError("OpenAI returned a variant without a replacements object.")
        deterministic_replacements = variant.get("deterministic_replacements", {})
        if not isinstance(deterministic_replacements, dict):
            deterministic_replacements = {}

        ai_replacements = {str(key): str(value) for key, value in replacements.items() if str(key)}
        merged_replacements, skipped = filter_safe_ai_replacements(selected_paths, ai_replacements)
        safety_notes.extend(f"{variant_name}: {note}" for note in skipped)
        for key, value in deterministic_replacements.items():
            merged_replacements[str(key)] = str(value)
        for key, value in manual_replacements.items():
            merged_replacements[str(key)] = str(value)
        all_replacements[variant_name] = merged_replacements

        variant["resolved_name"] = variant_name
        variant["resolved_prefix"] = variant_prefix
        variant["resolved_replacements"] = merged_replacements

        if output_strategy == "separate" or len(variants) == 1:
            variant_output_dir = output_dir / variant_name if output_strategy == "separate" and len(variants) > 1 else output_dir
            generated_files.extend(
                write_template_variant(selected_paths, variant_output_dir, variant_prefix, merged_replacements, variant_name)
            )

    if output_strategy == "merge" and len(variants) > 1:
        generated_files.extend(write_merged_template_variants(selected_paths, output_dir, variants))

    id_manifest = build_template_id_manifest(context, request)
    id_manifest_path = output_dir / "template_ids.json"
    id_manifest_path.write_text(json.dumps(id_manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    generated_files.append(
        {
            "path": str(id_manifest_path),
            "url": file_url(id_manifest_path),
            "template": "Template ID manifest",
            "variant": "ids",
            "replacement_count": 0,
        }
    )

    ai_notes = ai_payload.get("notes", [])
    if not isinstance(ai_notes, list):
        ai_notes = [str(ai_notes)]

    return {
        "status": "success",
        "output_dir": str(output_dir),
        "output_strategy": output_strategy,
        "variant_count": len(variants),
        "generated_files": generated_files,
        "replacements": all_replacements,
        "notes": [
            *multi_entity_output_notes(output_strategy, variants),
            *(str(note) for note in ai_notes),
            *unique_preserving_order(safety_notes),
        ],
    }


def multi_entity_output_notes(output_strategy: str, variants: list[dict[str, Any]]) -> list[str]:
    if len(variants) <= 1:
        return []
    if output_strategy == "merge":
        return [
            "Unified output: multiple civilizations/leaders are written as additional rows in the same selected template files.",
            "Use Separate variant folders only when debugging one generated civ/leader at a time.",
        ]
    return [
        "Separate output: each civilization/leader variant was written to its own folder for review/debugging.",
    ]


def normalize_template_variants(ai_payload: dict[str, Any], output_strategy: str) -> list[dict[str, Any]]:
    variants = ai_payload.get("variants")
    if output_strategy == "separate" and isinstance(variants, list) and variants:
        return [variant for variant in variants if isinstance(variant, dict)]
    return [
        {
            "name": "merged",
            "file_prefix": ai_payload.get("file_prefix", "GeneratedCiv"),
            "replacements": ai_payload.get("replacements", {}),
        }
    ]


def combine_ai_and_entity_variants(
    ai_payload: dict[str, Any],
    ai_variants: list[dict[str, Any]],
    context: dict[str, Any],
    request: dict[str, Any],
) -> list[dict[str, Any]]:
    entity_variants = build_entity_variants(context, request)
    if not entity_variants:
        return ai_variants

    combined = []
    for index, entity_variant in enumerate(entity_variants):
        ai_variant = ai_variants[index] if index < len(ai_variants) else ai_variants[0]
        ai_replacements = ai_variant.get("replacements", {})
        if not isinstance(ai_replacements, dict):
            ai_replacements = {}
        entity_replacements = entity_variant.get("replacements", {})
        combined.append(
            {
                "name": entity_variant.get("name") or ai_variant.get("name") or f"variant_{index + 1}",
                "file_prefix": entity_variant.get("file_prefix") or ai_variant.get("file_prefix") or ai_payload.get("file_prefix"),
                "replacements": {str(key): str(value) for key, value in ai_replacements.items()},
                "deterministic_replacements": entity_replacements,
            }
        )
    return combined


def build_entity_variants(context: dict[str, Any], request: dict[str, Any]) -> list[dict[str, Any]]:
    entities = context.get("entities", {})
    civilizations = list(entities.get("civilizations") or [])
    leaders = list(entities.get("leaders") or [])
    if not civilizations and not leaders:
        return []

    mod_code = identifier_from_name(str(context.get("fields", {}).get("mod_code") or "Generated Civ"))
    leader_bindings = normalized_leader_bindings(request.get("leader_bindings"), civilizations, leaders)
    if leader_bindings:
        variants = []
        for index, binding in enumerate(leader_bindings):
            civilization_name = binding.get("civilization") or pick_index(civilizations, index) or "Generated Civilization"
            leader_name = binding.get("name") or pick_index(leaders, index) or "Generated Leader"
            civ_suffix = identifier_from_name(civilization_name, fallback=mod_code)
            leader_suffix = leader_suffix_from_id_or_name(binding.get("leader_id", ""), leader_name, mod_code)
            variant_name = sanitize_filename(f"{civ_suffix}_{leader_suffix}")
            replacements = deterministic_entity_replacements(civilization_name, leader_name, civ_suffix, leader_suffix, mod_code)
            replacements.update(deterministic_profile_replacements(profile_for_civilization(context, civilization_name), civ_suffix))
            for key, value in (request.get("manual_replacements") or {}).items():
                replacements[str(key)] = str(value)
            variants.append(
                {
                    "name": variant_name,
                    "file_prefix": filename_prefix_from_identifier(civ_suffix),
                    "replacements": replacements,
                }
            )
        return variants

    count = max(len(civilizations), len(leaders), 1)
    variants = []
    for index in range(count):
        civilization_name = pick_index(civilizations, index) or pick_index(civilizations, 0) or "Generated Civilization"
        leader_name = pick_index(leaders, index) or pick_index(leaders, 0) or "Generated Leader"
        civ_suffix = identifier_from_name(civilization_name, fallback=mod_code)
        leader_suffix = leader_suffix_from_id_or_name("", leader_name, mod_code)
        variant_name = sanitize_filename(f"{civ_suffix}_{leader_suffix}" if civilizations and leaders else civ_suffix if civilizations else leader_suffix)
        replacements = deterministic_entity_replacements(civilization_name, leader_name, civ_suffix, leader_suffix, mod_code)
        replacements.update(deterministic_profile_replacements(profile_for_civilization(context, civilization_name), civ_suffix))
        for key, value in (request.get("manual_replacements") or {}).items():
            replacements[str(key)] = str(value)
        variants.append(
            {
                "name": variant_name,
                "file_prefix": filename_prefix_from_identifier(civ_suffix if civilizations else leader_suffix),
                "replacements": replacements,
            }
        )
    return variants


def profile_for_civilization(context: dict[str, Any], civilization_name: str) -> dict[str, Any]:
    for profile in context.get("civilization_profiles") or []:
        if str(profile.get("name") or "").strip() == civilization_name:
            return profile
    return {}


def deterministic_profile_replacements(profile: dict[str, Any], civ_suffix: str) -> dict[str, str]:
    replacements: dict[str, str] = {}
    if not profile:
        return replacements
    if profile.get("demonym"):
        replacements["LOC_CIVILIZATION_TEMPLATE_ADJECTIVE"] = f"LOC_CIVILIZATION_{civ_suffix}_ADJECTIVE"
        replacements["Template citizen adjective"] = str(profile["demonym"])
    first_by_kind = {
        "UNIT": parse_entity_list(profile.get("unit_names", [])),
        "BUILDING": parse_entity_list(profile.get("building_names", [])),
        "IMPROVEMENT": parse_entity_list(profile.get("improvement_names", [])),
        "DISTRICT": parse_entity_list(profile.get("district_names", [])),
        "GOVERNOR": parse_entity_list(profile.get("governor_names", [])),
    }
    for kind, names in first_by_kind.items():
        if not names:
            continue
        suffix = identifier_from_name(names[0], fallback=f"{civ_suffix}_{kind}")
        replacements[f"{kind}_TEMPLATE"] = f"{kind}_{suffix}"
        replacements[f"LOC_{kind}_TEMPLATE_NAME"] = f"LOC_{kind}_{suffix}_NAME"
        replacements[f"LOC_{kind}_TEMPLATE_DESCRIPTION"] = f"LOC_{kind}_{suffix}_DESCRIPTION"
        replacements[f"ICON_{kind}_TEMPLATE"] = f"ICON_{kind}_{suffix}"
        if kind == "DISTRICT":
            replacements["LOC_DISTRICT_TEMPLATE_HOLY_SITE_NAME"] = f"LOC_DISTRICT_{suffix}_NAME"
            replacements["LOC_DISTRICT_TEMPLATE_HOLY_SITE_DESCRIPTION"] = f"LOC_DISTRICT_{suffix}_DESCRIPTION"
    return replacements


def leader_suffix_from_id_or_name(leader_id: str, leader_name: str, mod_code: str) -> str:
    if leader_id.strip():
        cleaned_id = identifier_from_name(leader_id, fallback="")
        if cleaned_id.startswith("LEADER_") and len(cleaned_id) > len("LEADER_"):
            return cleaned_id.removeprefix("LEADER_")
        if cleaned_id:
            return cleaned_id
    return identifier_from_name(leader_name, fallback=f"{mod_code}_LEADER")


def normalized_leader_bindings(value: Any, civilizations: list[str], leaders: list[str]) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    bindings: list[dict[str, str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            continue
        leader_name = str(item.get("name") or pick_index(leaders, index) or "").strip()
        leader_id = str(item.get("leader_id") or "").strip()
        civilization_name = str(item.get("civilization") or "").strip()
        if not civilization_name:
            try:
                civ_index = int(item.get("civilization_index") or 0)
            except (TypeError, ValueError):
                civ_index = 0
            civilization_name = pick_index(civilizations, civ_index) or pick_index(civilizations, 0)
        if leader_name or civilization_name:
            bindings.append(
                {
                    "name": leader_name,
                    "leader_id": leader_id,
                    "civilization": civilization_name,
                }
            )
    return bindings


def pick_index(items: list[str], index: int) -> str:
    if not items:
        return ""
    if index < len(items):
        return items[index]
    return items[-1]


def identifier_from_name(value: str, fallback: str = "GENERATED") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", value.strip()).strip("_").upper()
    if not cleaned:
        cleaned = fallback.strip("_").upper() or "GENERATED"
    if cleaned[0].isdigit():
        cleaned = f"X_{cleaned}"
    return cleaned


def filename_prefix_from_identifier(value: str) -> str:
    parts = [part for part in value.lower().split("_") if part]
    return "".join(part[:1].upper() + part[1:] for part in parts) or "Generated"


def deterministic_entity_replacements(
    civilization_name: str,
    leader_name: str,
    civ_suffix: str,
    leader_suffix: str,
    mod_code: str,
) -> dict[str, str]:
    civ_id = f"CIVILIZATION_{civ_suffix}"
    leader_id = f"LEADER_{leader_suffix}"
    return {
        "CIVILIZATION_TEMPLATE": civ_id,
        "TRAIT_CIVILIZATION_TEMPLATE_ABILITY": f"TRAIT_CIVILIZATION_{civ_suffix}_ABILITY",
        "TRAIT_CIVILIZATION_BUILDING_TEMPLATE": f"TRAIT_CIVILIZATION_{civ_suffix}_BUILDING",
        "TRAIT_CIVILIZATION_DISTRICT_TEMPLATE": f"TRAIT_CIVILIZATION_{civ_suffix}_DISTRICT",
        "TRAIT_CIVILIZATION_UNIT_TEMPLATE": f"TRAIT_CIVILIZATION_{civ_suffix}_UNIT",
        "LOC_CIVILIZATION_TEMPLATE": f"LOC_CIVILIZATION_{civ_suffix}",
        "LOC_TRAIT_CIVILIZATION_TEMPLATE": f"LOC_TRAIT_CIVILIZATION_{civ_suffix}",
        "LOC_CITY_NAME_TEMPLATE": f"LOC_CITY_NAME_{civ_suffix}",
        "ICON_CIVILIZATION_TEMPLATE": f"ICON_CIVILIZATION_{civ_suffix}",
        "TEMPLATE_POPULATION": f"{civ_suffix}_POPULATION",
        "LEADER_TEMPLATE_LEADER": leader_id,
        "TRAIT_LEADER_TEMPLATE_ABILITY": f"TRAIT_LEADER_{leader_suffix}_ABILITY",
        "ABILITY_TEMPLATE_RELIGIOUS_UNITS": f"ABILITY_{leader_suffix}_RELIGIOUS_UNITS",
        "LOC_LEADER_TEMPLATE_LEADER": f"LOC_LEADER_{leader_suffix}",
        "LOC_LOADING_INFO_LEADER_TEMPLATE_LEADER": f"LOC_LOADING_INFO_LEADER_{leader_suffix}",
        "LEADER_TEMPLATE_NEUTRAL": f"LEADER_{leader_suffix}_NEUTRAL",
        "LEADER_TEMPLATE_BACKGROUND": f"LEADER_{leader_suffix}_BACKGROUND",
        "AGENDA_TEMPLATE": f"AGENDA_{leader_suffix}",
        "TRAIT_AGENDA_TEMPLATE": f"TRAIT_AGENDA_{leader_suffix}",
        "LOC_AGENDA_TEMPLATE": f"LOC_AGENDA_{leader_suffix}",
        "TEMPLATEInquisitionPreference": f"{leader_suffix}InquisitionPreference",
        "TEMPLATEInquisitorPreference": f"{leader_suffix}InquisitorPreference",
        "TEMPLATE_LEADER": leader_suffix,
        "Template Leader": leader_name,
        "Template": civilization_name,
        "TEMPLATE": mod_code,
    }


def filter_safe_ai_replacements(
    selected_paths: list[Path],
    replacements: dict[str, str],
) -> tuple[dict[str, str], list[str]]:
    source_texts = [(str(path.relative_to(TEMPLATE_ROOT)).replace("\\", "/"), read_text_file(path)) for path in selected_paths]
    safe: dict[str, str] = {}
    skipped: list[str] = []
    for old, new in replacements.items():
        key = old.strip()
        if not key:
            continue
        if key in GENERIC_TEMPLATE_KEYS:
            skipped.append(f"Skipped broad OpenAI replacement {key!r}; use Manual replacements JSON if you really want it.")
            continue
        if "\n" in key or "<" in key or ">" in key:
            skipped.append(f"Skipped XML/SQL/ArtDef block replacement starting {key[:40]!r}; Template Copilot now avoids structural rewrites.")
            continue

        occurrence_count = sum(text.count(key) for _, text in source_texts)
        filename_count = sum(name.count(key) for name, _ in source_texts)
        total_count = occurrence_count + filename_count
        if total_count == 0:
            skipped.append(f"Skipped replacement {key!r}; it was not found in selected template files.")
            continue
        if total_count > MAX_AI_TEXT_REPLACEMENT_OCCURRENCES and not is_civ_identifier(key):
            skipped.append(
                f"Skipped high-spread replacement {key!r} ({total_count} matches); use a more exact key or Manual replacements JSON."
            )
            continue
        safe[key] = new
    return safe, skipped


def is_civ_identifier(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Z][A-Z0-9_]*", value))


def unique_preserving_order(items: list[str]) -> list[str]:
    seen = set()
    unique = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique


def write_template_variant(
    selected_paths: list[Path],
    output_dir: Path,
    file_prefix: str,
    replacements: dict[str, str],
    variant_name: str,
) -> list[dict[str, Any]]:
    generated_files = []
    for template_path in selected_paths:
        relative = template_path.relative_to(TEMPLATE_ROOT)
        output_relative = relative.with_name(apply_replacements_to_text(relative.name, filename_safe_replacements(replacements)))
        if output_relative.name == relative.name and relative.name.startswith("TemplateCiv"):
            output_relative = relative.with_name(relative.name.replace("TemplateCiv", file_prefix, 1))
        output_path = output_dir / output_relative
        output_path.parent.mkdir(parents=True, exist_ok=True)

        original = read_text_file(template_path)
        rendered = apply_replacements_to_text(original, replacements)
        output_path.write_text(rendered, encoding="utf-8")
        generated_files.append(
            {
                "path": str(output_path),
                "url": file_url(output_path),
                "template": str(relative).replace("\\", "/"),
                "variant": variant_name,
                "replacement_count": count_applied_replacements(original, replacements),
            }
        )
    return generated_files


def filename_safe_replacements(replacements: dict[str, str]) -> dict[str, str]:
    unsafe = {"Template", "Template Leader", "Template Faith", "TEMPLATE"}
    return {
        key: value
        for key, value in replacements.items()
        if key not in unsafe and ("\n" not in key and "<" not in key and ">" not in key)
    }


def write_merged_template_variants(
    selected_paths: list[Path],
    output_dir: Path,
    variants: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    generated_files = []
    output_dir.mkdir(parents=True, exist_ok=True)
    file_prefix = sanitize_filename(str(variants[0].get("resolved_prefix") or "GeneratedCiv"))
    for template_path in selected_paths:
        relative = template_path.relative_to(TEMPLATE_ROOT)
        output_relative = relative.with_name(relative.name)
        if output_relative.name.startswith("TemplateCiv"):
            output_relative = relative.with_name(relative.name.replace("TemplateCiv", file_prefix, 1))
        output_path = output_dir / output_relative
        output_path.parent.mkdir(parents=True, exist_ok=True)

        original = read_text_file(template_path)
        rendered_variants = [
            apply_replacements_to_text(original, variant.get("resolved_replacements", {}))
            for variant in variants
        ]
        if template_path.suffix.lower() in {".xml", ".artdef"}:
            rendered = merge_xml_variant_texts(rendered_variants)
        elif template_path.suffix.lower() == ".sql":
            rendered = merge_sql_variant_texts(rendered_variants, variants)
        else:
            rendered = "\n\n".join(rendered_variants)
        output_path.write_text(rendered, encoding="utf-8")
        generated_files.append(
            {
                "path": str(output_path),
                "url": file_url(output_path),
                "template": str(relative).replace("\\", "/"),
                "variant": "merged",
                "replacement_count": sum(count_applied_replacements(original, variant.get("resolved_replacements", {})) for variant in variants),
            }
        )
    return generated_files


def merge_xml_variant_texts(rendered_variants: list[str]) -> str:
    roots = []
    for text in rendered_variants:
        try:
            roots.append(ET.fromstring(text))
        except ET.ParseError:
            return "\n\n".join(rendered_variants)
    if not roots:
        return ""

    output_root = ET.Element(roots[0].tag, roots[0].attrib)
    sections: dict[str, ET.Element] = {}
    seen: dict[str, set[str]] = {}
    for root in roots:
        for child in list(root):
            section = sections.get(child.tag)
            if section is None:
                section = ET.SubElement(output_root, child.tag, child.attrib)
                sections[child.tag] = section
                seen[child.tag] = set()
            if list(child):
                for row in list(child):
                    key = ET.tostring(row, encoding="unicode")
                    if key in seen[child.tag]:
                        continue
                    seen[child.tag].add(key)
                    section.append(ET.fromstring(key))
            else:
                key = ET.tostring(child, encoding="unicode")
                if key not in seen[child.tag]:
                    seen[child.tag].add(key)
                    section.text = child.text
    ET.indent(output_root, space="\t")
    return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(output_root, encoding="unicode") + "\n"


def merge_sql_variant_texts(rendered_variants: list[str], variants: list[dict[str, Any]]) -> str:
    chunks = []
    for text, variant in zip(rendered_variants, variants):
        name = variant.get("resolved_name") or "variant"
        chunks.append(f"-- Template Copilot variant: {name}\n{text.strip()}\n")
    return "\n".join(chunks)


def resolve_template_selection(selected_files: list[Any]) -> list[Path]:
    paths = []
    for item in selected_files:
        relative = Path(str(item))
        if relative.is_absolute() or ".." in relative.parts:
            raise FrontendError(f"Invalid template selection: {item}")
        path = (TEMPLATE_ROOT / relative).resolve()
        try:
            path.relative_to(TEMPLATE_ROOT.resolve())
        except ValueError as exc:
            raise FrontendError(f"Template is outside template root: {item}") from exc
        if not path.is_file() or path.suffix.lower() not in TEMPLATE_EXTENSIONS:
            raise FrontendError(f"Template file not found: {item}")
        paths.append(path)
    return paths


def save_uploaded_templates(uploaded_templates: list[Any]) -> list[Path]:
    if not uploaded_templates:
        return []
    upload_dir = TEMPLATE_ROOT / "_uploaded"
    upload_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for index, item in enumerate(uploaded_templates, start=1):
        if not isinstance(item, dict):
            raise FrontendError("Uploaded template entries must be objects.")
        raw_name = str(item.get("name") or f"uploaded_template_{index}.xml")
        suffix = Path(raw_name).suffix.lower() or ".xml"
        if suffix == ".txt":
            suffix = ".xml"
        if suffix not in TEMPLATE_EXTENSIONS:
            raise FrontendError(f"Unsupported uploaded template type: {raw_name}")
        content = item.get("content")
        if not isinstance(content, str):
            raise FrontendError(f"Uploaded template has no text content: {raw_name}")
        if len(content) > 2_000_000:
            raise FrontendError(f"Uploaded template is too large: {raw_name}")
        safe_name = sanitize_filename(Path(raw_name).stem) + suffix
        path = (upload_dir / safe_name).resolve()
        try:
            path.relative_to(TEMPLATE_ROOT.resolve())
        except ValueError as exc:
            raise FrontendError(f"Invalid uploaded template name: {raw_name}") from exc
        path.write_text(content, encoding="utf-8")
        paths.append(path)
    return paths


def resolve_template_output_dir(value: str) -> Path:
    output_dir = Path(value.strip() or str(DEFAULT_TEMPLATE_OUTPUT))
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    return output_dir


def resolve_input_path(value: str) -> Path:
    if not value.strip():
        raise FrontendError("Enter a file or folder path first.")
    return Path(value.strip()).expanduser().resolve()


def resolve_json_output_path(value: str, default_name: str) -> Path:
    raw_value = value.strip()
    target = Path(raw_value or f"output/xml_extractor/{default_name}")
    if not target.is_absolute():
        target = ROOT / target
    if target.suffix.lower() != ".json":
        target = target / default_name
    return target.resolve()


def build_template_context(selected_paths: list[Path], request: dict[str, Any]) -> dict[str, Any]:
    placeholder_set: set[str] = set()
    previews = []
    for path in selected_paths:
        text = read_text_preview(path)
        placeholders = extract_template_placeholders(text)
        placeholder_set.update(placeholders)
        previews.append(
            {
                "file": str(path.relative_to(TEMPLATE_ROOT)).replace("\\", "/"),
                "placeholders": placeholders[:80],
                "sample": text[:2500],
            }
        )

    entities = {
        "civilizations": parse_entity_list(request.get("civilization_names", request.get("civilization_name", ""))),
        "leaders": parse_entity_list(request.get("leader_names", request.get("leader_name", ""))),
        "units": parse_entity_list(request.get("unit_names", request.get("unit_name", ""))),
        "buildings": parse_entity_list(request.get("building_names", request.get("building_name", ""))),
        "improvements": parse_entity_list(request.get("improvement_names", request.get("improvement_name", ""))),
        "districts": parse_entity_list(request.get("district_names", request.get("district_name", ""))),
        "governors": parse_entity_list(request.get("governor_names", "")),
        "named_geography": parse_entity_list(request.get("named_geography", "")),
    }
    return {
        "fields": {
            "mod_code": request.get("mod_code", ""),
            "religion_name": request.get("religion_name", ""),
            "primary_color": request.get("primary_color", ""),
            "secondary_color": request.get("secondary_color", ""),
        },
        "entities": entities,
        "civilization_profiles": normalize_civilization_profiles(request.get("civilization_profiles")),
        "leader_bindings": normalized_leader_bindings(
            request.get("leader_bindings"),
            entities["civilizations"],
            entities["leaders"],
        ),
        "city_names": parse_entity_list(request.get("city_names", "")),
        "citizen_names": parse_entity_list(request.get("citizen_names", "")),
        "output_strategy": request.get("output_strategy", "merge"),
        "all_placeholders": sorted(placeholder_set, key=len, reverse=True),
        "files": previews,
    }


def parse_entity_list(value: Any) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = re.split(r"[\n,;]+", str(value or ""))
    return [str(item).strip() for item in raw_items if str(item).strip()]


def normalize_civilization_profiles(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    profiles: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            continue
        profiles.append(
            {
                "index": index,
                "name": str(item.get("name") or "").strip(),
                "demonym": str(item.get("demonym") or "").strip(),
                "city_names": parse_entity_list(item.get("city_names", [])),
                "citizen_names": parse_entity_list(item.get("citizen_names", [])),
                "governor_names": parse_entity_list(item.get("governor_names", []))[:8],
                "governor_details": str(item.get("governor_details") or "").strip(),
                "named_geography": str(item.get("named_geography") or "").strip(),
                "unit_names": parse_entity_list(item.get("unit_names", []))[:5],
                "building_names": parse_entity_list(item.get("building_names", []))[:5],
                "improvement_names": parse_entity_list(item.get("improvement_names", []))[:5],
                "district_names": parse_entity_list(item.get("district_names", []))[:5],
                "unique_details": normalize_unique_details(item.get("unique_details")),
            }
        )
    return profiles


def normalize_unique_details(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {"units": "", "buildings": "", "improvements": "", "districts": ""}
    return {
        "units": str(value.get("units") or "").strip(),
        "buildings": str(value.get("buildings") or "").strip(),
        "improvements": str(value.get("improvements") or "").strip(),
        "districts": str(value.get("districts") or "").strip(),
    }


def build_template_id_manifest(context: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    mod_code = identifier_from_name(str(context.get("fields", {}).get("mod_code") or "Generated Civ"))
    profiles = context.get("civilization_profiles") or []
    if not profiles:
        profiles = [
            {"index": index, "name": name}
            for index, name in enumerate(context.get("entities", {}).get("civilizations") or [])
        ]
    leader_bindings = context.get("leader_bindings") or []
    leaders: list[dict[str, Any]] = []
    civilizations: list[dict[str, Any]] = []

    for index, profile in enumerate(profiles):
        civ_name = str(profile.get("name") or f"Generated Civilization {index + 1}")
        civ_suffix = identifier_from_name(civ_name, fallback=mod_code)
        civ_id = f"CIVILIZATION_{civ_suffix}"
        civ_entry: dict[str, Any] = {
            "index": index,
            "name": civ_name,
            "id": civ_id,
            "loc": {
                "name": f"LOC_CIVILIZATION_{civ_suffix}_NAME",
                "description": f"LOC_CIVILIZATION_{civ_suffix}_DESCRIPTION",
                "adjective": f"LOC_CIVILIZATION_{civ_suffix}_ADJECTIVE",
            },
            "icon": f"ICON_CIVILIZATION_{civ_suffix}",
            "atlas": f"ATLAS_ICON_CIVILIZATION_{civ_suffix}",
            "cropper_options": [
                cropper_option("Civilization icons", "civilization_icons", f"ICON_CIVILIZATION_{civ_suffix}", "output/civilization_icons"),
            ],
            "demonym": profile.get("demonym", ""),
            "city_names": profile.get("city_names", []),
            "citizen_names": profile.get("citizen_names", []),
            "governor_details": profile.get("governor_details", ""),
            "named_geography": profile.get("named_geography", ""),
            "unique_details": profile.get("unique_details", {}),
            "units": named_asset_manifest_items(profile.get("unit_names", []), "UNIT", "unit_icons", "output/unit_icons", unit_icon_base=True),
            "buildings": named_asset_manifest_items(profile.get("building_names", []), "BUILDING", "building_icons", "output/building_icons"),
            "improvements": named_asset_manifest_items(profile.get("improvement_names", []), "IMPROVEMENT", "building_icons", "output/improvement_icons"),
            "districts": named_asset_manifest_items(profile.get("district_names", []), "DISTRICT", "civilization_icons", "output/district_icons"),
            "governors": named_asset_manifest_items(profile.get("governor_names", []), "GOVERNOR", "governor_icons", "output/governor_icons", icon_prefix="ICON_GOVERNOR"),
        }
        civilizations.append(civ_entry)

    for index, binding in enumerate(leader_bindings):
        leader_name = str(binding.get("name") or f"Leader {index + 1}")
        civ_name = str(binding.get("civilization") or "")
        leader_suffix = leader_suffix_from_id_or_name(str(binding.get("leader_id") or ""), leader_name, mod_code)
        leader_id = f"LEADER_{leader_suffix}"
        leaders.append(
            {
                "index": index,
                "name": leader_name,
                "id": leader_id,
                "civilization": civ_name,
                "loc": {
                    "name": f"LOC_LEADER_{leader_suffix}_NAME",
                    "quote": f"LOC_LEADER_{leader_suffix}_QUOTE",
                    "loading_info": f"LOC_LOADING_INFO_LEADER_{leader_suffix}",
                    "diplomacy_prefix": f"LOC_DIPLO_*_LEADER_{leader_suffix}_ANY",
                },
                "trait": f"TRAIT_LEADER_{leader_suffix}_ABILITY",
                "agenda": f"AGENDA_{leader_suffix}",
                "icon": f"ICON_LEADER_{leader_suffix}",
                "atlas": f"ATLAS_ICON_{leader_suffix}_LEADER",
                "fallback_neutral": f"FALLBACK_NEUTRAL_LEADER_{leader_suffix}",
                "portrait": f"LEADER_{leader_suffix}_NEUTRAL",
                "portrait_background": f"LEADER_{leader_suffix}_BACKGROUND",
                "cropper_options": [
                    cropper_option("Leader icons", "leader_icons", f"ICON_LEADER_{leader_suffix}", "output/leader_icons"),
                    cropper_option("Leader portrait + fallback neutral", "leader_portraits", f"ICON_LEADER_{leader_suffix}", "output/leader_portraits"),
                ],
            }
        )

    return {
        "schema": "icon_forge_template_ids_v1",
        "mod_code": mod_code,
        "notes": [
            "Load this file in the Cropper page to auto-fill profile and base_name.",
            "Leader LOC pattern comes from LEADER_TEMPLATE_LEADER placeholders: LOC_LEADER_*_NAME, LOC_LOADING_INFO_LEADER_*, and LOC_DIPLO_*_LEADER_*_ANY.",
        ],
        "civilizations": civilizations,
        "leaders": leaders,
    }


def named_asset_manifest_items(
    names: Any,
    id_prefix: str,
    cropper_mode: str,
    output_dir: str,
    icon_prefix: str | None = None,
    unit_icon_base: bool = False,
) -> list[dict[str, Any]]:
    items = []
    for name in parse_entity_list(names)[:5 if id_prefix in {"UNIT", "BUILDING", "IMPROVEMENT", "DISTRICT"} else 8]:
        suffix = identifier_from_name(name, fallback=id_prefix)
        item_id = f"{id_prefix}_{suffix}"
        icon_id = f"{icon_prefix or 'ICON_' + id_prefix}_{suffix}"
        base_name = f"{filename_prefix_from_identifier(suffix)}UnitAtlas" if unit_icon_base else icon_id
        items.append(
            {
                "label": name,
                "id": item_id,
                "loc": {
                    "name": f"LOC_{id_prefix}_{suffix}_NAME",
                    "description": f"LOC_{id_prefix}_{suffix}_DESCRIPTION",
                },
                "icon": icon_id,
                "cropper_options": [
                    cropper_option(f"{id_prefix.title()} icons", cropper_mode, base_name, output_dir),
                ],
            }
        )
    return items


def cropper_option(label: str, mode: str, base_name: str, output_dir: str) -> dict[str, str]:
    return {
        "label": label,
        "mode": mode,
        "base_name": base_name,
        "output_dir": output_dir,
    }


def create_template_replacement_plan(
    brief: str,
    context: dict[str, Any],
    settings: dict[str, Any],
) -> dict[str, Any]:
    if not settings["api_key"]:
        raise ValueError("Missing OPENAI_API_KEY. Add it to .env before using Template Copilot.")

    prompt = {
        "task": "Create exact string replacements for Civilization VI XML and SQL mod templates.",
        "rules": [
            "Return only valid JSON.",
            "Do not return markdown.",
            "Return a conservative replacement map only; do not rewrite whole files.",
            "Do not use XML blocks, SQL statements, or multi-line chunks as replacement keys or values.",
            "Do not use broad generic keys such as Template, Leader, Civilization, Name, Text, Row, or Description.",
            "Keys in replacements must be exact strings from all_placeholders, exact XML/SQL/ArtDef identifiers, or exact visible template text values from file samples.",
            "Prefer the longest exact placeholder or text value available.",
            "Never invent replacement keys that are not present in the selected templates.",
            "Original template files are read-only; output files must preserve XML and SQL structure unless the user manually provides replacements.",
            "For SQL files, replace only scalar identifiers or quoted text values; never rewrite INSERT/UPDATE statement structure.",
            "When selected XML and SQL files refer to the same entity, use the same replacement values across both formats.",
            "Use Civ-style uppercase identifiers for XML IDs, e.g. CIVILIZATION_NAME, LEADER_NAME, ICON_LEADER_NAME.",
            "Keep LOC_ tags as uppercase underscore identifiers.",
            "Generate natural in-game English text for visible localization values.",
            "Use civilization_profiles to keep each civilization's city names, citizen/demonym names, and unique governors separated.",
            "Governor details are optional and include governor title, short title, identity pressure, portrait IDs, traits, promotion sets, prereqs, promotion modifiers, and LOC text.",
            "Named geography is a compulsory core civilization component in TemplateCiv_Civilization plus Base text LOC rows: rivers, lakes, seas, deserts, volcanoes, and mountains must stay tied to the owning civilization.",
            "Use leader_bindings so each leader is attached to the intended civilization; do not randomly pair leaders and civilizations.",
            "District names belong to district XML, district modifiers, projects, icons, and localization when those files are selected.",
            "If output_strategy is separate and there are multiple leaders/civilizations/units/buildings/improvements/governors, return variants.",
            "If output_strategy is merge, return one replacements object that merges the requested entities into selected XML, SQL, or ArtDef files where possible.",
        ],
        "required_json_shape": {
            "file_prefix": "Short filename prefix, e.g. MyCiv",
            "replacements": {"OLD_EXACT_TEXT": "NEW_EXACT_TEXT"},
            "variants": [
                {
                    "name": "Short variant name for separate output",
                    "file_prefix": "Short filename prefix",
                    "replacements": {"OLD_EXACT_TEXT": "NEW_EXACT_TEXT"},
                }
            ],
            "notes": ["short note"],
        },
        "user_brief": brief,
        "context": context,
    }
    request_body = {
        "model": settings.get("text_model") or "gpt-4.1-mini",
        "input": [
            {
                "role": "system",
                "content": "You produce safe deterministic replacement maps for Civilization VI XML and SQL template files.",
            },
            {
                "role": "user",
                "content": json.dumps(prompt, ensure_ascii=False),
            },
        ],
        "text": {
            "format": {
                "type": "json_object",
            }
        },
    }
    response = call_openai_responses_api(request_body, settings["api_key"])
    text = extract_openai_text(response)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"OpenAI returned invalid JSON: {text[:500]}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("OpenAI returned JSON, but not an object.")
    return parsed


def call_openai_responses_api(body: dict[str, Any], api_key: str) -> dict[str, Any]:
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API returned {exc.code}: {details}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach OpenAI API: {exc.reason}") from exc


def extract_openai_text(response: dict[str, Any]) -> str:
    if isinstance(response.get("output_text"), str):
        return response["output_text"]
    chunks: list[str] = []
    for output in response.get("output", []):
        for content in output.get("content", []):
            if content.get("type") in {"output_text", "text"} and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    if chunks:
        return "".join(chunks)
    raise RuntimeError("OpenAI response did not include text output.")


def apply_replacements_to_text(text: str, replacements: dict[str, str]) -> str:
    rendered = text
    for old, new in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
        if old:
            rendered = rendered.replace(old, new)
    return rendered


def count_applied_replacements(text: str, replacements: dict[str, str]) -> int:
    return sum(text.count(old) for old in replacements if old)


def workspace_files(root: Path, limit: int) -> list[str]:
    try:
        result = subprocess.run(
            ["rg", "--files"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        files = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return [file for file in files if not ignored_workspace_file(file)][:limit]
    except (FileNotFoundError, subprocess.CalledProcessError):
        files: list[str] = []
        for path in root.rglob("*"):
            if len(files) >= limit:
                break
            if path.is_dir():
                continue
            relative = path.relative_to(root)
            if any(part in DEFAULT_IGNORE_DIRS for part in relative.parts):
                continue
            files.append(str(relative).replace("\\", "/"))
        return files


def ignored_workspace_file(path: str) -> bool:
    return any(part in DEFAULT_IGNORE_DIRS for part in Path(path).parts)


def profile_notes(mode: str) -> str:
    notes = {
        "building_icons": "Buildings: square icons at 32, 38, 50, 80, 128, and 256.",
        "civilization_icons": "Civilizations: common square Civ icon set.",
        "unit_icons": "Units: wide 2x atlas files with a normal left icon and smart white right icon; circular seals use detail masks instead of a plain disk.",
        "leader_icons": "Leaders: circular portrait icons with dark circular background.",
        "arx_icons": "ARX: square 54x54 cropper output for small Civ ARX assets.",
        "leader_portraits": "Leader portraits: 825x1024, FALLBACK_NEUTRAL 825x1024, and 1024x1024 HD-upscaled crops.",
        "diplomacy_backgrounds": "Diplomacy backgrounds: HD-upscaled 1920x960 cover-fit crops for Civ diploBGs.",
        "moment_pictures": "Moment pictures: HD-upscaled 375x375 cover-fit square scene crops.",
        "thumbnails": "Thumbnails: HD-upscaled 512x512 cover-fit square thumbnails.",
        "governor_icons": "Governors: 22 and 32 include normal, alternate, and disabled gray variants.",
        "leader_circle": "Custom leader-circle preset using the common Civ icon sizes.",
        "raw_256": "Raw uploaded image resized into a 256x256 PNG canvas.",
    }
    return notes.get(mode, "")


def with_file_urls(manifest: dict) -> dict:
    for item in manifest.get("generated_files", []):
        item["url"] = file_url(Path(item["path"]))
    return manifest


def file_url(path: Path) -> str:
    return f"/api/file?path={quote(str(path.resolve()))}"


def resolve_output_dir(value: str) -> Path:
    output_dir = Path(value.strip() or "output/icons")
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    return output_dir


def sanitize_base_name(value: str, preserve_case: bool = False) -> str:
    source = value.strip() if preserve_case else value.strip().upper()
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", source).strip("_")
    return cleaned or "ICON_CUSTOM"


def sanitize_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return cleaned or "upload.png"


def parse_hex_color(value: str) -> list[int]:
    color = value.strip().lstrip("#")
    if len(color) != 6:
        raise FrontendError("Circle color must be a 6-digit hex color.")
    return [int(color[index : index + 2], 16) for index in (0, 2, 4)] + [255]


def form_value(form: FormData, key: str, default: str) -> str:
    return form.values.get(key, default)


def form_bool(form: FormData, key: str, default: bool) -> bool:
    if key not in form.values:
        return default
    return form_value(form, key, "false").lower() in {"1", "true", "yes", "on"}


def form_int(form: FormData, key: str, default: int) -> int:
    return int(float(form_value(form, key, str(default))))


def form_float(form: FormData, key: str, default: float) -> float:
    return float(form_value(form, key, str(default)))


class CropperFrontendServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], settings: dict[str, Any]):
        super().__init__(server_address, CropperFrontendHandler)
        self.settings = settings
        self.server_pool: dict[int, subprocess.Popen] = {}


def run(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, settings: dict[str, Any] | None = None) -> None:
    RUN_ROOT.mkdir(exist_ok=True)
    if settings is None:
        settings = load_settings(argparse.Namespace(
            api_key="",
            workflow_id="",
            workflow_version="",
            user="",
            workspace="",
            prompt="",
            text_model="",
            image_model="",
            file_limit=200,
        ))
    server = CropperFrontendServer((host, port), settings)
    print(f"Cropper frontend running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the local Civ icon cropper frontend.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--api-key", default="", help="OpenAI API key for ChatKit session creation.")
    parser.add_argument("--workflow-id", default="", help="Published Agent Builder workflow ID.")
    parser.add_argument("--workflow-version", default="", help="Optional Agent Builder workflow version.")
    parser.add_argument("--user", default="", help="ChatKit user scope.")
    parser.add_argument("--workspace", default="", help="Workspace folder to summarize for the agent.")
    parser.add_argument("--prompt", default="", help="Initial workflow prompt/context.")
    parser.add_argument("--text-model", default="", help="OpenAI model for Template Copilot.")
    parser.add_argument("--image-model", default="", help="OpenAI image model for Image Lab.")
    parser.add_argument("--file-limit", type=int, default=200)
    parser.add_argument(
        "--once",
        action="store_true",
        help="Create one ChatKit session and print it instead of starting the UI.",
    )
    args = parser.parse_args()
    settings = load_settings(args)
    if args.once:
        print(json.dumps(create_chatkit_session(settings), indent=2))
    else:
        run(args.host, args.port, settings)
