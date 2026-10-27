#!/usr/bin/env python3
"""Compare global and adaptive threshold segmentation on sky images."""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
CONFIGURATIONS = ("otsu", "adaptive")
COMPONENT_FIELDS = (
    "image",
    "configuration",
    "component_id",
    "area_processing_px",
    "bbox_x_processing_px",
    "bbox_y_processing_px",
    "bbox_width_processing_px",
    "bbox_height_processing_px",
    "aspect_ratio",
    "perimeter_processing_px",
    "circularity",
    "solidity",
)
SUMMARY_FIELDS = (
    "image",
    "configuration",
    "image_width_px",
    "image_height_px",
    "processed_width_px",
    "processed_height_px",
    "foreground_pixels",
    "foreground_fraction",
    "candidate_count",
)
ANNOTATION_FIELDS = ("image", "class", "x", "y", "width", "height", "status")
MAX_PROCESSING_SIDE = 1280
MIN_COMPONENT_AREA = 4
ADAPTIVE_BLOCK_SIZE = 31
ADAPTIVE_C = 5
MORPHOLOGY_KERNEL_SIZE = 3
IOU_THRESHOLD = 0.3
PREVIEW_WIDTH = 360
PREVIEW_HEIGHT = 240


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare global Otsu and adaptive Gaussian threshold segmentation "
            "on all images in the input directory."
        )
    )
    parser.add_argument(
        "--images",
        type=Path,
        default=ROOT / "images" / "input",
        help="Input image directory (default: images/input).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "results",
        help="Output directory (default: results).",
    )
    parser.add_argument(
        "--annotations",
        type=Path,
        default=ROOT / "data" / "object_annotations.csv",
        help="Optional reviewed bounding-box annotation CSV.",
    )
    parser.add_argument(
        "--max-side",
        type=int,
        default=MAX_PROCESSING_SIDE,
        help=f"Maximum processing dimension in pixels (default: {MAX_PROCESSING_SIDE}).",
    )
    parser.add_argument(
        "--min-area",
        type=int,
        default=MIN_COMPONENT_AREA,
        help=f"Minimum component area at processing resolution (default: {MIN_COMPONENT_AREA}).",
    )
    return parser.parse_args()


def list_images(images_dir: Path) -> list[Path]:
    if not images_dir.is_dir():
        raise ValueError(f"Image directory does not exist: {images_dir}")
    paths = sorted(
        path
        for path in images_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )
    if not paths:
        raise ValueError(f"No supported images found in: {images_dir}")
    return paths


def relative_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError as error:
        raise ValueError(
            f"Images must be inside the repository to keep outputs portable: {path}"
        ) from error


def resize_for_processing(
    image: np.ndarray, max_side: int
) -> tuple[np.ndarray, float]:
    height, width = image.shape[:2]
    scale = min(max_side / max(height, width), 1.0)
    if scale == 1.0:
        return image.copy(), scale
    resized = cv2.resize(
        image,
        (max(1, round(width * scale)), max(1, round(height * scale))),
        interpolation=cv2.INTER_AREA,
    )
    return resized, scale


def threshold_image(gray: np.ndarray, configuration: str) -> np.ndarray:
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    if configuration == "otsu":
        _, mask = cv2.threshold(
            blurred, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU
        )
    elif configuration == "adaptive":
        block_size = min(ADAPTIVE_BLOCK_SIZE, min(gray.shape))
        if block_size % 2 == 0:
            block_size -= 1
        if block_size < 3:
            raise ValueError(
                f"Image is too small for adaptive thresholding: {gray.shape[1]}x{gray.shape[0]}"
            )
        mask = cv2.adaptiveThreshold(
            blurred,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            block_size,
            ADAPTIVE_C,
        )
    else:
        raise ValueError(f"Unknown segmentation configuration: {configuration}")

    kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (MORPHOLOGY_KERNEL_SIZE, MORPHOLOGY_KERNEL_SIZE),
    )
    return cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)


