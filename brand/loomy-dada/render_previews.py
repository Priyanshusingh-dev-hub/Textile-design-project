"""Preview renders of LOOMY DADA (Cycles, CPU, transparent background).

    python render_previews.py --blend loomy-dada.blend --out previews/ [--size 1024] [--samples 64]
    python render_previews.py --set app --blend loomy-dada.blend --calm-blend calm/loomy-dada.blend \
        --out ../../frontend/src/assets/mascot/

`--set app` makes the web app's stills: one fixed orthographic camera per framing (a face crop for the
header avatar, the whole body for the Upload screen), so the character keeps one size and place when
the app swaps moods, plus a Processing sprite strip. `--calm-blend` is a build made with
`build_loomy_dada.py --face calm` (closed mouth, concerned brows) for the careful/oops moods.

Studio lighting lives only in this render scene: nothing is baked into the
model or its textures.
"""
import argparse
import math
import os

import bpy
from mathutils import Vector

VIEWS = {                      # name: (action, frame, camera azimuth in degrees, 0 = front)
    'hero_thumbs_up': ('ThumbsUp', 45, -28),
    'apose_front': ('Neutral_APose', 1, 0),
    'apose_three_quarter': ('Neutral_APose', 1, 35),
    'apose_side': ('Neutral_APose', 1, 90),
    'apose_back': ('Neutral_APose', 1, 180),
    'wave': ('Wave', 12, -18),
    'processing': ('Processing', 20, 22),
    'idle': ('Idle', 18, -12),
    'face_closeup': ('Neutral_APose', 1, -12),
    'think': ('Think', 18, -15),
    'shrug': ('Shrug', 40, -10),
}
CLOSE = {'face_closeup': (1.45, 0.64)}            # name: (camera distance, look-at height)


def setup(size, samples):
    s = bpy.context.scene
    s.render.engine = 'CYCLES'; s.cycles.device = 'CPU'; s.cycles.samples = samples
    s.cycles.use_denoising = True
    s.render.resolution_x = s.render.resolution_y = size
    s.render.film_transparent = True
    s.view_settings.view_transform = 'AgX'
    s.view_settings.look = 'AgX - Medium High Contrast'
    world = bpy.data.worlds.new('studio'); s.world = world
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.62, 0.64, 0.68, 1)
    world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.55

    def area(name, loc, energy, size_, color=(1, 1, 1)):
        ld = bpy.data.lights.new(name, 'AREA'); ld.energy = energy; ld.size = size_; ld.color = color
        ob = bpy.data.objects.new(name, ld); s.collection.objects.link(ob)
        ob.location = loc
        d = Vector((0, 0, 0.5)) - Vector(loc)
        ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    area('key', (-1.6, -2.2, 2.2), 260, 1.6, (1.0, 0.97, 0.93))
    area('fill', (2.0, -1.6, 1.0), 90, 2.0, (0.92, 0.96, 1.0))
    area('rim', (0.6, 2.2, 2.0), 220, 1.2, (0.85, 0.95, 1.0))
    cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); s.collection.objects.link(cam)
    cam.data.lens = 85
    s.camera = cam
    return cam


def place_camera(cam, az, dist=3.9, target=0.49):
    a = math.radians(az)
    cam.location = (dist * math.sin(a), -dist * math.cos(a), target + 0.29 * dist / 3.9)
    d = Vector((0, 0, target)) - cam.location
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


# --set app: name -> (face, framing, action, frame). The same camera for every name of one framing.
APP = {
    'face_idle': ('smile', 'face', 'Idle', 18),
    'face_hello': ('smile', 'face', 'Wave', 12),
    'face_cheer': ('smile', 'face', 'ThumbsUp', 45),
    'face_careful': ('calm', 'face', 'Think', 18),
    'face_oops': ('calm', 'face', 'Shrug', 40),
    'face_calm': ('calm', 'face', 'Idle', 18),
    'body_hello': ('smile', 'body', 'Wave', 12),
    'body_idle': ('smile', 'body', 'Idle', 18),
    'body_cheer': ('smile', 'body', 'ThumbsUp', 45),
    'body_working': ('smile', 'body', 'Processing', 20),
}
# framing -> (orthographic width in m, centre height, render px, saved px)
FRAMING = {'face': (0.62, 0.67, 192, 96), 'body': (1.16, 0.49, 640, 440)}
SPRITE = ('Processing', range(0, 60, 5))                   # 12 frames of the 2 s loop, for the header
APP_AZ, APP_ELEV = -14, 6                                  # degrees: a little to the right, a little above


