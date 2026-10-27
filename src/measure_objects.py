#!/usr/bin/env python3
"""Annotate object bounding boxes and report their pixel-space dimensions."""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
from pathlib import Path

import cv2


ROOT = Path(__file__).resolve().parents[1]
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
ANNOTATION_FIELDS = ("image", "class", "x", "y", "width", "height", "status")
MEASUREMENT_FIELDS = (
    "image",
    "class",
    "x",
    "y",
    "width_px",
    "height_px",
    "bbox_area_px2",
    "bbox_area_pct_image",
    "aspect_ratio",
    "short_side_px",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Measure manually annotated object bounding boxes in the input "
            "images. Bounding-box area is not foreground-mask area."
        )
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--annotate",
        action="store_true",
        help="Open each image and manually draw one or more object boxes.",
    )
    mode.add_argument(
        "--analyze",
        action="store_true",
        help="Validate annotations and export measurements and a Markdown summary.",
    )
    parser.add_argument(
        "--images",
        type=Path,
        default=ROOT / "images" / "input",
        help="Image directory (default: images/input).",
    )
    parser.add_argument(
        "--annotations",
        type=Path,
        default=ROOT / "data" / "object_annotations.csv",
        help="Annotation CSV (default: data/object_annotations.csv).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "results",
        help="Analysis output directory (default: results).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing annotation CSV when starting annotation.",
    )
    return parser.parse_args()


def image_files(images_dir: Path) -> list[Path]:
    if not images_dir.is_dir():
        raise ValueError(f"Image directory does not exist: {images_dir}")
    files = sorted(
        path
        for path in images_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )
    if not files:
        raise ValueError(f"No supported images found in: {images_dir}")
    return files


def relative_image_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError as error:
        raise ValueError(
            f"Image must be inside the repository to keep annotations portable: {path}"
        ) from error


def annotate(images_dir: Path, annotations_path: Path, overwrite: bool) -> None:
    if annotations_path.exists() and not overwrite:
        raise ValueError(
            f"Annotations already exist: {annotations_path}. "
            "Choose another --annotations path or pass --overwrite."
        )

    files = image_files(images_dir)
    annotations_path.parent.mkdir(parents=True, exist_ok=True)
    max_width, max_height = 1280, 800

    print(
        "Draw a rectangle around one object, then press ENTER or SPACE. "
        "Press C when there are no more boxes in this image. After each box, "
        "press b (bird), d (drone), or q (save and quit). At the end of each "
        "image, press y to confirm it was reviewed, s to leave it unreviewed, "
        "or q to save and quit."
    )
    try:
        with annotations_path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=ANNOTATION_FIELDS)
            writer.writeheader()
            file.flush()

            for index, image_path in enumerate(files, start=1):
                image = cv2.imread(str(image_path))
                if image is None:
                    raise ValueError(f"Could not read image: {image_path}")
                height, width = image.shape[:2]
                scale = min(max_width / width, max_height / height, 1.0)
                display = cv2.resize(
                    image,
                    (round(width * scale), round(height * scale)),
                    interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR,
                )
                window = f"[{index}/{len(files)}] {relative_image_path(image_path)}"
                print(f"\n{window} ({width} x {height} px)")

                while True:
                    x, y, box_width, box_height = cv2.selectROI(
                        window, display, fromCenter=False, showCrosshair=True
                    )
                    if box_width == 0 or box_height == 0:
                        break

                    print("Label selected object: [b]ird, [d]rone, [q]uit and save")
                    while True:
                        key = cv2.waitKey(0) & 0xFF
                        if key in (ord("b"), ord("d"), ord("q")):
                            break
                        print("Invalid key. Press b, d, or q.")

                    label = {ord("b"): "bird", ord("d"): "drone"}.get(key)
                    if label is not None:
                        original_x = round(x / scale)
                        original_y = round(y / scale)
                        original_width = round(box_width / scale)
                        original_height = round(box_height / scale)
                        writer.writerow(
                            {
                                "image": relative_image_path(image_path),
                                "class": label,
                                "x": original_x,
                                "y": original_y,
                                "width": original_width,
                                "height": original_height,
                                "status": "object",
                            }
                        )
                        file.flush()
                        print(
                            f"Saved {label}: x={original_x}, y={original_y}, "
                            f"width={original_width}, height={original_height}."
                        )
                    if key == ord("q"):
                        print(f"\nPartial annotations saved to {annotations_path}")
                        return

                    cv2.destroyWindow(window)
                    cv2.imshow(window, display)
                    print("Annotate another object or press C to finish this image.")

                cv2.imshow(window, display)
                print("Confirm image review: [y] yes, [s] leave unreviewed, [q] quit")
                while True:
                    key = cv2.waitKey(0) & 0xFF
                    if key in (ord("y"), ord("s"), ord("q")):
                        break
                    print("Invalid key. Press y, s, or q.")
                if key == ord("y"):
                    writer.writerow(
                        {
                            "image": relative_image_path(image_path),
                            "class": "",
                            "x": "",
                            "y": "",
                            "width": "",
                            "height": "",
                            "status": "reviewed",
                        }
                    )
                    file.flush()
                if key == ord("q"):
                    print(f"\nPartial annotations saved to {annotations_path}")
                    return
                cv2.destroyWindow(window)
    finally:
        cv2.destroyAllWindows()

    print(f"\nAnnotations saved to {annotations_path}")


