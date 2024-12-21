## @file
# Copyright (c) 2024, Cory Bennett. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
##
from datetime import datetime, timedelta

import sys; sys.path.append('src')
from asi import fetch_archetypes, compute_archetype_bigrams

FORMATS = [
  'standard',
  'modern',
  'pioneer',
  'vintage',
  'legacy',
  'pauper',
]
MIN_DATE = (TIMESTAMP := datetime.now()) - timedelta(days=90)

for format in FORMATS:
  bigram = compute_archetype_bigrams(fetch_archetypes(format, MIN_DATE))
  with open(f'src/artifacts/{format}.py', 'w') as f:
    f.write(f"""#
# This is an auto-generated file. Do not modify.
# Generated on {TIMESTAMP:%Y-%m-%d %H:%M:%S}.
#
bigrams = {str({ k1: { k2: round(v2, 8) } for k1, v1 in bigram.items()
                                          for k2, v2 in v1.items() })}""")
