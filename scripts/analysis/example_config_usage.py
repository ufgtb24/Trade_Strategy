"""
Example script demonstrating how to use configuration loader

This shows how to initialize analysis modules with parameters from YAML config.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from BreakthroughStrategy.config_loader import get_config_loader
from BreakthroughStrategy.analysis import BreakthroughDetector
from BreakthroughStrategy.analysis.features import FeatureCalculator
from BreakthroughStrategy.analysis.quality_scorer import QualityScorer


def main():
    # Load configuration
    config_loader = get_config_loader()

    print("=" * 60)
    print("Configuration Loaded Successfully")
    print("=" * 60)

    # Example 1: Create BreakthroughDetector with config
    detector_config = config_loader.get_detector_config()
    print("\nBreakthroughDetector Configuration:")
    for key, value in detector_config.items():
        print(f"  {key}: {value}")

    detector = BreakthroughDetector(
        symbol="TEST",
        **detector_config
    )
    print(f"\nCreated detector: {detector}")

    # Example 2: Create FeatureCalculator with config
    feature_config = config_loader.get_feature_calculator_config()
    print("\nFeatureCalculator Configuration:")
    for key, value in feature_config.items():
        print(f"  {key}: {value}")

    feature_calc = FeatureCalculator(config=feature_config)
    print(f"\nCreated feature calculator: {feature_calc}")

    # Example 3: Create QualityScorer with config
    scorer_config = config_loader.get_quality_scorer_config()
    print("\nQualityScorer Configuration:")
    print("  Peak weights:")
    for key in ['peak_weight_volume', 'peak_weight_candle', 'peak_weight_suppression',
                'peak_weight_height', 'peak_weight_merged']:
        if key in scorer_config:
            print(f"    {key}: {scorer_config[key]}")

    print("  Breakthrough weights:")
    for key in ['bt_weight_change', 'bt_weight_gap', 'bt_weight_volume',
                'bt_weight_continuity', 'bt_weight_stability', 'bt_weight_resistance']:
        if key in scorer_config:
            print(f"    {key}: {scorer_config[key]}")

    quality_scorer = QualityScorer(config=scorer_config)
    print(f"\nCreated quality scorer: {quality_scorer}")

    # Example 4: Get scan configuration
    scan_config = config_loader.get_scan_config()
    print("\nScan Configuration:")
    for key, value in scan_config.items():
        print(f"  {key}: {value}")

    print("\n" + "=" * 60)
    print("All modules initialized with YAML configuration!")
    print("=" * 60)


if __name__ == '__main__':
    main()
