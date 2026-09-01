import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

def build_interactive_chart(df: pd.DataFrame, ticker: str) -> go.Figure:
    """캔들스틱 및 거래량, 보조지표가 포함된 Plotly 차트 객체를 생성합니다."""
    # 상단 캔들 차트(75%), 하단 거래량(25%) 2단 레이아웃
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.75, 0.25]
    )

    # 1. 캔들스틱 추가
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
        name="OHLC",
        increasing_line_color="#26a69a", decreasing_line_color="#ef5350"
    ), row=1, col=1)

    # 2. 이동평균선 & 볼린저 밴드
    fig.add_trace(go.Scatter(x=df.index, y=df["EMA10"], line=dict(color="#FF9800", width=1.5), name="10 EMA"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["EMA20"], line=dict(color="#2196F3", width=1.5), name="20 EMA"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["BB_UPPER"], line=dict(color="#78909C", width=1, dash="dash"), name="BB Upper"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["BB_LOWER"], line=dict(color="#78909C", width=1, dash="dash"), name="BB Lower"), row=1, col=1)

    # 3. 하단 거래량(Volume) 바 차트
    colors = ["#26a69a" if c >= o else "#ef5350" for o, c in zip(df["Open"], df["Close"])]
    fig.add_trace(go.Bar(
        x=df.index, y=df["Volume"],
        name="Volume",
        marker_color=colors,
        opacity=0.6
    ), row=2, col=1)

    # 스타일 및 레이아웃 정리
    fig.update_layout(
        title=f"<b>{ticker.upper()}</b> Technical Analysis Chart (Data provided by Massive)",
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        height=600,
        margin=dict(l=30, r=30, t=50, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    return fig