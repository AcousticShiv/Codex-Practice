from __future__ import annotations

from typing import Any, Dict

from .converter import convert_m_code


def parse_m_code(m_code: str) -> Dict[str, Any]:
    return convert_m_code(m_code)


def convert(m_code: str) -> Dict[str, Any]:
    return convert_m_code(m_code)


def generate_conversion(m_code: str) -> Dict[str, Any]:
    return convert_m_code(m_code)