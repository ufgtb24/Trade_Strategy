"""
TPE Optimization Checkpoint Viewer

浏览器可视化 Optuna Study 的 pickle 检查点数据。
展示优化收敛曲线、参数分布对比、并行坐标图和 Trial 详情表格。

启动: uv run python BreakoutStrategy/mining/tpe_viewer.py
"""

import pickle
import math
import pandas as pd
import numpy as np
from pathlib import Path

import dash
from dash import html, dcc, dash_table, Input, Output
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# ==================== Data Loading ====================

def load_study_as_dataframe(pkl_path: str) -> tuple[pd.DataFrame, list[str]]:
    """加载 Optuna Study pickle 文件，提取全部 trial 信息为 DataFrame。

    Returns:
        (df, param_names): DataFrame 包含全部 trial 数据, param_names 为参数列名列表
    """
    with open(pkl_path, "rb") as f:
        study = pickle.load(f)

    records = []
    for t in study.trials:
        if t.value is None:
            continue
        row = {
            "trial_number": t.number,
            "value": t.value,
            **t.params,
            "top_median": t.user_attrs.get("top_median"),
            "top_count": t.user_attrs.get("top_count"),
            "top_adjusted": t.user_attrs.get("top_adjusted"),
        }
        if t.datetime_start and t.datetime_complete:
            row["duration_sec"] = (t.datetime_complete - t.datetime_start).total_seconds()
        else:
            row["duration_sec"] = None
        records.append(row)

    # 从第一个完成的 trial 提取参数名
    param_names = list(study.trials[0].params.keys()) if study.trials else []

    # 释放 Study 对象
    del study

    df = pd.DataFrame(records)
    df.sort_values("trial_number", inplace=True, ignore_index=True)
    df["best_so_far"] = df["value"].cummax()

    return df, param_names


# ==================== Chart Builders ====================

