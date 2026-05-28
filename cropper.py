from __future__ import annotations

import json
import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageDraw, ImageFilter, ImageOps


CIV6_COMMON_SIZES = [256, 200, 128, 80, 64, 50, 48, 45, 44, 36, 32, 30, 24, 22]
CIV6_BUILDING_SIZES = [32, 38, 50, 80, 128, 256]
CIV6_CIVILIZATION_SIZES = [22, 30, 32, 36, 44, 45, 48, 50, 64, 80, 128, 200, 256]
CIV6_UNIT_SIZES = [22, 32, 38, 50, 70, 80, 95, 200, 256]
CIV6_LEADER_SIZES = [32, 45, 50, 55, 64, 80, 256]
CIV6_GOVERNOR_SIZES = [22, 24, 32, 64]
CIV6_ARX_SIZES = [54]
LEADER_PORTRAIT_DIMENSIONS = [[825, 1024], [1024, 1024]]
DIPLOMACY_BACKGROUND_DIMENSIONS = [[1920, 960]]
MOMENT_PICTURE_SIZES = [375]
THUMBNAIL_SIZES = [512]
SUPPORTED_SHAPES = {"square", "wide_2x", "custom"}
SUPPORTED_CANVAS_FITS = {"contain", "cover"}
SUPPORTED_MODES = {
    "building_icons",
    "civilization_icons",
    "unit_icons",
    "leader_icons",
    "governor_icons",
    "arx_icons",
    "leader_circle",
    "leader_portraits",
    "diplomacy_backgrounds",
    "moment_pictures",
    "thumbnails",
    "raw_256",
}

LEADER_CIRCLE_PRESET: dict[str, Any] = {
    "profile": "leader_circle",
    "shape": "square",
    "circle": {
        "enabled": True,
        "crop_to_circle": True,
        "background": {
            "enabled": True,
            "color": [18, 18, 18, 255],
        },
    },
    "trim_transparency": True,
    "padding_percent": 0,
    "subject_scale_percent": 108,
    "vertical_offset_percent": 0,
    "horizontal_offset_percent": 0,
    "background_remove": {
        "enabled": True,
    },
}

MODE_PRESETS: dict[str, dict[str, Any]] = {
    "building_icons": {
        "profile": "building_icons",
        "shape": "square",
        "sizes": CIV6_BUILDING_SIZES,
        "trim_transparency": True,
        "padding_percent": 8,
    },
    "civilization_icons": {
        "profile": "civilization_icons",
        "shape": "square",
        "sizes": CIV6_CIVILIZATION_SIZES,
        "trim_transparency": True,
        "padding_percent": 8,
    },
    "unit_icons": {
        "profile": "unit_icons",
        "shape": "wide_2x",
        "sizes": CIV6_UNIT_SIZES,
        "trim_transparency": True,
        "padding_percent": 8,
        "unit_white_right": True,
    },
    "leader_icons": {
        **LEADER_CIRCLE_PRESET,
        "profile": "leader_icons",
        "sizes": CIV6_LEADER_SIZES,
    },
    "governor_icons": {
        "profile": "governor_icons",
        "shape": "square",
        "sizes": CIV6_GOVERNOR_SIZES,
        "trim_transparency": True,
        "padding_percent": 8,
        "governor_variants": True,
    },
    "arx_icons": {
        "profile": "arx_icons",
        "shape": "square",
        "sizes": CIV6_ARX_SIZES,
        "trim_transparency": True,
        "padding_percent": 6,
        "subject_scale_percent": 100,
        "background_remove": {
            "enabled": False,
        },
        "hd_upscale": True,
    },
    "leader_circle": LEADER_CIRCLE_PRESET,
    "leader_portraits": {
        "profile": "leader_portraits",
        "shape": "custom",
        "dimensions": LEADER_PORTRAIT_DIMENSIONS,
        "trim_transparency": True,
        "padding_percent": 0,
        "subject_scale_percent": 100,
        "background_remove": {
            "enabled": False,
        },
        "hd_upscale": True,
    },
    "diplomacy_backgrounds": {
        "profile": "diplomacy_backgrounds",
        "shape": "custom",
        "dimensions": DIPLOMACY_BACKGROUND_DIMENSIONS,
        "trim_transparency": False,
        "padding_percent": 0,
        "subject_scale_percent": 100,
        "background_remove": {
            "enabled": False,
        },
        "hd_upscale": True,
        "canvas_fit": "cover",
    },
    "moment_pictures": {
        "profile": "moment_pictures",
        "shape": "square",
        "sizes": MOMENT_PICTURE_SIZES,
        "trim_transparency": False,
        "padding_percent": 0,
        "subject_scale_percent": 100,
        "background_remove": {
            "enabled": False,
        },
        "hd_upscale": True,
        "canvas_fit": "cover",
    },
    "thumbnails": {
        "profile": "thumbnails",
        "shape": "square",
        "sizes": THUMBNAIL_SIZES,
        "trim_transparency": False,
        "padding_percent": 0,
        "subject_scale_percent": 100,
        "background_remove": {
            "enabled": False,
        },
        "hd_upscale": True,
        "canvas_fit": "cover",
    },
    "raw_256": {
        "profile": "raw_256",
        "shape": "square",
        "sizes": [256],
        "trim_transparency": False,
        "padding_percent": 0,
        "raw_resize_only": True,
    },
}


class CropperError(Exception):
    """Raised for expected, user-facing cropper failures."""


@dataclass(frozen=True)
class BackgroundRemoveConfig:
    enabled: bool
    sample: str
    method: str
    tolerance: int
    feather: float
    despill: bool


