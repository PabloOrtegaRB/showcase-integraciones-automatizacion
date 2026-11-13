"""Política de reintentos: espera exponencial con tope y variación aleatoria (jitter)."""
from __future__ import annotations

import random
from typing import Callable


def espera(intento: int, base: float, maxima: float, aleatorio: Callable[[], float] = random.random) -> float:
    """Segundos a esperar antes del intento siguiente: base·2^(intento-1), con tope y hasta 25 % de variación."""
    if base <= 0:
        return 0.0
    bruta = min(maxima, base * 2 ** (intento - 1))
    return round(bruta * (1 + 0.25 * aleatorio()), 3)