def component_features(
    mask: np.ndarray, min_area: int
) -> list[dict[str, int | float]]:
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        mask, connectivity=8
    )
    components: list[dict[str, int | float]] = []
    height, width = mask.shape
    max_component_area = int(height * width * 0.25)

    for label in range(1, count):
        x, y, box_width, box_height, area = (
            int(value) for value in stats[label]
        )
        if area < min_area or area > max_component_area:
            continue

        component = (labels[y : y + box_height, x : x + box_width] == label).astype(
            np.uint8
        )
        contours, _ = cv2.findContours(
            component, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        if not contours:
            continue
        contour = max(contours, key=cv2.contourArea)
        perimeter = float(cv2.arcLength(contour, True))
        contour_area = float(cv2.contourArea(contour))
        hull_area = float(cv2.contourArea(cv2.convexHull(contour)))
        circularity = (
            4 * np.pi * contour_area / (perimeter * perimeter)
            if perimeter > 0
            else 0.0
        )
        solidity = contour_area / hull_area if hull_area > 0 else 0.0

        components.append(
            {
                "component_id": label,
                "area_processing_px": area,
                "bbox_x_processing_px": x,
                "bbox_y_processing_px": y,
                "bbox_width_processing_px": box_width,
                "bbox_height_processing_px": box_height,
                "aspect_ratio": box_width / box_height,
                "perimeter_processing_px": perimeter,
                "circularity": circularity,
                "solidity": solidity,
            }
        )
    return components


def intersection_over_union(
    first: tuple[int, int, int, int], second: tuple[int, int, int, int]
) -> float:
    first_x, first_y, first_width, first_height = first
    second_x, second_y, second_width, second_height = second
    left = max(first_x, second_x)
    top = max(first_y, second_y)
    right = min(first_x + first_width, second_x + second_width)
    bottom = min(first_y + first_height, second_y + second_height)
    intersection = max(0, right - left) * max(0, bottom - top)
    union = first_width * first_height + second_width * second_height - intersection
    return intersection / union if union else 0.0


def match_boxes(
    predictions: list[tuple[int, int, int, int]],
    references: list[tuple[int, int, int, int]],
    iou_threshold: float = IOU_THRESHOLD,
) -> tuple[int, int, int]:
    candidates = sorted(
        (
            (intersection_over_union(prediction, reference), pred_index, ref_index)
            for pred_index, prediction in enumerate(predictions)
            for ref_index, reference in enumerate(references)
        ),
        reverse=True,
    )
    matched_predictions: set[int] = set()
    matched_references: set[int] = set()
    for iou, pred_index, ref_index in candidates:
        if iou < iou_threshold:
            break
        if pred_index in matched_predictions or ref_index in matched_references:
            continue
        matched_predictions.add(pred_index)
        matched_references.add(ref_index)
    true_positives = len(matched_predictions)
    return (
        true_positives,
        len(predictions) - true_positives,
        len(references) - true_positives,
    )


def load_references(
    annotations_path: Path,
    images: list[Path],
) -> dict[str, list[tuple[int, int, int, int]]]:
    if not annotations_path.is_file():
        raise ValueError(f"Annotation CSV does not exist: {annotations_path}")
    known_images = {relative_path(path): path for path in images}
    references: dict[str, list[tuple[int, int, int, int]]] = defaultdict(list)
    reviewed_images: set[str] = set()
    image_dimensions: dict[str, tuple[int, int]] = {}

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
                    f"Line {line_number}: image is not in the dataset: {image_name}"
                )
            if row["status"] == "reviewed":
                if image_name in reviewed_images:
                    raise ValueError(
                        f"Line {line_number}: image is marked reviewed more than once."
                    )
                if any(row[field] for field in ("class", "x", "y", "width", "height")):
                    raise ValueError(
                        f"Line {line_number}: reviewed rows must not contain an object."
                    )
                reviewed_images.add(image_name)
                references[image_name]
                continue
            if row["status"] != "object":
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
                    f"Line {line_number}: bounding box values must be integers."
                ) from error
            if x < 0 or y < 0 or width <= 0 or height <= 0:
                raise ValueError(f"Line {line_number}: invalid bounding box.")
            if image_name not in image_dimensions:
                image = cv2.imread(str(known_images[image_name]))
                if image is None:
                    raise ValueError(
                        f"Line {line_number}: could not read {image_name}."
                    )
                image_dimensions[image_name] = (image.shape[1], image.shape[0])
            image_width, image_height = image_dimensions[image_name]
            if x + width > image_width or y + height > image_height:
                raise ValueError(
                    f"Line {line_number}: bounding box exceeds image dimensions "
                    f"({image_width} x {image_height})."
                )
            if image_name in reviewed_images:
                raise ValueError(
                    f"Line {line_number}: object appears after the image review row."
                )
            references[image_name].append((x, y, width, height))

    if not reviewed_images:
        raise ValueError("Reference CSV has no images marked as reviewed.")
    if reviewed_images - known_images.keys():
        raise ValueError(
            "Reference CSV contains images that are not in the current dataset."
        )
    return references