def build_convergence_figure(df: pd.DataFrame) -> go.Figure:
    """收敛曲线: trial values + running max + user_attrs"""
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.65, 0.35],
        vertical_spacing=0.06,
        subplot_titles=("Trial Score & Best So Far", "Top Template Attributes"),
    )

    # Trial values (WebGL scatter)
    hover_custom = df[["top_median", "top_count"]].values
    fig.add_trace(go.Scattergl(
        x=df["trial_number"], y=df["value"],
        mode="markers", marker=dict(size=3, opacity=0.25, color="#6495ED"),
        name="Trial Score", customdata=hover_custom,
        hovertemplate="Trial %{x}<br>Score: %{y:.4f}<br>Median: %{customdata[0]:.4f}<br>Count: %{customdata[1]}<extra></extra>",
    ), row=1, col=1)

    # Best so far line — hover 显示产生该 best 值的 trial 信息
    best_trial_idx = df["value"].expanding().apply(lambda s: s.idxmax(), raw=False).astype(int)
    best_custom = df.loc[best_trial_idx.values, ["trial_number", "top_median", "top_count"]].values
    fig.add_trace(go.Scatter(
        x=df["trial_number"], y=df["best_so_far"],
        mode="lines", line=dict(color="red", width=2),
        name="Best So Far", customdata=best_custom,
        hovertemplate="Best Trial #%{customdata[0]:.0f}<br>Best: %{y:.4f}<br>Median: %{customdata[1]:.4f}<br>Count: %{customdata[2]}<extra></extra>",
    ), row=1, col=1)

    # Mark the global best
    best_idx = df["value"].idxmax()
    best_row = df.loc[best_idx]
    fig.add_trace(go.Scatter(
        x=[best_row["trial_number"]], y=[best_row["value"]],
        mode="markers+text",
        marker=dict(size=12, color="red", symbol="star"),
        text=[f"#{int(best_row['trial_number'])} = {best_row['value']:.4f}"],
        textposition="top center",
        showlegend=False,
        hoverinfo="skip",
    ), row=1, col=1)

    # User attrs: top_median, top_count, top_adjusted
    if "top_median" in df.columns and df["top_median"].notna().any():
        fig.add_trace(go.Scatter(
            x=df["trial_number"], y=df["top_median"],
            mode="lines", line=dict(width=1, color="#2ca02c"),
            name="top_median",
        ), row=2, col=1)
        fig.add_trace(go.Scatter(
            x=df["trial_number"], y=df["top_adjusted"],
            mode="lines", line=dict(width=1, color="#ff7f0e"),
            name="top_adjusted",
        ), row=2, col=1)
        fig.add_trace(go.Scatter(
            x=df["trial_number"], y=df["top_count"],
            mode="lines", line=dict(width=1, color="#9467bd"),
            name="top_count", yaxis="y4",
        ), row=2, col=1)
        # top_count 使用右侧 y 轴
        fig.update_layout(
            yaxis4=dict(
                overlaying="y3", side="right",
                title="top_count", showgrid=False,
            )
        )

    fig.update_layout(
        height=600,
        xaxis2=dict(title="Trial Number", rangeslider=dict(visible=True, thickness=0.05)),
        yaxis=dict(title="Score"),
        yaxis3=dict(title="Median / Adjusted"),
        margin=dict(t=40, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    return fig


def build_param_distribution_figure(
    df: pd.DataFrame, param_names: list[str], top_quantile: float = 0.9
) -> go.Figure:
    """参数分布对比: top group vs bottom group histogram"""
    n_params = len(param_names)
    ncols = 2
    nrows = math.ceil(n_params / ncols)

    fig = make_subplots(rows=nrows, cols=ncols, subplot_titles=param_names)

    top_threshold = df["value"].quantile(top_quantile)
    bot_threshold = df["value"].quantile(0.25)
    top_mask = df["value"] >= top_threshold
    bot_mask = df["value"] <= bot_threshold

    for i, name in enumerate(param_names):
        row = i // ncols + 1
        col = i % ncols + 1

        fig.add_trace(go.Histogram(
            x=df.loc[bot_mask, name], nbinsx=40,
            name=f"Bottom 25%", opacity=0.6,
            marker_color="#6495ED", histnorm="probability density",
            showlegend=(i == 0),
            legendgroup="bottom",
        ), row=row, col=col)

        fig.add_trace(go.Histogram(
            x=df.loc[top_mask, name], nbinsx=40,
            name=f"Top {int((1 - top_quantile) * 100)}%", opacity=0.6,
            marker_color="#FF6347", histnorm="probability density",
            showlegend=(i == 0),
            legendgroup="top",
        ), row=row, col=col)

        fig.update_xaxes(title_text=name, row=row, col=col)

    fig.update_layout(
        barmode="overlay",
        height=max(300, nrows * 250),
        margin=dict(t=40, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    return fig


def build_parallel_coords_figure(
    df: pd.DataFrame, param_names: list[str], max_lines: int = 5000
) -> go.Figure:
    """并行坐标图: 参数组合与目标值的关系"""
    # 采样: 保留 top trials + 随机采样补足
    if len(df) > max_lines:
        top_n = min(2000, max_lines // 2)
        random_n = max_lines - top_n
        top_df = df.nlargest(top_n, "value")
        remaining = df.drop(top_df.index)
        random_df = remaining.sample(n=min(random_n, len(remaining)), random_state=42)
        sampled = pd.concat([top_df, random_df]).sort_values("trial_number")
    else:
        sampled = df

    dimensions = []
    for name in param_names:
        col = sampled[name]
        dimensions.append(dict(
            label=name,
            values=col,
            range=[col.min(), col.max()],
        ))
    # Score 维度放最后
    dimensions.append(dict(
        label="Score",
        values=sampled["value"],
        range=[sampled["value"].min(), sampled["value"].max()],
    ))

    fig = go.Figure(go.Parcoords(
        line=dict(
            color=sampled["value"],
            colorscale="Viridis",
            showscale=True,
            colorbar=dict(title="Score"),
        ),
        dimensions=dimensions,
    ))

    fig.update_layout(
        height=500,
        margin=dict(t=40, b=20),
    )
    return fig


# ==================== App Layout ====================

def create_app(df: pd.DataFrame, param_names: list[str], pkl_path: str) -> dash.Dash:
    """创建 Dash 应用"""
    app = dash.Dash(__name__)

    best_idx = df["value"].idxmax()
    best_row = df.loc[best_idx]
    total_trials = len(df)
    best_score = best_row["value"]
    best_trial_num = int(best_row["trial_number"])

    # 预构建静态图表
    convergence_fig = build_convergence_figure(df)
    parallel_fig = build_parallel_coords_figure(df, param_names)

    # 表格列
    display_cols = ["trial_number", "value", "best_so_far",
                    "top_median", "top_count", "top_adjusted",
                    "duration_sec"] + param_names
    table_columns = []
    for c in display_cols:
        fmt = {"name": c, "id": c}
        if c not in ("trial_number", "top_count"):
            fmt["type"] = "numeric"
            fmt["format"] = dash_table.Format.Format(precision=4, scheme=dash_table.Format.Scheme.fixed)
        table_columns.append(fmt)

    top_10_threshold = df["value"].quantile(0.9)

    app.layout = html.Div([
        # Header
        html.Div([
            html.H2("TPE Optimization Viewer", style={"margin": "0", "display": "inline-block"}),
            html.Span(f"  {pkl_path}", style={"color": "#888", "marginLeft": "16px", "fontSize": "14px"}),
        ], style={"padding": "12px 20px", "borderBottom": "1px solid #ddd"}),

        # Summary stats
        html.Div([
            html.Span(f"Total Trials: {total_trials}", style={"marginRight": "32px", "fontWeight": "bold"}),
            html.Span(f"Best Score: {best_score:.4f} (Trial #{best_trial_num})",
                       style={"marginRight": "32px", "fontWeight": "bold", "color": "red"}),
            html.Span(f"Params: {len(param_names)}", style={"marginRight": "32px"}),
        ], style={"padding": "8px 20px", "backgroundColor": "#f8f8f8", "borderBottom": "1px solid #eee"}),

        # Tabs
        dcc.Tabs([
            # Tab 1: Convergence
            dcc.Tab(label="Convergence", children=[
                dcc.Graph(id="convergence-chart", figure=convergence_fig),
            ]),

            # Tab 2: Parameters
            dcc.Tab(label="Parameters", children=[
                html.Div([
                    html.Label("Top Percentile: ", style={"marginRight": "8px"}),
                    dcc.Dropdown(
                        id="quantile-dropdown",
                        options=[
                            {"label": "Top 5%", "value": 0.95},
                            {"label": "Top 10%", "value": 0.90},
                            {"label": "Top 20%", "value": 0.80},
                        ],
                        value=0.90,
                        style={"width": "140px", "display": "inline-block", "verticalAlign": "middle"},
                        clearable=False,
                    ),
                ], style={"padding": "12px 20px"}),
                dcc.Graph(id="param-dist-chart"),
            ]),

            # Tab 3: Parallel Coordinates
            dcc.Tab(label="Parallel Coords", children=[
                html.Div([
                    html.Label("Max Lines: ", style={"marginRight": "8px"}),
                    dcc.Slider(
                        id="parallel-slider",
                        min=1000, max=min(10000, len(df)), step=1000,
                        value=min(5000, len(df)),
                        marks={v: str(v) for v in range(1000, min(10001, len(df) + 1), 2000)},
                    ),
                ], style={"padding": "12px 20px"}),
                dcc.Graph(id="parallel-chart", figure=parallel_fig),
            ]),

            # Tab 4: Details Table
            dcc.Tab(label="Details", children=[
                dash_table.DataTable(
                    id="details-table",
                    data=df[display_cols].to_dict("records"),
                    columns=table_columns,
                    page_size=50,
                    sort_action="native",
                    sort_mode="multi",
                    filter_action="native",
                    style_table={"overflowX": "auto"},
                    style_cell={"textAlign": "right", "padding": "4px 8px", "fontSize": "13px"},
                    style_header={"fontWeight": "bold", "backgroundColor": "#f0f0f0"},
                    style_data_conditional=[
                        {
                            "if": {"filter_query": f"{{value}} >= {top_10_threshold}"},
                            "backgroundColor": "#e6ffe6",
                        }
                    ],
                ),
            ]),
        ]),
    ])

    # === Callbacks ===

    @app.callback(
        Output("param-dist-chart", "figure"),
        Input("quantile-dropdown", "value"),
    )
    def update_param_dist(quantile_val):
        return build_param_distribution_figure(df, param_names, quantile_val)

    @app.callback(
        Output("parallel-chart", "figure"),
        Input("parallel-slider", "value"),
    )
    def update_parallel(max_lines):
        return build_parallel_coords_figure(df, param_names, int(max_lines))

    return app


# ==================== Entry Point ====================

def main():
    # === 参数声明 ===
    pkl_path = "outputs/statistics/20260330_114654/optuna.pkl"
    host = "127.0.0.1"
    port = 8050
    debug = True

    # === 加载数据 ===
    project_root = Path(__file__).resolve().parent.parent.parent
    full_path = str(project_root / pkl_path)

    print(f"Loading checkpoint: {full_path}")
    df, param_names = load_study_as_dataframe(full_path)
    print(f"Loaded {len(df)} trials, {len(param_names)} params: {param_names}")

    # === 启动服务 ===
    app = create_app(df, param_names, pkl_path)
    print(f"Starting server at http://{host}:{port}")
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
