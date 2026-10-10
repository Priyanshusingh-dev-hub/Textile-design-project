# LOOMY DADA — LoomLab Studio mascot

![LOOMY DADA: thumbs-up, wave, processing, idle](previews/overview.png)

LOOMY DADA (Loomi) is LoomLab Studio's mascot: an anthropomorphic thread spool
with a holographic visor, robotic arms and legs, and chunky sneakers. It ships as
one rigged, animated glTF 2.0 file that runs straight in the browser
(three.js, `<model-viewer>`, Babylon.js) as well as in Blender, Unity and Unreal.

| File | What it is |
| --- | --- |
| `loomy-dada.glb` | The model: mesh, rig, 5 animations and embedded PBR textures (3.1 MB) |
| `previews/` | Cycles renders (1024 px, transparent background) |
| `build_loomy_dada.py` | Builds the mesh, materials, rig and animations, then exports the GLB |
| `loomy_textures.py` | Procedural 2048 px PBR textures (numpy) |
| `render_previews.py` | Preview renders (studio lights live only in the render scene) |

## Model

- **Size / placement:** ~0.97 units (metres) tall, centred on the origin, feet on
  the ground (y = 0), facing **+Z**. Rest pose = A-pose.
- **Mesh:** 33,312 triangles / 17,301 vertices; built as 93% quads, with
  triangles only at the poles of round shapes. All closed parts have outward
  normals; tangents are exported for the normal map.
- **Materials (metal/rough PBR):**
  - `LoomyDada_Atlas`, opaque. 2048×2048 base colour, ORM (R = occlusion,
    G = roughness, B = metallic), OpenGL normal map, and emissive for the
    knee/ankle lights and the tablet logo.
  - `LoomyDada_Visor`, alpha-blended glowing teal hologram with HUD markings.
    2048×2048 base colour (RGBA) + emissive.
  - Uses `KHR_materials_emissive_strength` for the glow.
- **Palette:** teal, violet, cream, light wood and dark grey only.
- **No** background, floor, lights, cameras or baked shadows in the file.
- Khronos glTF Validator: **0 errors, 0 warnings**, max 4 bone influences per vertex.

## Rig (35 bones, humanoid names)

```
Root
└─ Hips
   ├─ Spine
   │  ├─ Head
   │  ├─ LeftShoulder ─ LeftUpperArm ─ LeftLowerArm ─ LeftHand
   │  │     ├─ LeftThumb/Index/Middle/Ring Proximal ─ …Distal
   │  │     └─ LeftHandProp        (the tablet)
   │  └─ RightShoulder ─ RightUpperArm ─ RightLowerArm ─ RightHand
   │        └─ RightThumb/Index/Middle/Ring Proximal ─ …Distal
   ├─ LeftUpperLeg ─ LeftLowerLeg ─ LeftFoot
   └─ RightUpperLeg ─ RightLowerLeg ─ RightFoot
```

The thread body blends `Hips` → `Spine` → `Head` by height. The face, visor and top
flange follow `Head`, and the bottom flange follows `Hips`, so a head tilt moves the face
and visor together while the base stays planted.

## Animations (30 fps)

| Clip | Length | Loop | What it does |
| --- | --- | --- | --- |
| `Idle` | 2.4 s | yes | Gentle breathing bob, body sway, small head turn, relaxed arms |
| `Wave` | 1.6 s | yes | Right hand waves beside the head |
| `ThumbsUp` | 1.5 s | no, hold last frame | Right thumbs-up, left hand shows the tablet's "L" logo |
| `Processing` | 2.0 s | yes | Looks down at the tablet, right finger draws circles ("working…") |
| `Neutral_APose` | 1 frame | – | The rest A-pose |

## Use it on the web (three.js)

```js
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const clock = new THREE.Clock();
let mixer;
new GLTFLoader().load('loomy-dada.glb', (gltf) => {
  scene.add(gltf.scene);
  mixer = new THREE.AnimationMixer(gltf.scene);
  const clip = (name) => mixer.clipAction(THREE.AnimationClip.findByName(gltf.animations, name));

  clip('Idle').play();

  // one-shot thumbs-up that holds its last frame:
  // const a = clip('ThumbsUp'); a.setLoop(THREE.LoopOnce); a.clampWhenFinished = true; a.play();
});

// in the render loop
mixer?.update(clock.getDelta());
```

Use a light environment (e.g. `RoomEnvironment` + `PMREMGenerator`) so the PBR
materials read correctly. The visor is transparent, so keep
`renderer.sortObjects` on (the default).

Or with no code at all:

```html
<script type="module" src="https://cdn.jsdelivr.net/npm/@google/model-viewer@3.5.0/dist/model-viewer.min.js"></script>
<model-viewer src="loomy-dada.glb" animation-name="Idle" autoplay camera-controls
              environment-image="neutral" style="width:400px;height:400px"></model-viewer>
```

## Rebuild / edit

Everything is generated from code, so any change (colours, proportions, poses)
is an edit plus a rebuild:

```bash
python3.11 -m venv venv-bpy && . venv-bpy/bin/activate
pip install bpy==5.0.1 pillow scipy          # Blender 5.0 as a Python module
python build_loomy_dada.py --out build --blend          # build/loomy-dada.glb + .blend
python render_previews.py --blend build/loomy-dada.blend --out previews --size 1024 --samples 64
cp build/loomy-dada.glb .
```

- Colours: the palette constants at the top of `loomy_textures.py`.
- Proportions: the constants at the top of `build_loomy_dada.py`.
- Poses: `poses_for()` in `build_loomy_dada.py`.

The `.blend` and the `_textures/` working folder are build outputs and are not
committed (see `.gitignore`); the textures are embedded in the GLB.

---

### Hinglish mein short

- **`loomy-dada.glb`** hi asli file hai. Website, Blender, Unity, sab mein seedha chal jaati hai.
- 5 animations hain: `Idle`, `Wave`, `ThumbsUp`, `Processing` aur `Neutral_APose`.
- Height ~1 unit hai, character +Z ki taraf dekhta hai aur pair zameen par hain.
- Background aur lights file mein nahi hain.
- Rang ya pose badalna ho to Python file mein value badlo aur `build_loomy_dada.py` dobara chalao. Model same tareeke se phir ban jaayega.