def evaluate_detections(
    predictions: dict[tuple[str, str], list[tuple[int, int, int, int]]],
    references: dict[str, list[tuple[int, int, int, int]]],
) -> dict[str, dict[str, float | int]]:
    metrics: dict[str, dict[str, float | int]] = {}
    for configuration in CONFIGURATIONS:
        true_positives = false_positives = false_negatives = 0
        for image_name, reference_boxes in references.items():
            predicted_boxes = predictions.get((image_name, configuration), [])
            tp, fp, fn = match_boxes(predicted_boxes, reference_boxes)
            true_positives += tp
            false_positives += fp
            false_negatives += fn
        precision = (
            true_positives / (true_positives + false_positives)
            if true_positives + false_positives
            else 0.0
        )
        recall = (
            true_positives / (true_positives + false_negatives)
            if true_positives + false_negatives
            else 0.0
        )
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )
        metrics[configuration] = {
            "true_positives": true_positives,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }
    return metrics


def draw_overlay(image: np.ndarray, components: list[dict[str, Any]], scale: float):
    overlay = image.copy()
    for component in components:
        x = round(int(component["bbox_x_processing_px"]) / scale)
        y = round(int(component["bbox_y_processing_px"]) / scale)
        width = round(int(component["bbox_width_processing_px"]) / scale)
        height = round(int(component["bbox_height_processing_px"]) / scale)
        cv2.rectangle(overlay, (x, y), (x + width, y + height), (0, 255, 0), 2)
    return overlay


def fit_preview(image: np.ndarray) -> np.ndarray:
    return cv2.resize(
        image,
        (PREVIEW_WIDTH, PREVIEW_HEIGHT),
        interpolation=cv2.INTER_AREA,
    )


def build_comparison_grid(
    panel_groups: list[list[tuple[str, np.ndarray]]],
) -> np.ndarray:
    header_height = 30
    rows = []
    for group in panel_groups:
        panels = []
        for title, image in group:
            preview = fit_preview(image)
            panel = np.full(
                (PREVIEW_HEIGHT + header_height, PREVIEW_WIDTH, 3),
                255,
                dtype=np.uint8,
            )
            panel[header_height:] = preview
            cv2.putText(
                panel,
                title[:55],
                (6, 21),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (0, 0, 0),
                1,
                cv2.LINE_AA,
            )
            panels.append(panel)
        rows.append(np.hstack(panels))
    return np.vstack(rows)


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(
            {field: row.get(field, "") for field in fields} for row in rows
        )


