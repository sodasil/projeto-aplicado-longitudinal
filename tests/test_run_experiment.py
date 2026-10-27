import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import run_experiment


class SegmentationExperimentTests(unittest.TestCase):
    def test_thresholds_and_morphology_return_binary_masks(self):
        image = np.full((100, 120), 220, dtype=np.uint8)
        image[30:70, 40:80] = 15

        for configuration in run_experiment.CONFIGURATIONS:
            with self.subTest(configuration=configuration):
                mask = run_experiment.threshold_image(image, configuration)
                self.assertEqual(mask.shape, image.shape)
                self.assertTrue(set(np.unique(mask)).issubset({0, 255}))
                self.assertGreater(cv2_count(mask), 0)

    def test_component_descriptors_measure_synthetic_rectangle(self):
        mask = np.zeros((80, 100), dtype=np.uint8)
        mask[20:40, 30:60] = 255

        components = run_experiment.component_features(mask, min_area=4)

        self.assertEqual(len(components), 1)
        component = components[0]
        self.assertEqual(component["area_processing_px"], 600)
        self.assertEqual(component["bbox_width_processing_px"], 30)
        self.assertEqual(component["bbox_height_processing_px"], 20)
        self.assertAlmostEqual(component["aspect_ratio"], 1.5)

    def test_box_matching_is_one_to_one(self):
        predictions = [(0, 0, 10, 10), (1, 1, 10, 10)]
        references = [(0, 0, 10, 10)]

        true_positives, false_positives, false_negatives = run_experiment.match_boxes(
            predictions, references, iou_threshold=0.3
        )

        self.assertEqual((true_positives, false_positives, false_negatives), (1, 1, 0))

    def test_pilot_reference_is_explicitly_a_two_image_subset(self):
        root = Path(__file__).resolve().parents[1]
        images = run_experiment.list_images(root / "images" / "input")
        references = run_experiment.load_references(
            root / "data" / "pilot_annotations.csv", images
        )

        self.assertEqual(len(references), 2)
        self.assertEqual(
            len(references["images/input/LowResolution/Aves 2.jpg"]), 1
        )
        self.assertEqual(
            len(references["images/input/LowResolution/Nada 1.jpg"]), 0
        )

    def test_detection_metrics_count_false_positives_on_negative_sample(self):
        predictions = {
            ("positive", "otsu"): [(460, 28, 28, 34)],
            ("negative", "otsu"): [(100 + 4 * index, 100, 3, 3) for index in range(6)],
            ("positive", "adaptive"): [(460, 28, 28, 34)],
            ("negative", "adaptive"): [],
        }
        references = {"positive": [(460, 28, 28, 34)], "negative": []}

        metrics = run_experiment.evaluate_detections(predictions, references)

        self.assertEqual(metrics["otsu"]["false_positives"], 6)
        self.assertEqual(metrics["adaptive"]["false_positives"], 0)
        self.assertEqual(metrics["adaptive"]["recall"], 1.0)

    def test_processing_resize_preserves_aspect_ratio(self):
        image = np.zeros((600, 1200, 3), dtype=np.uint8)

        resized, scale = run_experiment.resize_for_processing(image, max_side=300)

        self.assertEqual(resized.shape[:2], (150, 300))
        self.assertAlmostEqual(scale, 0.25)


def cv2_count(mask):
    import cv2

    return cv2.countNonZero(mask)


if __name__ == "__main__":
    unittest.main()
