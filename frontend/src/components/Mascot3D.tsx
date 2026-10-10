import { useEffect, useRef, useState } from 'react';
import {
  AgXToneMapping, AnimationMixer, Clock, DirectionalLight, LoopOnce, LoopRepeat, MathUtils, PMREMGenerator,
  PerspectiveCamera, Quaternion, Scene, Vector3, WebGLRenderer, type AnimationAction, type Material, type Mesh,
  type Object3D, type Texture,
} from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import glbUrl from '../assets/mascot/loomy-web.glb?url';
import type { HostPose } from '../lib/mascot';

/** The live Loomy (loomy-web.glb: the brand model with 512 px textures, ~2 MB, ~6 MB of GPU memory).
 *  Loaded lazily, only on the empty Upload screen, so three.js never runs while the engine works.
 *  Renders at most 30 frames a second and none at all while off screen or in a hidden tab. */
const CLIP: Record<HostPose, string> = { hello: 'Wave', idle: 'Idle', working: 'Processing', catch: 'Wave' };
const WAVES_MS = 3200;              // a hello or a poke: two waves, then back to the pose
const UP = new Vector3(0, 1, 0);

type Player = { pose: (p: HostPose) => void; wave: () => void };

export default function Mascot3D({ pose, poke, still, onFail }: { pose: HostPose; poke: number; still: string; onFail: () => void }) {
  const host = useRef<HTMLDivElement>(null);
  const player = useRef<Player | null>(null);
  const [ready, setReady] = useState(false);
  const fail = useRef(onFail);
  fail.current = onFail;
  const first = useRef(pose);

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    let renderer: WebGLRenderer;
    try {
      renderer = new WebGLRenderer({ alpha: true, antialias: true, powerPreference: 'low-power' });
    } catch {
      fail.current();
      return;
    }
    const width = el.clientWidth || 250, height = el.clientHeight || 330;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
    renderer.setSize(width, height, false);
    renderer.toneMapping = AgXToneMapping;
    el.appendChild(renderer.domElement);
    const lost = (e: Event) => { e.preventDefault(); fail.current(); };
    renderer.domElement.addEventListener('webglcontextlost', lost);

    const scene = new Scene();
    const pmrem = new PMREMGenerator(renderer);
    const env = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    scene.environment = env;
    const key = new DirectionalLight(0xfff4e8, 1.4);
    key.position.set(-1.5, 2.5, 2.5);
    scene.add(key);
    const camera = new PerspectiveCamera(24, width / height, 0.1, 20);
    camera.position.set(-0.6, 0.66, 2.65);
    camera.lookAt(0, 0.5, 0);

    let disposed = false, mixer: AnimationMixer | undefined, head: Object3D | undefined, model: Object3D | undefined;
    const actions = new Map<string, AnimationAction>();
    let current: AnimationAction | undefined, posed: HostPose = first.current;
    let back: ReturnType<typeof setTimeout> | undefined;
    const play = (name: string) => {
      const next = actions.get(name);
      if (!next || next === current) return;
      next.reset().setLoop(LoopRepeat, Infinity).play();
      if (current) next.crossFadeFrom(current, 0.3, false);
      current = next;
    };
    const settle = (p: HostPose) => {
      clearTimeout(back);
      play(CLIP[p]);
      if (p === 'hello') back = setTimeout(() => { if (posed === 'hello') play('Idle'); }, WAVES_MS);
    };
    player.current = {
      pose: p => { posed = p; settle(p); },
      wave: () => {
        if (posed === 'working') return;
        clearTimeout(back);
        play('Wave');
        back = setTimeout(() => play(CLIP[posed === 'hello' ? 'idle' : posed]), WAVES_MS);
      },
    };

    new GLTFLoader().load(glbUrl, gltf => {
      if (disposed) { dispose(gltf.scene); return; }
      model = gltf.scene;
      scene.add(model);
      mixer = new AnimationMixer(model);
      for (const clip of gltf.animations) actions.set(clip.name, mixer.clipAction(clip));
      actions.get('ThumbsUp')?.setLoop(LoopOnce, 1);
      head = model.getObjectByName('Head');
      settle(posed);
      setReady(true);
    }, undefined, () => fail.current());

    // the head turns towards the pointer (yaw only, about 20 degrees at most)
    let yaw = 0, aim = 0;
    const look = (e: PointerEvent) => {
      const r = el.getBoundingClientRect();
      aim = MathUtils.clamp((e.clientX - (r.left + r.width / 2)) / 700, -1, 1) * 0.35;
    };
    window.addEventListener('pointermove', look);
    let visible = true;
    const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; });
    io.observe(el);
    const clock = new Clock(), turn = new Quaternion();
    let gap = 0;
    renderer.setAnimationLoop(() => {
      const dt = Math.min(clock.getDelta(), 0.1);
      if (!visible || document.hidden || !mixer) return;
      gap += dt;
      if (gap < 1 / 30) return;
      mixer.update(gap);
      yaw += (aim - yaw) * Math.min(1, gap * 4);
      head?.quaternion.multiply(turn.setFromAxisAngle(UP, yaw));
      gap = 0;
      renderer.render(scene, camera);
    });

    function dispose(root: Object3D) {
      root.traverse(o => {
        const mesh = o as Mesh;
        if (!mesh.isMesh) return;
        mesh.geometry.dispose();
        for (const mat of ([] as Material[]).concat(mesh.material)) {
          for (const v of Object.values(mat)) if ((v as Texture)?.isTexture) (v as Texture).dispose();
          mat.dispose();
        }
      });
    }
    return () => {
      disposed = true;
      player.current = null;
      clearTimeout(back);
      renderer.setAnimationLoop(null);
      io.disconnect();
      window.removeEventListener('pointermove', look);
      renderer.domElement.removeEventListener('webglcontextlost', lost);
      mixer?.stopAllAction();
      if (model) dispose(model);
      env.dispose();
      pmrem.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
      renderer.domElement.remove();
    };
  }, []);

  useEffect(() => { player.current?.pose(pose); }, [pose]);
  useEffect(() => { if (poke) player.current?.wave(); }, [poke]);

  return (
    <div ref={host} className={'loomy-3d' + (ready ? ' ready' : '')}>
      {!ready && <img className="loomy-still" src={still} alt="" />}
    </div>
  );
}
