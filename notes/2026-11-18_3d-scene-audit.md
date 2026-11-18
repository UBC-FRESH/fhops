> Public project-note copy. See the matching instance planning note.

# 3D scene and browser audit — 2026-11-18

## Finding and repair

The portal's MKRF WS4 3D link loaded the static viewer, but
`/ws4/instance/femic-mkrf-instance/api/studio3d` returned HTTP 404. The MKRF
instance had no `planning/studio3d/mkrf_scene.json`; the portal card was
advertising a scene that did not exist.

The scene was built from:

- 1,763 public MKRF block polygons (`ws4/runtime/fragments.geojson`);
- 2016 LidarBC 5 m CHM and 1 m DEM;
- block density and height from the WS4 matrix;
- species mix from the MKRF AU summary;
- 15 m scene grid, 452 × 908 cells, 17.5 MB JSON.

The scene reports CHM coverage over 99.6% of the block area. CHM no-data gaps
use block-height fallback for display only, not measured canopy. Stems are
synthetic positions at block density, not a measured tree census.

The API now returns 200 with the 17.5 MB scene. The portal link is live.

## Browser audit

Browser: Playwright Chromium, headless, 1100 × 760 unless noted. The browser
selected **SwiftShader** because this container has the NVIDIA device and
driver but no NVIDIA GLX/EGL/Vulkan userspace libraries.

| Forest | Blocks | All-tree stems | Scene error | JS errors |
| --- | ---: | ---: | --- | --- |
| MKRF | 1,763 | 3,580,356 | none | none |
| Gavin Lake | 2,907 | 3,488,685 | none | none |
| Knife Creek | 183 | 2,917,588 | none | none |

The all-tree checkbox is checked by default, the scene note identifies the
source and fallback, and each page reaches `loading = hidden` with no failed
requests.

Screenshots:

- Gavin and Knife LOD views render successfully at 1100 × 760.
- MKRF LOD renders successfully at 640 × 480 (`all=0`).
- An MKRF all-tree screenshot at 640 × 480 timed out after 300 s under
  SwiftShader; the counter still showed 3,580,356 stems. This is a renderer
  limit, not a scene-data failure.

## What remains

A real-GPU browser pass is still outstanding. The host has an NVIDIA RTX PRO
6000, but the container lacks the NVIDIA userspace GL/Vulkan stack, so Chromium
falls back to software rendering (about 0.1 fps in all-tree mode and 1.9–2.5
fps in LOD). Passing this audit on the current host would require installing
the NVIDIA GL/EGL/Vulkan runtime or running the browser on a GPU-enabled
display host; neither was done here.

The scene is a screening visual, not an inventory. The 3.58M stems are
synthetic positions inside the block polygons.
