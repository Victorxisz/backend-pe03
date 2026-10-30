"""Compatibilidade com imports anteriores; implementação em app.publicacoes."""
import sys
from app.publicacoes import repository as _modulo
sys.modules[__name__] = _modulo
