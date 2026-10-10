"""Preview renders of LOOMY DADA (Cycles, CPU, transparent background).

    python render_previews.py --blend loomy-dada.blend --out previews/ [--size 1024] [--samples 64]

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--blend', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--size', type=int, default=1024)
    ap.add_argument('--samples', type=int, default=64)
    ap.add_argument('--only', default='')
    args, _ = ap.parse_known_args()
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(args.blend))
    rig = bpy.data.objects['LOOMY_DADA_Rig']
    for tr in rig.animation_data.nla_tracks:
        tr.mute = True
    cam = setup(args.size, args.samples)
    os.makedirs(args.out, exist_ok=True)
    for name, (action, frame, az) in VIEWS.items():
        if args.only and name not in args.only.split(','):
            continue
        rig.animation_data.action = bpy.data.actions[action]
        try:
            rig.animation_data.action_slot = bpy.data.actions[action].slots[0]
        except Exception:
            pass
        bpy.context.scene.frame_set(frame)
        place_camera(cam, az, *CLOSE.get(name, (3.9, 0.49)))
        bpy.context.scene.render.filepath = os.path.join(os.path.abspath(args.out), name + '.png')
        bpy.ops.render.render(write_still=True)
        print('rendered', name)


if __name__ == '__main__':
    main()