def summarize(
    image_summaries: list[dict[str, Any]],
    component_rows: list[dict[str, Any]],
    annotations_path: Path,
    max_side: int,
    min_area: int,
) -> str:
    lines = [
        "# Experimento M2: limiarização global e adaptativa",
        "",
        "## Pergunta e protocolo",
        "",
        "A limiarização adaptativa localiza componentes distintos da limiarização "
        "global de Otsu nas mesmas imagens? Comparam-se duas configurações; "
        "pré-processamento, escala, morfologia e filtro de componentes são "
        "mantidos constantes.",
        "",
        f"- Imagens processadas: {len({row['image'] for row in image_summaries})}",
        f"- Escala: redução proporcional para no máximo {max_side} "
        "pixels no maior lado; coordenadas das caixas convertidas para a imagem original.",
        "- Pré-processamento comum: escala de cinza e filtro Gaussiano 5 x 5.",
        "- Pós-processamento comum: abertura morfológica com elipse 3 x 3.",
        f"- Componentes aceitos: área entre {min_area} pixels na "
        "imagem reduzida e 25% da imagem processada.",
        "- Otsu: limiar global automático, máscara invertida.",
        f"- Adaptativo: Gaussiano local, bloco {ADAPTIVE_BLOCK_SIZE} x "
        f"{ADAPTIVE_BLOCK_SIZE}, C={ADAPTIVE_C}, máscara invertida.",
        "- Descritores: área de pixels, caixa delimitadora, razão de aspecto, "
        "perímetro, circularidade e solidez.",
        "",
        "## Resultados quantitativos",
        "",
        "A fração de pixels em primeiro plano e a contagem de componentes são "
        "indicadores descritivos da segmentação, não acurácia. Um componente "
        "pode ser ruído, nuvem ou objeto, e objetos fragmentados podem gerar "
        "contagens múltiplas.",
        "",
        "| Configuração | Componentes candidatos | Mediana por imagem | "
        "Mediana da fração de primeiro plano |",
        "|---|---:|---:|---:|",
    ]
    by_configuration: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in image_summaries:
        by_configuration[row["configuration"]].append(row)
    for configuration in CONFIGURATIONS:
        image_rows = by_configuration[configuration]
        total_components = sum(int(row["candidate_count"]) for row in image_rows)
        median_count = statistics.median(
            int(row["candidate_count"]) for row in image_rows
        )
        median_foreground = statistics.median(
            float(row["foreground_fraction"]) for row in image_rows
        )
        lines.append(
            f"| {configuration} | {total_components} | {median_count:g} | "
            f"{median_foreground:.6f} |"
        )

    lines.extend(["", "## Resultado por imagem", ""])
    lines.extend(
        [
            "| Imagem | Configuração | Componentes | Fração de primeiro plano |",
            "|---|---|---:|---:|",
        ]
    )
    for row in image_summaries:
        lines.append(
            f"| `{row['image']}` | {row['configuration']} | "
            f"{row['candidate_count']} | {float(row['foreground_fraction']):.6f} |"
        )

    if annotations_path.is_file():
        references = load_references(
            annotations_path,
            [
                ROOT / row["image"]
                for row in image_summaries
                if row["configuration"] == "otsu"
            ],
        )
        lines.extend(
            [
                "",
                "## Avaliação com caixas de referência",
                "",
                f"Foram revisadas {len(references)} imagens no CSV de referência; "
                "as métricas são preliminares e valem apenas para esse subconjunto. "
                f"Usa-se IoU >= {IOU_THRESHOLD:.1f} para parear caixas preditas e manuais.",
                "",
                "| Configuração | TP | FP | FN | Precisão | Recall | F1 |",
                "|---|---:|---:|---:|---:|---:|---:|",
            ]
        )
        prediction_boxes: dict[
            tuple[str, str], list[tuple[int, int, int, int]]
        ] = defaultdict(list)
        for row in component_rows:
            scale = next(
                float(summary["scale"])
                for summary in image_summaries
                if summary["image"] == row["image"]
                and summary["configuration"] == row["configuration"]
            )
            prediction_boxes[(row["image"], row["configuration"])].append(
                (
                    round(int(row["bbox_x_processing_px"]) / scale),
                    round(int(row["bbox_y_processing_px"]) / scale),
                    round(int(row["bbox_width_processing_px"]) / scale),
                    round(int(row["bbox_height_processing_px"]) / scale),
                )
            )
        metrics = evaluate_detections(prediction_boxes, references)
        for configuration in CONFIGURATIONS:
            metric = metrics[configuration]
            lines.append(
                f"| {configuration} | {metric['true_positives']} | "
                f"{metric['false_positives']} | {metric['false_negatives']} | "
                f"{metric['precision']:.3f} | {metric['recall']:.3f} | "
                f"{metric['f1']:.3f} |"
            )
        lines.extend(
            [
                "",
                "A caixa da ave no piloto foi preparada por inspeção visual com "
                "apoio de IA e ainda requer revisão independente de um integrante; "
                "os resultados são preliminares. Em `LowResolution/Aves 2.jpg`, "
                "ambos os métodos produzem um candidato pareado à caixa. Em "
                "`LowResolution/Nada 1.jpg`, Otsu produz seis falsos candidatos "
                "e o adaptativo nenhum. Isso exemplifica um sucesso e uma falha, "
                "mas não valida desempenho fora destas duas imagens.",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "## Referência e interpretação",
                "",
                "Não foi fornecido CSV de referência; portanto, não é possível "
                "calcular precisão, recall, F1 ou IoU nesta execução. Os valores "
                "apresentados caracterizam apenas a saída dos limiares e não "
                "demonstram detecção correta nem separabilidade entre aves e "
                "drones. Para completar a avaliação, anotar e revisar os objetos "
                "e as imagens sem objeto e executar novamente o comando com "
                "`--annotations` apontando para o CSV revisado.",
            ]
        )

    lines.extend(
        [
            "",
            "## Interpretação, sucessos e limitações",
            "",
            "A comparação mantém as mesmas imagens, escala de processamento, "
            "filtro Gaussiano, morfologia e critérios de área; varia somente "
            "o método de limiarização. A fração de primeiro plano e o número "
            "de componentes mostram diferenças entre configurações, mas não "
            "permitem declarar uma vencedora sem referência manual.",
            "",
            "Inspecione a figura `segmentation_comparison.jpg` junto à tabela "
            "por imagem. Em `LowResolution/Drone 2.jpg`, o adaptativo produz "
            "521 componentes candidatos, ilustrando fragmentação e falsos "
            "candidatos em céu nublado. Nuvens e regiões escuras podem ser "
            "confundidas com objetos; objetos muito pequenos podem desaparecer "
            "com a abertura morfológica ou ficar abaixo do limite de área. "
            "Objetos próximos podem se unir e uma silhueta pode se fragmentar.",
            "",
            "## Artefatos e próximo passo",
            "",
            "- `segmentation_comparison.csv`: métricas descritivas por imagem.",
            "- `segmented_components.csv`: descritores dos componentes.",
            "- `masks/`: máscaras binárias das duas configurações.",
            "- `segmentation_comparison.jpg`: figura comparativa com a entrada "
            "e as detecções candidatas.",
            "- `measurement_summary.md` e `object_measurements.csv`: saídas "
            "complementares do script de anotação manual, quando executado.",
            "- `data/pilot_annotations.csv`: referência piloto de duas imagens; "
            "a equipe deve revisar essa anotação antes de considerá-la validada.",
            "",
            "Na próxima execução, complete e revise as caixas de referência; "
            "avalie separadamente segmentação (precisão/recall de caixas) e "
            "descritores de classe. O conjunto atual é pequeno e heterogêneo; "
            "uma divisão treino/teste por imagem só deve ser feita quando "
            "houver dados suficientes e as origens relacionadas estiverem "
            "identificadas. Nenhum classificador é treinado neste experimento.",
            "",
        ]
    )
    return "\n".join(lines)