@dataclass(frozen=True)
class CircleBackgroundConfig:
    enabled: bool
    color: tuple[int, int, int, int]


@dataclass(frozen=True)
class CircleConfig:
    enabled: bool
    crop_to_circle: bool
    background: CircleBackgroundConfig
    margin_percent: float
    allow_non_square: bool


@dataclass(frozen=True)
class SilhouetteConfig:
    enabled: bool
    color: tuple[int, int, int, int]


@dataclass(frozen=True)
class OutputDimension:
    width: int
    height: int


@dataclass(frozen=True)
class OutputJob:
    dimension: OutputDimension
    suffix: str = ""
    variant: str = "normal"
    filename_override: str | None = None


@dataclass(frozen=True)
class Recipe:
    source: Path
    output_dir: Path
    base_name: str
    profile: str
    mode: str | None
    shape: str
    dimensions: list[OutputDimension]
    padding_percent: float
    trim_transparency: bool
    make_transparent: bool
    background_remove: BackgroundRemoveConfig
    circle: CircleConfig
    silhouette: SilhouetteConfig
    subject_scale_percent: float
    vertical_offset_percent: float
    horizontal_offset_percent: float
    unit_right_scale_percent: float
    unit_white_right: bool
    governor_variants: bool
    raw_resize_only: bool
    hd_upscale: bool
    canvas_fit: str
    overwrite: bool


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: python cropper.py recipe.json", file=sys.stderr)
        return 2

    try:
        recipe_path = Path(argv[1])
        recipe_data = load_recipe_json(recipe_path)
        recipe = validate_recipe(recipe_data, recipe_path)
        manifest = process_recipe(recipe)
        print(f"Generated {len(manifest['generated_files'])} file(s).")
        return 0
    except CropperError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def load_recipe_json(recipe_path: Path) -> dict[str, Any]:
    try:
        with recipe_path.open("r", encoding="utf-8") as recipe_file:
            data = json.load(recipe_file)
    except FileNotFoundError as exc:
        raise CropperError(f"Recipe file does not exist: {recipe_path}") from exc
    except json.JSONDecodeError as exc:
        raise CropperError(
            f"Invalid JSON in {recipe_path}: line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    except OSError as exc:
        raise CropperError(f"Cannot read recipe file {recipe_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise CropperError("Recipe JSON must be an object.")
    return data


def validate_recipe(data: dict[str, Any], recipe_path: Path) -> Recipe:
    data = apply_mode_defaults(data)

    source = required_path(data, "source", recipe_path)
    output_dir = required_path(data, "output_dir", recipe_path)
    base_name = required_string(data, "base_name")
    profile = optional_string(data, "profile", "custom")
    mode = validate_mode(data.get("mode"))
    shape = optional_string(data, "shape", "square")

    if shape not in SUPPORTED_SHAPES:
        raise CropperError(
            f"Unsupported shape {shape!r}. Expected one of: {', '.join(sorted(SUPPORTED_SHAPES))}."
        )

    padding_percent = optional_number(data, "padding_percent", 0)
    if padding_percent < 0:
        raise CropperError("padding_percent must be 0 or greater.")

    subject_scale_percent = optional_number(data, "subject_scale_percent", 100)
    if subject_scale_percent <= 0:
        raise CropperError("subject_scale_percent must be greater than 0.")

    vertical_offset_percent = optional_number(data, "vertical_offset_percent", 0)
    horizontal_offset_percent = optional_number(data, "horizontal_offset_percent", 0)
    unit_right_scale_percent = optional_number(data, "unit_right_scale_percent", subject_scale_percent)
    if unit_right_scale_percent <= 0:
        raise CropperError("unit_right_scale_percent must be greater than 0.")

    trim_transparency = optional_bool(data, "trim_transparency", True)
    make_transparent = optional_bool(data, "make_transparent", False)
    unit_white_right = optional_bool(data, "unit_white_right", False)
    governor_variants = optional_bool(data, "governor_variants", False)
    raw_resize_only = optional_bool(data, "raw_resize_only", False)
    hd_upscale = optional_bool(data, "hd_upscale", False)
    canvas_fit = optional_string(data, "canvas_fit", "contain")
    if canvas_fit not in SUPPORTED_CANVAS_FITS:
        raise CropperError(
            f"Unsupported canvas_fit {canvas_fit!r}. Expected one of: {', '.join(sorted(SUPPORTED_CANVAS_FITS))}."
        )
    overwrite = optional_bool(data, "overwrite", False)

    background_remove = validate_background_remove(data.get("background_remove"))
    circle = validate_circle(data.get("circle"))
    silhouette = validate_silhouette(data.get("silhouette"))
    dimensions = validate_dimensions(data, shape)

    return Recipe(
        source=source,
        output_dir=output_dir,
        base_name=base_name,
        profile=profile,
        mode=mode,
        shape=shape,
        dimensions=dimensions,
        padding_percent=padding_percent,
        trim_transparency=trim_transparency,
        make_transparent=make_transparent,
        background_remove=background_remove,
        circle=circle,
        silhouette=silhouette,
        subject_scale_percent=subject_scale_percent,
        vertical_offset_percent=vertical_offset_percent,
        horizontal_offset_percent=horizontal_offset_percent,
        unit_right_scale_percent=unit_right_scale_percent,
        unit_white_right=unit_white_right,
        governor_variants=governor_variants,
        raw_resize_only=raw_resize_only,
        hd_upscale=hd_upscale,
        canvas_fit=canvas_fit,
        overwrite=overwrite,
    )


def apply_mode_defaults(data: dict[str, Any]) -> dict[str, Any]:
    mode = data.get("mode")
    if mode is None:
        return dict(data)
    if not isinstance(mode, str) or not mode.strip():
        raise CropperError("mode must be a non-empty string when provided.")
    if mode not in MODE_PRESETS:
        raise CropperError(f"Unsupported mode {mode!r}. Expected one of: {', '.join(sorted(SUPPORTED_MODES))}.")

    merged = deep_merge(MODE_PRESETS[mode], data)
    merged["mode"] = mode
    return merged


def deep_merge(defaults: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = dict(defaults)
    for key, value in overrides.items():
        default_value = merged.get(key)
        if isinstance(default_value, dict) and isinstance(value, dict):
            merged[key] = deep_merge(default_value, value)
        else:
            merged[key] = value
    return merged


def validate_mode(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise CropperError("mode must be a non-empty string when provided.")
    if value not in SUPPORTED_MODES:
        raise CropperError(f"Unsupported mode {value!r}. Expected one of: {', '.join(sorted(SUPPORTED_MODES))}.")
    return value


def required_path(data: dict[str, Any], key: str, recipe_path: Path) -> Path:
    value = required_string(data, key)
    path = Path(value)
    if not path.is_absolute():
        path = recipe_path.parent / path
    return path


def required_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CropperError(f"Missing or invalid required string field: {key}.")
    return value


def optional_string(data: dict[str, Any], key: str, default: str) -> str:
    value = data.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise CropperError(f"Invalid string field: {key}.")
    return value


def optional_bool(data: dict[str, Any], key: str, default: bool) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise CropperError(f"Invalid boolean field: {key}.")
    return value


def optional_number(data: dict[str, Any], key: str, default: float) -> float:
    value = data.get(key, default)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise CropperError(f"Invalid number field: {key}.")
    return float(value)


def validate_background_remove(value: Any) -> BackgroundRemoveConfig:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise CropperError("background_remove must be an object.")

    enabled = optional_bool(value, "enabled", False)
    sample = optional_string(value, "sample", "corners")
    if sample != "corners":
        raise CropperError("background_remove.sample currently supports only 'corners'.")

    method = optional_string(value, "method", "advanced")
    if method not in {"advanced", "simple"}:
        raise CropperError("background_remove.method must be either 'advanced' or 'simple'.")

    tolerance_value = value.get("tolerance", 30)
    if not isinstance(tolerance_value, int) or isinstance(tolerance_value, bool):
        raise CropperError("background_remove.tolerance must be an integer.")
    if tolerance_value < 0 or tolerance_value > 441:
        raise CropperError("background_remove.tolerance must be between 0 and 441.")

    feather = optional_number(value, "feather", 0)
    if feather < 0:
        raise CropperError("background_remove.feather must be 0 or greater.")

    despill = optional_bool(value, "despill", False)

    return BackgroundRemoveConfig(
        enabled=enabled,
        sample=sample,
        method=method,
        tolerance=tolerance_value,
        feather=feather,
        despill=despill,
    )


def validate_circle(value: Any) -> CircleConfig:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise CropperError("circle must be an object.")

    background_value = value.get("background", {})
    if not isinstance(background_value, dict):
        raise CropperError("circle.background must be an object.")

    margin_percent = optional_number(value, "margin_percent", 0)
    if margin_percent < 0 or margin_percent >= 50:
        raise CropperError("circle.margin_percent must be at least 0 and less than 50.")

    return CircleConfig(
        enabled=optional_bool(value, "enabled", False),
        crop_to_circle=optional_bool(value, "crop_to_circle", False),
        background=CircleBackgroundConfig(
            enabled=optional_bool(background_value, "enabled", False),
            color=parse_rgba_color(background_value.get("color", [18, 18, 18, 255]), "circle.background.color"),
        ),
        margin_percent=margin_percent,
        allow_non_square=optional_bool(value, "allow_non_square", False),
    )


def validate_silhouette(value: Any) -> SilhouetteConfig:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise CropperError("silhouette must be an object.")

    enabled = optional_bool(value, "enabled", False)
    return SilhouetteConfig(
        enabled=enabled,
        color=parse_rgba_color(value.get("color", [255, 255, 255, 255]), "silhouette.color"),
    )


def parse_rgba_color(value: Any, field_name: str) -> tuple[int, int, int, int]:
    if not isinstance(value, list) or len(value) != 4:
        raise CropperError(f"{field_name} must be a list of four integers: [r, g, b, a].")
    channels: list[int] = []
    for channel in value:
        if not isinstance(channel, int) or isinstance(channel, bool) or channel < 0 or channel > 255:
            raise CropperError(f"{field_name} channels must be integers from 0 to 255.")
        channels.append(channel)
    return tuple(channels)


def validate_dimensions(data: dict[str, Any], shape: str) -> list[OutputDimension]:
    dimensions_value = data.get("dimensions")
    if dimensions_value is not None:
        return parse_dimensions(dimensions_value)

    if shape == "custom":
        raise CropperError("custom shape requires dimensions, for example [[512, 256], [400, 200]].")

    sizes_value = data.get("sizes", CIV6_COMMON_SIZES)
    sizes = parse_sizes(sizes_value)

    if shape == "square":
        return [OutputDimension(size, size) for size in sizes]
    if shape == "wide_2x":
        return [OutputDimension(size * 2, size) for size in sizes]

    raise CropperError(f"Unsupported shape {shape!r}.")


def parse_sizes(value: Any) -> list[int]:
    if not isinstance(value, list) or not value:
        raise CropperError("sizes must be a non-empty list of positive integers.")

    sizes: list[int] = []
    for item in value:
        if not isinstance(item, int) or isinstance(item, bool) or item <= 0:
            raise CropperError("sizes must contain only positive integers.")
        sizes.append(item)
    return sizes


def parse_dimensions(value: Any) -> list[OutputDimension]:
    if not isinstance(value, list) or not value:
        raise CropperError("dimensions must be a non-empty list of [width, height] pairs.")

    dimensions: list[OutputDimension] = []
    for item in value:
        if (
            not isinstance(item, list)
            or len(item) != 2
            or not all(isinstance(part, int) and not isinstance(part, bool) and part > 0 for part in item)
        ):
            raise CropperError("dimensions must contain only [width, height] positive integer pairs.")
        dimensions.append(OutputDimension(item[0], item[1]))
    return dimensions


def process_recipe(recipe: Recipe) -> dict[str, Any]:
    warnings: list[str] = []

    if not recipe.source.exists():
        raise CropperError(f"Missing source file: {recipe.source}")
    if not recipe.source.is_file():
        raise CropperError(f"Source path is not a file: {recipe.source}")

    ensure_output_dir(recipe.output_dir)
    remove_stale_manifest(recipe.output_dir, warnings)
    warn_if_output_dir_not_empty(recipe, warnings)
    ensure_targets_writable(recipe)

    try:
        image = Image.open(recipe.source).convert("RGBA")
    except OSError as exc:
        raise CropperError(f"Cannot open source image {recipe.source}: {exc}") from exc

    original_width, original_height = image.size
    if recipe.background_remove.enabled and has_meaningful_alpha(image):
        warnings.append("Background removal is enabled, but the source image already has meaningful alpha.")

    if recipe.background_remove.enabled:
        image = remove_background_from_corners(
            image,
            recipe.background_remove.tolerance,
            recipe.background_remove.feather,
            recipe.background_remove.despill,
            recipe.background_remove.method,
        )

    if recipe.make_transparent:
        image = make_color_transparent_from_corners(
            image,
            recipe.background_remove.tolerance,
            recipe.background_remove.feather,
            recipe.background_remove.despill,
            recipe.background_remove.method,
        )

    if recipe.trim_transparency:
        image = trim_transparent_pixels(image)
    elif image.getchannel("A").getbbox() is None:
        raise CropperError("No visible pixels after trimming/background removal.")

    padded = add_padding(image, recipe.padding_percent)
    subject = apply_silhouette(padded, recipe.silhouette.color) if recipe.silhouette.enabled else padded

    generated_files: list[dict[str, Any]] = []
    for job in output_jobs_for_recipe(recipe):
        dimension = job.dimension
        working_subject = subject
        if original_width < dimension.width or original_height < dimension.height:
            warnings.append(
                f"Source image {original_width}x{original_height} is smaller than requested "
                f"output {dimension.width}x{dimension.height}."
            )
            if recipe.hd_upscale:
                warnings.append(
                    f"HD upscale applied before fitting {dimension.width}x{dimension.height}."
                )
                working_subject = hd_upscale_subject(subject, dimension)

        if recipe.unit_white_right:
            subject_canvas = compose_unit_white_right(working_subject, dimension, recipe)
            final_image = subject_canvas
        else:
            if recipe.canvas_fit == "cover":
                subject_canvas = cover_subject_on_target_canvas(
                    working_subject,
                    dimension,
                    recipe.subject_scale_percent,
                    recipe.horizontal_offset_percent,
                    recipe.vertical_offset_percent,
                )
            else:
                subject_canvas = place_subject_on_target_canvas(
                    working_subject,
                    dimension,
                    recipe.subject_scale_percent,
                    recipe.horizontal_offset_percent,
                    recipe.vertical_offset_percent,
                )
            final_image = compose_circle_layers(subject_canvas, recipe.circle)

        if job.variant == "disabled_gray":
            final_image = apply_disabled_gray(final_image)

        if recipe.canvas_fit != "cover" and visible_content_touches_edge(subject_canvas):
            warnings.append(
                f"Visible content touches the final canvas edge for {dimension.width}x{dimension.height}."
            )

        output_path = output_file_path(recipe, dimension, job.suffix, job.filename_override)
        remove_legacy_unit_output(recipe, dimension, output_path, job.suffix, warnings)
        try:
            final_image.save(output_path, "PNG")
        except OSError as exc:
            raise CropperError(f"Cannot write output PNG {output_path}: {exc}") from exc
        file_record = {
            "path": str(output_path),
            "width": dimension.width,
            "height": dimension.height,
        }
        if job.variant != "normal":
            file_record["variant"] = job.variant
        generated_files.append(file_record)

    manifest = {
        "status": "success",
        "source": str(recipe.source),
        "profile": recipe.profile,
        "mode": recipe.mode,
        "shape": recipe.shape,
        "generated_files": generated_files,
        "warnings": unique_preserving_order(warnings),
    }
    return manifest


def ensure_output_dir(output_dir: Path) -> None:
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise CropperError(f"Cannot write output directory {output_dir}: {exc}") from exc

    if not output_dir.is_dir():
        raise CropperError(f"Cannot write output directory because path is not a directory: {output_dir}")


def remove_stale_manifest(output_dir: Path, warnings: list[str]) -> None:
    manifest_path = output_dir / "manifest.json"
    if not manifest_path.exists():
        return
    try:
        manifest_path.unlink()
    except OSError as exc:
        warnings.append(f"Could not remove stale manifest.json: {exc}")


def warn_if_output_dir_not_empty(recipe: Recipe, warnings: list[str]) -> None:
    if recipe.output_dir.exists() and not recipe.overwrite:
        try:
            has_files = any(path.is_file() for path in recipe.output_dir.iterdir())
        except OSError as exc:
            raise CropperError(f"Cannot inspect output directory {recipe.output_dir}: {exc}") from exc
        if has_files:
            warnings.append("output_dir already contains files and overwrite is false.")


def ensure_targets_writable(recipe: Recipe) -> None:
    for job in output_jobs_for_recipe(recipe):
        path = output_file_path(recipe, job.dimension, job.suffix, job.filename_override)
        if path.exists() and not recipe.overwrite:
            raise CropperError(f"Output file already exists and overwrite is false: {path}")


def has_meaningful_alpha(image: Image.Image) -> bool:
    alpha = image.getchannel("A")
    extrema = alpha.getextrema()
    return extrema[0] < 255


def remove_background_from_corners(
    image: Image.Image,
    tolerance: int,
    feather: float,
    despill: bool,
    method: str = "advanced",
) -> Image.Image:
    if method == "advanced":
        return remove_edge_connected_background(image, tolerance, feather, despill)
    if method != "simple":
        raise CropperError("background removal method must be 'advanced' or 'simple'.")

    image = image.copy()
    background = estimate_corner_color(image)
    pixels = image.load()
    width, height = image.size

    for y in range(height):
        for x in range(width):
            red, green, blue, alpha = pixels[x, y]
            distance = color_distance((red, green, blue), background)
            if alpha > 0 and distance <= tolerance:
                pixels[x, y] = (red, green, blue, 0)
            elif alpha > 0 and despill:
                pixels[x, y] = (*despill_pixel((red, green, blue), background, distance, tolerance, feather), alpha)

    if feather > 0:
        alpha = image.getchannel("A").filter(ImageFilter.GaussianBlur(radius=feather))
        image.putalpha(alpha)
    return image


def make_color_transparent_from_corners(
    image: Image.Image,
    tolerance: int,
    feather: float,
    despill: bool,
    method: str = "advanced",
) -> Image.Image:
    return remove_background_from_corners(image, tolerance, feather, despill, method)


def remove_edge_connected_background(
    image: Image.Image,
    tolerance: int,
    feather: float,
    despill: bool,
) -> Image.Image:
    image = image.copy()
    width, height = image.size
    pixels = image.load()
    background = estimate_edge_background_color(image, tolerance)
    background_mask = flood_fill_background_mask(image, background, tolerance)

    foreground_alpha = ImageOps.invert(background_mask)
    if feather > 0:
        background_mask = background_mask.filter(ImageFilter.MaxFilter(3))
        foreground_alpha = ImageOps.invert(background_mask).filter(ImageFilter.GaussianBlur(radius=feather))

    original_alpha = image.getchannel("A")
    image.putalpha(multiply_alpha(original_alpha, foreground_alpha))

    if despill:
        spill_range = max(1, tolerance + feather * 12 + 42)
        new_pixels = image.load()
        for y in range(height):
            for x in range(width):
                red, green, blue, alpha = new_pixels[x, y]
                if alpha == 0:
                    continue
                distance = color_distance((red, green, blue), background)
                if distance <= spill_range or foreground_alpha.getpixel((x, y)) < 250:
                    new_pixels[x, y] = (*despill_pixel((red, green, blue), background, distance, tolerance, feather), alpha)

    return image


def flood_fill_background_mask(
    image: Image.Image,
    background: tuple[int, int, int],
    tolerance: int,
) -> Image.Image:
    width, height = image.size
    pixels = image.load()
    visited = bytearray(width * height)
    background_mask = Image.new("L", (width, height), 0)
    mask_pixels = background_mask.load()
    queue: deque[tuple[int, int]] = deque()
    threshold = tolerance + 10

    def index(x: int, y: int) -> int:
        return y * width + x

    def is_background_candidate(x: int, y: int) -> bool:
        red, green, blue, alpha = pixels[x, y]
        if alpha == 0:
            return True
        return color_distance((red, green, blue), background) <= threshold

    for x in range(width):
        for y in (0, height - 1):
            current = index(x, y)
            if not visited[current] and is_background_candidate(x, y):
                visited[current] = 1
                queue.append((x, y))
    for y in range(height):
        for x in (0, width - 1):
            current = index(x, y)
            if not visited[current] and is_background_candidate(x, y):
                visited[current] = 1
                queue.append((x, y))

    while queue:
        x, y = queue.popleft()
        mask_pixels[x, y] = 255
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if nx < 0 or nx >= width or ny < 0 or ny >= height:
                continue
            current = index(nx, ny)
            if visited[current]:
                continue
            if not is_background_candidate(nx, ny):
                visited[current] = 1
                continue
            visited[current] = 1
            queue.append((nx, ny))

    return background_mask


def estimate_edge_background_color(image: Image.Image, tolerance: int) -> tuple[int, int, int]:
    corner_color = estimate_corner_color(image)
    width, height = image.size
    edge_pixels: list[tuple[int, int, int]] = []
    stride = max(1, min(width, height) // 160)
    acceptance = max(32, tolerance * 2 + 24)

    for x in range(0, width, stride):
        for y in (0, height - 1):
            red, green, blue, alpha = image.getpixel((x, y))
            if alpha > 0 and color_distance((red, green, blue), corner_color) <= acceptance:
                edge_pixels.append((red, green, blue))
    for y in range(0, height, stride):
        for x in (0, width - 1):
            red, green, blue, alpha = image.getpixel((x, y))
            if alpha > 0 and color_distance((red, green, blue), corner_color) <= acceptance:
                edge_pixels.append((red, green, blue))

    if len(edge_pixels) < 4:
        return corner_color

    edge_pixels.sort()
    reds = sorted(pixel[0] for pixel in edge_pixels)
    greens = sorted(pixel[1] for pixel in edge_pixels)
    blues = sorted(pixel[2] for pixel in edge_pixels)
    middle = len(edge_pixels) // 2
    return reds[middle], greens[middle], blues[middle]


def despill_pixel(
    color: tuple[int, int, int],
    background: tuple[int, int, int],
    distance: float,
    tolerance: int,
    feather: float,
) -> tuple[int, int, int]:
    spill_range = max(1, tolerance + feather * 8 + 24)
    if distance > spill_range:
        return color

    strength = (1 - (distance / spill_range)) * 0.45
    channels = []
    for channel, background_channel in zip(color, background):
        corrected = channel + (channel - background_channel) * strength
        channels.append(clamp_channel(round(corrected)))
    return tuple(channels)


def clamp_channel(value: int) -> int:
    return max(0, min(255, value))


def estimate_corner_color(image: Image.Image) -> tuple[int, int, int]:
    width, height = image.size
    corners = [
        image.getpixel((0, 0)),
        image.getpixel((width - 1, 0)),
        image.getpixel((0, height - 1)),
        image.getpixel((width - 1, height - 1)),
    ]
    visible_corners = [corner for corner in corners if corner[3] > 0]
    if not visible_corners:
        visible_corners = corners

    red = round(sum(corner[0] for corner in visible_corners) / len(visible_corners))
    green = round(sum(corner[1] for corner in visible_corners) / len(visible_corners))
    blue = round(sum(corner[2] for corner in visible_corners) / len(visible_corners))
    return red, green, blue


def color_distance(left: tuple[int, int, int], right: tuple[int, int, int]) -> float:
    return sum((a - b) ** 2 for a, b in zip(left, right)) ** 0.5


def trim_transparent_pixels(image: Image.Image) -> Image.Image:
    alpha_bbox = image.getchannel("A").getbbox()
    if alpha_bbox is None:
        raise CropperError("No visible pixels after trimming/background removal.")
    return image.crop(alpha_bbox)


def add_padding(image: Image.Image, padding_percent: float) -> Image.Image:
    width, height = image.size
    padding = round(max(width, height) * (padding_percent / 100))
    if padding == 0:
        return image

    canvas = Image.new("RGBA", (width + padding * 2, height + padding * 2), (0, 0, 0, 0))
    canvas.alpha_composite(image, (padding, padding))
    return canvas


def place_on_aspect_canvas(image: Image.Image, target_aspect: float) -> Image.Image:
    width, height = image.size
    source_aspect = width / height

    if source_aspect > target_aspect:
        canvas_width = width
        canvas_height = max(1, round(width / target_aspect))
    else:
        canvas_height = height
        canvas_width = max(1, round(height * target_aspect))

    canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
    x = (canvas_width - width) // 2
    y = (canvas_height - height) // 2
    canvas.alpha_composite(image, (x, y))
    return canvas


def place_subject_on_target_canvas(
    image: Image.Image,
    dimension: OutputDimension,
    subject_scale_percent: float,
    horizontal_offset_percent: float,
    vertical_offset_percent: float,
) -> Image.Image:
    target_width = dimension.width
    target_height = dimension.height
    source_width, source_height = image.size
    fit_scale = min(target_width / source_width, target_height / source_height)
    scale = fit_scale * (subject_scale_percent / 100)
    resized_width = max(1, round(source_width * scale))
    resized_height = max(1, round(source_height * scale))
    resized = image.resize((resized_width, resized_height), Image.Resampling.LANCZOS)

    x = round((target_width - resized_width) / 2 + target_width * (horizontal_offset_percent / 100))
    y = round((target_height - resized_height) / 2 + target_height * (vertical_offset_percent / 100))

    canvas = Image.new("RGBA", (target_width, target_height), (0, 0, 0, 0))
    alpha_composite_clipped(canvas, resized, x, y)
    return canvas


def hd_upscale_subject(image: Image.Image, dimension: OutputDimension) -> Image.Image:
    width, height = image.size
    if width >= dimension.width and height >= dimension.height:
        return image

    scale = max(dimension.width / width, dimension.height / height)
    upscale_width = max(width, round(width * scale))
    upscale_height = max(height, round(height * scale))
    upscaled = image.resize((upscale_width, upscale_height), Image.Resampling.LANCZOS)
    upscaled = upscaled.filter(ImageFilter.UnsharpMask(radius=1.4, percent=120, threshold=3))
    return upscaled


def cover_subject_on_target_canvas(
    image: Image.Image,
    dimension: OutputDimension,
    scale_percent: float,
    horizontal_offset_percent: float,
    vertical_offset_percent: float,
) -> Image.Image:
    source_width, source_height = image.size
    target_width, target_height = dimension.width, dimension.height
    scale = max(target_width / source_width, target_height / source_height) * (scale_percent / 100)
    resized_width = max(1, round(source_width * scale))
    resized_height = max(1, round(source_height * scale))
    resized = image.resize((resized_width, resized_height), Image.Resampling.LANCZOS)

    x = round((target_width - resized_width) / 2 + target_width * (horizontal_offset_percent / 100))
    y = round((target_height - resized_height) / 2 + target_height * (vertical_offset_percent / 100))

    canvas = Image.new("RGBA", (target_width, target_height), (0, 0, 0, 0))
    alpha_composite_clipped(canvas, resized, x, y)
    return canvas


def alpha_composite_clipped(target: Image.Image, source: Image.Image, x: int, y: int) -> None:
    target_width, target_height = target.size
    source_width, source_height = source.size

    left = max(0, x)
    top = max(0, y)
    right = min(target_width, x + source_width)
    bottom = min(target_height, y + source_height)
    if left >= right or top >= bottom:
        return

    source_left = left - x
    source_top = top - y
    source_right = source_left + (right - left)
    source_bottom = source_top + (bottom - top)
    target.alpha_composite(source.crop((source_left, source_top, source_right, source_bottom)), (left, top))


def compose_circle_layers(subject_canvas: Image.Image, circle: CircleConfig) -> Image.Image:
    if not circle.enabled:
        return subject_canvas

    width, height = subject_canvas.size
    is_square = width == height
    if not is_square and not circle.allow_non_square:
        return subject_canvas

    final_image = Image.new("RGBA", subject_canvas.size, (0, 0, 0, 0))
    circle_bbox = circle_bounding_box(width, height, circle.margin_percent)
    circle_mask = make_circle_mask(subject_canvas.size, circle_bbox)

    if circle.background.enabled:
        red, green, blue, alpha = circle.background.color
        background = Image.new("RGBA", subject_canvas.size, (red, green, blue, 0))
        background.putalpha(circle_mask.point(lambda value: round(value * (alpha / 255))))
        final_image.alpha_composite(background)

    final_image.alpha_composite(subject_canvas)

    if circle.crop_to_circle:
        final_image.putalpha(multiply_alpha(final_image.getchannel("A"), circle_mask))

    return final_image


def circle_bounding_box(width: int, height: int, margin_percent: float) -> tuple[int, int, int, int]:
    diameter = min(width, height)
    margin = round(diameter * (margin_percent / 100))
    left = (width - diameter) // 2 + margin
    top = (height - diameter) // 2 + margin
    right = left + diameter - margin * 2 - 1
    bottom = top + diameter - margin * 2 - 1
    return left, top, max(left, right), max(top, bottom)


def make_circle_mask(size: tuple[int, int], bbox: tuple[int, int, int, int]) -> Image.Image:
    scale = 4
    scaled_size = (size[0] * scale, size[1] * scale)
    scaled_bbox = tuple(value * scale for value in bbox)
    mask = Image.new("L", scaled_size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse(scaled_bbox, fill=255)
    return mask.resize(size, Image.Resampling.LANCZOS)


def multiply_alpha(alpha: Image.Image, mask: Image.Image) -> Image.Image:
    alpha_pixels = alpha.load()
    mask_pixels = mask.load()
    result = Image.new("L", alpha.size, 0)
    result_pixels = result.load()
    width, height = alpha.size
    for y in range(height):
        for x in range(width):
            result_pixels[x, y] = round(alpha_pixels[x, y] * (mask_pixels[x, y] / 255))
    return result


def visible_content_touches_edge(image: Image.Image) -> bool:
    alpha = image.getchannel("A")
    width, height = image.size

    top = alpha.crop((0, 0, width, 1)).getbbox() is not None
    bottom = alpha.crop((0, height - 1, width, height)).getbbox() is not None
    left = alpha.crop((0, 0, 1, height)).getbbox() is not None
    right = alpha.crop((width - 1, 0, width, height)).getbbox() is not None
    return top or bottom or left or right


def apply_silhouette(image: Image.Image, color: tuple[int, int, int, int]) -> Image.Image:
    red, green, blue, silhouette_alpha = color
    alpha = image.getchannel("A")
    if silhouette_alpha < 255:
        alpha = alpha.point(lambda value: round(value * (silhouette_alpha / 255)))

    silhouette = Image.new("RGBA", image.size, (red, green, blue, 0))
    silhouette.putalpha(alpha)
    return silhouette


def compose_unit_white_right(image: Image.Image, dimension: OutputDimension, recipe: Recipe) -> Image.Image:
    half_width = dimension.width // 2
    if half_width <= 0:
        raise CropperError("unit_white_right requires an output width of at least 2 pixels.")

    half_dimension = OutputDimension(half_width, dimension.height)
    left = place_subject_on_target_canvas(
        image,
        half_dimension,
        recipe.subject_scale_percent,
        recipe.horizontal_offset_percent,
        recipe.vertical_offset_percent,
    )
    right = apply_unit_white_silhouette(left)
    if recipe.unit_right_scale_percent != recipe.subject_scale_percent:
        right = place_subject_on_target_canvas(
            image,
            half_dimension,
            recipe.unit_right_scale_percent,
            recipe.horizontal_offset_percent,
            recipe.vertical_offset_percent,
        )
        right = apply_unit_white_silhouette(right)

    canvas = Image.new("RGBA", (dimension.width, dimension.height), (0, 0, 0, 0))
    canvas.alpha_composite(left, (0, 0))
    canvas.alpha_composite(right, (half_width, 0))
    return canvas


def apply_unit_white_silhouette(image: Image.Image) -> Image.Image:
    detail_mask = circular_badge_detail_mask(image)
    if detail_mask is not None:
        silhouette = Image.new("RGBA", image.size, (255, 255, 255, 0))
        silhouette.putalpha(detail_mask)
        return silhouette
    return apply_silhouette(image, (255, 255, 255, 255))


def circular_badge_detail_mask(image: Image.Image) -> Image.Image | None:
    alpha = image.getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        return None

    left, top, right, bottom = bbox
    width = right - left
    height = bottom - top
    if min(width, height) < 12:
        return None
    aspect = width / height
    if not 0.82 <= aspect <= 1.22:
        return None

    alpha_crop = alpha.crop(bbox)
    alpha_values = image_pixels(alpha_crop)
    visible_count = sum(1 for value in alpha_values if value > 32)
    if visible_count == 0:
        return None

    fill_ratio = visible_count / (width * height)
    if not 0.58 <= fill_ratio <= 0.92:
        return None

    rgb_crop = image.convert("RGB").crop(bbox)
    rgb_pixels = image_pixels(rgb_crop)
    visible_pixels = [
        pixel for pixel, alpha_value in zip(rgb_pixels, alpha_values)
        if alpha_value > 160
    ]
    if len(visible_pixels) < 24:
        return None

    background = dominant_quantized_color(visible_pixels)
    detail_alpha = Image.new("L", (width, height), 0)
    detail_pixels = []
    for (red, green, blue), alpha_value in zip(rgb_pixels, alpha_values):
        if alpha_value <= 32:
            detail_pixels.append(0)
            continue
        distance = color_distance((red, green, blue), background)
        detail_pixels.append(alpha_value if distance > 42 else 0)
    detail_alpha.putdata(detail_pixels)

    detail_count = sum(1 for value in detail_pixels if value > 32)
    detail_ratio = detail_count / visible_count
    if not 0.025 <= detail_ratio <= 0.68:
        return None

    detail_alpha = detail_alpha.filter(ImageFilter.MaxFilter(3))
    mask = Image.new("L", image.size, 0)
    mask.paste(detail_alpha, bbox[:2])
    return mask


def dominant_quantized_color(pixels: list[tuple[int, int, int]]) -> tuple[int, int, int]:
    buckets: dict[tuple[int, int, int], int] = {}
    for red, green, blue in pixels:
        key = (round(red / 16) * 16, round(green / 16) * 16, round(blue / 16) * 16)
        buckets[key] = buckets.get(key, 0) + 1
    return max(buckets, key=buckets.get)


def image_pixels(image: Image.Image) -> list[Any]:
    if hasattr(image, "get_flattened_data"):
        return list(image.get_flattened_data())
    return list(image.getdata())


def color_distance(first: tuple[int, int, int], second: tuple[int, int, int]) -> float:
    return (
        (first[0] - second[0]) ** 2
        + (first[1] - second[1]) ** 2
        + (first[2] - second[2]) ** 2
    ) ** 0.5


def apply_disabled_gray(image: Image.Image) -> Image.Image:
    alpha = image.getchannel("A")
    gray = image.convert("LA").getchannel("L")
    muted = Image.merge("RGBA", (gray, gray, gray, alpha))
    overlay = Image.new("RGBA", image.size, (70, 70, 70, 0))
    overlay.putalpha(alpha.point(lambda value: round(value * 0.38)))
    muted.alpha_composite(overlay)
    return muted


def output_jobs_for_recipe(recipe: Recipe) -> list[OutputJob]:
    jobs: list[OutputJob] = []
    for dimension in recipe.dimensions:
        if recipe.mode == "leader_portraits" and dimension.width == 825 and dimension.height == 1024:
            neutral_base = recipe.base_name.removeprefix("ICON_")
            jobs.extend(
                [
                    OutputJob(dimension=dimension),
                    OutputJob(
                        dimension=dimension,
                        variant="fallback_neutral",
                        filename_override=f"FALLBACK_NEUTRAL_{neutral_base}.png",
                    ),
                ]
            )
            continue
        if recipe.governor_variants and dimension.width == dimension.height and dimension.width in {22, 32}:
            jobs.extend(
                [
                    OutputJob(dimension=dimension),
                    OutputJob(dimension=dimension, suffix="_ALT", variant="alternate"),
                    OutputJob(dimension=dimension, suffix="_DISABLED", variant="disabled_gray"),
                ]
            )
        else:
            jobs.append(OutputJob(dimension=dimension))
    return jobs


def output_file_path(
    recipe: Recipe,
    dimension: OutputDimension,
    suffix: str = "",
    filename_override: str | None = None,
) -> Path:
    if filename_override:
        return recipe.output_dir / filename_override
    if recipe.unit_white_right or recipe.mode == "unit_icons" or recipe.profile == "unit_icons":
        filename = f"{unit_atlas_base_name(recipe.base_name)}{dimension.height}{suffix}.png"
        return recipe.output_dir / filename
    if recipe.shape == "square" and dimension.width == dimension.height:
        filename = f"{recipe.base_name}_{dimension.width}{suffix}.png"
    else:
        filename = f"{recipe.base_name}_{dimension.width}x{dimension.height}{suffix}.png"
    return recipe.output_dir / filename


def unit_atlas_base_name(base_name: str) -> str:
    suffix = "UNITATLAS"
    if base_name.upper().endswith(suffix):
        return f"{base_name[:-len(suffix)]}UnitAtlas"
    return base_name


def remove_legacy_unit_output(
    recipe: Recipe,
    dimension: OutputDimension,
    output_path: Path,
    suffix: str,
    warnings: list[str],
) -> None:
    if not (recipe.unit_white_right or recipe.mode == "unit_icons" or recipe.profile == "unit_icons"):
        return
    if not recipe.overwrite:
        return

    candidates = {
        recipe.output_dir / f"{recipe.base_name}_{dimension.width}x{dimension.height}{suffix}.png",
        recipe.output_dir / f"{recipe.base_name.upper()}_{dimension.width}x{dimension.height}{suffix}.png",
        recipe.output_dir / f"{unit_atlas_base_name(recipe.base_name)}_{dimension.width}x{dimension.height}{suffix}.png",
    }
    for candidate in candidates:
        if candidate == output_path or not candidate.exists():
            continue
        try:
            candidate.unlink()
        except OSError as exc:
            warnings.append(f"Could not remove legacy unit atlas file {candidate.name}: {exc}")


def unique_preserving_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    unique_items: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            unique_items.append(item)
    return unique_items


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
