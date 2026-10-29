# FHOPS tree-system example

A small synthetic end-to-end example for the multi-machine ground-based system.
It uses the 12-tree P17 contract fixture, one block, one feller-buncher, two
skidders, one processor, one loader, and one truck.

All data is synthetic. It is not a real tree map, harvest plan, or calibrated
machine dataset.

Run the system from the repository root:

```bash
fhops tree system examples/tree_system/scenario/scenario.yaml \
  --block B01 \
  --feller H1 --skidder H2 --skidder H3 \
  --processor H5 --loader H4 \
  --shift-days 2 --shifts-per-day 1 --hours-per-shift 8 \
  --truck-capacity 5 --truck-count 1 --landing-capacity 15 \
  --out build/tree_system_example
```

The checked-in `system_events.json`, `scene.gltf`, and `viewer.html` are a
prebuilt example. Serve this directory over HTTP and open `viewer.html`:

```bash
cd examples/tree_system
python3 -m http.server 8793 --bind 127.0.0.1
```

Or regenerate the scene with `fhops tree scene` after running the system.