def run_experiment(
    images_dir: Path,
    output_dir: Path,
    annotations_path: Path | None,
    max_side: int,
    min_area: int,
) -> None:
    if max_side < 3:
        raise ValueError("--max-side must be at least 3.")
    if min_area < 1:
        raise ValueError("--min-area must be positive.")
    paths = list_images(images_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    mask_dir = output_dir / "masks"
    for configuration in CONFIGURATIONS:
        (mask_dir / configuration).mkdir(parents=True, exist_ok=True)

    summary_rows: list[dict[str, Any]] = []
    component_rows: list[dict[str, Any]] = []
    panel_groups: list[list[tuple[str, np.ndarray]]] = []

    for image_path in paths:
        image = cv2.imread(str(image_path))
        if image is None:
            raise ValueError(f"Could not read image: {image_path}")
        processed, scale = resize_for_processing(image, max_side)
        gray = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)
        height, width = processed.shape[:2]
        image_name = relative_path(image_path)
        image_output_name = Path(image_name).with_suffix(".png")

        image_label = (
            f"{'HR' if image_path.parent.name == 'HighResolution' else 'LR'}"
            f"/{image_path.name}"
        )
        image_panels = [(f"{image_label} | input", image)]
        for configuration in CONFIGURATIONS:
            mask = threshold_image(gray, configuration)
            components = component_features(mask, min_area)
            mask_path = mask_dir / configuration / image_output_name
            mask_path.parent.mkdir(parents=True, exist_ok=True)
            if not cv2.imwrite(str(mask_path), mask):
                raise OSError(f"Could not write mask: {mask_path}")

            foreground_pixels = int(cv2.countNonZero(mask))
            summary_rows.append(
                {
                    "image": image_name,
                    "configuration": configuration,
                    "image_width_px": image.shape[1],
                    "image_height_px": image.shape[0],
                    "processed_width_px": width,
                    "processed_height_px": height,
                    "foreground_pixels": foreground_pixels,
                    "foreground_fraction": f"{foreground_pixels / (width * height):.8f}",
                    "candidate_count": len(components),
                    "scale": scale,
                }
            )

            overlay = draw_overlay(image, components, scale)
            image_panels.append(
                (
                    f"{image_label} | {configuration} ({len(components)})",
                    overlay,
                )
            )
            for component in components:
                component_rows.append(
                    {
                        "image": image_name,
                        "configuration": configuration,
                        **component,
                    }
                )

        panel_groups.append(image_panels)

    write_csv(output_dir / "segmentation_comparison.csv", SUMMARY_FIELDS, summary_rows)
    write_csv(
        output_dir / "segmented_components.csv",
        COMPONENT_FIELDS,
        component_rows,
    )
    grid = build_comparison_grid(panel_groups)
    grid_path = output_dir / "segmentation_comparison.jpg"
    if not cv2.imwrite(str(grid_path), grid, [cv2.IMWRITE_JPEG_QUALITY, 88]):
        raise OSError(f"Could not write comparison image: {grid_path}")

    # `scale` is needed for optional box-reference evaluation but is not part
    # of the published CSV schema.
    report = summarize(
        summary_rows,
        component_rows,
        annotations_path if annotations_path and annotations_path.is_file() else Path(),
        max_side,
        min_area,
    )
    (output_dir / "segmentation_experiment.md").write_text(
        report, encoding="utf-8"
    )

    print(f"Processed {len(paths)} images with {len(CONFIGURATIONS)} configurations.")
    print(f"Comparison report: {output_dir / 'segmentation_experiment.md'}")
    print(f"Per-image metrics: {output_dir / 'segmentation_comparison.csv'}")
    print(f"Component descriptors: {output_dir / 'segmented_components.csv'}")
    print(f"Comparison figure: {grid_path}")


def main() -> int:
    args = parse_args()
    try:
        annotation_path = args.annotations
        run_experiment(
            args.images,
            args.output_dir,
            annotation_path if annotation_path.is_file() else None,
            args.max_side,
            args.min_area,
        )
    except (OSError, ValueError, cv2.error) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