def load_measurements(
    annotations_path: Path, images_dir: Path
) -> tuple[list[dict[str, str]], int, int]:
    if not annotations_path.is_file():
        raise ValueError(f"Annotation CSV does not exist: {annotations_path}")

    images = image_files(images_dir)
    known_images = {relative_image_path(path): path for path in images}
    measurements: list[dict[str, str]] = []
    reviewed_images: set[str] = set()
    object_images: set[str] = set()

    with annotations_path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None or not set(ANNOTATION_FIELDS).issubset(
            reader.fieldnames
        ):
            raise ValueError(
                "Annotation CSV must contain columns: "
                + ", ".join(ANNOTATION_FIELDS)
            )

        for line_number, row in enumerate(reader, start=2):
            image_name = row["image"]
            if image_name not in known_images:
                raise ValueError(
                    f"Line {line_number}: image is not in the input dataset: "
                    f"{image_name}"
                )
            status = row["status"]
            if status == "reviewed":
                if image_name in reviewed_images:
                    raise ValueError(
                        f"Line {line_number}: image is marked reviewed more than once."
                    )
                if any(row[field] for field in ("class", "x", "y", "width", "height")):
                    raise ValueError(
                        f"Line {line_number}: reviewed rows must not contain an object."
                    )
                reviewed_images.add(image_name)
                continue
            if status != "object":
                raise ValueError(
                    f"Line {line_number}: status must be 'object' or 'reviewed'."
                )
            if row["class"] not in {"bird", "drone"}:
                raise ValueError(
                    f"Line {line_number}: class must be 'bird' or 'drone'."
                )
            try:
                x, y, width, height = (
                    int(row[field]) for field in ("x", "y", "width", "height")
                )
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Line {line_number}: x, y, width, and height must be integers."
                ) from error
            if x < 0 or y < 0 or width <= 0 or height <= 0:
                raise ValueError(
                    f"Line {line_number}: box coordinates and dimensions are invalid."
                )

            image = cv2.imread(str(known_images[image_name]))
            if image is None:
                raise ValueError(f"Could not read image: {image_name}")
            image_height, image_width = image.shape[:2]
            if x + width > image_width or y + height > image_height:
                raise ValueError(
                    f"Line {line_number}: box extends beyond image dimensions "
                    f"({image_width} x {image_height})."
                )

            box_area = width * height
            image_area = image_width * image_height
            measurements.append(
                {
                    "image": image_name,
                    "class": row["class"],
                    "x": str(x),
                    "y": str(y),
                    "width_px": str(width),
                    "height_px": str(height),
                    "bbox_area_px2": str(box_area),
                    "bbox_area_pct_image": f"{100 * box_area / image_area:.6f}",
                    "aspect_ratio": f"{width / height:.6f}",
                    "short_side_px": str(min(width, height)),
                }
            )
            object_images.add(image_name)

    unreviewed_images = sorted(set(known_images) - reviewed_images)
    if unreviewed_images:
        preview = ", ".join(unreviewed_images[:5])
        more = " ..." if len(unreviewed_images) > 5 else ""
        raise ValueError(
            f"{len(unreviewed_images)} image(s) are not explicitly marked as "
            f"reviewed: {preview}{more}. Finish and confirm every image before "
            "analyzing."
        )

    no_object_images = len(reviewed_images - object_images)
    return measurements, len(images), no_object_images


