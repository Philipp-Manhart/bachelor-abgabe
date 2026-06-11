from __future__ import annotations

from mcp_server.models import ChartConfig, ChartConfigRequest


def generate_chart_config(request: ChartConfigRequest) -> ChartConfig:
    return ChartConfig(
        mark=request.type,
        encoding={
            "x": {"field": request.x_axis, "type": "nominal"},
            "y": {"field": request.y_axis, "type": "quantitative"},
        },
    )
