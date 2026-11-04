FHOPS serious game
==================

The optional web service includes a deterministic, instructor-run serious game
built on three stand-scale FHOPS levels. It is a simulation exercise, not an
operational harvesting or profitability decision tool.

Levels
------

The game ships with one block per level and a finite control grid:

.. list-table::
   :header-rows: 1

   * - Level
     - Stand
     - Area
     - PSP / inventory basis
   * - MKRF
     - ``RES_KEY 684``
     - 6.86 ha
     - FAIB CWHdm, Fraser TSA, age 80–125
   * - Gavin Lake
     - ``BLOCK_ID 1032``
     - 10.00 ha
     - FAIB ICHmk3, Williams Lake TSA, age 90–150
   * - Knife Creek
     - VRI polygon ``57254551``
     - 35.95 ha
     - local IDF Cariboo PSP, selection-cut split

The stand boundaries and provenance are under ``examples/game/stands/``.
Level manifests and precomputes are under ``examples/game/levels/`` and
``examples/game/precomputed/``.

Prerequisites
-------------

Install the web extra and the FAIB/Nemora workflow only for regenerating game
assets. Playing the game needs the normal FHOPS web extra::

    pip install 'fhops[web]'

Start the service
-----------------

Pass the levels and matching precomputes in play order::

    fhops web \
      --game-level examples/game/levels/mkrf_684/level.yaml \
      --game-precompute examples/game/precomputed/mkrf_684.json \
      --game-level examples/game/levels/gavin_1032/level.yaml \
      --game-precompute examples/game/precomputed/gavin_1032.json \
      --game-level examples/game/levels/kc_57254551/level.yaml \
      --game-precompute examples/game/precomputed/kc_57254551.json

Open ``http://127.0.0.1:8765/game``.

The game routes are disabled unless at least one matching level/precompute pair
is configured. The service has no authentication; keep it on localhost or an
instructor-controlled network.

How a round works
-----------------

1. Create or join a session/team on the Game page.
2. Select the next level. The server enforces MKRF → Gavin → Knife Creek order.
3. Choose the finite controls:
   - skidder count;
   - log length;
   - (Knife Creek only) careful-logging level;
   - sawlog threshold and landing option where exposed.
4. Submit once. Replay and skip-ahead are rejected.
5. The response shows the score and selected-run components. The server uses
   the complete precomputed grid; it does not rerun the tree system per
   submission.
6. Open the debrief to reveal the optimal choice and per-parameter costs.
7. After the final level, the optional final chat panel unlocks.

Scoring
-------

Each level precomputes every feasible control combination. The normalized score
is::

    score = 100 * (net_profit - worst) / (best - worst)

with clamping to 0–100. The precompute is complete or the level is not played.

Knife Creek uses selection-cut careful logging. Higher care slows the harvester
and adds an operator premium, but reduces residual-stem damage with diminishing
marginal returns. The exact curve is server-side; the briefing exposes only
ranges.

Gavin is deliberately calibrated so its finite range straddles break-even:
the best log-length choice is profitable and the weaker choice loses money.

Optional agent
--------------

Debrief and final-chat explanations are optional. Start with ``--allow-agent``
and ensure the installed ``opencode`` CLI is available::

    fhops web ... --allow-agent \
      --game-agent-model opencode-go/deepseek-v4.1-flash \
      --game-explanation-cache build/game_explanations.json

The structured debrief uses a strict JSON schema against deterministic facts.
Explanations are cached by level + choice hash. If the agent is disabled or
fails validation, deterministic templates are used. The final chat is refused
by the API until every level is complete.

Regenerate assets
-----------------

The checked-in inventories were produced with the FAIB/Nemora workflow::

    fhops tree inventory validate \
      examples/game/stands/kc_57254551/trees.csv \
      --metadata examples/game/stands/kc_57254551/inventory.meta.json \
      --block KC01

    python scripts/precompute_stand_level.py \
      examples/game/levels/kc_57254551/level.yaml \
      --out examples/game/precomputed/kc_57254551.json

The precompute script is a repository script; the game does not require Nemora
at runtime.

Caveats
-------

- Tree lists are synthetic, not surveyed stem maps.
- MKRF and Gavin use VRI-derived stand layers rather than raw VRI polygons.
- Gavin's PSP support is thin (two plots) and its target stand is synthetic.
- Price decks and machine costs are game assumptions, not market forecasts.
- FHOPS stem products are placeholders; game value recovery is illustrative.
- No operational, regulatory, or profitability claim is made.