def create_summary(
    measurements: list[dict[str, str]], image_count: int, no_object_images: int
) -> str:
    counts = {
        label: sum(row["class"] == label for row in measurements)
        for label in ("bird", "drone")
    }
    lines = [
        "# Resumo das medidas dos objetos anotados",
        "",
        f"- Imagens no conjunto: {image_count}",
        f"- Objetos anotados: {len(measurements)} "
        f"(aves: {counts['bird']}; drones: {counts['drone']})",
        f"- Imagens revisadas sem objeto: {no_object_images}",
        "",
        "As áreas abaixo são áreas de caixas delimitadoras (bounding boxes), "
        "não áreas de máscaras de silhueta.",
        "",
        "| Classe | Objetos | Largura mediana (px) | Altura mediana (px) | "
        "Área mediana da caixa (px²) | Razão de aspecto mediana |",
        "|---|---:|---:|---:|---:|---:|",
    ]

    for label in ("bird", "drone"):
        rows = [row for row in measurements if row["class"] == label]
        if not rows:
            lines.append(f"| {label} | 0 | — | — | — | — |")
            continue
        medians = {
            "width_px": statistics.median(int(row["width_px"]) for row in rows),
            "height_px": statistics.median(int(row["height_px"]) for row in rows),
            "bbox_area_px2": statistics.median(
                int(row["bbox_area_px2"]) for row in rows
            ),
            "aspect_ratio": statistics.median(
                float(row["aspect_ratio"]) for row in rows
            ),
        }
        lines.append(
            f"| {label} | {len(rows)} | {medians['width_px']:g} | "
            f"{medians['height_px']:g} | {medians['bbox_area_px2']:g} | "
            f"{medians['aspect_ratio']:.3f} |"
        )

    lines.extend(
        [
            "",
            "A tabela resume o conjunto anotado e não é, isoladamente, uma "
            "avaliação de separabilidade nem de desempenho de classificação. "
            "A anotação manual das caixas e a ausência de máscara de silhueta "
            "limitam a interpretação dos descritores.",
            "",
        ]
    )
    return "\n".join(lines)


def analyze(
    images_dir: Path, annotations_path: Path, output_dir: Path
) -> None:
    measurements, image_count, no_object_images = load_measurements(
        annotations_path, images_dir
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "object_measurements.csv"
    summary_path = output_dir / "measurement_summary.md"

    with csv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=MEASUREMENT_FIELDS)
        writer.writeheader()
        writer.writerows(measurements)
    summary_path.write_text(
        create_summary(measurements, image_count, no_object_images),
        encoding="utf-8",
    )
    print(f"Measurements: {csv_path}")
    print(f"Summary: {summary_path}")


def main() -> int:
    args = parse_args()
    try:
        if args.annotate:
            annotate(args.images, args.annotations, args.overwrite)
        else:
            analyze(args.images, args.annotations, args.output_dir)
    except (OSError, ValueError, cv2.error) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
