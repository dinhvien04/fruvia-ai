#!/usr/bin/env python3
"""
Fruvia AI — Export Model Artifacts

Exports a trained PyTorch classifier checkpoint into the standard
deployment format expected by the backend:

  models/classifier/model.pth        — state dict
  models/classifier/class_names.json — ordered class list
  models/classifier/model_config.json — architecture metadata
  models/classifier/preprocessing.json — image preprocessing params

Usage:
    python scripts/export_model.py \
        --checkpoint path/to/best_model.pth \
        --output-dir models/classifier \
        --model-name convnext_tiny \
        --classes configs/classes.yaml \
        --training-config configs/training.yaml
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml


def load_yaml(path: Path) -> dict:
    """Load a YAML file."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def export_model(
    checkpoint_path: Path,
    output_dir: Path,
    model_name: str,
    classes_path: Path,
    training_config_path: Path,
) -> None:
    """
    Export model artifacts for deployment.

    This script copies the checkpoint and generates the metadata files
    that the backend reads at startup. The checkpoint itself should contain
    the model state_dict saved during training.
    """
    import shutil

    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Copy checkpoint
    dest_pth = output_dir / "model.pth"
    shutil.copy2(checkpoint_path, dest_pth)
    print(f"[export] Checkpoint copied to {dest_pth}")

    # 2. Export class names
    classes_cfg = load_yaml(classes_path)
    class_names = classes_cfg.get("classes", [])
    class_names_path = output_dir / "class_names.json"
    with open(class_names_path, "w", encoding="utf-8") as f:
        json.dump(class_names, f, indent=2, ensure_ascii=False)
    print(f"[export] Class names ({len(class_names)} classes) saved to {class_names_path}")

    # 3. Export model config
    training_cfg = load_yaml(training_config_path)
    if model_name == "convnext_tiny":
        _model_section = training_cfg.get("convnext", {})
    elif model_name == "efficientnet_b0":
        _model_section = training_cfg.get("efficientnet", {})

    model_config = {
        "model_name": model_name,
        "num_classes": len(class_names),
        "pretrained_source": "torchvision",
        "input_size": training_cfg.get("preprocessing", {}).get("image_size", 224),
        "architecture": model_name,
    }
    model_config_path = output_dir / "model_config.json"
    with open(model_config_path, "w", encoding="utf-8") as f:
        json.dump(model_config, f, indent=2, ensure_ascii=False)
    print(f"[export] Model config saved to {model_config_path}")

    # 4. Export preprocessing config
    preprocess_cfg = training_cfg.get("preprocessing", {})
    preprocessing = {
        "image_size": preprocess_cfg.get("image_size", 224),
        "mean": preprocess_cfg.get("mean", [0.485, 0.456, 0.406]),
        "std": preprocess_cfg.get("std", [0.229, 0.224, 0.225]),
        "interpolation": "bilinear",
        "color_mode": "RGB",
    }
    preprocessing_path = output_dir / "preprocessing.json"
    with open(preprocessing_path, "w", encoding="utf-8") as f:
        json.dump(preprocessing, f, indent=2, ensure_ascii=False)
    print(f"[export] Preprocessing config saved to {preprocessing_path}")

    print(f"\n[export] All artifacts exported to {output_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export trained model for deployment")
    parser.add_argument("--checkpoint", type=Path, required=True, help="Path to trained model .pth")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("models/classifier"),
        help="Output directory for model artifacts",
    )
    parser.add_argument(
        "--model-name",
        type=str,
        default="convnext_tiny",
        choices=["convnext_tiny", "efficientnet_b0"],
        help="Model architecture name",
    )
    parser.add_argument(
        "--classes", type=Path, default=Path("configs/classes.yaml"), help="classes.yaml path"
    )
    parser.add_argument(
        "--training-config",
        type=Path,
        default=Path("configs/training.yaml"),
        help="training.yaml path",
    )
    args = parser.parse_args()

    if not args.checkpoint.exists():
        print(f"[ERROR] Checkpoint not found: {args.checkpoint}", file=sys.stderr)
        sys.exit(1)

    export_model(
        checkpoint_path=args.checkpoint,
        output_dir=args.output_dir,
        model_name=args.model_name,
        classes_path=args.classes,
        training_config_path=args.training_config,
    )


if __name__ == "__main__":
    main()
