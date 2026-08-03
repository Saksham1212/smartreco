"""Shared Jinja2Templates instance used across page routers."""
import json

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")

CATEGORY_COLORS = {
    "AI/ML": "#a78bfa",
    "Web Development": "#38bdf8",
    "Data Science": "#4ade80",
    "DevOps": "#fb923c",
    "Mobile Development": "#f472b6",
}


def category_color(category: str) -> str:
    return CATEGORY_COLORS.get(category, "#94a3b8")


def from_json(value):
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return []


templates.env.filters["category_color"] = category_color
templates.env.filters["from_json"] = from_json
