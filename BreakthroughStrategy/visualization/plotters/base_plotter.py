"""基础绘图器 - 提供通用绘图逻辑"""
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from typing import Optional, Tuple
from ..utils import ensure_datetime_index, filter_date_range


class BasePlotter:
    """基础绘图器"""

    def __init__(self, style: str = 'seaborn-v0_8-darkgrid'):
        """
        初始化绘图器

        Args:
            style: matplotlib 样式
        """
        self.style = style
        try:
            plt.style.use(style)
        except:
            # 如果样式不存在，使用默认样式
            pass

    def prepare_data(self,
                    df: pd.DataFrame,
                    start_date: Optional[str] = None,
                    end_date: Optional[str] = None) -> pd.DataFrame:
        """
        准备数据（格式转换、日期过滤）

        Args:
            df: 输入 DataFrame
            start_date: 开始日期 (可选)
            end_date: 结束日期 (可选)

        Returns:
            处理后的 DataFrame
        """
        # 确保 DatetimeIndex
        df = ensure_datetime_index(df)

        # 过滤日期范围
        if start_date or end_date:
            df = filter_date_range(df, start_date, end_date)

        return df

    def create_figure(self,
                     figsize: Tuple[int, int] = (16, 10),
                     nrows: int = 3,
                     height_ratios: list = None) -> Tuple:
        """
        创建图表布局

        Args:
            figsize: 图表大小
            nrows: 子图行数
            height_ratios: 子图高度比例

        Returns:
            (fig, axes) 元组
        """
        if height_ratios is None:
            height_ratios = [10, 0.3][:nrows]

        fig, axes = plt.subplots(
            nrows=nrows,
            ncols=1,
            figsize=figsize,
            gridspec_kw={'height_ratios': height_ratios},
            sharex=True
        )

        # 如果只有一个子图，将其转换为列表
        if nrows == 1:
            axes = [axes]

        # 调整子图间距和边距
        plt.subplots_adjust(left=0.06, right=0.98, top=0.98, bottom=0.08, hspace=0.15)

        return fig, axes

    def save_figure(self,
                   fig,
                   save_path: Optional[str] = None,
                   dpi: int = 150):
        """
        保存图表

        Args:
            fig: matplotlib Figure 对象
            save_path: 保存路径 (可选)
            dpi: 图像分辨率
        """
        if save_path:
            # 创建目录
            save_path = Path(save_path)
            save_path.parent.mkdir(parents=True, exist_ok=True)

            # 保存图表
            fig.savefig(
                save_path,
                dpi=dpi,
                bbox_inches='tight',
                facecolor='white'
            )
            print(f"Figure saved to: {save_path}")

    def show_or_save(self,
                    fig,
                    save_path: Optional[str] = None,
                    show: bool = True,
                    dpi: int = 150):
        """
        显示或保存图表

        Args:
            fig: matplotlib Figure 对象
            save_path: 保存路径 (可选)
            show: 是否显示图表
            dpi: 图像分辨率
        """
        if save_path:
            self.save_figure(fig, save_path, dpi)

        if show:
            plt.show()
        else:
            plt.close(fig)

    def add_title(self,
                 fig,
                 title: str,
                 subtitle: Optional[str] = None):
        """
        添加图表标题

        Args:
            fig: matplotlib Figure 对象
            title: 主标题
            subtitle: 副标题 (可选)
        """
        if subtitle:
            full_title = f"{title}\n{subtitle}"
        else:
            full_title = title

        fig.suptitle(
            full_title,
            fontsize=40,
            weight='bold',
            y=0.995
        )

    def add_legend(self, ax, loc: str = 'upper left'):
        """
        添加图例

        Args:
            ax: matplotlib Axes 对象
            loc: 图例位置
        """
        handles, labels = ax.get_legend_handles_labels()

        # 去重（同一个label只保留一个）
        by_label = dict(zip(labels, handles))

        ax.legend(
            by_label.values(),
            by_label.keys(),
            loc=loc,
            fontsize=26,
            framealpha=0.9
        )
