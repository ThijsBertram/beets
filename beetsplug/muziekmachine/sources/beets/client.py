from __future__ import annotations
from typing import Any, Dict, Iterable, Mapping, Optional

from clients.base import SourceClient, RetryPolicy
from clients.errors import (
    ClientConfigError, ClientNotFoundError, ClientCapabilityError
)
from domain.models import SourceRef