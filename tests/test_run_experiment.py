import sys
import unittest
from pathlib import Path
import cv2
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
                self.assertGreater(cv2.countNonZero(mask), 0)

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
        predictions = [
            (0, 0, 10, 10),
            (1, 1, 10, 10),
        ]
        references = [(0, 0, 10, 10)]

        true_positives, false_positives, false_negatives = (
            run_experiment.match_boxes(
                predictions,
                references,
                iou_threshold=0.3,
            )
        )

        self.assertEqual(
            (true_positives, false_positives, false_negatives),
            (1, 1, 0),
        )

    def test_pilot_reference_is_explicitly_a_two_image_subset(self):
        root = Path(__file__).resolve().parents[1]
        images = run_experiment.list_images(root / "images" / "input")
        references = run_experiment.load_references(
            root / "data" / "pilot_annotations.csv",
            images,
        )

        self.assertEqual(len(references), 2)

        self.assertEqual(
            len(references["images/input/LowResolution/Aves 2.jpg"]),
            1,
        )

        self.assertEqual(
            len(references["images/input/LowResolution/Nada 1.jpg"]),
            0,
        )

    def test_detection_metrics_count_false_positives_on_negative_sample(self):
        predictions = {
            ("positive", "otsu"): [(460, 28, 28, 34)],
            ("negative", "otsu"): [
                (100 + 4 * index, 100, 3, 3)
                for index in range(6)
            ],
            ("positive", "adaptive"): [(460, 28, 28, 34)],
            ("negative", "adaptive"): [],
        }

        references = {
            "positive": [(460, 28, 28, 34)],
            "negative": [],
        }

        metrics = run_experiment.evaluate_detections(
            predictions,
            references,
        )

        self.assertEqual(metrics["otsu"]["false_positives"], 6)
        self.assertEqual(metrics["adaptive"]["false_positives"], 0)
        self.assertEqual(metrics["adaptive"]["recall"], 1.0)

    def test_processing_resize_preserves_aspect_ratio(self):
        image = np.zeros((600, 1200, 3), dtype=np.uint8)
        resized, scale = run_experiment.resize_for_processing(
            image,
            max_side=300,
        )

        self.assertEqual(resized.shape[:2], (150, 300))
        self.assertAlmostEqual(scale, 0.25)

    def test_resize_does_not_enlarge_small_images(self):
        image = np.zeros((100, 200, 3), dtype=np.uint8)
        resized, scale = run_experiment.resize_for_processing(
            image,
            max_side=300,
        )

        self.assertEqual(resized.shape[:2], (100, 200))
        self.assertAlmostEqual(scale, 1.0)

    def test_invalid_configuration_raises_error(self):
        image = np.zeros((100, 100), dtype=np.uint8)
        with self.assertRaises((ValueError, KeyError)):
            run_experiment.threshold_image(image, "invalid")

    def test_adaptive_threshold_handles_small_image(self):
        image = np.zeros((3, 3), dtype=np.uint8)
        mask = run_experiment.threshold_image(image, "adaptive")
        self.assertEqual(mask.shape, image.shape)
        self.assertTrue(set(np.unique(mask)).issubset({0, 255}))

    def test_empty_mask_returns_no_components(self):
        mask = np.zeros((80, 100), dtype=np.uint8)
        components = run_experiment.component_features(
            mask,
            min_area=4,
        )

        self.assertEqual(components, [])

    def test_minimum_area_filters_small_components(self):
        mask = np.zeros((100, 100), dtype=np.uint8)
        mask[10:12, 10:12] = 255
        mask[30:40, 30:40] = 255
        components = run_experiment.component_features(
            mask,
            min_area=10,
        )

        self.assertEqual(len(components), 1)
        self.assertEqual(components[0]["area_processing_px"], 100)

    def test_component_shape_descriptors_are_valid(self):
        mask = np.zeros((100, 100), dtype=np.uint8)
        mask[20:60, 30:70] = 255
        components = run_experiment.component_features(
            mask,
            min_area=4,
        )

        self.assertEqual(len(components), 1)
        component = components[0]
        self.assertGreater(component["perimeter_processing_px"], 0)
        self.assertGreater(component["circularity"], 0)
        self.assertLessEqual(component["circularity"], 1.0)
        self.assertGreater(component["solidity"], 0)
        self.assertLessEqual(component["solidity"], 1.0)

    def test_identical_boxes_are_matched(self):
        box = (10, 20, 30, 40)

        tp, fp, fn = run_experiment.match_boxes(
            [box],
            [box],
            iou_threshold=0.5,
        )

        self.assertEqual((tp, fp, fn), (1, 0, 0))


    def test_non_overlapping_boxes_are_not_matched(self):
        box_a = (0, 0, 10, 10)
        box_b = (20, 20, 10, 10)

        tp, fp, fn = run_experiment.match_boxes(
            [box_a],
            [box_b],
            iou_threshold=0.5,
        )

        self.assertEqual((tp, fp, fn), (0, 1, 1))

    def test_no_predictions_produce_false_negatives(self):
        predictions = {
            ("image1", "otsu"): [],
            ("image1", "adaptive"): [],
        }

        references = {
            "image1": [(10, 10, 20, 20)],
        }

        metrics = run_experiment.evaluate_detections(
            predictions,
            references,
        )

        self.assertEqual(metrics["otsu"]["false_negatives"], 1)
        self.assertEqual(metrics["adaptive"]["false_negatives"], 1)
        self.assertEqual(metrics["otsu"]["true_positives"], 0)

    def test_metrics_handle_no_predictions_and_no_references(self):
        predictions = {
            ("image1", "otsu"): [],
            ("image1", "adaptive"): [],
        }

        references = {
            "image1": [],
        }

        metrics = run_experiment.evaluate_detections(
            predictions,
            references,
        )

        for configuration in ("otsu", "adaptive"):
            with self.subTest(configuration=configuration):
                self.assertEqual(
                    metrics[configuration]["false_positives"],
                    0,
                )
                self.assertEqual(
                    metrics[configuration]["false_negatives"],
                    0,
                )

    def test_precision_recall_and_f1_for_missed_detection(self):
        predictions = {
            ("image1", "otsu"): [(10, 10, 20, 20)],
            ("image2", "otsu"): [],
        }

        references = {
            "image1": [(10, 10, 20, 20)],
            "image2": [(30, 30, 10, 10)],
        }

        metrics = run_experiment.evaluate_detections(
            predictions,
            references,
        )

        self.assertAlmostEqual(metrics["otsu"]["precision"], 1.0)
        self.assertAlmostEqual(metrics["otsu"]["recall"], 0.5)
        self.assertAlmostEqual(metrics["otsu"]["f1"], 2 / 3)


if __name__ == "__main__":
    unittest.main()