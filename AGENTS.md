# Trade Strategy - AI Agent Guide

Use this guide to understand the codebase architecture, workflows, and conventions.

## 1. System Architecture & Core Logic
- **Domain**: Breakout Stock Selection Strategy (US Markets).
- **Core Engine (`BreakoutStrategy/analysis/`)**:
  - `breakout_detector.py`: Implements incremental peak & breakout detection. Key classes: `Peak`, `BreakoutDetector`.
  - `breakout_scorer.py`: Scores breakout quality based on volume, price action, and resistance duration.
- **Observation Pools**:
  - `daily_pool/`: Daily timeframe analysis with State Machine (`PhaseStateMachine`) for tracking stock phases.
  - `observation/`: Real-time monitoring (5-min intervals) with scoring strategies.
- **UI (`BreakoutStrategy/UI/`)**:
  - `tkinter`-based interactive dashboard.
  - Entry point: `scripts/visualization/interactive_viewer.py`.
  - **Single Source of Truth** for parameters: `BreakoutStrategy/UI/config/param_loader.py`.

## 2. Critical Workflows
- **Running the System**:
  - **Scan**: Configure `configs/scan_config.yaml` -> Run UI -> Click "New Scan".
  - **Analysis**: Results are saved as JSON in `outputs/scan_results/`.
  - **Visualization**: Use UI to load JSON results and inspect charts.
- **Parameter Tuning**:
  - Edit YAML files in `configs/analysis/params/` (e.g., `scan_params.yaml`).
  - **Hot Reload**: The UI detects file changes and reloads parameters automatically (or via button).
- **Dependency Management**:
  - strictly use `uv` (e.g., `uv add`, `uv run`, `uv sync`). Do not use `pip` directly.

## 3. Key Conventions & Patterns
- **Language**: 
  - **UI Labels/Logs**: English.
  - **Comments/Docs**: Simplified Chinese (implementation details, logic explanation).
  - **Docstrings**: Mandatory, English or Chinese (consistent with module).
- **Paths**: ALWAYS use `pathlib.Path` (e.g., `Path("datasets/pkls")`), never string concatenation for paths.
- **Configuration**:
  - Use `yaml` for all config files.
  - `configs/analysis/config.yaml` is the main system config.
  - Strategy params are isolated in `configs/analysis/params/`.
- **Data Handling**:
  - Stock data is in `datasets/pkls/` (pickle format).
  - Use `pandas` for time-series manipulation.
- **Terminology**:
  - **Peak (pk)**: Resistance level.
  - **Breakout (bo)**: Price crossing a peak.
  - **Suppression**: Duration price held below peak.

## 4. Common Tasks & Files
- **New Feature in Strategy**:
  - Update `BreakoutStrategy/analysis/` logic.
  - Add parameter to `configs/analysis/params/scan_params.yaml`.
  - Update `UIParamLoader` if necessary to expose it to UI.
- **UI Modification**:
  - Components in `BreakoutStrategy/UI/panels/` or `charts/`.
  - Layouts use `pack()` or `grid()`.
- **Debugging**:
  - Check `outputs/logs/` (if configured) or console output.
  - UI errors often relate to `tkinter` thread safety or config loading issues.

## 5. Integration Points
- **External Data**: `akshare` is used for data fetching (if applicable).
- **Internal**: `PeakDetector` feeds into `BreakoutDetector`, which feeds into `QualityScorer`.

## 6. AI Agent Guidelines
- **Philosophy**:
  - **First Principles**: Drill down to core requirements. Avoid assumptions.
  - **Occam's Razor**: Simplest solution is best. Avoid over-engineering.
- **Workflow**:
  - **Context**: Check `.claude/docs/system_outline.md` before starting complex tasks. For module-specific detail, see `.claude/docs/modules/<模块名>.md`.
  - **Planning**: Use `docs/tmp/` for drafting complex implementation strategies.
  - **Documentation**: Put code explanations in `docs/explain/` and research in `docs/research/`.
- **Agent Roles**:
  - **Standard**: Routine coding, bug fixes.
  - **tom (High Difficulty)**: Deep research, architecture review, first-principles thinking, innovative algorithms.
  - **Team**: Default to `tom` for leading multi-agent teams.