def set_action(rig, action, frame):
    rig.animation_data.action = bpy.data.actions[action]
    try:
        rig.animation_data.action_slot = bpy.data.actions[action].slots[0]
    except Exception:
        pass
    bpy.context.scene.frame_set(frame)


def ortho_camera(cam, framing):
    width, zc, px, _ = FRAMING[framing]
    bpy.context.scene.render.resolution_x = bpy.context.scene.render.resolution_y = px
    cam.data.type = 'ORTHO'; cam.data.ortho_scale = width
    a, e = math.radians(APP_AZ), math.radians(APP_ELEV)
    d = 6.0
    target = Vector((0, 0, zc))
    cam.location = target + Vector((d * math.cos(e) * math.sin(a), -d * math.cos(e) * math.cos(a), d * math.sin(e)))
    cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()


def render_to(path):
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print('rendered', os.path.basename(path))


def open_blend(path, size, samples):
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(path))
    rig = bpy.data.objects['LOOMY_DADA_Rig']
    for tr in rig.animation_data.nla_tracks:
        tr.mute = True
    return rig, setup(size, samples)


def app_set(args):
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    only = set(args.only.split(',')) if args.only else None
    for face, blend in (('smile', args.blend), ('calm', args.calm_blend)):
        names = [n for n, v in APP.items() if v[0] == face and (not only or n in only)]
        sprite = face == 'smile' and (not only or 'sprite_working' in only)
        if not names and not sprite:
            continue
        rig, cam = open_blend(blend, args.size, args.samples)
        for name in names:
            _, framing, action, frame = APP[name]
            set_action(rig, action, frame)
            ortho_camera(cam, framing)
            render_to(os.path.join(out, '_raw', name + '.png'))
        if sprite:
            action, frames = SPRITE
            ortho_camera(cam, 'face')
            for i, f in enumerate(frames):
                set_action(rig, action, f)
                render_to(os.path.join(out, '_raw', f'sprite_working_{i:02d}.png'))
    pack(out)


def pack(out):
    """_raw renders -> the app's files: each still at its saved size, the sprite frames side by side
    in one strip (CSS steps() plays it), all as palette PNGs (a few KB; any browser, any server)."""
    from PIL import Image
    raw = os.path.join(out, '_raw')

    def small(img, px):
        img = img.convert('RGBA').resize((px, px), Image.LANCZOS)
        return img.quantize(256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)
    for name, (_, framing, _, _) in APP.items():
        src = os.path.join(raw, name + '.png')
        if os.path.exists(src):
            small(Image.open(src), FRAMING[framing][3]).save(os.path.join(out, name + '.png'), optimize=True)
    frames = sorted(f for f in os.listdir(raw) if f.startswith('sprite_working_'))
    if frames:
        px = FRAMING['face'][3]
        strip = Image.new('RGBA', (px * len(frames), px))
        for i, f in enumerate(frames):
            strip.paste(Image.open(os.path.join(raw, f)).convert('RGBA').resize((px, px), Image.LANCZOS), (i * px, 0))
        strip.quantize(256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE).save(
            os.path.join(out, 'sprite_working.png'), optimize=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--blend', required=True)
    ap.add_argument('--calm-blend', help='a --face calm build, for --set app')
    ap.add_argument('--set', choices=('previews', 'app'), default='previews')
    ap.add_argument('--out', required=True)
    ap.add_argument('--size', type=int, default=1024)
    ap.add_argument('--samples', type=int, default=64)
    ap.add_argument('--only', default='')
    args, _ = ap.parse_known_args()
    if args.set == 'app':
        return app_set(args)
    rig, cam = open_blend(args.blend, args.size, args.samples)
    os.makedirs(args.out, exist_ok=True)
    for name, (action, frame, az) in VIEWS.items():
        if args.only and name not in args.only.split(','):
            continue
        set_action(rig, action, frame)
        place_camera(cam, az, *CLOSE.get(name, (3.9, 0.49)))
        render_to(os.path.join(os.path.abspath(args.out), name + '.png'))


if __name__ == '__main__':
    main()
