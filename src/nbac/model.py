## @file
# Copyright (c) 2025, Cory Bennett. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
##
"""NBAC model data structures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ModelKind = Literal["counts", "presence"]


@dataclass(frozen=True)
class NBACModelParams:
  alpha: float
  background_lambda: float
  temperature: float


@dataclass(frozen=True)
class NBACModel:
  kind: ModelKind
  params: NBACModelParams
  log_prior: list[float]
  log_unseen: list[float]


@dataclass(frozen=True)
class NBACMeta:
  version: int
  build_unix: int
  archetypes: list[str]
  counts: NBACModel
  presence: NBACModel

  def model(self, kind: ModelKind) -> NBACModel:
    return self.counts if kind == "counts" else self.presence
