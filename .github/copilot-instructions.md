# Trade Strategy - AI Coding Instructions

## 1. Project Overview
This project implements a **Breakthrough Stock Selection Strategy** for US markets. It identifies historical resistance levels (peaks), detects breakouts, and evaluates them using a multi-stage scoring system. The system includes an analysis engine, an interactive UI, and a configuration management system.

## 2. Architecture & Core Components

### Core Logic (`BreakthroughStrategy/analysis/`)
- **Peak Detection**: Identifies local maxima in price history (`breakthrough_detector.py`).
- **Breakout Detection**: Detects when price exceeds historical peaks (`breakthrough_detector.py`).
- **Quality Scoring**: Evaluates breakouts based on volume, price action, and resistance duration (`breakthrough_scorer.py`).
- **Incremental Processing**: The detector supports incremental data updates for efficiency.

### User Interface (`BreakthroughStrategy/UI/`)
- **Framework**: Python `tkinter` with `matplotlib` for charting.
- **Entry Point**: `scripts/visualization/interactive_viewer.py` launches the `InteractiveUI`.
- **Components**:
    - `panels/`: UI layout components.
    - `charts/`: Canvas managers for stock charts.
    - `config/`: UI-specific parameter management (`param_loader.py` acts as the Single Source of Truth).

### Configuration (`configs/`)
- **Format**: YAML files.
- **Structure**:
    - `configs/analysis/config.yaml`: Main system config.
    - `configs/analysis/params/`: Strategy parameter sets (e.g., `breakthrough_0.yaml`).
- **Loaders**: `BreakthroughStrategy/config_loader.py` handles loading and validation.

## 3. Critical Workflows

### Running the System
- **Batch Scan**: Run `python scripts/analysis/batch_scan.py` to scan stocks and generate JSON results in `outputs/scan_results/`.
- **Interactive UI**: Run `python scripts/visualization/interactive_viewer.py` to visualize scan results and tune parameters.

### Development Patterns
- **Parameter Tuning**: Modify YAML files in `configs/analysis/params/`. The UI allows live reloading of these parameters.
- **Data Flow**:
    1.  **Data Ingestion**: Historical price data (PKL/CSV).
    2.  **Analysis**: `PeakDetector` -> `BreakoutDetector` -> `QualityScorer`.
    3.  **Output**: JSON files containing breakout candidates.
    4.  **Visualization**: UI loads JSON to display charts and metrics.

## 4. Coding Conventions

### Language & Style
- **UI Text**: English (for international compatibility).
- **Comments/Docs**: Chinese (Simplified) for detailed explanations.
- **Docstrings**: Mandatory for all modules (`__init__.py`), classes, and complex functions. Explain purpose, args, and logic.

### Terminology
- **Peak (pk)**: A historical high point acting as resistance.
- **Breakout/Breakthrough (bt)**: Price exceeding a Peak.
- **Suppression**: The duration a price has been held below a peak.

### Best Practices
- **Paths**: Always use `pathlib.Path` for file operations. Avoid string manipulation for paths.
- **Imports**: Use absolute imports (e.g., `from BreakthroughStrategy.analysis import ...`) to avoid circular dependency issues.
- **Error Handling**: Fail fast in configuration loading; log errors gracefully in the scanning loop to avoid stopping the entire batch.

## 5. Documentation & Context
- **Status**: Check `docs/system/current_state.md` for the latest development progress.
- **Requirements**: See `docs/system/PRD.md` for detailed architectural goals and definitions.
- **Quick Start**: `CLAUDE.md` contains a map of the codebase and useful commands.
